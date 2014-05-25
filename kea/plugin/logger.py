
from collections import OrderedDict

from mad2 import madfile
import arrow
from lockfile import FileLock
import leip


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

    with FileLock('kea.log'):
        for i, info in enumerate(all_info):
            with open('kea.log', 'a') as F:
                F.write("-" * 80 + "\n")
                for i in info:
                    F.write("{}: ".format(i))
                    val = info[i]
                    if isinstance(val, list):
                        F.write("\n")
                        for lv in val:
                            F.write(' - {}\n'.format(to_str(lv)))
                    else:
                        F.write(" {}\n".format(to_str(val)))
