import copy
from datetime import datetime
from collections import defaultdict
import gzip
import hashlib
from itertools import chain
import logging
import os

from bson.objectid import ObjectId

#import gnupg

import leip
from termcolor import cprint
import yaml

from kea.plugin.logger import dictprint
from kea.cl_generator import render_parameters
import kea.utils

lg = logging.getLogger(__name__)

madlog = logging.getLogger("mad2")
#madlog.setLevel(logging.DEBUG)

MADAPP = None       # contains mad applicaton object


@leip.hook('pre_argparse')
def transaction_arg_define(app):
    tragroup = app.parser.add_argument_group('Transaction plugin')
    tragroup.add_argument('--st', dest = 'save_transation_to_disk',
                          help='save transaction to disk',
                          action='store_true')
    tragroup.add_argument('-B', '--always_run',
                          help='do not skip because of a transaction match',
                          action='store_true')
    tragroup.add_argument('--utd', dest='up_to_date',
                          help='assume all files are up to date if they exists',
                          action='store_true')

    tragroup.add_argument('--ss', dest='skip_save',
                          help='create a transcation for skipped jobs',
                          action='store_true')

    tragroup.add_argument('--tfi', dest='transact_file_in', action='append',
                          help='transcription input file', nargs=2)
    tragroup.add_argument('--tfo', dest='transact_file_out', action='append',
                          help='transcription output file', nargs=2)
    tragroup.add_argument('--tfu', dest='transact_file_use', action='append',
                          help='transcription used file', nargs=2)
    tragroup.add_argument('--pt', dest='print_transaction', action='store_true',
                          help='print a transaction summary to screen')



def hash(o):
    o = str(o)
    h = hashlib.sha256()
    h.update(o.encode('utf-8'))
    return h.hexdigest()


# thanks: https://stackoverflow.com/questions/5884066/hashing-a-python-dictionary
def make_hash(o):
  """
  Makes a hash from a dictionary, list, tuple or set to any level, that contains
  only other hashable types (including any lists, tuples, sets, and
  dictionaries).
  """

  if isinstance(o, (set, tuple, list)):
    return tuple([make_hash(e) for e in o])

  elif not isinstance(o, dict):
    return hash(o)

  new_o = copy.deepcopy(o)
  for k, v in list(new_o.items()):
    new_o[k] = make_hash(v)

  return hash(tuple(frozenset(sorted(new_o.items()))))


def get_coll_transaction(conf):

    mconf = conf['plugin.transaction']

    c2t_name = 'checksum2transaction'
    tra_name = 'transaction'

    c2t = kea.utils.get_mongo_collection(conf, c2t_name)

    if c2t is None:
        #mongo is not configured
        return None, None

    tra = kea.utils.get_mongo_collection(conf, tra_name)

    if tra is None or c2t is None:  #mongo not configured?
        return None, None

    tra.ensure_index('timestamp')
    tra.ensure_index('transaction_id')

    c2t.ensure_index('application')
    c2t.ensure_index('timestamp')
    c2t.ensure_index('category')
    c2t.ensure_index('application')
    c2t.ensure_index('file_sha1sum')
    c2t.ensure_index('category')

    return tra, c2t


def get_madapp():
    global MADAPP
    if MADAPP is None:
        MADAPP = leip.app(name='mad2', disable_commands=True)
    return MADAPP


@leip.hook('post_fire')
def mad_register_file(app, jinf):

    from mad2.util import get_mad_file

    madapp = get_madapp()

    if jinf.get('deferred'):
        return
    if jinf.get('dummy'):
        return


    for cat in ['input', 'output', 'database', 'use']:
        for name, fdata in list(jinf.get(cat, {}).items()):

            filename = fdata['path']
            if not os.path.exists(filename):
                continue

            madfile = get_mad_file(madapp, filename)
            try:
                fdata['sha1sum'] = str(madfile['sha1sum'])
            except:
                lg.debug("error getting mad/sha1sum for %s", filename)
                continue



@leip.hook('pre_fire', 1000)
def check_transaction(app, jinf):

    #first check if there are more in/output files defined...
    for cat, filelist in [['input', app.args.transact_file_in],
                      ['output', app.args.transact_file_out],
                      ['use', app.args.transact_file_use]]:
        if not filelist:
            continue
        for name, pattern in filelist:
            fname = render_parameters(pattern, jinf['param'])
            kea.utils.set_info_file(jinf, cat, name, fname)

    if app.args.print_transaction:
        for cat in ['input', 'output', 'use']:
            files = jinf.get(cat, {})
            if len(files) == 0:
                continue
            filekeys = sorted(files.keys())
            for fk in filekeys:
                cprint('#', end=' ')
                cprint(fk, 'cyan', end=' (')
                cprint(cat, 'green', end=') ')
                cprint(files[fk]['path'], 'yellow')

