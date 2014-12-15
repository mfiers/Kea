

import calendar
import copy
from datetime import datetime, timedelta
import logging
import os
import subprocess as sp
import sys

import fantail
import humanize
from leip import set_local_config

lg = logging.getLogger(__name__)


# Nicely format run log stats
FSIZEKEYS = ["ps_meminfo_max_rss", "ps_meminfo_max_vms",
             "ps_sys_swap_free", "ps_sys_swap_sin",
             "ps_sys_swap_sout", "ps_sys_swap_total",
             "ps_sys_swap_used", "ps_sys_vmem_active",
             "ps_sys_vmem_available", "ps_sys_vmem_buffers",
             "ps_sys_vmem_cached", "ps_sys_vmem_free",
             "ps_sys_vmem_inactive", "ps_sys_vmem_total",
             "ps_sys_vmem_used"]


def nicetime(t):
    """
    fomat time, assuming t is in utc
    """

    timestamp = calendar.timegm(t.timetuple())
    loct = datetime.fromtimestamp(timestamp)
    assert t.resolution >= timedelta(microseconds=1)
    loct.replace(microsecond=t.microsecond)
    return '{} ({})'.format(humanize.naturaltime(loct), t)

    
def make_pretty_kv(k, v):
    if k in ['cl', 'template_cl']:
        v = " ".join(v)
            
    if v is None:
        return ""
    elif str(v).strip() == "":
        return ""
    if k in FSIZEKEYS:
        return "{} ({})".format(humanize.naturalsize(v), v)
    elif k in ['start', 'stop']:
        return nicetime(v)
    elif k == 'runtime':
        return '{}s ({})'.format(humanize.intword(v), v)
    elif k.endswith('_percent'):
        return '{}%'.format(v)
    else:
        return str(v)

def make_pretty_kv_html(k, v):
    
    if k in ['cl', 'template_cl']:
        return (
            '<td colspan="2">' +
            '<span style="font-family:Lucida Console,Bitstream Vera Sans Mono,Courier New,monospace;">' +
            " ".join(v) +
            "</span></td>" )
            
    if v is None:
        return '<td colspan="2"></td>'
    elif str(v).strip() == "":
        return '<td colspan="2"></td>'
        
    if k in FSIZEKEYS:
        return "<td>{}</td><td>{}</td>".format(humanize.naturalsize(v), v)
    elif k in ['start', 'stop']:
        return '<td colspan="2">{}</td>'.format(v)
    elif k == 'runtime':
        return "<td>{}</td><td>{}</td>".format(humanize.intword(v), v)
    elif k.endswith('_percent'):
        return '<td colspan="2">{}%</td>'.format(v)
    else:
        return '<td colspan="2">{}</td>'.format(v)

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
