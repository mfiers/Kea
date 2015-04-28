
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

            if self.executor not in self.conf['executors']:
                lg.debug("unrecognized executor %s - setting to %s",
                           self.executor, self.conf['default_executor'])
                self.executor = self.conf['default_executor']


        lg.debug("executor: %s", self.executor)

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

        self.parser = argparse.ArgumentParser(add_help=False)
        self.discover(globals())


@leip.hook('pre_argparse', 10)
def main_arg_define(app):
    app.parser.add_argument('-h', '--help', action='store_true',
                            help='Show this help and exit')
    app.parser.add_argument('-v', '--verbose', action='count', default=0)
    app.parser.add_argument('-U', '--uid',
                            help='unique identifier for this run')
    app.parser.add_argument('-x', '--executor', help='executor to use',
                            default=app.conf['default_executor'])
    app.parser.add_argument('-V', '--version', help='tool version')
    app.parser.add_argument('-o', '--stdout', help='save stdout to')
    app.parser.add_argument('-e', '--stderr', help='save stderr to')
    app.parser.add_argument('--deferred', action='store_true',
                            help=argparse.SUPPRESS) #internal use
    app.parser.add_argument('-n', '--jobstorun', help='no jobs to start',
                            type=int)


@leip.hook('argparse')
def kea_argparse(app):
    """
    Separate Kea arguments from tool arguments & feed the kea arguments
    to argparse
    """

    tmpparser = copy.copy(app.parser)

    app.conf['original_cl'] = " ".join(sys.argv)

    lg.debug("execute: %s", sys.argv)
    tmpparser.add_argument('command', nargs='?')
    tmpparser.add_argument('arg', nargs=argparse.REMAINDER)

    tmpargs = tmpparser.parse_args()
    if tmpargs.command is not None:
        command_start = sys.argv.index(tmpargs.command)
        app.args = app.parser.parse_args(sys.argv[1:command_start])
        app.args.command = sys.argv[command_start]
        app.args.arg = sys.argv[command_start+1:]
    else:
        app.args = app.parser.parse_args(sys.argv[1:])
        app.args.command = None
        app.args.arg = []

    if app.args.help:
        kea_app = leip.app('kea', partial_parse=True)
        print("# Command mode\n")
        app.parser.print_help()
        print("\n# Utility mode\n")
        kea_app.parser.print_help()
        exit(0)

    if app.args.command and app.args.command[0] == '+':
        #snippet mode!!
        app.run_hook('snippet', app.args.command)
        tmpargs = tmpparser.parse_args()
        if tmpargs.command is not None:
            command_start = sys.argv.index(tmpargs.command)
            app.args = app.parser.parse_args(sys.argv[1:command_start])
            app.args.command = sys.argv[command_start]
            app.args.arg = sys.argv[command_start+1:]
        else:
            app.args = app.parser.parse_args(sys.argv[1:])
            app.args.command = None
            app.args.arg = []


    app.conf['cl_args'] = " ".join(app.args.arg)

    if not app.args.command:
        app.parser.print_usage()
        kea_app = leip.app('kea', partial_parse=True)
        kea_app.parser.print_usage()
        sys.exit(-1)

    cl = app.args.command

    if app.conf['cl_args']:
        cl += ' ' + app.conf['cl_args']

    app.conf['cl'] = cl
    app.name = os.path.basename(app.args.command)

    app.conf['original_executable'] = app.args.command
    executable = app.args.command

    P = sp.Popen(['which', executable], stdout=sp.PIPE)
    Pout, _ = P.communicate()
    executable = Pout.strip().decode('utf-8')
    lg.debug("executable: %s", executable)

    app.conf['executable'] = executable

    conf = get_tool_conf(app, app.name, app.args.version)
    app.conf.stack[1] = conf

    if app.args.verbose == 1:
        logging.getLogger().setLevel(logging.INFO)
    if app.args.verbose > 1 :
        logging.getLogger().setLevel(logging.DEBUG)

    #load args into the config object
    app.defargs = fantail.Fantail()
    app.defargs.update(app.conf.get('default'))
    app.defargs.update(app.conf.get('app.default.{}'.format(app.name)))
    for k in app.args.__dict__:
        v = getattr(app.args, k)
        if v is None: continue
        app.defargs[k] = v
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

        jinf['args'] = " ".join(app.conf['cl_args'])
        jinf['cwd'] = os.getcwd()

        executor.fire(jinf)

    executor.finish()
