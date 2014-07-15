
import sys
import logging
import os
import pkg_resources
import shutil
import subprocess as sp

import arrow
import leip
from mad2.recrender import recrender

import kea.mad

lg = logging.getLogger(__name__)
#lg.setLevel(logging.DEBUG)

def get_last_provenance_data(madfile):
    if not 'provenance' in madfile:
        return None
    prokeys = sorted(madfile['provenance'].keys())
    lastkey = prokeys[-1]
    return madfile['provenance'][lastkey]


@leip.hook('post_fire', 5)
def check_output(app, info):
    """
    In the case of a non-zero return code - mark the output files
    """
    rc = info['returncode']
    if rc == 0:
        return

    for fn, fi in info['files'].items():
        if fi['category'] != 'output':
            continue
        filename = fi['filename']
        if os.path.exists(fi['filename']):
            move_to = os.path.join(
                os.path.dirname(filename),
                os.path.basename(filename) + '.kea_error')
            lg.warning("non zero RC - moving %s to %s", filename, move_to)
            shutil.move(filename, move_to)

            #change file data for this run
            fi['filename'] = move_to
            fi['madfile'] = kea.mad.get_madfile(move_to)

@leip.hook('pre_fire')
def check_run(app, info):

    all_output_ok = True
    no_outputfiles_seen = 0

    for name in info['files']:
        finf = info['files'][name]
        if finf['category'] != 'output':
            if not os.path.exists(finf['filename']):
                lg.warning("Cannot find %s file %s",
                           finf['category'], finf['filename'])
                exit(-1)
        else:
            no_outputfiles_seen += 1

            if not os.path.exists(finf['filename']):
                #output file does not exist - continue
                return

            #find output file - check if inputs have changed
            lg.debug("check output file %s", finf['filename'])
            prod = get_last_provenance_data(finf['madfile'])
            if not prod:
                #no provenance data for this outputfile - so - run
                return
            for fn in prod.get('derived_from', []):
                fnd = prod['derived_from'][fn]
                kea_name = fnd.get('kea_name', '')
                this_run_finf = info['files'].get(kea_name)
                current_sha1 = this_run_finf['madfile']['sha1sum']
                # print('derivedfrom ', fnd)
                # print('currentsha  ', current_sha1)
                # print('thisrunfinf ', this_run_finf)
                if fnd['sha1sum'] != current_sha1:
                    all_output_ok = False

    if no_outputfiles_seen > 1 and  all_output_ok:
        lg.warning("Skipping - no input files have changed")
        exit(0)


def annotate(app, info, fname, fdata):
    madapp = kea.mad.get_madapp()

    lg.debug("annotating '%s' output file: '%s'",
             fname, fdata['filename'])
    maf = fdata['madfile']
    maf.load() # make sure we're dealing with current data
    stamp = str(info['stop']).split('.')[0]
    prod = maf.mad['provenance.%s' % stamp]
    prod['tool_name'] = info['app_name']
    prod['tool_path'] = info['executable']
    prod['tool_version'] = info['app_version']
    prod['username'] = maf['username']
    prod['userid'] = maf['userid']
    prod['host'] = maf['host']
    prod['started_at_time'] = str(info['start'])
    prod['stopped_at_time'] = str(info['stop'])
    prod['runtime'] = str(info['stop'] - info['start'])
    prod['command_line'] = " ".join(info['cl'])
    prod['working_directory'] = info['cwd']
    prod['kea_command_line'] = info['full_cl']
    prod['kea_executable'] = info['kea_executable']
    prod['kea_version'] = pkg_resources.get_distribution("kea").version


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
        derf['kea_name'] = fn
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


@leip.hook('post_fire',100)
def add_provenance(app, info):
    lg.debug('Adding provenance data')

    rc = info['returncode']

    for fname in info['files']:
        lg.debug('  for file: %s', fname)
        fdata = info['files'][fname]
        if fdata['category'] != 'output':
            continue

        annotate(app, info, fname, fdata)
