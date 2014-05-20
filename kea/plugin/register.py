#tools to help register & identify commands

import logging

import leip

from kea.utils import find_executable, register_executable

lg = logging.getLogger(__name__)


@leip.arg('-V', '--version', help='version number')
@leip.arg('name', help='executable name to register')
@leip.command
def register(app, args):

    execname = args.name
    if '/' in execname:
        execname = execname.split('/')[-1]

    lg.debug("register %s", execname)

    execs = list(find_executable(args.name))
    no_execs = len(execs)

    if no_execs == 1 and args.version:
        register_executable(app, execname, execs[0], args.version)
        return

    lg.warning("Could not register (yet?)")
    # for executable in find_executable(args.name):
    #     lg.debug("Discovered: %s", executable)


    # if os.path.isfile(name):
    #     executable = name
    # else


