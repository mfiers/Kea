
import os
import sys

import leip

from kea import Kea


def dispatch():
    """
    Run the MadMax app
    """
    app.run()


thisapp = os.path.basename(sys.argv[0])

if thisapp == 'kea':
    #calling the kea tool directly:
    app = leip.app(name='Kea')
else:
    #calling a tool that links to kea - Kea wrapper mode:
    app = Kea()
