
import leip
import sys
import logging
import pkg_resources
import subprocess as sp


import arrow

from mad2.recrender import recrender

import kea.mad

lg = logging.getLogger(__name__)
#lg.setLevel(logging.DEBUG)


def annotate(app, info, fname, fdata):
    madapp = kea.mad.get_madapp()

    lg.debug("annotating '%s' output file: '%s'",
             fname, fdata['filename'])
    maf = fdata['madfile']
    maf.load() # make sure we're dealing with current data
    stamp = str(info['stop']).split('.')[0]
    prod = maf.mad['provenance.%s' % stamp]
    prod['created_by.tool_name'] = info['app_name']
    prod['created_by.tool_path'] = info['executable']
    prod['created_by.tool_version'] = info['app_version']
    prod['created_by.username'] = maf['username']
    prod['created_by.userid'] = maf['userid']
    prod['host'] = maf['host']
    prod['started_at_time'] = info['start'].datetime
    prod['stopped_at_time'] = info['stop'].datetime
    prod['command_line'] = " ".join(info['cl'])
    prod['cwd'] = info['cwd']
    prod['kea.command_line'] = info['full_cl']
    prod['kea.executable'] = info['kea_executable']
    prod['kea.version'] = pkg_resources.get_distribution("kea").version

    for fn in info['files']:
        fd = info['files'][fn]
        fdmaf = fd['madfile']
        if fd['category'] == 'output':
            continue
        if fd['category'] == 'input':
            derf = prod['derived_from'][fn]
        elif fd['category'] == 'used':
            derf = prod['used'][fn]
        derf['filename'] = fdmaf['fullpath']
        derf['sha1sum'] = fdmaf['sha1sum']
        derf['host'] = fdmaf['host']

        #heritable data
        if not fd['category'] == 'input':
            continue
        for k in fdmaf.mad:
            kinfo = madapp.conf['keywords'][k]
            if not kinfo.get('propagate', False):
                continue
            maf[k] = fdmaf.mad[k]

    maf.save()

@leip.hook('post_fire')
def add_provenance(app, info):
    lg.debug('Adding provenance data')

    for fname in info['files']:
        fdata = info['files'][fname]
        if fdata['category'] != 'output':
            continue

        annotate(app, info, fname, fdata)
