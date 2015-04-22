
import argparse
from collections import defaultdict, OrderedDict
import logging
import os
import shlex
import sys
import re

import leip

from kea import Kea

lg = logging.getLogger('name')
lg.setLevel(logging.DEBUG)

def get_snippet_repos(app):

    if not 'snippet' in app.conf:
        return []

    groups = []
    for group in app.conf['snippet']:
        data = app.conf['snippet'][group]
        try:
            order = data.get('order', 100)
        except:
            order =100

        groups.append((order, group))

    groups.sort()
    return groups

def find_snippet_path(app, name, ensure_result=False):

    groups = get_snippet_repos(app)

    primary_group = groups[0][1]
    primary_path = None

    for order, group in groups:
        lg.debug("procssing snippet group %d %s", order, group)

        data = app.conf['snippet'][group]
        pth = data['dir']

        if not pth:
            lg.warning("Invalid snippet definition:\n %s", data.pretty())

        fullpath = os.path.join(os.path.expanduser(pth),
                                '{}.snippet'.format(name))

        if group == primary_group:
            primary_path = fullpath

        if os.path.exists(fullpath):
            return fullpath

    if ensure_result:
        return primary_path
    else:
        return None


def get_snippet(app, name):

    fullpath = find_snippet_path(app, name, ensure_result=True)

    fulldir = os.path.dirname(fullpath)
    if not os.path.exists(fulldir):
        os.makedirs(fulldir)

    if fullpath is None:
        lg.warning("cannot find snippet definition for %s", name)
        return ""

    if not os.path.exists(fullpath):
        return ""

    with open(fullpath) as F:
        raw = F.read().strip()

    return raw

def raw_snippet(app, name):
    snip = get_snippet(app, name)
    print(snip)
    sys.exit()

def edit_snippet(app, name):

    default = get_snippet(app, name)
    fullpath = find_snippet_path(app, name, ensure_result=True)
    from toMaKe import ui
    newdef = ui.askUserEditor(default)

    with open(fullpath, 'w') as F:
        F.write(newdef)
    sys.exit()


@leip.hook('snippet')
def process_snippet(app, snippet):

    FLAGS = 'p<>'
    sysarg = app.conf['original_cl']
    snippos = sysarg.index(snippet)
    snippet = snippet[1:].strip()

    if len(sysarg) > snippos+1:
        snipcomm = sysarg[snippos+1]
        if snipcomm == 'edit':
            return edit_snippet(app, snippet)
        if snipcomm == 'raw':
            return raw_snippet(app, snippet)

    lg.debug("snippet: %s", snippet)

    snipraw = get_snippet(app, snippet)
    if not snipraw:
        lg.warning("Could not find a snippet for %s", snippet)
        sys.exit(-1)

    if not '{{' in snipraw:
        # no need to expand - set & return
        lg.debug("no need to expand the snippet")
        lg.debug("returning: %s", snipraw)
        snipraw  = shlex.split(snipraw)
        sys.argv = sysarg[:snippos] + snipraw
        return

    comments = re.compile(
        r'{{\s*#.*?}}')

    find_arg = re.compile(
        r'{{(?P<type>[' + FLAGS + \
        r']*)\s*(?P<name>\w+)(?:\s*\|\s*(?P<args>.*?))?\s*}}')

    snipraw = comments.sub('', snipraw)

    lg.debug("Start parsing snippet")

    toreplace = []

    keyargs = []
    posargs = []
    #matches = []

    ##
    ## parse snippet & build argparser object
    ##

    lg.debug("regex parsing raw snippet")
    for i, arghit in enumerate(find_arg.finditer(snipraw)):

        hitdata = arghit.groupdict()

        name = hitdata['name'].strip()
        atype = hitdata['type']
        rawargs = hitdata['args']

        hitdata['raw'] = snipraw[arghit.start():arghit.end()]

        lg.debug("found: %s", hitdata['raw'])
        lg.debug(" - name: %s", name)
        lg.debug(" - atype: %s", atype)
        lg.debug(" - rawargs: %s", rawargs)

        arg_kwdata = {}

        if not rawargs is None:
            for k, v in [(a.strip(), b.strip()) for
                         a,b in [x.strip().split('=', 1) for x in
                                 hitdata.get('args', '').split('|')]]:
                arg_kwdata[k] = v

        #check if an environment variable is defined
        envname = 'KEA_{}'.format(name.upper())
        envdef = os.environ.get(envname)

        if not envdef is None:
            arg_kwdata['default'] = envdef

        if 'p' in atype:
            posargs.append((name, arg_kwdata))
        else:
            keyargs.append((name, arg_kwdata))

        toreplace.append(hitdata)

    # prepare argument parser for this snippet
    parser = argparse.ArgumentParser(snippet)

    for name, kwdata in posargs:
        if kwdata.get('default'):
            kwdata['nargs'] = '?'
            kwdata['help'] = kwdata.get('help', '') + ' (default: {})'.format(
                kwdata['default']).strip()

        parser.add_argument(name, **kwdata)

    for name, kwdata in keyargs:
        if kwdata.get('default'):
            kwdata['help'] = kwdata.get('help', '') + ' ({})'.format(kwdata['default']).strip()
        else:
            kwdata['help'] = kwdata.get('help', '') + ' (mandatory)'.strip()

        parser.add_argument('--{}'.format(name), **kwdata)


    # parse command line for this snippet
    commandline_args = parser.parse_args(sysarg[snippos+1:])
    errors = False
    parsed_snip = snipraw

    clargvals = {}
    # process arguments:
    for name in keyargs:
        clarg = getattr(commandline_args, name)
        if clarg is None:
            lg.debug('No value found for: %s', name)
            errors = True
            continue
        clargvals[name] = clarg
