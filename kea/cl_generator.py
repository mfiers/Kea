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
import glob
import logging
import itertools
import re
import shlex
import sys
from collections import OrderedDict

lg = logging.getLogger(__name__)

RE_FIND_MAPINPUT = re.compile(r'{([a-zA-Z_][a-zA-Z0-9_]*)([\~\=])([^}]+)}')


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
        map_items = map(str, range(int(start), int(stop), int(step)))
    elif mappat_range_2:
        start, stop = mappat_range_2.groups()
        map_items = map(str, range(int(start), int(stop)))
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


def map_glob_expand(map_info, cl, pipes):
    thisarg = map_info['arg']
    argi = cl.index(thisarg)
    iterpat = map_info['pattern']
    iterstring = map_info['iterstring']

    globpattern = RE_FIND_MAPINPUT.sub(iterpat, thisarg)
    globhits = glob.glob(globpattern)

    if len(globhits) == 0:
        lg.critical("No files matching pattern: '%s' found", globpattern)
        exit(-1)

    substart = thisarg.index(iterstring)
    subtail = len(thisarg) - (substart + len(iterstring))
    
    for g in globhits:
        newcl = copy.copy(cl)
        newcl[argi] = g
        subrep = g[substart:]
        if subtail > 0:
            subrep = subrep[:-subtail]
        for j, rarg in enumerate(newcl):
            newcl[j] = map_info['rep_from'].sub(subrep, rarg)

        new_pipes = []
        for p in pipes:
            if p is None:
                new_pipes.append(None)
            else:
                new_pipes.append(map_info['rep_from'].sub(g, p))

        yield newcl, new_pipes


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


def basic_command_line_generator(app):
    """
    Most basic command line generator possible
    """
    
    info = OrderedDict()
    
    pipes = [app.args.stdout, app.args.stderr]

    cl = app.cl

    cljoin = " ".join(cl)

    #check if there are iterable arguments in here
    mapcount = 0
    mapins = RE_FIND_MAPINPUT.search(cljoin)

    # no map definitions found - then simply return the cl & execute
    if mapins is None:
        info['cl'] = cl
        info['run_no'] = 1
        info['stdout_file'] = pipes[0]
        info['stderr_file'] = pipes[1]
        yield info
        return

    #define iterators for each of the definitions

    #lg.setLevel(logging.DEBUG)

    lg.debug("iterables found in: %s", cljoin)
    
    def expander(cl, pipes):
        
        for i, arg in enumerate(cl):
            mima = RE_FIND_MAPINPUT.search(arg)
            if mima:
                break
        else:
            yield cl, pipes
            return

        map_info = {}
        map_info['re_search'] = mima
        map_info['name'], map_info['operator'], map_info['pattern'] = \
                mima.groups()

        map_info['iterstring'] = mima.group(0)
        map_info['arg'] = arg
        

        lg.debug("iterable name: {name} operator: {operator} pattern: {pattern}".format(**map_info))
        
        map_info['re_from'] = re.compile(r'({' + map_info['name']
                                         + r'[\~\=][^}]*})')
        map_info['re_replace'] = re.compile(r'({' + map_info['name'] + r'})')
        map_info['rep_from'] = re.compile(r'({' + map_info['name'] + '})')
        
        map_info['start'] = mima.start()
        map_info['tail'] = len(arg) - mima.end()

        if map_info['operator'] == '~':
            expand_function = map_glob_expand
        elif map_info['operator'] == '=':
            expand_function = map_range_expand
        
        for ncl, pipes in  expand_function(map_info, cl, pipes):
            for nncl, pipes in expander(ncl, pipes):
                    yield nncl, pipes

    no = 0
    for newcl, pipes in  expander(cl, pipes):
        no += 1
        
        newinfo = copy.copy(info)
        newinfo['cl'] = newcl
        newinfo['run_no'] = no
        newinfo['stdout_file'] = pipes[0]
        newinfo['stderr_file'] = pipes[1]
        yield newinfo
