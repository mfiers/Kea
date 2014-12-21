
import copy
import logging
import os

from jinja2 import Template
import arrow

import leip

from kea.plugin.executor_simple import BasicExecutor, get_deferred_cl
from kea.utils import get_base_uid

lg = logging.getLogger(__name__)


@leip.hook('pre_argparse')
def prep_sge_exec(app):
    if app.executor == 'pbs':
        pbs_group = app.parser.add_argument_group('PBS Executor')
        pbs_group.add_argument('--pbs_nodes',
                               help='No nodes requested', type=int)
        pbs_group.add_argument('-j', '--pbs_ppn', type=int,
                               help='No ppn requested (default=cl per job)')
        pbs_group.add_argument('--pbs_account', 
                               help='Account requested (default none)')
        pbs_group.add_argument('-w', '--walltime',
                                help=('max time that this process can take'))


PBS_SUBMIT_SCRIPT_HEADER = """#!/bin/bash
#PBS -N {{appname}}.{{uid}}
#PBS -e {{ cwd }}/{{appname}}.{{uid}}.$PBS_JOBID.err
#PBS -o {{ cwd }}/{{appname}}.{{uid}}.$PBS_JOBID.out
#PBS -l nodes={{pbs_nodes}}:ppn={{pbs_ppn}}

{% if pbs_account -%}
  #PBS -A {{ pbs_account }}{% endif %}
{% if walltime -%}
  #PBS -l walltime={{ walltime }}{% endif %}

set -v

"""


class PbsExecutor(BasicExecutor):

    def __init__(self, app):

        super(PbsExecutor, self).__init__(app)

        self.buffer = []
        self.batch = 0
        self.clno = 0


    def submit_to_pbs(self):
        uid = get_base_uid()
        
        #write pbs script
        pbs_script = '{}.{}.pbs'.format(self.app.name, uid)

        template = Template(PBS_SUBMIT_SCRIPT_HEADER)

        data = dict(self.app.defargs)
        data['appname'] = self.app.name
        data['cwd'] = os.getcwd()
        data['uid'] = uid

        
        lg.debug("submit to pbs with uid %s", uid)
        for info in self.buffer:

            info['submitted'] = arrow.utcnow()
            info['pbs_uid'] = uid
            info['pbs_script_file'] = pbs_script

            with open(pbs_script, 'w') as F:
                F.write(template.render(**data))
                for info in self.buffer:
                    F.write("( " + " ".join(get_deferred_cl(info)))
                    F.write(" ) & \n")
                F.write("wait\n")
                F.write('echo "done"\n')

            self.clno += 1

        #fire & forget the pbs job
        pbs_cl = ['qsub', pbs_script]
        print " ".join(pbs_cl)
        self.buffer = []
        self.batch += 1


    def fire(self, info):
        self.app.run_hook('pre_fire', info)
        self.buffer.append(copy.copy(info))
        info['returncode'] = 0
        info['status'] = 'queued'
        self.app.run_hook('post_fire', info)
        if len(self.buffer) >= self.app.defargs['pbs_ppn']:
            lg.info("submitting pbs job. No commands: %d", len(self.buffer))
            self.submit_to_pbs()

    def finish(self):
        if len(self.buffer) > 0:
            lg.info("submitting pbs job. No commands: %d", len(self.buffer))
            self.submit_to_pbs()


conf = leip.get_config('kea')
conf['executors.pbs'] = PbsExecutor