#        replace_re = r'{{[p]*\s*' + name + r'(?=\W).*?}}'
#        parsed_snip = re.sub(replace_re, clarg, parsed_snip)

    for name, kwargs in posargs:
        clarg = getattr(commandline_args, name)
        if clarg is None:
            lg.debug('No value found for: %s', name)
            errors = True
            continue
        clargvals[name] = clarg
#        replace_re = r'{{[' + FLAGS + r']*\s*' + name + r'(?=\W).*?}}'
#        parsed_snip = re.sub(replace_re, clarg, parsed_snip)

    if errors:
        parser.print_help()
        sys.exit(-1)

    #process snip -
    for item in toreplace:
        name = item['name']
        src = item['raw']
        rep = clargvals[name]
        typ = item['type']
        lg.debug("clarg %s: %s", name, rep)

        for iou in '<^>':
            if iou in typ:
                if '{' in rep:
                    rep = "{" + iou + name + "} "  + rep
                else:
                    rep = "{" + iou + name + "} " \
                          + '{' + name + '~' + rep +'}'
        lg.debug("replace --- %s --- %s ---", src, rep)
        parsed_snip = parsed_snip.replace(src, rep)

    lg.debug("converted: %s", parsed_snip)
    parsed_snip_split = shlex.split(parsed_snip)

    app.conf['snippet_cl_raw'] = " ".join(sysarg[:snippos]) + ' ' + parsed_snip
    app.conf['snippet_cl'] = sysarg[:snippos] + parsed_snip_split
    sys.argv = sysarg[:snippos] + parsed_snip_split


# @leip.command
# def jobrun(app, args):

#     if not os.path.exists('run.sh'):
#         lg.error("no run.sh found")
#         exit(-1)
#     with open ('./run.sh') as F:
#         code = F.read()

#     os.system(code)
#     exit()

# @leip.command
# def jr(app, args):
#     return jobrun(app, args)


# @leip.arg('args', nargs=argparse.REMAINDER)
# @leip.arg('name')
# @leip.command
# def snipset(app, args):
#     cl = args.args
#     lg.warning('saving to "%s": %s', args.name, " ".join(args.args))
#     lconf = leip.get_local_config_file('kea')
#     if 'snippet' in lconf:
#         lconf['snippet'] = {}
#     lconf['snippet.{}'.format(args.name)] = args.args
#     leip.save_local_config_file(lconf, 'kea')

#     #force rehash
#     leip.get_config('kea', rehash=True)


# @leip.arg('command_line', nargs=argparse.REMAINDER)
# @leip.command
# def jobset(app, args):
#     """
#     Set a local job

#     if no command line is provided a prompt is provided
#     """

#     if len(args.command_line) == 0:
#         import toMaKe.ui
#         default = ""
#         if os.path.exists('run.sh'):
#             with open('run.sh') as F:
#                 default = F.read().strip()
#         jcl = toMaKe.ui.askUser("cl", appname='kea', default=default,
#                                 prompt='cl: ')
#     else:
#         jcl = args.command_line

#     lg.info('saving as job: %s', " ".join(jcl))
#     with open('./run.sh', 'w') as F:
#         F.write(jcl.rstrip() +  "\n")

# @leip.arg('command_line', nargs=argparse.REMAINDER)
# @leip.command
# def js(app, args):
#     """
#     Alias for jobset
#     """
#     return jobset(app, args)
