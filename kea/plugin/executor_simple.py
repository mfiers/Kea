
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

@leip.hook('pre_argparse')
def main_arg_define(app):
    if app.executor == 'simple':
        simple_group = app.parser.add_argument_group('Simple Executor')
        simple_group.add_argument('-T', '--no_track_stat', help='do not track process status',
                                action='store_true', default=None)
        simple_group.add_argument('-j', '--threads', help='no threads to use',
                                type=int)
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

    if not stream_id in BINARY_STREAMS:
        try:
            dq.append(d.decode('utf-8'))
        except UnicodeDecodeError:
            BINARY_STREAMS.add(stream_id)
        
    d_len = len(d)
    with outputlock:
        tar.write(d) #d.encode('utf-8'))
    return d_len

    
def get_deferred_cl(info):
    dcl = ['kea']
    if info['stdout_file']:
        dcl.extend(['-o', info['stdout_file']])
    if info['stderr_file']:
        dcl.extend(['-e', info['stderr_file']])
    dcl.extend(info['cl'])
    return dcl

    
def store_process_info(info):
    psu = info.get('psutil_process')
    if not psu: return

    try:
        info['pid'] = psu.pid
        info['ps_nice'] = psu.nice()
        info['ps_num_fds'] = psu.num_fds()
        info['ps_threads'] = psu.num_threads()

        cputime = psu.cpu_times()

        info['ps_cputime_user'] = cputime.user 
        info['ps_cputime_system'] = cputime.system
        info['ps_cpu_percent_max'] = max(
            info.get('ps_cpu_percent_max', 0),
            psu.cpu_percent())

        meminfo = psu.memory_info()

        for f in meminfo._fields:
            info['ps_meminfo_max_{}'.format(f)] = \
                    max(getattr(meminfo, f),
                        info.get('ps_meminfo_max_{}'.format(f), 0))

        try:
            ioc = psu.io_counters()
            info['ps_io_read_count'] = ioc.read_count
        except AttributeError:
            #may not have iocounters (osx)
            pass

    except (psutil.NoSuchProcess, psutil.AccessDenied):
        #process went away??
        return

