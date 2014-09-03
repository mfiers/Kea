

import copy
import logging

import leip
from mad2.recrender import recrender

lg = logging.getLogger(__name__)
#lg.setLevel(logging.DEBUG)

@leip.hook('pre_fire', 1000)
def hook_pre_run(app, info):
    rinf = copy.copy(info)
    rinf['f'] = {}
    for fn in info['files']:
        rinf['f'][fn] = rinf['files'][fn]['madfile']

    for i in range(len(info['cl'])):
        v = info['cl'][i]
        if ('{{' in v) or ('{%' in v):
            lg.debug("rendering: %s", v)
            nv = recrender(v, rinf)
            info['cl'][i] = nv

