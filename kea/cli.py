
import os
import sys

import leip

from kea import Kea


def dispatch():
    """
    Run the MadMax app
    """
    app.run()

#check if there is a kea command

command = None
for i in range(1, len(sys.argv)):
    if not sys.argv[i].startswith('-'):
        command = sys.argv[i]
        break

if command in ['conf', 'snipset', 'jobset', 'js', 'run']:
    app = leip.app('kea', partial_parse = True)
else:
    app = Kea()
