
# kea runner

import argparse
import copy
from collections import OrderedDict
import logging
import os
import subprocess as sp
import sys

import arrow
import leip
import fantail

import mad2.util as mad2util

from kea.utils import get_tool_conf
from kea.plugin.register import print_tool_versions
from kea.cl_generator import basic_command_line_generator
from kea.executor import executors

lg = logging.getLogger(__name__)
#lg.setLevel(logging.DEBUG)

conf = leip.get_config('kea')

#leiplog = logging.getLogger('leip')
#leiplog.setLevel(logging.DEBUG)


class Kea(leip.app):

    def __init__(self, *args, **kwargs):
        if len(args) == 0:
            name = os.path.split(sys.argv[0])[1]
            if name[:3] == 'kea_':
                name = name[3:]
        else:
            name = args[0]

        # Call Leip - we do not need the Leip argparser:
        super(Kea, self).__init__('kea', disable_commands=True)

        # replace the config by a stack so we can backfill
        self.conf = fantail.Fanstack([self.conf, fantail.Fantail()])

        # hack - if kea verbose is set - do that early:

        verbose_flag = self.conf['arg_prefix'] + '-v'
        if verbose_flag in sys.argv:
            lg.setLevel(logging.DEBUG)

        #default executors
        self.executors = executors

        lg.debug("start kea initialization")

        # different hooks!
        self.hook_order = [
            'pre_argparse',
            'argparse',
            'post_argparse',
            'prepare',
            'pre_run',
            'run',
            'finish']

        # for the kea argparse (starting with app.conf.arg_prefix)
        # default prefix = '---'
        # need to define how many arguments are taken from the command
        # line for each flag - the rest is handled by argparse
        self.kea_arg_harvest_extra = {}
        self.kea_argparse = argparse.ArgumentParser(
            prog='(kea){}'.format(name),
            description='Kea wrapper for: {}'.format(name),
            epilog='NOTE: Prefix all Kea arguments with: "' +
            self.conf['arg_prefix'] + '"')

        self._madapp = None  # hold the Leip Mad Application

        self.conf['appname'] = name
        self.conf['kea_executable'] = sys.argv[0]
        self.discover(globals())

    @property
    def madapp(self):
        if not self._madapp is None:
            return self._madapp

        self._madapp = leip.app('mad2', disable_commands=True)
        return self._madapp

    def get_madfile(self, filename):
        return mad2util.get_mad_file(self.madapp, filename)


@leip.hook('pre_argparse')
def main_arg_define(app):

    for a in ('-V --version -j --threads -x --executor -o --stdout ' +
              '-e --stderr').split():
        app.kea_arg_harvest_extra[a] = 1

    app.kea_argparse.add_argument('-V', '--version', default='default',
                                  help='version number to use')
    app.kea_argparse.add_argument('-L', '--list_versions', action='store_true',
                                  help='list all versions of this tool & exit')
    app.kea_argparse.add_argument('-v', '--verbose', action='store_true')
    app.kea_argparse.add_argument('-E', '--command_echo', action='store_true',
                                  help='echo Kea commands to stdout')
    app.kea_argparse.add_argument('-j', '--threads', type=int, default=-1,
                                  help='kea threads to use (if applicable)')
    app.kea_argparse.add_argument('-x', '--executor', help='executor to use')
    app.kea_argparse.add_argument('-o', '--stdout', help='save stdout to')
    app.kea_argparse.add_argument('-e', '--stderr', help='save stderr to')


@leip.hook('argparse')
def kea_argparse(app):
    """
    Separate Kea arguments from tool arguments & feed the kea arguments
    to argparse
    """
    app.original_args = copy.copy(sys.argv)
    prefix = app.conf['arg_prefix']
    prelen = len(prefix)
    new_sysargv = []
    kea_argv = []
    i = 0
    while i < len(sys.argv):
        a = sys.argv[i]

        if a.startswith(prefix + '-'):
            flag = a[prelen:]
            kea_argv.append(flag)
            harvest_no = app.kea_arg_harvest_extra.get(flag, 0)
            if harvest_no > 0:
                harvest = sys.argv[i + 1:i + 1 + harvest_no]
                kea_argv.extend(harvest)
                i += harvest_no
        else:
            new_sysargv.append(a)

        i += 1

    app.kea_clargs = kea_argv
    app.kea_args = app.kea_argparse.parse_args(kea_argv)
    lg.debug("kea args: {}".format(" ".join(kea_argv)))
    lg.debug("com args: {}".format(" ".join(new_sysargv)))
    lg.debug("kea argparse: {}".format(str(app.kea_args)))
    sys.argv = new_sysargv


@leip.hook('post_argparse')
def main_arg_process(app):
    """
    Process parsed arguments
    """
    if app.kea_args.verbose:
        lg.setLevel(logging.DEBUG)

    if app.kea_args.list_versions:
        print_tool_versions(app, app.conf['appname'])
        exit(0)

    if app.kea_args.command_echo:
        app.conf['command_echo'] = True
    app.conf['threads'] = app.kea_args.threads


@leip.hook('prepare', 10)
def prepare_config(app):

    version = app.kea_args.version
    if version is None:
        lg.debug("Prepping tool conf: %s (default version)",
                 app.conf['appname'])
    else:
        lg.debug("Prepping tool conf: %s %s",
                 app.conf['appname'], version)

    conf = get_tool_conf(app, app.conf['appname'], app.kea_args.version)
    app.conf.stack[1] = conf

    lg.debug("Loaded config: %s",  app.conf['appname'])


@leip.hook('run')
def run_kea(app):
    lg.debug("Start Kea run")
    executor_name = 'simple'
    if app.kea_args.executor:
        executor_name = app.kea_args.executor

    lg.info("loading executor %s", executor_name)
    executor = app.executors[executor_name](app)

    all_info = []
    for info in basic_command_line_generator(app):
        info['executable'] = app.conf['executable']
        info['kea_executable'] = app.conf['kea_executable']
        info['kea_arg_prefix'] = app.conf['arg_prefix']
        info['app_name'] = app.conf['appname']
        info['app_version'] = app.conf['version']

        all_info.append(info)
        info['executor'] = executor_name
        cl = info['cl']

        lg.debug("command line arguments: %s", " ".join(cl))
        if app.conf.get('command_echo'):
            print " ".join(cl)

        info['kea_args'] = " ".join(app.kea_clargs)
        info['cwd'] = os.getcwd()
        info['full_cl'] = " ".join(app.original_args)

        app.run_hook('pre_fire', info)
        executor.fire(info)
        app.run_hook('post_fire', info)

    executor.finish()
    app.run_hook('post_run', all_info)


@leip.hook('prepare')
def find_executable(app):

    lg.debug("find executable location")

    if 'executable' in app.conf:
        return

    this = sys.argv[0]
    P = sp.Popen(['which', '-a', app.conf['appname']], stdout=sp.PIPE)
    out, err = P.communicate()
    for line in out.strip().split("\n"):
        if os.path.samefile(line, this):
            # this is the called executable wrapper - ignore
            continue
        else:
            app.conf['executable'] = line.strip()
