
import os
import re
import sys
import shlex
import subprocess as sp

import leip

from kea import Kea


def dispatch():
    """
    Run the MadMax app
    """
    app.run()

#check if there is a kea command

command = None


if 'KEA_LAST_HIST' in os.environ:
    _orco = os.environ['KEA_LAST_HIST']
    _orco = re.sub(r'^ *[0-9]+ +', '', _orco)
    sys.argv = shlex.split(_orco)


for i in range(1, len(sys.argv)):
    if not sys.argv[i].startswith('-'):
        command = sys.argv[i]
        break

if command in ['conf', 'snipset', 'jobset', 'js', 'run', 'jobrun', 'jr',
               'list_executors', 'tra', 'mng']:
    app = leip.app('kea', partial_parse = True)
else:
    app = Kea()
