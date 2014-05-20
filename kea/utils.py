

import logging
import os
import subprocess as sp

from leip import set_local_config

lg = logging.getLogger(__name__)


def get_tool_conf(app, name):
    tool_data = app.conf['app.{}'.format(name)]
    default_group = app.conf['group.default']
   # if tool_data


def is_kea(fname):

    with open(fname) as F:
        start = F.read(1000)

    fline = start.strip().split("\n")[0]
    if not fline.startswith('#!'):
        lg.debug(" - not a shell script - not kea")
        return False

    if not 'python' in fline:
        lg.debug(" - not a python script - not kea")
        return False

    if 'load_entry_point' in start and \
            'Kea==' in start:
        lg.debug(" - looks like a link to the kea entry point script - kea")
        return True

    if 'import Kea' in start or \
            'from Kea import' in start:
        lg.debug(" - looks like custom Kea script - kea")
        return True

    lg.debug(" - does not look like a kea script")
    return False


def find_executable(name):

    # check if this is a single executable:
    if os.path.isfile(name) and os.access(name, os.X_OK):
        executable = name
        name = os.path.basename(executable)
        yield executable

    else:

        # no? try to use the 'which' tool

        # no '/' allowed anymore
        if '/' in name:
            raise IOError(name)

        P = sp.Popen(['which', '-a', name], stdout=sp.PIPE)

        out, err = P.communicate()

        for line in out.strip().split("\n"):
            lg.debug("check %s", line)
            if not is_kea(line):
                lg.debug("%s is not a kea file", line)

                yield line


def register_executable(app, name, executable, version, is_default=None):
    """
    Register an executable
    """

    is_first_version = True

    if app.conf.has_key('app.{}.version'.format(name)):
        is_first_version = False

    if is_default is None:
        if is_first_version:
            lg.debug("First versrion of %s - setting to default", name)
            is_default = True
        else:
            lg.debug("Other version of %s present - not setting default", name)
            is_default = False

    version_key = version.replace('.', '_')

    if is_default:
        set_local_config(app, 'app.{}.default_version'.format(name),
                         version_key)

    lg.debug("register %s - %s - %s - %s", name, executable,
             version_key, version)

    basekey = 'app.{}.version.{}'.format(name, version_key)
    lg.debug("register to: %s", basekey)

    set_local_config(app, '{}.executable'.format(basekey), executable)
    set_local_config(app, '{}.version'.format(basekey), version)
