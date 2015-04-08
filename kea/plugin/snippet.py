
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
#lg.setLevel(logging.DEBUG)

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
    fullpath = find_snippet_path(app, name)
    if fullpath is None:
        lg.warning("cannot find snippet definition for %s", name)
        sys.exit(-1)
        
    with open(fullpath) as F:
        raw = F.read().strip()

    return raw


def edit_snippet(app, snippet):

    fullpath = find_snippet_path(app, snippet, ensure_result=True)
    fulldir = os.path.dirname(fullpath)
    if not os.path.exists(fulldir):
        os.makedirs(fulldir)

    if os.path.exists(fullpath):
        with open(fullpath) as F:
            default = F.read()
    else:
        default = ""

    from toMaKe import ui
    newdef = ui.askUserEditor(default)

    with open(fullpath, 'w') as F:
        F.write(newdef)
    sys.exit()
    

@leip.hook('snippet')
def process_snippet(app, snippet):

    snippos = sys.argv.index(snippet)
    snippet = snippet[1:].strip()

    if len(sys.argv) > snippos+1 and sys.argv[snippos+1] == 'edit':
        return edit_snippet(app, snippet)
    
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
        sys.argv = sys.argv[:snippos] + snipraw
        return

    find_arg = re.compile(
        r'{{\s*(?P<name>\w+)\s*' +
        r'(\|(?P<default>[^}\|]*))?'
        r'}}'
    )

    lg.debug("Start parsing snippet")
    pargs = defaultdict(lambda:{})
    positional_counter = 0
    ## preparse snippet - remove predefined arguments
    snipsplit = snipraw.split("\n")
    newsnip = []
    for line in snipsplit:
        line = line.strip()
        if not line: continue
        if line[:2] == '##':
            #prepare argument
            line = line[2:]
            line = shlex.split(line)
            name = line[0]
            positional = False
            adata = {}
            for a in line[1:]:
                if a == 'positional':
                    adata['positional'] = positional_counter
                    positional_counter += 1
                    continue
                k, v = a.split('=', 1)
                adata[k] = v
            if positional:
                ppargs[name] = adata
            else:
                pargs[name] = adata
            continue
        
        #lastword = shlex.split(line)[-1]
        # if line[-1] not in ';\\{' and \
        #   lastword not in 'then do in'.split():
        #    line += ';'
        newsnip.append(line)

    snipraw = "\n".join(newsnip).rstrip(';')
    
    ##
    ## parse snippet
    ##

    for arghit in find_arg.finditer(snipraw):
        hitdata = arghit.groupdict()
        name = hitdata['name'].strip()
        lg.debug("found argument: %s", name)
        envname = 'KEA_{}'.format(name.upper())
        envdef = os.environ.get(envname)

        if not envdef is None:
            pargs[name]['default'] = envdef
        else:
            default = hitdata.get('default')

        # do not overwrite default value when it is already set
        # this may come in useful when there are multiple instances
        # of an argument

        if not 'default' in pargs[name] or pargs[name]['default'] is None:
            pargs[name]['default'] = default

    # prepare temp command line
    
    parser = argparse.ArgumentParser(snippet)
    posargs = []
    for name, kwdata in pargs.items():
        if kwdata.get('default'):
            kwdata['help'] = kwdata.get('help', '') + ' ({})'.format(kwdata['default']).strip()
        else:
            kwdata['help'] = kwdata.get('help', '') + ' (mandatory)'.strip()

        if 'positional' in kwdata:
            posno = kwdata['positional']
            del kwdata['positional']
            posargs.append((posno, name, kwdata))
        else:
            parser.add_argument('--{}'.format(name), **kwdata)

    posargs.sort()
    for ano, name, kwdata in posargs:
        parser.add_argument(name, **kwdata)
        
    commandline_args = parser.parse_args(sys.argv[snippos+1:])
    errors = False
    parsed_snip = snipraw
    
    for name in pargs:
        clarg = getattr(commandline_args, name)
        if clarg is None:
            lg.debug('No value found for: %s', name)
            errors = True
            continue
        replace_re = r'{{\s*' + name + r'(?=[\|\s}]).*?}}'
        parsed_snip = re.sub(replace_re, clarg, parsed_snip)

    if errors:
        parser.print_help()
        sys.exit(-1)
        
    parsed_snip_split = shlex.split(parsed_snip)
    
    app.conf['snippet_cl_raw'] = " ".join(sys.argv[:snippos]) + ' ' + parsed_snip
    app.conf['snippet_cl'] = sys.argv[:snippos] + parsed_snip_split
    sys.argv = sys.argv[:snippos] + parsed_snip_split


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
