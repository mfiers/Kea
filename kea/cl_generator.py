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
import re
import shlex
import socket
import sys
from collections import OrderedDict

import leip
from kea.utils import get_uid, set_info_file

lg = logging.getLogger(__name__)
#lg.setLevel(logging.DEBUG)


def map_range_expand(map_info, cl, pipes):
    """
    Convert a map range to a list of items:

    first - range conversion:
      - a,b,c -> ['a', 'b', 'c']
      - 5:10 -> [5,6,7,8,9]
      - 5:10:2 -> [5,7,9]
    then, merge with the command line item in which this was embedded (if any)

    so: test.{a=5:10:2}.in becomes: ['test.5.in', 'test.7.in', 'test.9.in']

    """

    mappat_range_3 = re.match(r'([0-9]+):([0-9]+):([0-9]+)',
                              map_info['pattern'])
    mappat_range_2 = re.match(r'([0-9]+):([0-9]+)',
                              map_info['pattern'])

    thisarg = map_info['arg']
    iterstring = map_info['iterstring']
    argi = cl.index(thisarg)

    if mappat_range_3:
        start, stop, step = mappat_range_3.groups()
        map_items = list(map(str, list(range(int(start), int(stop), int(step)))))
    elif mappat_range_2:
        start, stop = mappat_range_2.groups()
        map_items = list(map(str, list(range(int(start), int(stop)))))
    elif ',' in map_info['pattern']:
        map_items = [x.strip() for x in map_info['pattern'].split(',')]
    else:
        lg.critical("Can not parse range: %s", map_info['pattern'])
        exit(-1)


    substart = thisarg.index(iterstring)
    subtail = substart + len(iterstring)
    for g in map_items:
        newcl = copy.copy(cl)
        argrep = thisarg[:substart] + str(g) +  thisarg[subtail:]
        newcl[argi] = argrep
        for j, rarg in enumerate(newcl):
            newcl[j] = map_info['rep_from'].sub(g, rarg)

        new_pipes = []
        for p in pipes:
            if p is None:
                new_pipes.append(None)
            else:
                new_pipes.append(map_info['rep_from'].sub(g, p))

        yield newcl, new_pipes

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
        newinfo['cl'] = newcl
        newinfo['param'][name] = rep_str
        yield newinfo

        
def map_iter(map_info):
    for i in map_info['items']:
        map_clean = copy.copy(map_info)
        map_clean['item'] = i
        yield map_clean


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
            ftype, name = m.groups()
            
            cat = {'<': 'input',
                   '>': 'output',
                   '^': 'use',
                   'x': 'executable'}[ftype]
            
            newname = set_info_file(info, cat, name, fname)
            info['param'][newname] = fname
            cl = cl[:m.start()] + cl[m.end():]
            break
        else:
            done = True
            break
    info['cl'] = cl

def render_parameters(s, param):
    FIND_PARAM = re.compile(r'{([A-Za-z_][a-zA-Z0-9_]*)}')
    while True:
        mtch = FIND_PARAM.search(s)
        if not mtch:
            break
        name = mtch.groups()[0]
        
        if not name in param:
            lg.critical("invalid replacement: %s",
                        cl[mtch.start():mtch.end()])
            exit()
        s = s[:mtch.start()] + str(param[name]) + s[mtch.end():]
    return s
    
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

        process_targetfiles(info)
        info['cl'] = render_parameters(info['cl'], info['param'])
        info['run']['no'] = i
        if pipes[0]:
            set_info_file(info, 'output', 'stdout',
                          render_parameters(pipes[0], info['param']))
        if pipes[1]:
            set_info_file(info, 'output', 'stderr',
                          render_parameters(pipes[1], info['param']))
        yield info
                    
