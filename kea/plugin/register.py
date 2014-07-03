# tools to help register & identify commands

import logging
import os
import pprint
import subprocess as sp
import sys

from jinja2 import Template
import yaml

import leip
from leip import set_local_config

from kea.utils import find_executable, register_executable
from kea.utils import get_tool_conf, create_kea_link


lg = logging.getLogger(__name__)


@leip.arg('-V', '--version', help='version number')
@leip.arg('-a', '--appname', help='application name')
@leip.command
def show(app, args):
    lg.info("show conf: %s", args.appname)

    conf = get_tool_conf(app, args.appname, args.version)

    del conf['versions']

    yaml.dump(conf, sys.stdout, default_flow_style=False)


@leip.hook('post_argparse')
def run_register_tool_commands(app):
    if app.kea_args.list_versions:
        print_tool_versions(app, app.conf['appname'])
        exit(0)



@leip.arg('-v', '--version', help='version to set default')
@leip.arg('-a', '--appname', help='application name')
@leip.command
def set_default(app, args):
    """
    List tool versions
    """
    tkey = args.version
    tdata = app.conf['app.{}.version.{}'.format(args.appname, args.version)]
    print "set default:"
    print '{}: {}'.format(tkey, tdata['executable'])

    tv = tdata['version']
    if len(tv) < 80:
        print '  version: {}'.format(tv)
    else:
        i = 0
        while tv:
            if i == 0:
                print '  version: {}'.format(tv[:80])
                tv = tv[80:]
            else:
                print '     {}'.format(tv[:86])
                tv = tv[86:]
            i += 1

    set_local_config(app, 'app.{}.default_version'.format(args.appname), tkey)


def print_tool_versions(app, appname):
    tool_version_data = app.conf['app.{}.versions'.format(appname)]
    def_version = app.conf['app.{}.default_version'.format(appname)]
    for tkey in tool_version_data:
        tdata = app.conf['app.{}.versions.{}'.format(appname, tkey)]
        print '{}: {}'.format(tkey, tdata['executable'])
        tv = tdata['version']
        if len(tv) < 80:
            print '  version: {}'.format(tdata['version'])
        else:
            i = 0
            while tv:
                if i == 0:
                    print '  version: {}'.format(tv[:80])
                    tv = tv[80:]
                else:
                    print '     {}'.format(tv[:86])
                    tv = tv[86:]
                i += 1
        if tkey == def_version:
            print("  default")


@leip.arg('-a', '--appname', help='application name')
@leip.command
def list(app, args):
    """
    List tool versions
    """
    if not args.appname is None:
        print_tool_versions(app, args.appname)
        return
    for tool in app.conf['app']:
        if 'versions' in app.conf['app.{}'.format(tool)]:
            print(tool)

@leip.arg('-a', '--appname', help='application name')
@leip.command
def create_execs(app, args):
    """
    Create Kea executables
    """
    for tool in app.conf['app']:
        if args.appname and tool == args.appname:
            if 'versions' in app.conf['app.{}'.format(tool)]:
                print(tool)
                create_kea_link(app, tool)


@leip.flag('-d', '--set_default', help='set this executable as default')
@leip.arg('-V', '--version', help='version number')
@leip.arg('-a', '--appname', help='application name')
@leip.command
def add(app, args):

    execname = args.appname
    if '/' in execname:
        execname = execname.split('/')[-1]

    lg.debug("register %s", execname)

    execs = list(find_executable(args.appname))
    no_execs = len(execs)

    # make sure there is a link in the kea bin path
    keabin = os.path.expanduser(app.conf['bin_path'])
    if not os.path.exists(keabin):
        os.makedirs(keabin)

    if no_execs == 1 and args.version:
        register_executable(app, execname, execs[0], args.version,
                            args.set_default)
        return

    if no_execs > 1 and args.version:
        lg.error("multiple executables found & have only one version")
        for e in execs:
            lg.error("  - %s", e)
        exit(-1)

    if no_execs > 1 and args.is_default:
        lg.error("multiple executables found & cannot set them all as default")
        for e in execs:
            lg.error("  - %s", e)
        exit(-1)

    toolconf = get_tool_conf(app, execname, version=None)

    if not 'version_command' in toolconf:
        lg.error("No information on how to retrieve tool version")
        lg.error("Please specify using:")
        lg.error("   kea conf set app.%s.version_command '<command>'",
                 execname)
        exit(-1)

    version_command = toolconf['version_command']
    lg.debug("version command: %s", version_command)
    vc_template = Template(version_command)

    lg.info("version command: %s", version_command)

    for ex in execs:
        cmd = vc_template.render(executable=ex)
        P = sp.Popen(cmd, shell=True, stdout=sp.PIPE)
        o, e = P.communicate()
        version = o.strip()
        register_executable(app, execname, ex, version,
                            args.set_default)


    #lg.warning("Could not register (yet?)")
