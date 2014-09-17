
import logging
import os

from mad2.recrender import recrender

import kea.mad
from kea.utils import message

lg = logging.getLogger(__name__)
#lg.setLevel(logging.DEBUG)

def register_file(info, name, category, filename):
    madfile = kea.mad.get_madfile(filename)
    message('info', 'registered {}/{}: {}', category, name, filename)
    info['files'][name]['filename'] = filename
    info['files'][name]['madfile'] = madfile
    info['files'][name]['category'] = category


def set_input(info, filename):
    lg.debug("set %s as input file", filename)
    madfile = kea.mad.get_madfile(filename)
    info['files']['input']['filename'] = filename
    info['files']['input']['madfile'] = madfile
    info['files']['input']['category'] = 'input'


def set_output(info, filename):
    lg.debug("set %s as output file", filename)
    madfile = kea.mad.get_madfile(filename)
    info['files']['output']['filename'] = filename
    info['files']['output']['madfile'] = madfile
    info['files']['output']['category'] = 'output'


def assign_on_position(info, name, category, pos):
    filename = info['cl'][1]
    madfile = kea.mad.get_madfile(filename)
    info['files'][name]['madfile'] = madfile
    info['files'][name]['category'] = category


def assign_filename(info, name, category, filename):
    madfile = kea.mad.get_madfile(filename)
    info['files'][name]['madfile'] = madfile
    info['files'][name]['category'] = category


def flag_find(lst, flg):
    if not flg or not flg in lst:
        lg.debug("Cannot assign find file with flag %s", flg)
        return None

    p = lst.index(flg)
    if p+1 >= len(lst):
        lg.warning("Cannot assign find file with flag %s (cl too short)", flg)
        return None
    return lst[p+1]


def flag_find_list(lst, flg):

    if not flg or not flg in lst:
        lg.debug("Cannot assign find file with flag %s", flg)
        return set()

    rv = []
    for i, f in enumerate(lst[:-1]):
        lg.debug('%s %s %s', f, f == flg, lst[i+1])
        if f == flg:
            rv.append(lst[i+1])
    return rv

#
