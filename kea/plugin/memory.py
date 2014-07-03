
import sys
import os
import subprocess as sp

from mad2 import ui
import leip


@leip.hook('pre_argparse')
def main_arg_define(app):
    app.kea_argparse.add_argument('-R', '--remember', action='store_true',
                                  help='Save command line to this folder ' +
                                  'in a file called "kea.sh"')

# @leip.hook('post_argparse')
# def run_moa_tool_commands(app):
#     if app.kea_args.remember:
#         remember(app)
#         exit(0)


# @leip.hook('pre_argparse')
# def prep_sge_exec(app):
#     app.executors['pbs'] = PbsExecutor
#     for a in '--pbs_nodes --pbs_ppn --pbs_account'.split():
#         app.kea_arg_harvest_extra[a] = 1

#     app.kea_argparse.add_argument('--pbs_nodes',
#                                   help='No nodes requested (default=jobs '
#                                   + 'submitted)', type=int)
#     app.kea_argparse.add_argument('--pbs_ppn',
#                                   help='No ppn requested (default=cl per '
#                                   + 'job)', type=int)
#     app.kea_argparse.add_argument('--pbs_account',
#                                   help='Account requested (default none)')
#     app.kea_argparse.add_argument('--pbs_dry_run',
#                                   action='store_true',
#                                   help='create script, do not submit)')


@leip.hook('post_fire')
def memory_store_cl(app, info):
    """
    Store command line in history
    """

    if app.kea_args.is_iteration:
        #do not store cl when this is an iteration
        return

    histdir = os.path.join(os.path.expanduser('~'),
                           '.config', 'kea', 'history')

    fullcl = info['full_cl'].strip()

    if info.get('iteration', 0) > 0:
        #only do one (first) iteration since this function will
        #be the same for all iteration
        return

    #expand executable
    ls = fullcl.split()
    lsx, lsr = ls[0], ls[1:]
    lsx = os.path.abspath(lsx)

    #remove +-R (if it is there)
    while '+-R' in lsr:
        lsr.remove('+-R')

    fullcl = (lsx + " " + " ".join(lsr)).strip()

    _store_to_histfile(fullcl, histdir, info['app_name'])
    _store_to_histfile(fullcl, histdir, '__all__')

    if app.kea_args.remember:
        with open('kea.sh', 'w') as F:
            F.write(fullcl + "\n")


def _store_to_histfile(cl, histdir, histfilename):

    try:
        if not os.path.exists(histdir):
            os.makedirs(histdir)

    except OSError, IOError:
        #cannot create history dir - do not store
        return

    histfile = os.path.join(histdir, histfilename)

    if os.path.exists(histfile):
        histsize = os.stat(histfile).st_size
        hist_exists = True
    else:
        histsize = 0
        hist_exists = False

    with open(histfile, 'a+') as F:
        if hist_exists:
            if histsize > 3333:
                F.seek(-3000, 2)
            else:
                F.seek(0)

            last = F.read().rstrip().rsplit("\n", 1)[-1]
            last = last.strip()

            if last and last == cl:
                return

        F.write(cl + "\n")


@leip.arg('-a', '--appname', help='application name')
@leip.commandName('!')
def memory_history(app, args):
    if args.appname is None:
        appname = '__all__'
    else:
        appname = args.appname
    val = ui.askUser(appname, 'kea', default='__last__',
                     prompt='')
    rc = sp.call(val, shell=True)
    exit(rc)
