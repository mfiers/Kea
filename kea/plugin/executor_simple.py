


from collections import deque
import copy
from datetime import datetime
import fcntl
import hashlib
import logging
from multiprocessing.dummy import Pool as ThreadPool
from multiprocessing.dummy import Lock
import os
import pwd
import re
import shlex
import signal
import socket
import subprocess as sp
import sys
import tempfile
import time


import psutil

import leip

lg = logging.getLogger(__name__)
#lg.setLevel(logging.DEBUG)
MPJOBNO = 0
INTERRUPTED = False

@leip.hook('pre_argparse')
def main_arg_define(app):
    if app.executor == 'simple':
        simple_group = app.parser.add_argument_group('Simple Executor')
        simple_group.add_argument('-T', '--no_track_stat', help='do not track process status',
                                action='store_true', default=None)
        simple_group.add_argument('-j', '--threads', help='no threads to use',
                                  type=int, default=1)
        simple_group.add_argument('-E', '--echo', help='echo command line to screen',
                                action='store_true', default=None)
        simple_group.add_argument('-w', '--walltime',
                                help=('max time that this process can take, ' +
                                      'after this time, the process gets killed. ' +
                                      'Specified in seconds, or with ' +
                                      'postfix m for minutes, h for hours, ' +
                                      'd for days'))



#thanks: https://gist.github.com/sebclaeys/1232088
def non_block_read(stream, chunk_size=10000):
    fd = stream.fileno()
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
    try:
        return stream.read()
    except:
        return ""

outputlock = Lock()

BINARY_STREAMS = set()

def streamer(src, tar, dq, hsh=None):
    """
    :param src: input stream
    :param tar: target stream
    :param dq: deque object keeping a tail of chunks for this stream
    :param hsh: hash object to calculate a checksum
    """
    d = non_block_read(src)
    if d is None:
        return 0
    if hsh:
        hsh.update(d)

    global BINARY_STREAMS
    stream_id = '{}_{}'.format(src.__repr__(), tar.__repr__())

    dd = d.decode('utf-8')
    if not stream_id in BINARY_STREAMS:
        try:
            dq.append(dd)
        except UnicodeDecodeError:
            BINARY_STREAMS.add(stream_id)

    d_len = len(d)
    with outputlock:
        tar.write(dd) #.encode('utf-8'))
    return d_len


def get_deferred_cl(info):
    dcl = ['kea', '--deferred']
    if info.get('stdout_file'):
        dcl.extend(['-o', info['stdout_file']])
    if info.get('stderr_file'):
        dcl.extend(['-e', info['stderr_file']])
    dcl.extend(info['cl'])
    return dcl


def store_process_info(rundata):
    psu = rundata.get('psutil_process')
    if not psu: return

    try:
        rundata['pid'] = psu.pid
        rundata['ps_nice'] = psu.nice()
        rundata['ps_num_fds'] = psu.num_fds()
        rundata['ps_threads'] = psu.num_threads()

        cputime = psu.cpu_times()

        rundata['ps_cputime_user'] = cputime.user
        rundata['ps_cputime_system'] = cputime.system
        rundata['ps_cpu_percent_max'] = max(
            rundata.get('ps_cpu_percent_max', 0),
            psu.cpu_percent())

        meminfo = psu.memory_info()

        for f in meminfo._fields:
            rundata['ps_meminfo_max_{}'.format(f)] = \
                    max(getattr(meminfo, f),
                        rundata.get('ps_meminfo_max_{}'.format(f), 0))

        try:
            ioc = psu.io_counters()
            rundata['ps_io_read_count'] = ioc.read_count
        except AttributeError:
            #may not have iocounters (osx)
            pass

    except (psutil.NoSuchProcess, psutil.AccessDenied):
        #process went away??
        return

def run_interrupt(P, info):
    global INTERRUPTED
    INTERRUPTED = True
    rv = []
    lg.warning("Interrupt!, press ctrl-C again to kill")
    info['status'] = 'interrupted'
    rv.append("Keyboard interrupt")
    P.send_signal(signal.SIGINT)

    try:
        while not isinstance(P.poll(), int):
            time.sleep(0.25)
            P.terminate()
    except KeyboardInterrupt as e:
        lg.warning("Kill!")
        rv.append("Repeat Keyboard Interrupt, killing")
        info['status'] = 'killed'

        P.kill()

    return rv

