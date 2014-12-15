
# kea runner

import argparse
import copy
from collections import OrderedDict
import logging
import os
import shlex
import subprocess as sp
import sys

import leip
import fantail


from kea.utils import get_tool_conf
from kea.plugin.register import print_tool_versions
from kea.cl_generator import basic_command_line_generator

lg = logging.getLogger(__name__)
#lg.setLevel(logging.DEBUG)

conf = leip.get_config('kea')

#leiplog = logging.getLogger('leip')
#leiplog.setLevel(logging.DEBUG)


class Kea(leip.app):

    def __init__(self, *args, **kwargs):

        # Call Leip - but we do not want the argparser:
        super(Kea, self).__init__('kea', disable_commands=True)

        self.all_jinf = [] #store job reports
        
        # replace the config by a stack so we can backfill
        self.conf = fantail.Fanstack([self.conf, fantail.Fantail()])

        # hack - if -v/--verbose is set - use that early:
        if '-vv' in sys.argv:
            lg.setLevel(logging.DEBUG)
        elif '-v' in sys.argv:
            lg.setLevel(logging.INFO)
            
        # another hack - early discovery of the executor
        # print(sys.argv.find('-x')
        if not '-x' in sys.argv:
            self.executor = self.conf['default_executor']
        else:
            xindx = sys.argv.index('-x')
            if xindx < len(sys.argv):
                self.executor = sys.argv[xindx + 1]
            else:
                self.executor = self.conf['default_executor']

            
        lg.debug("start kea initialization")

        # different hooks!
        self.hook_order = [
            'pre_argparse',
            'argparse',
            'post_argparse',
            'prepare',
            'pre_run',
            'run',
            'post_run',
            'finish']

        self.parser = argparse.ArgumentParser()
        self.discover(globals())


@leip.hook('pre_argparse')
def main_arg_define(app):

    app.parser.add_argument('-v', '--verbose', action='count')
    app.parser.add_argument('-U', '--uid',
                            help='unique identifier for this run')
    app.parser.add_argument('-x', '--executor', help='executor to use',
                            default=app.conf['default_executor'])
    app.parser.add_argument('-V', '--version', help='tool version')
    app.parser.add_argument('-o', '--stdout', help='save stdout to')
    app.parser.add_argument('-e', '--stderr', help='save stderr to')


@leip.hook('argparse')
def kea_argparse(app):
    """
    Separate Kea arguments from tool arguments & feed the kea arguments
    to argparse
    """

    app.parser.add_argument('command')
    app.parser.add_argument('arg', nargs=argparse.REMAINDER)

    app.args = app.parser.parse_args()
    app.cl_args = app.args.arg

    cl = [app.args.command]
    
    if app.cl_args:
        cl.extend(app.cl_args)

    #special case - probably used quotes on the command line
    if len(cl) == 1 and ' ' in cl[0]:
        cl = shlex.split(cl[0])

    app.cl = cl
    app.name = os.path.basename(app.cl[0])
    app.conf['executable'] = app.cl[0]
    conf = get_tool_conf(app, app.name, app.args.version)
    app.conf.stack[1] = conf

    if app.args.verbose == 1:
        logging.getLogger().setLevel(logging.INFO)
    if app.args.verbose > 1 :
        logging.getLogger().setLevel(logging.DEBUG)

    app.executor = app.args.executor
    lg.debug("Loaded config: %s",  app.name)


    
@leip.hook('run')
def run_kea(app):
    
    lg.debug("Start Kea run")
    executor_name = app.executor

    lg.debug("loading executor %s", executor_name)
    executor = app.conf['executors.{}'.format(executor_name)](app)

    app.all_jinf = []
    for jinf in basic_command_line_generator(app):
        app.all_jinf.append(jinf)

        jinf['executable'] = app.conf['executable']
        jinf['executor'] = executor_name
        cl = jinf['cl']
        lg.debug("command line arguments: %s", " ".join(cl))

        jinf['args'] = " ".join(app.cl_args)
        jinf['cwd'] = os.getcwd()

        app.run_hook('pre_fire', jinf)
        executor.fire(jinf)
        app.run_hook('post_fire', jinf)
        
    executor.finish()
