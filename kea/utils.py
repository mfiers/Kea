

import logging
import os
import subprocess as sp

lg = logging.getLogger(__name__)


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