#    lg.setLevel(logging.DEBUG)
    lg.debug("check transaction")

    madfiles = {}
    mng_tra, mng_c2t = get_coll_transaction(app.conf)

    if mng_tra is mng_c2t is None:  # mongo not configured?
        lg.debug('no mongo db - no transcation check')
        return

    from mad2.util import get_mad_file

    if not 'output' in jinf:
        #no outputfiles - can't really check if we need to rerun
        lg.debug("no outputfiles - nothing to check")
        return

    madapp = get_madapp()

    all_outputfiles_exist = True
    #check if all output files exist
    for outfile, outfile_data in list(jinf.get('output', {}).items()):
        filename = outfile_data['path']
        if not os.path.exists(filename):
            all_outputfiles_exist = False
        else:
            madfile = get_mad_file(madapp, filename)
            madfiles[filename] = madfile

    if all_outputfiles_exist and app.args.up_to_date:
        lg.debug("files exists - assume up to date")
        jinf['skip'] = True
        lg.info("Assuming up to date -> Skipping")
        return

    if not all_outputfiles_exist:
        lg.debug("not all outputfiles exists - returning")
        return

    transact_list = defaultdict(lambda: set())

    for infile, infile_data in chain(list(jinf.get('input', {}).items()),
                                     list(jinf.get('database', {}).items()),
                                     list(jinf.get('use', {}).items())):
        filename = infile_data['path']
        madfile = get_mad_file(madapp, filename)
        query = {'name': infile,
                 'application': app.name,
                 'file_sha1sum': madfile['sha1sum']}
        for rec in mng_c2t.find(query):
            transact_list[infile].add(rec['transaction_id'])


    if len(transact_list) > 0:
        translist = list(transact_list.values())[0]
        for t in transact_list:
            translist &= transact_list[t]
    else:
        lg.debug("no candidate transaction found based on input file sha1sums")
        return

#    lg.setLevel(logging.DEBUG)
    lg.debug("Found %d %s transactions with the same inputfiles", len(translist), app.name)

    one_transaction_matches = False
    matching_transcations = []

    for traid in translist:
        lg.debug("checking transaction %s", traid)
        tra = mng_tra.find_one({'transaction_id': traid})
        trarec = tra['transaction']

        output_matches = True
        #check if output files match
        for outfile, outfile_data in list(jinf.get('output', {}).items()):
            filename = outfile_data['path']
            if not os.path.exists(filename):
                output_matches = False
                break

            if not 'output' in trarec:
                output_matches = False
                break

            if not outfile in trarec['output']:
                output_matches = False
                break

            if 'sha1sum' not in madfiles[filename]:
                output_matches = False
                break

            if madfiles[filename]['sha1sum'] != trarec['output'][outfile].get('sha1sum'):
                output_matches = False
                break

            lg.debug("match %s (%s)", filename, madfiles[filename]['sha1sum'])

        if not output_matches:
            lg.debug("no transaction match")
            continue

        lg.debug('transaction match!')
        one_transaction_matches = True
        matching_transcations.append(tra)


    if one_transaction_matches and (not app.args.always_run):
        if app.args.print_transaction:
            cprint("# Transcation Match -- skipping job", 'green')
            cprint("# No transcations matching:", end=" ")
            cprint(str(len(matching_transcations)), 'yellow')
            t = matching_transcations[0]
            for t in matching_transcations:
                cprint("# transcation id:", end=" ")
                cprint(t['transaction_id'], 'green')
                cprint("#           date:", end=" ")
                cprint(t['timestamp'], 'blue')

        else:
            lg.warning("Transaction match (%d) -> Skipping job", len(matching_transcations))
            lg.debug("Transcation %s", matching_transcations[0])

        jinf['skip'] = True



@leip.hook('post_fire', 1000)
def create_transaction(app, jinf):
    #clean jinf a little

    if jinf.get('deferred'):
        return

    dat = yaml.load(yaml.safe_dump(dict(jinf), default_flow_style=False))

    if not ( (app.args.skip_save and jinf['status'] == 'skipped') or \
             (jinf['status'] == 'success') ):
        lg.info("Not storing transaction (status:%s)", jinf['status'])
        return

    tra = {}
    tra['transaction'] = dat
    tra['timestamp'] = datetime.utcnow().isoformat()
    tra['transaction_id'] = make_hash(dat)

    #attempt signature
    # gpg = gnupg.GPG(use_agent=True)
    # key = gpg.list_keys()[0]
    # tra['signature'] = str(gpg.sign(tra['sha256'], detach=True))
    # tra['signature_id'] = key['uids'][0]
    # tra['signature_key'] = key['keyid']
    #print(gpg)

    with open('kea.transaction', 'ab') as F:
        F.write(b'---\n')
        F.write(yaml.safe_dump(tra, default_flow_style=False).encode('UTF-8'))

    # if app.args.save_transation_to_disk:
    #     filename = "{}.{}.{}.transaction".format(
    #         app.name, jinf['run']['uid'], jinf['run']['no'])
    #     with gzip.open(filename, 'w') as F:
    #         F.write(yaml.safe_dump(tra, default_flow_style=False).encode('UTF-8'))

    mc_tra, mc_c2t = get_coll_transaction(app.conf)
    if mc_tra is None:
        #no mongo database - return
        return

    if mc_tra is None:
        return #mongo is not configured

    tra_recid = str(mc_tra.insert(tra))

    for cat in ['input', 'output', 'database', 'use']:
        if not cat in dat:
            continue
        for fname in dat[cat]:
            fdat = dat[cat][fname]
            rec = dict(transaction_record_id = tra_recid,
                       transaction_id = tra['transaction_id'],
                       category = cat,
                       timestamp = datetime.utcnow(),
                       application = app.name,
                       name = fname,
                       filename = os.path.basename(fdat['path']),
                       file_sha1sum = fdat['sha1sum'])
            mc_c2t.insert(rec)


