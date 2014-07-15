import copy
import logging
import sys

import leip
from mad2.recrender import recrender

import kea.files

lg = logging.getLogger(__name__)


MADAPP = None


def flag_find(lst, flg, app):
    if not flg or not flg in lst:
        return []

    p_last = 0
    p = lst.index(flg)

    rv = []
    while p != -1:
        value = lst[p+1]
        madfile = app.get_madfile(value)
        rv.append(madfile)
        p_last = p
        try:
            p = lst.index(flg, p_last+1)
        except ValueError:
            break
    return rv


def find_input_file(app, info):
    ff_conf = app.conf.get('filefind')

    if not ff_conf:
        return

    iff = ff_conf['input_file_flag']
    off = ff_conf['output_file_flag']

    if not 'input_files' in info:
        info['input_files'] = []
    if not 'output_files' in info:
        info['output_files'] = []


    info['input_files'].extend(flag_find(sys.argv, iff, app))
    info['output_files'].extend(flag_find(sys.argv, off, app))


@leip.hook('pre_fire')
def hook_pre_run(app, info):

    ffc = app.conf.get('filefind')

    if not ffc:
        return

    #determine category
    def get_category(finf):
        if 'category' in finf:
            return finf['category']
        elif name.startswith('input'):
            return 'input'
        elif name.startswith('output'):
            return 'output'
        else:
            return 'used'

    #find all files - except of type render
    for name in ffc:
        finf = ffc[name]

        if 'position' in finf:
            pos = finf['position']

            if len(info['cl']) <= pos:
                lg.warning("Cannot assign file %s - cl too short", name)
                continue

            kea.files.register_file(
                info, name,
                get_category(finf),
                info['cl'][pos])

    #find all files to be rendered
    for name in ffc:
        finf = ffc[name]

        if 'render' in finf:
            template = finf['render']
            filename = recrender(template, info)
            if '{' in filename:
                lg.warning("Cannot render file %s - '%s'", name, template)
                continue
            kea.files.register_file(
                info, name, get_category(finf), filename)


@leip.hook('post_fire', 1)
def check_sha1sum(app, info):
    if not 'files' in info:
        return
    for f in info['files']:
        mf = info['files'][f]['madfile']
        from mad2.hash import get_or_create_sha1sum
        mf['sha1sum'] = get_or_create_sha1sum(mf['inputfile'])
