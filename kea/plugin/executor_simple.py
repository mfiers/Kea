
from collections import deque
import copy
from datetime import datetime
import fcntl
import hashlib
import logging
from multiprocessing.dummy import Pool as ThreadPool
import os
import subprocess as sp
import sys
import time


import psutil

import leip

lg = logging.getLogger(__name__)


@leip.hook('pre_argparse')
def main_arg_define(app):
    if app.executor == 'simple':
        app.parser.add_argument('-j', '--threads', help='no threads to use', type=int)


#thanks: https://gist.github.com/sebclaeys/1232088
def non_block_read(stream, chunk_size=10000):
    #print('xxx', type(stream))
    fd = stream.fileno()
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
    try:
        return stream.read()
    except:
        return ""

    
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
    
    dq.append(d.decode('utf-8'))
    d_len = len(d)
    tar.write(d) #d.encode('utf-8'))
    return d_len

    
def get_deferred_cl(info):
    dcl = ['kea']
    if info['stdout_file']:
        dcl.extend(['-o', info['stdout_file']])
    if info['stderr_file']:
        dcl.extend(['-e', info['stderr_file']])
    dcl.extend(info['cl'])
    return cl

def store_process_info(info):
    psu = info.get('psutil_process')
    if not psu: return
    try:
        info['ps_nice'] = psu.nice()
        info['ps_num_fds'] = psu.num_fds()
        info['ps_threads'] = psu.num_threads()
        cputime = psu.cpu_times()
        info['ps_cputime_user'] = cputime.user 
        info['ps_cputime_system'] = cputime.system
        meminfo = psu.memory_info()
        for f in meminfo._fields:
            #info['ps_meminfo_{}'.format(f)] = getattr(meminfo, f)
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
            
def simple_runner(info, defer_run=False):
    """
    Defer run executes the run with the current executor, but with
    the Kea executable so that all kea related functionality is
    executed in the second stage.
    """

    stdout_handle = sys.stdout  # Unless redefined - do not capture stdout
    stderr_handle = sys.stderr  # Unless redefined - do not capture stderr


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

    #system psutil stuff
    info['ps_sys_cpucount'] = psutil.cpu_count()
    psu_vm = psutil.virtual_memory()
    for field in psu_vm._fields:
        info['ps_sys_vmem_{}'.format(field)] = getattr(psu_vm, field)
    psu_sw = psutil.swap_memory()
    for field in psu_sw._fields:
        info['ps_sys_swap_{}'.format(field)] = getattr(psu_sw, field)


    if defer_run:
        P = sp.Popen(cl, shell=True)
        info['pid'] = P.pid
        info['submitted'] = datetime.utcnow()
    else:
        P = sp.Popen(" ".join(cl), shell=True, stdout=sp.PIPE, stderr=sp.PIPE)

        info['pid'] = P.pid
        try:
            psu = psutil.Process(P.pid)
            info['psutil_process'] = psu
            store_process_info(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            #job may have already finished - ignore
            pass
        
        stdout_dq = deque(maxlen=100)
        stderr_dq = deque(maxlen=100)

        stdout_len = 0
        stderr_len = 0

        stdout_sha = hashlib.sha1()
        stderr_sha = hashlib.sha1()
        
        while True:
            pc = P.poll()

            if not pc is None:
                break

            #read_proc_status(td)
            time.sleep(0.2)
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


    def fire(self, info):
        lg.debug("start execution")

        if self.simple:
            simple_runner(info)
        else:
            self.pool.apply_async(simple_runner, [info,], {'defer_run': False})

    def finish(self):
        if not self.simple:
            lg.info('waiting for the threads to finish')
            self.pool.close()
            self.pool.join()
            lg.debug('finished waiting for threads to finish')


class DummyExecutor(BasicExecutor):

    def fire(self, info):
        lg.debug("start dummy execution")
        cl = copy.copy(info['cl'])

        if info['stdout_file']:
            cl.extend(['>', info['stdout_file']])
        if info['stderr_file']:
            cl.extend(['2>', info['stderr_file']])

        lg.debug("  cl: %s", cl)
        print " ".join(cl)
        info['mode'] = 'synchronous'


conf = leip.get_config('kea')
conf['executors.simple'] = BasicExecutor
conf['executors.dummy'] = DummyExecutor