@leip.subparser
def tra(app, args):
    pass

@leip.arg('output')
@leip.arg('file')
@leip.subcommand(tra, 'network')
def build_network(app, args):

    import networkx as nx
    from mad2.util import get_mad_file

    mc_tra, mc_c2t = get_coll_transaction(app.conf)

    filename = args.file
    madapp = get_madapp()
    madfile = get_mad_file(madapp, filename)
    sha1sum = madfile['sha1sum']
    G = nx.DiGraph()

    tra_seen = set()
    sha_seen = set()

    def _add_transaction(tra_id):
        if tra_id in tra_seen:
            return

        tra_seen.add(tra_id)

        trarec = mc_tra.find_one(dict(_id=ObjectId(tra_id)))
        traobj = trarec['transaction']
        tra_cwd = traobj['cwd']
        tra_name = os.path.basename(traobj['executable'])

        G.add_node(tra_id,
                   name=tra_name,
                   cwd=tra_cwd,
                   type='transaction',
                   host=traobj.get('sys', {}).get('host', 'unknown'),
                   status=traobj.get('status', 'unknown'))

        for cat in ['input', 'database', 'use', 'output']:
            if cat not in traobj:
                continue
            for fn, fo in list(traobj[cat].items()):
                if not 'sha1sum' in fo:
                    return
                fosh = fo['sha1sum']
                name = os.path.basename(fo['path'])

                G.add_node(fosh,
                           name=name,
                           type='file',
                           path=os.path.join(tra_cwd, fo['path']))

                if cat == 'output':
                    G.add_edge(tra_id, fosh, type=cat)
                else:
                    G.add_edge(fosh, tra_id, type=cat)
                    _add_sha1sum(fosh)

    def _add_sha1sum(sha1sum):
        if sha1sum in sha_seen:
            return
        sha_seen.add(sha1sum)

        if False:
            for rec in mc_c2t.find({'file_sha1sum': sha1sum}):
                _add_transaction(rec['transaction_record_id'])
        else:
            latest_rec = None
            latest_date = None
            hits =mc_c2t.find(dict(file_sha1sum=sha1sum,
                                  category='output'),
                             sort=[('timestamp',-1)],
                             limit=1)
            for hit in hits:
                _add_transaction(hit['transaction_record_id'])
                break

    _add_sha1sum(sha1sum)
    print(len(G.nodes()))
    nx.write_graphml(G, args.output)


@leip.arg("file")
@leip.subcommand(tra, "find")
def find_transactions(app, args):
    from mad2.util import get_mad_file

    filename = args.file
    madapp = get_madapp()
    madfile = get_mad_file(madapp, filename)
    sha1sum = madfile['sha1sum']

    mongo_tra, mongo_c2t = get_coll_transaction(app.conf)

    for rec in mongo_c2t.find({'file_sha1sum': sha1sum}):
        tract = mongo_tra.find_one(
            {'_id': ObjectId(rec['transaction_record_id'])})
        jinf = tract['transaction']

        cprint("# TRANSACTION: ", end="")
        cprint(tract['transaction_id'], "green")
        for cat in ['input', 'database', 'use', 'output']:
            if not cat in jinf:
                continue
            cprint("Category: ", end="")
            cprint("{:10}".format(cat), "yellow")
            for fk, fd in sorted(jinf[cat].items()):
                fdp = fd['path']
                s1s = fd['sha1sum']
                if s1s == sha1sum:
                    cprint(" * ", 'yellow', end="")
                else:
                    cprint(" - ", 'blue', end="")

                cprint("{}".format(fk), "blue", end=":")

                if os.path.exists(fdp):
                    cprint(fd['path'], "green")
                else:
                    cprint(fd['path'], "red")

@leip.arg('transaction_file')
@leip.subcommand(tra, 'validate')
def validate_transaction(app, args):
    trafile= args.transaction_file
    with gzip.open(trafile) as F:
        tra = yaml.load(F)
    hatra = make_hash(tra['transaction'])

    if hatra == tra['transaction_id']:
        print("{} ok".format(trafile))
    else:
        print("{} FAIL".format(trafile))
