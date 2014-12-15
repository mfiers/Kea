
import argparse
import logging
import os
import shlex
import sys

import leip

from kea import Kea

lg = logging.getLogger('name')


@leip.arg('arg', nargs=argparse.REMAINDER)
@leip.arg('name', nargs='?')
@leip.command
def run(app, args):
    if not args.name:
        if not os.path.exists('run.sh'):
            lg.error("no run.sh found")
        with open ('./run.sh') as F:
            snippet = shlex.split(F.read())
            if 'kea' in snippet[0]:
                snippet = snippet[1:] 
    else:
        snippet = app.conf.get('snippet.{}'.format(args.name))
        
    sys.argv = sys.argv[:sys.argv.index('run')] + snippet + args.arg
    kea_app = Kea()
    kea_app.run()
    
    
@leip.arg('args', nargs=argparse.REMAINDER)
@leip.arg('name')
@leip.command
def snipset(app, args):
    cl = args.args
    lg.warning('saving to "%s": %s', args.name, " ".join(args.args))
    lconf = leip.get_local_config_file('kea')
    if lconf.has_key('snippet'):
        lconf['snippet'] = {}
    lconf['snippet.{}'.format(args.name)] = args.args
    leip.save_local_config_file(lconf, 'kea')

    #force rehash
    leip.get_config('kea', rehash=True)


@leip.arg('command_line', nargs=argparse.REMAINDER)
@leip.command
def jobset(app, args):
    """
    Set a local job

    if no command line is provided a prompt is provided
    """
    
    ukargs = app.trans.get('unknown_args', [])
    
    if len(args.command_line) == 0:
        import toMaKe.ui
        default = ""
        if os.path.exists('run.sh'):
            with open('run.sh') as F:
                default = F.read().strip()
            defsplit = shlex.split(default)
            if 'kea' in defsplit[0]:
                default = " ".join(defsplit[1:])
        jcl = shlex.split(toMaKe.ui.askUser("cl ", appname='kea', default=default,
                                            prompt='cl: kea '))
    else:
        jcl = args.command_line
    
    cl = ['kea'] + ukargs + jcl
    
    lg.info('saving as job: %s', " ".join(cl))
    with open('./run.sh', 'w') as F:
        F.write(" ".join(cl) + "\n")

@leip.arg('command_line', nargs=argparse.REMAINDER)
@leip.command
def js(app, args):
    """
    Alias for jobset
    """
    return jobset(app, args)
    
