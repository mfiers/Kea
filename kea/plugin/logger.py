
from collections import OrderedDict
import copy
import datetime
import logging
import os
import signal
import sys
import time

import humanize
import termcolor
import leip
from lockfile import FileLock

import kea.utils

lg = logging.getLogger(__name__)

def to_str(s):
    return str(s)


@leip.hook('pre_argparse')
def logger_arg_define(app):
    logger_group = app.parser.add_argument_group('Report plugin')

    logger_group.add_argument('-S', '--report_screen', action='count', default=0)
    logger_group.add_argument('-Y', '--report_yaml', action='store_true')
    logger_group.add_argument('-L', '--report_file', action='store_true')
    logger_group.add_argument('-M', '--report_mongo', action='store_true')


def get_mongo_logcol(conf):
    try:
        mconf = conf['plugin.logger.mongo']
    except KeyError:
        return None
    
    colname = mconf.get('collection', 'log')
    collection = kea.utils.get_mongo_collection(conf, colname)
    collection.ensure_index('created')
    collection.ensure_index('status')
    collection.ensure_index('logflush')
    return collection


@leip.subparser
def mng(app, args):
    pass


@leip.subcommand(mng, 'flush')
def mng_flush(app, args):
    coll = get_mongo_logcol(app.conf)
    if coll is None:
        return
    
    coll.update({ 'status': 'start',
                  'logflush': {"$exists": False}},
                {"$set": {'logflush': True}},
                multi=True)


@leip.arg('-s', '--status', action='append')
@leip.flag('-f', '--follow')
@leip.subcommand(mng, 'ls')
def mng_ls(app, args):

    if not args.status:
        states = ['start', 'failed']
    states = list(set(states))

    coll = get_mongo_logcol(app.conf)
    if coll is None:
        return

    
    fmt = '{} {} {:7s} {}@{}: {}'
    query = {'status': {"$in": states},
             'logflush': {"$exists": False}}

    status_colors = dict( fai='red', sta='blue',
                          int='red', kil='red', suc='green')

    def _exit(signal, frame):
        sys.exit()
    signal.signal(signal.SIGINT, _exit)
    while True:
        if args.follow:
            sys.stdout.write(chr(27) + "[2J" + chr(27) + "[1;1f")
            print(datetime.datetime.now())
            print()
        for rec in coll.find(query):
            frec = fmt.format(
                rec['run_uid'],
                termcolor.colored(rec['status'][:3],
                                  status_colors[rec['status'][:3]]),
                termcolor.colored(
                    kea.utils.nicetime(rec['create'], short=True),
                    'cyan'),
                rec.get('user'), rec.get('host'),
                (" ".join(rec.get('cl')))[:40]
            )
            print(frec)
        if not args.follow:
            break
        time.sleep(2)

@leip.hook('pre_fire')
def prefire_mongo_mongo(app, jinf):
    coll = get_mongo_logcol(app.conf)
    if coll is None:
        return
    
    jinf_copy = copy.copy(jinf)
    try:
        del jinf_copy['run']['psutil_process']
    except KeyError:
        pass

    try:
        jinf['mongo_id'] = coll.insert(jinf_copy)
    except Exception as e:
        import pprint
        pprint.pprint(jinf)
        raise


@leip.hook('post_fire', 10)
def postfire_mongo(app, jinf):
    coll = get_mongo_logcol(app.conf)
    if coll is None:
        return
    
    mongo_id = jinf['mongo_id']
    coll.update({'_id' : mongo_id},
                jinf)
    if '_id' in jinf:
        del jinf['_id']
    jinf['mongo_id'] = str(jinf['mongo_id'])


def dictprint(d, firstpre="", nextpre=""):
    if len(d) == 0:
        return
    mxkyln = max([len(x) for x in list(d.keys())] + [5])
    fs = '{:<' + str(mxkyln) + '} : {}'
    fp = '{:<' + str(mxkyln) + '} > '
    i = 0
    for k in sorted(d.keys()):
        #            if k == 'run_stats':
        #                continue
        #            if k in ['args']:
        #                continue

        v = d[k]
        v = kea.utils.make_pretty_kv(k, v)

        if isinstance(v, str) and not v.strip():
            continue

        i = i + 1
        pre = firstpre if i == 1 else nextpre
        if not isinstance(v, dict):
            print(pre + fs.format(k, v))
        else:
            bfp = pre + fp.format(k)
            bnp = nextpre + fp.format(' ')
            dictprint(v, bfp, bnp)


@leip.hook('post_fire', 100)
def log_screen(app, jinf):

    if jinf.get('deferred'):
        return

    if app.args.report_yaml:
        import yaml

        if 'psutil_process' in jinf:
            del jinf['psutil_process']

        fn = '{}.{}.report.yaml'.format(
            app.name, jinf['run']['uid'])

        with open(fn, 'w') as F:
            yaml.safe_dump(dict(jinf), F)

    if app.args.report_screen == 0:
        return

    print('--KEA-REPORT' + '-' * 68)
    if app.args.report_screen > 1:
        dictprint(jinf)
    else:
        jj = dict(jinf)
        jj['sys'] = {}
        jj['run'] = {}
        dictprint(jj)
    print('-' * 80)

#@leip.hook('post_run')
#def

@leip.hook('post_run')
def log_cl(app):

    if not app.args.deferred:
        oricl = copy.copy(app.original_cl)
        oricl[0] = os.path.basename(oricl[0])
        runsh_line = "# " + " ".join(oricl)
        with FileLock('run.sh'):
            with open('run.sh', 'a') as F:
                F.write("{}\n".format(runsh_line))

    if not app.args.report_file:
        return

    all_jinf = app.all_jinf
    try:
        with FileLock('kea.log'):
            for i, info in enumerate(all_jinf):
                with open('kea.log', 'a') as F:
                    F.write("-" * 80 + "\n")
                    for i in info:
                        F.write("{}: ".format(i))
                        val = info[i]
                        if i == 'cl':
                            F.write(" ".join(val) + "\n")
                        elif isinstance(val, list):
                            F.write("\n")
                            for lv in val:
                                F.write(' - {}\n'.format(to_str(lv)))
                        else:
                            F.write(" {}\n".format(to_str(val)))

    except Exception as e:
        lg.warning("Cannot write to log file (%s)", str(e))
