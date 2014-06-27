

import leip

import mad2.util
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