def simple_runner(info, executor, defer_run=False):
    """
    Defer run executes the run with the current executor, but with
    the Kea executable so that all kea related functionality is
    executed in the second stage.
    """

    if INTERRUPTED:
        info['status'] = 'interrupted'
        return

    #get a thread run number
    global MPJOBNO

    thisjob = MPJOBNO
    MPJOBNO += 1

    lg.info("job %s started", MPJOBNO)

    #track system status (memory, etc)
    sysstatus = not executor.app.defargs['no_track_stat']

    run_stats = info['run']
    sys_stats = info['sys']

    run_stats['job_thread_no'] = thisjob
    lgx = logging.getLogger("job{}".format(thisjob))
    #lgx.setLevel(logging.DEBUG)

    stdout_handle = sys.stdout  # Unless redefined - do not capture stdout
    stderr_handle = sys.stderr  # Unless redefined - do not capture stderr
    stdout_file = info.get('output', {}).get('stdout_00', {}).get('path')
    stderr_file = info.get('output', {}).get('stderr_00', {}).get('path')

    walltime = executor.walltime

    if defer_run:
        cl = get_deferred_cl(info)
    else:
        cl = info['cl']
        if stdout_file:
            lg.debug('capturing stdout in %s', stdout_file)
            stdout_handle = open(stdout_file, 'w')
        if stderr_file:
            lg.debug('capturing stderr in %s', stderr_file)
            stderr_handle = open(stderr_file, 'w')

    run_stats['start'] = datetime.utcnow()
    lgx.debug("thread start %s", run_stats['start'])

    #system psutil stuff
    if sysstatus:
        sys_stats['cpucount'] = psutil.cpu_count()
        psu_vm = psutil.virtual_memory()
        for field in psu_vm._fields:
            run_stats['sys_vmem_{}'.format(field)] = getattr(psu_vm, field)
        psu_sw = psutil.swap_memory()
        for field in psu_sw._fields:
            run_stats['sys_swap_{}'.format(field)] = getattr(psu_sw, field)


    if defer_run:
        P = psutil.Popen(cl, shell=True)
        run_stats['pid'] = P.pid
        run_stats['submitted'] = datetime.utcnow()
        return info

    def _get_psu(pid):
        return psutil.Process(pid)

    #execute!
    lgx.info("Starting: %s", " ".join(cl))

    mcl = " ".join(cl)

    #capture output
    stdout_dq = deque(maxlen=100)
    stderr_dq = deque(maxlen=100)
    stdout_len = 0
    stderr_len = 0
    stdout_sha = hashlib.sha1()
    stderr_sha = hashlib.sha1()


    joberrors = []

    # in a try except to make sure that kea get's a chance to cleanly finish upon
    # an error
    try:
        lgx.debug("Popen: %s", mcl)
        P = psutil.Popen(mcl, shell=True, stdout=sp.PIPE, stderr=sp.PIPE)

        if INTERRUPTED:
            info['status'] = 'interrupted'
            return

        if sysstatus:
            try:
                psu = _get_psu(P.pid)
                if isinstance(psu, psutil.Process):
                    run_stats['psutil_process'] = psu
                    lgx.debug("psutil: %s", psu)
                    store_process_info(run_stats)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                #job may have already finished - ignore
                lg.warning('has the job finished already??')
                pass


        #loop & poll until the process finishes..
        while True:

            if INTERRUPTED:
                # somewhere a job got interrupted
                # KILL'EM ALL (Metallica, 1983)
                joberrors.extend(run_interrupt(P, info))
                info['status'] = 'interrupted'
                break

            if walltime:
                runtime = (datetime.utcnow() - run_stats['start']).total_seconds()
                if runtime > walltime:
                    # this job has been running for too long
                    joberrors.append("Hit Walltime")
                    joberrors.extend(run_interrupt(P, info))

            pc = P.poll()

            if isinstance(pc, int):
                #integer <- returncode => so exit.
                lgx.debug("got a return code (%d) - exit", pc)
                break

            #read_proc_status(td)
            time.sleep(0.2)

            if sysstatus:
                if 'psutil_process' in info:
                    store_process_info(info)
                else:
                    psu = _get_psu(P.pid)
                    if isinstance(psu, psutil.Process):
                        run_stats['psutil_process'] = psu
                        store_process_info(info)


            try:
                stdout_len += streamer(P.stdout, stdout_handle, stdout_dq, stdout_sha)
                stderr_len += streamer(P.stderr, stderr_handle, stderr_dq, stderr_sha)
            except IOError as e:
                #it appears as if one of the pipes has failed.
                if e.errno == 32:
                    joberrors.append("Broken Pipe")
                    #broken pipe - no problem.
                else:
                    message('err', str(dir(e)))
                    joberrors.append("IOError: " + str(e))
                break

    except KeyboardInterrupt as e:
        joberrors.extend(run_interrupt(P, info))

    finally:
        #clean the pipes
        try:
            stdout_len += streamer(P.stdout, stdout_handle, stdout_dq, stdout_sha)
            stderr_len += streamer(P.stderr, stderr_handle, stderr_dq, stderr_sha)
        except IOError as e:
            #it appears as if one of the pipes has failed.
            if e.errno == 32:
                joberrors.append("Broken pipe")
                #broken pipe - no problem.
            else:
                message('err', str(dir(e)))
                joberrors.append("IOError: " + str(e))

        if info['status'] == 'started':
            if P.returncode == 0:
                info['status'] = 'success'
            else:
                info['status'] = 'failed'

    if joberrors:
        info['errors'] = joberrors

    if stdout_file:
        lg.debug('closing stdout handle on %s', stdout_file)
        stdout_handle.close()
    if stderr_file:
        lg.debug('closing stderr handle on %s', stderr_file)
        stderr_handle.close()

    lgx.info("jobstatus: %s", info['status'])

    if stdout_len > 0:
        info['stdout_sha1'] = stdout_sha.hexdigest()
    if stderr_len > 0:
        info['stderr_sha1'] = stderr_sha.hexdigest()

    run_stats['stop'] = datetime.utcnow()
    run_stats['runtime'] = (run_stats['stop'] - run_stats['start']).total_seconds()

    if 'psutil_process' in run_stats:
        del run_stats['psutil_process']

    run_stats['returncode'] = P.returncode
    run_stats['stdout_len'] = stdout_len
    run_stats['stderr_len'] = stderr_len
    lgx.debug("end thread, calling post_fire (uid: %s)",
                info['run']['uid'],)
    executor.app.run_hook('post_fire', info)
    return info


