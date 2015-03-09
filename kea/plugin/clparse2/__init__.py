#
# yet another attempt at a useable command line parser

from collections import OrderedDict
import copy
import logging
import os
import re
import sys
import subprocess as sp

import pkg_resources
from termcolor import cprint
import yaml
import leip

from kea.utils import set_info_file

lg = logging.getLogger(__name__)
#lg.setLevel(logging.DEBUG)

PARSEFAIL = False   # has parsing failed??
PARSEDONE = False   # parsing finished


@leip.hook('pre_argparse')
def clparse2_arg_define(app):
    clparse2_group = app.parser.add_argument_group('Command line parser plugin')

    clparse2_group.add_argument('--pfe', action='store_true',
                                help='print parsed files & exit', default=0)
    clparse2_group.add_argument('--inf', default=[],
                                help='mark this file as an input file',
                                action='append')

def foreach(cl, jinf, tree, flag):
    while cl:
        processor(cl, jinf, tree)
        cl = cl[1:]

def basename(cl, jinf, tree, extens=""):
    rv = os.path.basename(cl[0])
    if extens and rv.endswith(extens):
        rv = rv[:-len(extens)]
    lg.warning('basename: %s -> %s', cl[0], rv)
    processor([rv], jinf, tree)

def debug(cl, jinf, tree, *args):
    print(cl, tree, args)

def flag0(cl, jinf, tree, *flags):
    flag = None
    for f in flags:
        if f in cl:
            flag = f
            break
    else:
        return

    flag_i = cl.index(flag)
    lg.debug("flag0: %s", flag)
    processor([], jinf, tree)
    return cl[:flag_i] + cl[flag_i+1:]

def flag(cl, jinf, tree, *flags):

    flag = None
    for f in flags:
        if f in cl:
            flag = f
            break
    else:
        return
    flag_i = cl.index(flag)
    rv = cl[flag_i+1]
    lg.debug("flag: %s >%s", flag, rv)
    processor([rv], jinf, tree)
    #return the command line with this flag removed
    return cl[:flag_i] + cl[flag_i+2:]


def repeat(cl, jinf, tree, pos=0):
    while cl:
        cl = processor(cl, jinf, tree)

def pop(cl, jinf, tree, pos=0):
    if not pos.strip():
        pos = 0
    else:
        pos = int(pos)
    assert pos == 0 or pos == -1
    if pos == 0:
        lg.debug("pop: 0  %s", cl[pos])
        processor([cl[0]], jinf, tree)
        return cl[1:]
    elif pos == -1:
        lg.debug("pop: -1  %s", cl[pos])
        processor([cl[-1]], jinf, tree)
        return cl[:-1]

def index(cl, jinf, tree, idx):
    idx = int(idx)
    lg.debug("index: %d -> %s", idx, cl[idx])
    processor([cl[idx]], jinf, tree)

def done(cl, jinf, tree, txt):
    global PARSEDONE
    PARSEDONE = True

def match(cl, jinf, tree, txt):
    success = cl[0].strip() == txt
    lg.debug('match %s (%s): %s', txt, success, " ".join(cl[1:]))
    if success:
        processor(cl[1:], jinf, tree)

def element_check(cl, jinf, tree, idx, pattern):
    elem = cl[int(idx)]
    if pattern in elem:
        processor(cl, jinf, tree)

def search (cl, jinf, tree, pattern):
    regex = re.compile(pattern)
    mtch = regex.search(cl[0])
    if mtch:
        processor(cl, jinf, tree)

def replace(cl, jinf, tree, fro, to):
    regex = re.compile(fro)
    ncl = [regex.sub(to, cl[0])] + cl[1:]
    processor(ncl, jinf, tree)

def append(cl, jinf, tree, txt):
    ncl = [cl[0] + txt] + cl[1:]
    processor(ncl, jinf, tree)

def path_append(cl, jinf, tree, txt):
    ncl = [os.path.join(cl[0], txt)] + cl[1:]
    processor(ncl, jinf, tree)

def insert(cl, jinf, tree, item):
    ncl = [item] + cl
    processor(ncl, jinf, tree)

def apply(cl, jinf, tree, txt):
    processor(cl, jinf, tree)

def parameter(cl, jinf, tree, name, value=None):
    if not 'parameter' in jinf:
        jinf['parameter'] = {}
    if value is None:
        jinf['parameter'][name] = cl[0]
    else:
        jinf['parameter'][name] = value


def output(cl, jinf, tree, name):
    set_info_file(jinf, 'output', name, cl[0])

def database(cl, jinf, tree, name):
    set_info_file(jinf, 'database', name, cl[0])

