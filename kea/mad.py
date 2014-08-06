

import leip
import logging

import mad2.util


lg = logging.getLogger(__name__)


MADAPP = None

def get_madapp():
    global MADAPP

    if MADAPP is None:
        app = leip.app('mad2')
        MADAPP = app
    return MADAPP

def get_madfile(filename):
    mapp = get_madapp()
    return mad2.util.get_mad_file(mapp, filename)

def finish():
    lg.debug("running mad finish hook")
    mapp = get_madapp()
    mapp.run_hook('finish')
