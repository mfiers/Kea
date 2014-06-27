
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
                        val = info[i]
                        if val is None:
                            #do not print any key/vals where the value
                            #is None
                            continue

                        F.write("{}: ".format(i))
                        if i == 'cl':
                            F.write(" ".join(val) + "\n")
                        elif i == 'files':
                            F.write("\n")
                            for fi in val:
                                fim = val[fi]['madfile']
                                fic = val[fi]['category']
                                F.write(" - %s:\n" % fi)
                                F.write("     path: %s\n" % fim['fullpath'])
                                F.write("     sha1sum: %s\n" % fim['sha1sum'])
                                F.write("     category: %s\n" % fic)



                        elif isinstance(val, list):
                            F.write("\n")
                            for lv in val:
                                F.write(' - {}\n'.format(to_str(lv)))
                        else:
                            F.write(" {}\n".format(to_str(val)))

    except:
        lg.warning("Cannot write to Kea log file")
