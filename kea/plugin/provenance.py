
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

    lg.debug("Check if we need to run this command")

    no_files_notok = 0
    no_outputfiles_seen = 0

    output_files = {}
    all_filenames = set()

    #first, find all outputfiles
    #also - if an outputfile does not exists - decide to run right away
    #also - if an inputfile is not present - decide to run also
    #       it is not up to Kea to decide not to run in the case of an
    #       error - the tool may complain
    for name in info['files']:
        finf = info['files'][name]
        all_filenames.add(name)

        if not os.path.exists(finf['filename']):
            if finf['category'] == 'output':
                #output file does not exist - continue
                lg.debug("Output file %s does not exist - run", name)
                return
            else:
                #non output file - should have been present
                lg.warning("Cannot check provenance")
                lw.warning("%s/%s file: %s does not exist",
                           finf['category'], name, finf['filename'])
                return

        if finf['category'] == 'output':
            lg.debug("found output: %s", name)
            no_outputfiles_seen += 1
            output_files[name] = finf

    for output_name, output_finf in output_files.items():

        #check if the input/outputfile structure is consistent

        #find output file - check if inputs have changed
        lg.debug("check provenance of: %s", finf['filename'])
        out_prov = get_last_provenance_data(output_finf['madfile'])

        if not out_prov:
            lg.debug("no provenance data for output file %s", output_name)
            #no provenance data for this outputfile - so - run
            return

        if set(out_prov['derived_from'].keys()) != all_filenames:
            #provenance recorded filenames do not match this run's filenames
            #hence - we shall run the tool:
            lg.debug("provenance data of %s does not match current run",
                     output_name)
            return

        #print(out_prov.pretty())
        for fn in out_prov.get('derived_from', []):
            lg.debug(" - prov check %s", fn)
            out_prov_file = out_prov['derived_from'][fn]
            fn_finf = info['files'].get(fn)
            current_sha1 = fn_finf['madfile']['sha1sum']
            lg.debug(' - current sha1       : %s', current_sha1)
            lg.debug(' - prov recorded sha1 : %s', out_prov_file['sha1sum'])
            if out_prov_file['sha1sum'] != current_sha1:
                lg.debug(" - sha1sum mismatch!")
                no_files_notok += 1

    if no_outputfiles_seen > 0 and  no_files_notok == 0:
        lg.warning("Skipping - provenance data indicates that this is a rerun")
        info['skip'] = True


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

        #store all recorded files
        derf = prod['derived_from'][fn]

        derf['filename'] = fdmaf['fullpath']
        derf['category'] = fd['category']
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