def use(cl, jinf, tree, name):
    set_info_file(jinf, 'use', name, cl[0])

def input(cl, jinf, tree, name):
    set_info_file(jinf, 'input', name, cl[0])

def version(cl, jinf, tree, command):
    P = sp.Popen(tree, shell=True, stdout=sp.PIPE)
    out, _ = P.communicate()
    jinf['tool_version'] = out.strip()

def not_implemented(*args):
    global PARSEFAIL
    PARSEFAIL = True

class OrderedDictSet(OrderedDict):
    def __setitem__(self, key, value):
        if not key in self:
            super(OrderedDictSet, self).__setitem__(key, [])
        self[key].append(value)

from kea.plugin.logger import dictprint

def processor(cl, jinf, tree):
    if isinstance(tree, str):
        items = [(tree, [{}])]
    elif isinstance(tree, dict):
        items = tree.items()
    else:
        lg.warning("invalid tree structure")
        exit(-1)
    for ky, vls in items:
        for vl in vls:
            if PARSEFAIL or PARSEDONE:
                break
            command, args = ky.split('|', 1) if '|' in ky else (ky, "")
            lg.debug("process: %s(%s)", command, args)
            lg.debug("     on: %s", " ".join(cl)[:80])
            if isinstance(vl, OrderedDict):
                lg.debug("   with od: %s...", str(dict(vl))[:50])
            else:
                lg.debug("   with: %s...", str(vl)[:50])
            args = args.split('|')
            ncl = eval(command)(cl, jinf, vl, *args)
            if ncl is not None:
                lg.debug("new cl %s", ncl)
                cl = ncl
    return cl



# from: https://stackoverflow.com/questions/5121931/\
#    in-python-how-can-you-load-yaml-mappings-as-ordereddicts
def yaml_ordered_load(stream, Loader=yaml.Loader,
                      object_pairs_hook=OrderedDictSet):
    class OrderedLoader(Loader):
        pass
    def construct_mapping(loader, node):
        loader.flatten_mapping(node)
        return object_pairs_hook(loader.construct_pairs(node))
    OrderedLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping)
    return yaml.load(stream, OrderedLoader)


@leip.hook('pre_fire')
def parse_commandline(app, jinf):

    global PARSEFAIL
    global PARSEDONE
    PARSEFAIL = PARSEDONE = False

    for inf in app.args.inf:
        set_info_file(jinf, 'input', 'input', inf)

    cl = jinf['cl']
    set_info_file(jinf, 'use', 'executable', jinf['executable'])

    find_filemark = re.compile('{(\w+)@}')
    elements_to_remove = []
    for i, cli in enumerate(cl):
        chk_cli = find_filemark.match(cli)
        if not chk_cli:
            continue
        elements_to_remove.append(cli)
        grp = chk_cli.groups()[0]
        grp = dict(i='input', o='output', d='database', u='use')[grp[0]]

        if not  grp in 'input database use output'.split():
            lg.critical('invalid category: %s', grp)
        set_info_file(jinf, grp, grp, cl[i+1])

    for etr in elements_to_remove:
        while etr in cl:
            cl.remove(etr)
    jinf['cl'] = cl

    try_parse = True
    try:
        tree = pkg_resources.resource_string(
            __name__, "parsers/{}.conf".format(app.name))
    except IOError:
        #no parser found - ignore
        try_parse = False
        if app.args.pfe:
            lg.info("No command line parser defined")

    parse_jinf = copy.copy(jinf)

    if try_parse:
        tree = yaml_ordered_load(tree, yaml.SafeLoader)
        processor(parse_jinf['cl'], parse_jinf, tree)

    if not PARSEFAIL:
        jinf.update(parse_jinf)
        if app.args.pfe:
            print('-' * 80)
            print(" ".join(jinf['cl']))
            for c in ['input', 'output', 'database', 'use']:
                if c not in jinf:
                    continue
                for fl in sorted(jinf[c]):
                    fld = jinf[c][fl]
                    cprint(c, "yellow", end=" ")
                    cprint(fl, "white", end=" ")
                    if os.path.exists(fld['path']):
                        cprint(fld['path'], "green")
                    else:
                        cprint(fld['path'], "red")
            for c in jinf.get('parameter', {}):
                cprint("parameter", "yellow", end=" ")
                cprint(c, "white", end=" ")
                cprint(jinf['parameter'][c], "cyan")
            jinf['skip'] = True
            return




    else:
        if app.args.pfe:
            print("Failed to parse the command line")
            sys.exit()
        else:
            lg.warning("Failed to parse the command line")
