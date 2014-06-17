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
import sys
from collections import OrderedDict

lg = logging.getLogger(__name__)

RE_FIND_MAPINPUT = re.compile(r'{([a-zA-Z_][a-zA-Z0-9_]*)([\~\=])([^}]+)}')

def very_basic_command_line_generator(app):
    """
    Most basic command line generator possible
    """
    cl = sys.argv[1:]
    yield cl


def map_range_expand(map_info, cl):
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

    return map_items
    # items = []
    # for mi in map_items:
    #     newitem = ""
    #     if map_info['start'] > 0:
    #         newitem += map_info['arg'][:map_info['start']]
    #     newitem += mi
    #     if map_info['tail'] > 0:
    #         newitem += map_info['arg'][-map_info['tail']:]
    #     items.append(newitem)
    # return items

def map_glob_expand(map_info, cl):

    globpattern = RE_FIND_MAPINPUT.sub(map_info['pattern'], map_info['arg'])
    globhits = glob.glob(globpattern)

    if len(globhits) == 0:
        lg.critical("No hits found for pattern: %s", globpattern)
        exit(-1)

    sta, tail = map_info['start'], map_info['tail']
    return sorted([g[sta:-tail] for g in globhits])


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
    stdout_file = app.kea_args.stdout
    stderr_file = app.kea_args.stderr

    #cl = [app.conf['executable']] + sys.argv[1:]
    cl = sys.argv[1:]

    #check if there are map arguments in here
    mapins = []
    mapcount = 0

    ## find all map definitions
    for i, arg in enumerate(cl):
        if not RE_FIND_MAPINPUT.search(arg):
            continue
        mapins.append(i)

    # no map definitions found - then simply return the cl & execute
    if len(mapins) == 0:
        info['cl'] = cl
        info['stdout_file'] = stdout_file
        info['stderr_file'] = stderr_file
        yield info
        return

    #define iterators for each of the definitions

    mapiters = []
    for arg_pos in mapins:
        map_info = {}
        map_info['pos'] = arg_pos
        map_info['arg'] = cl[arg_pos]
        map_info['re_search'] = RE_FIND_MAPINPUT.search(cl[arg_pos])
        map_info['name'], map_info['operator'], map_info['pattern'] = \
                map_info['re_search'].groups()
        map_info['re_from'] = re.compile(r'({' + map_info['name'] +
                                         r'[\~\=][^}]*})')
        map_info['re_replace'] = re.compile(r'({' + map_info['name'] + r'})')
        map_info['start'] = map_info['re_search'].start()
        map_info['tail'] = len(cl[arg_pos]) - map_info['re_search'].end()

        if map_info['operator'] == '~':
            map_info['items'] = map_glob_expand(map_info, cl)
        elif map_info['operator'] == '=':
            map_info['items'] = map_range_expand(map_info, cl)

        mapiters.append(map_iter(map_info))

    for map_info_set in itertools.product(*mapiters):
        newcl = copy.copy(cl)
        newinfo = copy.copy(info)
        newstdout = stdout_file
        newstderr = stderr_file

        for map_info in map_info_set:
            newcl = apply_map_info_to_cl(newcl, map_info)
            if not newstdout is None:
                newstdout = apply_map_info_to_cl([newstdout], map_info)[0]
            if not newstderr is None:
                newstderr = apply_map_info_to_cl([newstderr], map_info)[0]

        newinfo['cl'] = newcl
        newinfo['stdout_file'] = newstdout
        newinfo['stderr_file'] = newstderr
        yield newinfo