def simple_runner(info, executor, defer_run=False):
    """
    Defer run executes the run with the current executor, but with
    the Kea executable so that all kea related functionality is
    executed in the second stage.
    """

    #get a thread run number
    global MPJOBNO
    thisjob = MPJOBNO
    MPJOBNO += 1

    #track system status (memory, etc)
    sysstatus = not executor.app.defargs['no_track_stat']
    
    info['job_thread_no'] = MPJOBNO
    lgx = logging.getLogger("job{}".format(thisjob))
    #lgx.setLevel(logging.DEBUG)
    
    stdout_handle = sys.stdout  # Unless redefined - do not capture stdout
    stderr_handle = sys.stderr  # Unless redefined - do not capture stderr

    walltime = executor.walltime
    
    if defer_run:
        cl = get_deferred_cl(info)
    else:
        cl = info['cl']
        if info['stdout_file']:
            lg.debug('capturing stdout in %s', info['stdout_file'])
            stdout_handle = open(info['stdout_file'], 'w')
        if info['stderr_file']:
            lg.debug('capturing stderr in %s', info['stderr_file'])
            stderr_handle = open(info['stderr_file'], 'w')

    info['start'] = datetime.utcnow()
    lgx.debug("thread start %s", info['start'])

    #system psutil stuff
    if sysstatus:
        info['ps_sys_cpucount'] = psutil.cpu_count()
        psu_vm = psutil.virtual_memory()
        for field in psu_vm._fields:
            info['ps_sys_vmem_{}'.format(field)] = getattr(psu_vm, field)
        psu_sw = psutil.swap_memory()
        for field in psu_sw._fields:
            info['ps_sys_swap_{}'.format(field)] = getattr(psu_sw, field)


    if defer_run:
        P = psutil.Popen(cl, shell=True)
        info['pid'] = P.pid
        info['submitted'] = datetime.utcnow()
        return info

    #execute!
    lgx.debug("Starting: %s", " ".join(cl))
    strace_file = tempfile.NamedTemporaryFile(delete=False)
    strace_file.close()
    mcl = "strace -e trace=file -tt -r -f -o {} ".format(strace_file.name)
    lg.debug("strace to: %s", strace_file.name)
    mcl += " ".join(cl) 
    lg.debug("executing: %s", mcl)
    P = psutil.Popen(mcl, shell=True, stdout=sp.PIPE, stderr=sp.PIPE)

    info['strace_pid'] = P.pid
    lgx.debug("Job has started with (strace) pid: %d", info['strace_pid'])

    def _get_psu(pid):
        ppsu = psutil.Process(pid)
        child = ppsu.children()
        if len(child) == 0:
            return False
        assert len(child) == 1
        return child[0]

    if sysstatus:
        try:
            psu = _get_psu(P.pid)
            if isinstance(psu, psutil.Process):
                info['psutil_process'] = psu
                store_process_info(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            #job may have already finished - ignore
            lg.info('has the job finished already??')
            pass

    stdout_dq = deque(maxlen=100)
    stderr_dq = deque(maxlen=100)

    stdout_len = 0
    stderr_len = 0

    stdout_sha = hashlib.sha1()
    stderr_sha = hashlib.sha1()

    force_quit = False

    #loop & poll until the process finishes..
    while True:

        if walltime:
            runtime = (datetime.utcnow() - info['start']).total_seconds()
            if runtime > walltime:
                if not force_quit:
                    lg.warning("Killing process (walltime)")
                force_quit = True
                P.kill()

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
                    info['psutil_process'] = psu
                    store_process_info(info)
            


        try:
            stdout_len += streamer(P.stdout, stdout_handle, stdout_dq, stdout_sha)
            stderr_len += streamer(P.stderr, stderr_handle, stderr_dq, stderr_sha)
        except IOError as e:
            #it appears as if one of the pipes has failed.
            if e.errno == 32:
                errors.append("Broken Pipe")
                #broken pipe - no problem.
            else:
                message('err', str(dir(e)))
                errors.append("IOError: " + str(e))
            break

    #clean the pipes
    try:
        stdout_len += streamer(P.stdout, stdout_handle, stdout_dq, stdout_sha)
        stderr_len += streamer(P.stderr, stderr_handle, stderr_dq, stderr_sha)
    except IOError as e:
        #it appears as if one of the pipes has failed.
        if e.errno == 32:
            errors.append("Broken Pipe")
            #broken pipe - no problem.
        else:
            message('err', str(dir(e)))
            errors.append("IOError: " + str(e))


    if force_quit:
        info['status'] = 'kill'
    elif P.returncode == 0:
        info['status'] = 'success'
    else:
        info['status'] = 'fail'

    if info['stdout_file']:
        lg.debug('closing stdout handle on %s', info['stdout_file'])
        stdout_handle.close()
    if info['stderr_file']:
        lg.debug('closing stderr handle on %s', info['stderr_file'])
        stderr_handle.close()

    lgx.debug("job has status: %s", info['status'])

    if stdout_len > 0:
        info['stdout_sha1'] = stdout_sha.hexdigest()
    if stderr_len > 0:
        info['stderr_sha1'] = stderr_sha.hexdigest()

    info['stop'] = datetime.utcnow()
    info['runtime'] = (info['stop'] - info['start']).total_seconds()

    if 'psutil_process' in info:
        del info['psutil_process']

    info['returncode'] = P.returncode
    info['stdout_len'] = stdout_len
    info['stderr_len'] = stderr_len
    lgx.debug("end thread")


    #parse strace output & store data
    if not 'files' in info:
        info['files'] = {}

    filekeys = []

    def _fileupdate(d, k, v):
        if not k in filekeys:
            filekeys.append(k)
            kid = str(filekeys.index(k) + 1)

        if not kid in d:
            d[kid] = dict(path=k, mode=[])
        if not v in d[kid]['mode']:
            d[kid]['mode'].append(v)

    to_ignore = [
        re.compile(r'/site-packages/'),
        re.compile(r'/project/Mad2/'),
        re.compile(r'/project/Leip/'),
        re.compile(r'/lib/python'),
        re.compile(r'/project/Fantail/'),
        re.compile(r'^/dev/'),
        re.compile(r'^/proc/'),
        re.compile(r'^/lib/'),
        re.compile(r'^/usr/lib/'),
        re.compile(r'^/usr/local/lib/'),
    ]
            
    with open(strace_file.name) as F:
        for line in F:
            line = line.strip()
            ls = line.split(None, 2)
            if '(No such file or directory)' in line:
                continue
            typ, rest = ls[2].split('(',1)
            rest = shlex.split(rest.rsplit(')',1)[0])
            filename = rest[0].rstrip(',')
            if filename.strip() in ['AT_FDCWD']:
                continue
            if os.path.isdir(filename):
                continue #no directories
            ignore = False
            for toi in to_ignore:
                if toi.search(filename):
                    ignore=True
                    break
            if ignore:
                continue
            if 'stat' in typ: continue
            if 'SIGCHLD' in typ and filename == 'Child': 
                continue
            if 'exec' in typ:
                _fileupdate(info['files'], filename,
                            [typ])
            else:
                _fileupdate(info['files'], filename, 
                            [typ] + rest[1:])
    os.unlink(strace_file.name)


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
            lg.debug("using a threadpool with %d threads", self.threads)


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
        lg.warning("start execution")

        info['status'] = 'start'
        info['host'] = socket.gethostname()
        info['fqdn'] = socket.getfqdn()
        info['user'] = pwd.getpwuid(os.getuid())[0]

        self.app.run_hook('pre_fire', info)
        
        if self.app.args.echo:
            print(" ".join(info['cl']))

            
        if self.simple:
            simple_runner(info, self)
            self.app.run_hook('post_fire', info)
        else:
            def _callback(info):
                lg.warningdebug("job finished (%s) - callback!", info['job_thread_no'])
                self.app.run_hook('post_fire', info)

            self.pool.apply_async(simple_runner, [info, self], {'defer_run': False},
                                  callback=_callback)

    def finish(self):
        if not self.simple:
            lg.info('waiting for the threads to finish')
            self.pool.close()
            self.pool.join()
            lg.debug('finished waiting for threads to finish')


class DummyExecutor(BasicExecutor):

    def fire(self, info):
        
        self.app.run_hook('pre_fire', info)
        lg.debug("start dummy execution")
        cl = copy.copy(info['cl'])

        if info['stdout_file']:
            cl.extend(['>', info['stdout_file']])
        if info['stderr_file']:
            cl.extend(['2>', info['stderr_file']])

        lg.debug("  cl: %s", cl)
        print " ".join(cl)
        info['mode'] = 'synchronous'
        info['returncode'] = 0
        info['status'] = 'success'
        self.app.run_hook('post_fire', info)
        

conf = leip.get_config('kea')
conf['executors.simple'] = BasicExecutor
conf['executors.dummy'] = DummyExecutor

