

import copy
import logging
import os
import subprocess as sp
import sys

import fantail
from leip import set_local_config


lg = logging.getLogger(__name__)


def get_tool_conf(app, name, version='default'):

    data = copy.copy(app.conf['group.default'])
    tool_data = copy.copy(app.conf.get('app.{}'.format(name), fantail.Fantail()))
    group = tool_data.get('group')

    if not group is None:
        group_data = app.conf['group.{}'.format(group)]
        if group_data:
            data.update(group_data)

    data.update(tool_data)

    if version is 'default':
        version = tool_data.get('default_version', None)

    if (not version is None) and (not version in tool_data['versions']):
        candidates = []
        for v in tool_data['versions']:
            fullv =  tool_data['versions'][v]['version']
            if v in fullv:
                candidates.append(v)

    if not version is None:
        version_data = tool_data['versions.{}'.format(version)]
        data.update(version_data)
        data['version_key'] = version

    return data


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
        yield os.path.abspath(executable)

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

                yield os.path.abspath(line)


def create_kea_link(app, name):
    """
    """
    base = app.conf['bin_path']
    linkpath = os.path.expanduser(os.path.join(base, name))
    lg.debug("checking: %s", linkpath)
    if os.path.lexists(linkpath):
        lg.debug("path exists: %s", linkpath)
        os.unlink(linkpath)


    keapath = sys.argv[0]
    lg.info("creating link from %s", linkpath)
    lg.info(" to: %s", keapath)
    os.symlink(keapath, linkpath)

def register_executable(app, name, executable, version, is_default=None):
    """
    Register an executable
    """

    allversions = list('abcdefghijklmnopqrstuvwxyz123456789')

    is_first_version = True

    version_key = 'a'

    if app.conf.has_key('app.{}.versions'.format(name)):
        is_first_version = False
        for k in app.conf['app.{}.versions'.format(name)]:
            vinf = app.conf['app.{}.versions.{}'\
                            .format(name, k)]
            if vinf['executable'] == executable:
                lg.warning("Executable is already registered - overwriting")
                version_key = k
                break

            #registered - we do not want to use this key
            allversions.remove(k)

        version_key = allversions[0]

    if is_default == False:
        if is_first_version:
            lg.debug("First version of %s - setting to default", name)
            is_default = True
        else:
            lg.debug("Other version of %s present - not setting default", name)
            is_default = False

    lg.warning("register %s - %s - %s - %s", name, executable,
             version_key, version)

    if is_default:
        lg.warning("Set version %s as default", version_key)
        set_local_config(app, 'app.{}.default_version'.format(name),
                         version_key)

    basekey = 'app.{}.versions.{}'.format(name, version_key)
    lg.debug("register to: %s", basekey)

    set_local_config(app, '{}.executable'.format(basekey), executable)
    set_local_config(app, '{}.version'.format(basekey), version)

    create_kea_link(app, name)
