"""
Map arguments

input:

    {name~*}

    the * is treated as a glob and can be part of a filename
    name is used to expand the capture part later.

    {name=[1-5]}

    name is replaced by the range of

    {name=a,b,c,d}

"""

import copy
from datetime import datetime
import hashlib
import glob
import logging
import itertools
import os
import re
import shlex
import socket
import sys
from collections import OrderedDict

import leip
from kea.utils import get_uid, set_info_file

lg = logging.getLogger(__name__)
#lg.setLevel(logging.DEBUG)



def map_num_expand(mtch, info):
    cl = info['cl']
    name, operator, pattern = mtch.groups()
    matched_str = cl[mtch.start():mtch.end()]

    lg.debug('cl glob expansion')
    lg.debug('   -    name: %s', name)
    lg.debug('   -   match: %s', matched_str)
    lg.debug('   - pattern: %s', pattern)

    if ':' in pattern:
        nums = [int(x) for x in pattern.split(':')]
        rng = range(*nums)
    elif ',' in pattern:
        rng = [float(x) for x in pattern.split(',')]

    for r in rng:
        newcl = cl[:mtch.start()] + str(r) + cl[mtch.end():]
        newinfo = info.copy()
        newinfo['cl'] = newcl
        newinfo['param'][name] = r
        yield newinfo

    
def map_glob_expand(mtch, info):

    cl = info['cl']
    name, operator, pattern = mtch.groups()
    matched_str = cl[mtch.start():mtch.end()]
    clsplit = shlex.split(cl)

    matched_word = [x for x in clsplit if matched_str in x]
    assert len(matched_word) == 1
    matched_word = matched_word[0]

    assert matched_word.count(matched_str) == 1
    globstr = matched_word.replace(matched_str, pattern)

    lg.debug('cl glob expansion')
    lg.debug('   -    name: %s', name)
    lg.debug('   -   match: %s', matched_str)
    lg.debug('   - in word: %s', matched_word)
    lg.debug('   -    glob: %s', globstr)

    globhits = glob.glob(globstr)
    if len(globhits) == 0:
        lg.critical("No files matching pattern: '%s' found", globpattern)
        exit(-1)

    word_pre, word_post = matched_word.split(matched_str)

    for ghit in globhits:
        lg.debug(' = hit: %s', ghit)
        assert ghit.startswith(word_pre)
        assert ghit.endswith(word_post)
        rep_str = ghit[len(word_pre):-len(word_post)]
        newcl = cl.replace(matched_word, ghit)
        lg.debug('   - param: "%s"="%s"', name, rep_str)
        newinfo = info.copy()
        newinfo['cl'] = newcl.strip()
        newinfo['param'][name] = rep_str
        yield newinfo

        

def apply_map_info_to_cl(newcl, map_info):
    item = map_info['item']
    for i, arg in enumerate(newcl):
        map_to_re = map_info['re_replace']
        map_fr_re = map_info['re_from']
        if map_fr_re.search(arg):
            newcl[i] = map_fr_re.sub(item, arg)
        elif map_to_re.search(arg):
            newcl[i] = map_to_re.sub(item, arg)

    return newcl


def process_targetfiles(info):
    RE_FIND_FILETARGET = re.compile(r'{([\^<>!])([a-zA-Z_][a-zA-Z0-9_]*)}\s+')

    cl = info['cl']
    lg.debug('targets: %s', cl)
    done = False

    while True:
        for m in RE_FIND_FILETARGET.finditer(cl):
            fname = shlex.split(cl[m.end():])[0]
            if '{' in fname:
                # not good - not rendered (yet?)
                # maybe in the next round
                continue
            
            ftype, name = m.groups()
            
            cat = {'<': 'input',
                   '>': 'output',
                   '^': 'use',
                   'x': 'executable'}[ftype]

            newname = set_info_file(info, cat, name, fname)
#            print("set info file: ", cat, name, fname, newname)
            info['param'][newname] = fname
            cl = cl[:m.start()] + cl[m.end():]
            break
        else:
            done = True
            break
    info['cl'] = cl.strip()

def render_parameters(s, param):
    FIND_PARAM = re.compile(r'{([A-Za-z_][a-zA-Z0-9_]*)(?:\|([^}]+)?)?}')
    search_start = 0
    
    while True:
        mtch = FIND_PARAM.search(s, search_start)
        if not mtch:
            break

        name = mtch.groups()[0]
        flags = mtch.groups()[1]
        if not flags:
            flags = ''
            
        if '|' in flags:
            flags, pattern = flags.split('|', 1)
        else:
            pattern = None
            
        #lg.setLevel(logging.DEBUG)
        lg.debug('cl render')
        lg.debug(' -  string: %s', s)
        lg.debug(' -    name: %s', name)
        lg.debug(' -   flags: %s', flags)
        lg.debug(' - pattern: %s' % pattern)

        if not name in param:
            # this value may yet be found as a redirect file
            if re.search('{?' + name + '}', s):
                search_start = mtch.end()
                break
            else:
                lg.critical("invalid replacement: %s",
                            s[mtch.start():mtch.end()])
                lg.critical(s)
                exit()

        replace = str(param[name])
        if '/' in  flags:
            replace = os.path.basename(replace)
        for _extcut in range(flags.count('.')):
            if not '.' in replace:
                break
            replace = replace.rsplit('.')[0]

        if pattern:
            replace = pattern.replace('*', replace)
            
        lg.debug(' - pattern: %s' % pattern)
        lg.debug(' - replace: %s' % replace)
        s = s[:mtch.start()] + replace + s[mtch.end():]
    return s.strip()
    
def iterate_cls(info):

    yielded = 0

    cl = info['cl']
    
    RE_FIND_MAPINPUT = re.compile(r'{([a-zA-Z_][a-zA-Z0-9_]*)([\~\=])([^}]+)}')
    mapins = RE_FIND_MAPINPUT.search(cl)
    
    mtch = RE_FIND_MAPINPUT.search(cl)
    if mtch is None:
        yield info.copy()
        return
    
    name, operator, pattern = mtch.groups()
    if operator == '~':
        expand_function = map_glob_expand
    elif operator == '=':
        expand_function = map_num_expand
            
    for info in expand_function(mtch, info.copy()):
        for info in iterate_cls(info):
            yield info
    
    
def basic_command_line_generator(app):
    """
    Most basic command line generator possible
    """

    info = OrderedDict()
    info['param'] = info.get('param', {})
    info['cl'] = app.conf['cl']
    
    pipes = [app.args.stdout, app.args.stderr]

    #check if there are iterable arguments in here
    mapcount = 0

    nojobstorun = app.defargs['jobstorun']
    if nojobstorun:
        lg.debug('jobs to run %s', nojobstorun)

    info['create'] = datetime.utcnow()
    info['template_cl'] = info['cl']
    info['run'] = info.get('run', {})
    info['run']['uid'] = get_uid(app)
    info['sys'] = info.get('sys', {})

    for i, info in enumerate(iterate_cls(info)):
        if nojobstorun and i >= nojobstorun:
            break

        #iterative rendering - fun!
        lastcl = info['cl']
        while True:
            process_targetfiles(info) 
            info['cl'] = render_parameters(info['cl'], info['param'])
            if lastcl == info['cl']:
                break
            lastcl = info['cl']
#            else:
#                print(info['cl'])

        info['run']['no'] = i
        if pipes[0]:
            set_info_file(info, 'output', 'stdout',
                          render_parameters(pipes[0], info['param']))
        if pipes[1]:
            set_info_file(info, 'output', 'stderr',
                          render_parameters(pipes[1], info['param']))
        yield info
                    
