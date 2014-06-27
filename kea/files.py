

import kea.mad

def set_input(info, filename):
    madfile = kea.mad.get_madfile(filename)
    name = 'input'
    info['files'][name]['filename'] = filename
    info['files'][name]['madfile'] = madfile
    info['files'][name]['category'] = 'input'


def set_output(info, filename):
    madfile = kea.mad.get_madfile(filename)
    name = 'output'
    print filename
    info['files'][name]['filename'] = filename
    info['files'][name]['madfile'] = madfile
    info['files'][name]['category'] = 'output'


def assign_on_position(info, name, category, pos):
    filename = info['cl'][1]
    madfile = kea.mad.get_madfile(filename)
    info['files'][name]['madfile'] = madfile
    info['files'][name]['category'] = category

def assign_filename(info, name, category, filename):
    madfile = kea.mad.get_madfile(filename)
    info['files'][name]['madfile'] = madfile
    info['files'][name]['category'] = category
