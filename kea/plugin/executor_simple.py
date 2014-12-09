
from collections import deque
import copy
import fcntl
import logging
from multiprocessing.dummy import Pool as ThreadPool
import os
import subprocess as sp
import sys
import time

import arrow

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

    
def streamer(src, tar, dq):
    d = non_block_read(src)
    if d is None:
        return 0
    #print(type(d))
    # dd = d #d.decode('utf-8')

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

    info['start'] = arrow.utcnow()

    if defer_run:
        P = sp.Popen(cl, shell=True)
        info['pid'] = P.pid
        info['submitted'] = arrow.utcnow()
    else:
        P = sp.Popen(" ".join(cl), shell=True, stdout=sp.PIPE, stderr=sp.PIPE)
        info['pid'] = P.pid

        stdout_dq = deque(maxlen=100)
        stderr_dq = deque(maxlen=100)

        stdout_len = 0
        stderr_len = 0
        
        while True:
            pc = P.poll()

            if not pc is None:
                break

            #read_proc_status(td)
            time.sleep(0.1)

            try:
                stdout_len += streamer(P.stdout, stdout_handle, stdout_dq)
                stderr_len += streamer(P.stderr, stderr_handle, stderr_dq)

                
            except IOError as e:
                #it appears as if one of the pipes has failed.
                if e.errno == 32:
                    errors.append("Broken Pipe")
                    #broken pipe - no problem.
                else:
                    message('err', str(dir(e)))
                    errors.append("IOError: " + str(e))
                break

        info['stop'] = arrow.utcnow()
        info['runtime'] = info['stop'] - info['start']
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

