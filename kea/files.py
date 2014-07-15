
import logging

from mad2.recrender import recrender

import kea.mad


lg = logging.getLogger(__name__)


def register_file(info, name, category, filename):
    lg.debug("set %s as %s file: '%s'", filename, category, name)
    madfile = kea.mad.get_madfile(filename)

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
