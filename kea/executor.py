
import copy
import logging
from multiprocessing.dummy import Pool as ThreadPool
import os
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
    else:
        P = sp.Popen(cl, stdout=stdout_handle, stderr=stderr_handle)
        info['pid'] = P.pid
        P.communicate()
        info['stop'] = arrow.now()
        info['stop'] = arrow.now()
        info['runtime'] = info['stop'] - info['start']
        info['returncode'] = P.returncode


class BasicExecutor(object):

    def __init__(self, app):
        lg.debug("Starting executor")
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

        if self.simple:
            simple_runner(info)
        else:
            self.pool.apply_async(simple_runner, [info,], {'defer_run': False})

    def finish(self):
        if not self.simple:
            lg.warning('waiting for the threads to finish')
            self.pool.close()
            self.pool.join()
            lg.warning('finished waiting for threads to finish')


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
