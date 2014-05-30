
from collections import OrderedDict
import logging

import arrow
from mad2 import madfile
import leip
from lockfile import FileLock

lg = logging.getLogger(__name__)

def to_str(s):
    if isinstance(s, madfile.MadFile):
        if 'sha1sum' in s:
            return '{} (sha1: {})'.format(s['inputfile'], s['sha1sum'])
        else:
            return '{}'.format(s['inputfile'])
    else:
        return str(s)

@leip.hook('post_run')
def log_cl(app, all_info):

    try:
        with FileLock('kea.log'):
            for i, info in enumerate(all_info):
                with open('kea.log', 'a') as F:
                    F.write("-" * 80 + "\n")
                    for i in info:
                        F.write("{}: ".format(i))
                        val = info[i]
                        if i == 'cl':
                            F.write(" ".join(val) + "\n")
                        elif isinstance(val, list):
                            F.write("\n")
                            for lv in val:
                                F.write(' - {}\n'.format(to_str(lv)))
                            else:
                                F.write(" {}\n".format(to_str(val)))
    except:
        lg.warning("Cannot write to log file")
