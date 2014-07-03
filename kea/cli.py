
import os
import copy
import sys

import leip

from kea import Kea

def dispatch():
    """
    Run the MadMax app
    """
    app.run()


kea_conf = leip.get_config('kea')
prefix = kea_conf['arg_prefix']
thisapp = os.path.basename(sys.argv[0])

if thisapp == 'kea':
    #calling the kea tool directly:
    app = leip.app(name='kea')
else:
    #calling a tool that links to kea - Kea wrapper mode:
    # if prefix = '+', the first argument starts with '++'
    if len(sys.argv) > 1 and sys.argv[1][:2] == prefix + prefix:
        cmd = sys.argv[1][2:]
        #replace sys.argv &
        sys.argv = ['kea', cmd, '-a', thisapp] + sys.argv[2:]
        app = leip.app(name='kea')
    else:
        app = Kea()

