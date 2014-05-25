
import logging
import subprocess as sp

import arrow

lg = logging.getLogger(__name__)


class BasicExecutor(object):
    def __init__(self, app):
        self.app = app

    def fire(self, cl):
        lg.debug("start execution")
        lg.debug("  cl: %s", cl)

        info = {'mode' : 'synchronous'}
        P = sp.Popen(cl)
        info['pid'] = P.pid
        P.communicate()
        info['returncode'] = P.returncode
        lg.debug("finish fire execution")
        return info

    def finish(self):
        pass


executors = {
    'basic' : BasicExecutor,
}
