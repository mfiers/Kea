
import copy
import logging
from multiprocessing.dummy import Pool as ThreadPool
import os
import signal
import subprocess as sp
import sys

import arrow

lg = logging.getLogger(__name__)


def get_deferred_cl(info):
    kap = info['kea_arg_prefix']

    cl = [info['kea_executable']] + info['cl']
    if info['stdout_file']:
        cl.extend(['{}-o'.format(kap), info['stdout_file']])
    if info['stderr_file']:
        cl.extend(['{}-e'.format(kap), info['stderr_file']])
    return cl


def simple_runner(info, defer_run=False):
    """
    Defer run executes the run with the current executor, but with
    the Kea executable so that all kea related functionality is
    executed in the second stage.
    """

    stdout_handle = None  # Unless redefined - do not capture stdout
    stderr_handle = None  # Unless redefined - do not capture stderr

    kap = info['kea_arg_prefix']

    if defer_run:
        cl = get_deferred_cl(info)
    else:
        cl = [info['executable']] + info['cl']

        if info['stdout_file']:
            stdout_handle = open(info['stdout_file'], 'w')
        if info['stderr_file']:
            stderr_handle = open(info['stderr_file'], 'w')

    lg.debug("  cl: %s", cl)

    info['start'] = arrow.now()

    if defer_run:
        P = sp.Popen(cl)
        info['pid'] = P.pid
        info['submitted'] = arrow.now()
        info['status'] = 'deferred'
    else:

        def preexec(): # Don't forward signals.
            os.setpgrp()

        P = sp.Popen(cl, stdout=stdout_handle, stderr=stderr_handle,
                     preexec_fn = preexec)
        info['pid'] = P.pid
        P.communicate()
        info['stop'] = arrow.now()
        info['stop'] = arrow.now()
        info['runtime'] = info['stop'] - info['start']
        info['returncode'] = P.returncode
        if info['returncode'] == 0:
            info['status'] = 'success'
        else:
            info['status'] = 'error'

class BasicExecutor(object):

    def __init__(self, app):
        lg.debug("Starting executor")
        self.interrupted = False
        self.app = app
        self.threads =  self.app.kea_args.threads
        if self.threads < 2:
            self.simple = True
        else:
            self.simple = False
            self.pool = ThreadPool(self.threads)
            lg.debug("using a threadpool with %d threads", self.threads)


    def fire(self, info):
        lg.debug("start execution")

        if self.interrupted:
            #refuse execution after an interrupt was caught
            info['returncode'] = 2
            info['status'] = 'not_executed'
            return

        def sigint_handler(sgn, frame):
            #capture sigint
            #send sigint
            if self.interrupted:
                lg.warning('Captured Ctrl+C twice - exit now')
                sys.exit(-1)

            if self.simple:
                self.interrupted = True
                info['status'] = 'interrupted'
                lg.warning('Captured Ctrl+C - quitting')
                lg.warning('Sending SIGINT to %d', info['pid'])
                os.kill(info['pid'], signal.SIGINT)
                #os.kill(info['pid'], signal.SIGKILL)


        # weirdly enough, this following line makes the less pager
        # behave normally - i.e. this program quits when less quits
        signal.signal(signal.SIGPIPE, lambda s,f: None)

        # capture sigint as well
        signal.signal(signal.SIGINT, sigint_handler)

        if self.simple:
            simple_runner(info)
        else:
            self.pool.apply_async(simple_runner, [info,], {'defer_run': False})


    def finish(self):
        if not self.simple:
            lg.debug('waiting for the threads to finish')
            self.pool.close()
            self.pool.join()
            lg.debug('finished waiting for threads to finish')

        signal.signal(signal.SIGPIPE, signal.SIG_DFL)


class DummyExecutor(BasicExecutor):

    def fire(self, info):
        lg.debug("start dummy execution")
        cl = [info['executable']] + copy.copy(info['cl'])

        if info['stdout_file']:
            cl.extend(['>', info['stdout_file']])
        if info['stderr_file']:
            cl.extend(['2>', info['stderr_file']])

        lg.debug("  cl: %s", cl)
        print " ".join(cl)
        info['mode'] = 'synchronous'


executors = {
    'simple': BasicExecutor,
#    'bg': BgExecutor,
    'dummy': DummyExecutor,
}
