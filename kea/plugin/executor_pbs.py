
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
        pbs_group.add_argument('-j', dest='cl_per_job', type=int, default=1,
                               help='no of cls running parallel per job')
        pbs_group.add_argument('--ppn', dest='pbs_ppn', type=int, default=1,
                               help='No ppn requested')
        pbs_group.add_argument('--module', help='module to load',
                               action='append', default=[])
        pbs_group.add_argument('--mem', help='node memory to request of pbs', dest='pbs_mem',
                               default='8gb')
        pbs_group.add_argument('-A', '--pbs_account',
                               help='Account requested (default none)')
        pbs_group.add_argument('-w', '--pbs_walltime',
                                help=('max time that this process can take'))


PBS_SUBMIT_SCRIPT_HEADER = """#!/bin/bash
#PBS -N {{appname}}.{{uid}}.{{batch}}
#PBS -e {{ cwd }}/{{appname}}.{{uid}}.$PBS_JOBID.err
#PBS -o {{ cwd }}/{{appname}}.{{uid}}.$PBS_JOBID.out
#PBS -l nodes={{pbs_nodes}}:ppn={{pbs_ppn}}
#PBS -l mem={{pbs_mem}}
{% if pbs_account -%}
  #PBS -A {{ pbs_account }}{% endif %}
{% if pbs_walltime -%}
  #PBS -l walltime={{ pbs_walltime }}{% endif %}

set -v  # verbose output
set -e  # catch errors

{% for mod in module %}
module load {{ mod }}{% endfor %}

# make sure we're in the work directory
cd {{ cwd }}

{%if virtualenv %}
#load virtual environment
source {{ virtualenv }}/bin/activate
{% endif %}


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
        pbs_script = '{}.{}.{:03d}.pbs'.format(self.app.name, uid, self.batch)

        template = Template(PBS_SUBMIT_SCRIPT_HEADER)

        data = dict(self.app.defargs)

        if "VIRTUAL_ENV" in os.environ:
            lg.warning("virtual env: %s", os.environ['VIRTUAL_ENV'])
            data['virtualenv'] = os.environ['VIRTUAL_ENV']

        data['appname'] = self.app.name
        data['cwd'] = os.getcwd()
        data['uid'] = uid
        data['batch'] = self.batch


        lg.debug("submit to pbs with uid %s", uid)
        for info in self.buffer:

            info['submitted'] = arrow.utcnow()
            info['pbs_uid'] = uid
            info['pbs_script_file'] = pbs_script
            info['deferred'] = True
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

        if info.get('skip'):
            lg.debug("Pbs submit skip")
            return
        self.buffer.append(copy.copy(info))
        info['returncode'] = 0
        info['status'] = 'queued'
        self.app.run_hook('post_fire', info)
        if len(self.buffer) >= self.app.defargs['cl_per_job']:
            lg.warning("submitting pbs job. No commands: %d", len(self.buffer))
            self.submit_to_pbs()

    def finish(self):
        if len(self.buffer) > 0:
            lg.info("submitting pbs job. No commands: %d", len(self.buffer))
            self.submit_to_pbs()


conf = leip.get_config('kea')
conf['executors.pbs'] = PbsExecutor
