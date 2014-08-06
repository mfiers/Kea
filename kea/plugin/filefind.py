import copy
import logging
import sys

import leip
from mad2.recrender import recrender

import kea.files

lg = logging.getLogger(__name__)
lg.setLevel(logging.DEBUG)

MADAPP = None


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

    processed = []
    #find all files - except of type render
    for name in ffc:
        finf = ffc[name]
        if 'position' in finf:
            pos = finf['position']
            if len(info['cl']) <= pos:
                lg.info("Cannot assign file %s - cl too short", name)
                continue

            filename = info['cl'][pos]

        elif 'flag' in finf:
            filename = kea.files.flag_find(info['cl'], finf['flag'])

        elif 'pipe' in finf:
            pipe = finf['pipe']
            lg.debug("output is send to %s", pipe)
            filename = info.get('{}_file'.format(pipe))
            if filename is None:
                lg.warning("Tool output is send to {}".format(pipe))
                lg.warning("Cannot capture provenance data")
                lg.warning("maybe use: {0}-e / {0}-o".format(
                              app.conf['arg_prefix']))
                continue
        else:
            continue

        if 'render' in finf:
            template = finf['render']
            filename = recrender(template, {'this' : filename})

        processed.append(name)
        if not filename is None:
            kea.files.register_file(
                info, name, get_category(finf), filename)


    #find all files with only a render field
    for name in ffc:
        finf = ffc[name]
        if name in processed: continue
        if not 'render' in finf: continue


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
        from mad2.hash import get_sha1sum_mad
        get_sha1sum_mad(mf)