class BasicExecutor(object):

    def __init__(self, app):
        lg.debug("Starting executor")
        self.app = app

        try:
            self.threads =  self.app.args.threads
        except AttributeError:
            self.threads = 1

        if self.threads < 2:
            self.simple = True
        else:
            self.simple = False
            self.pool = ThreadPool(self.threads)
            lg.info("using a threadpool with %d threads", self.threads)


        self.walltime = None
        if hasattr(self.app.args, 'walltime'):
            w = self.app.args.walltime
            if not w is None:
                if len(w) > 1 and w[-1] == 'm':
                    self.walltime = float(w[:-1]) * 60
                elif len(w) > 1 and w[-1] == 'h':
                    self.walltime = float(w[:-1]) * 60 * 60
                elif len(w) > 1 and w[-1] == 'd':
                    self.walltime = float(w[:-1]) * 60 * 60 * 24
                else:
                    self.walltime = float(w)

    def fire(self, info):
        lg.debug("start execution")
        if INTERRUPTED:
            info['status'] = 'interrupted'
            return

        info['status'] = 'started'
        info['sys']['host'] = socket.gethostname()

        P = sp.Popen(['uname', '-a'], stdout=sp.PIPE)
        uname, _ = P.communicate()
        info['sys']['uname'] = uname.strip()
        info['sys']['fqdn'] = socket.getfqdn()
        info['sys']['user'] = pwd.getpwuid(os.getuid())[0]

        self.app.run_hook('pre_fire', info)

        if hasattr(self.app.args, 'echo'):
            if self.app.args.echo:
                print((" ".join(info['cl'])))

        if info.get('skip', False):
            # for whatever reason, Kea wants to skip this job
            # so - we will oblige
            info['status'] = 'skipped'
            self.app.run_hook('post_fire', info)
            return

        if self.simple:
            lg.debug("starting single threaded run")
            simple_runner(info, self)
            self.app.run_hook('post_fire', info)
            return

        lg.debug("starting parallel run")
        res = self.pool.apply_async(simple_runner,
                                    [info, self],
                                    {'defer_run': False})

    def finish(self):
        if not self.simple:
            lg.warning('waiting for the threads to finish')
            self.pool.close()
            self.pool.join()
            lg.warning('finished waiting for threads to finish')


class DummyExecutor(BasicExecutor):

    def fire(self, info):

        self.app.run_hook('pre_fire', info)
        info['dummy'] = True
        
        if info.get('skip', False):
            # for whatever reason, Kea wants to skip executing this job
            # so - we will oblige
            info['status'] = 'skipped'
        else:

            lg.debug("start dummy execution")
            cl = copy.copy(info['cl'])
            
            stdout_file = info.get('output', {}).get('stdout_00', {}).get('path')
            stderr_file = info.get('output', {}).get('stderr_00', {}).get('path')

            if stdout_file:
                cl.extend(['>', stdout_file])
            if stderr_file:
                cl.extend(['2>', stderr_file])

            lg.debug("  cl: %s", cl)
            print(" ".join(cl))

        info['mode'] = 'synchronous'
        info['run']['returncode'] = 0
        info['status'] = 'skipped'

        self.app.run_hook('post_fire', info)


conf = leip.get_config('kea')
conf['executors.simple'] = BasicExecutor
conf['executors.dummy'] = DummyExecutor
