import copy
import logging
import os
import subprocess as sp


from uuid import uuid4
from jinja2 import Template
import arrow

import leip

from kea.executor import BasicExecutor, get_deferred_cl


lg = logging.getLogger(__name__)


PBS_SUBMIT_SCRIPT_HEADER = """#!/bin/bash
#PBS -N {{appname}}.{{uuid}}
#PBS -e {{ cwd }}/pbs/{{appname}}.{{uuid}}.$PBS_JOBID.err
#PBS -o {{ cwd }}/pbs/{{appname}}.{{uuid}}.$PBS_JOBID.out
#PBS -l nodes={{nodes}}:ppn={{ppn}}

{%- if mem  %}
#PBS -l mem={{mem}}
{%- endif %}
{%- if account %}
#PBS -A {{ account }}{% endif %}
{%- if walltime %}
#PBS -l walltime={{ walltime }}{% endif %}

set -v

{%- if virtual_env %}

#load the same virtual env as was active during submission
source  "{{ virtual_env }}/bin/activate"
{% endif %}

#make sure we go to the working directory
cd {{ cwd }}

# start actual command

"""


class PbsExecutor(BasicExecutor):

    def __init__(self, app):

        super(PbsExecutor, self).__init__(app)
        if not os.path.exists('./pbs'):
            os.makedirs('./pbs')

        self.buffer = []
        self.cl_per_job =  self.app.kea_args.threads
        if self.cl_per_job == -1:
            self.cl_per_job = 1
        self.batch = 0
        self.clno = 0


    def submit_to_pbs(self):
        uuid = str(uuid4())[:8]

        #write pbs script
        pbs_script = os.path.join(
                  'pbs',
                  '{}.{}.pbs'.format(self.app.conf['appname'], uuid))

        template = Template(PBS_SUBMIT_SCRIPT_HEADER)

        data = copy.copy(self.app.conf['pbs'])

        data['appname'] = self.app.conf['appname']
        data['cwd'] = os.getcwd()
        data['uuid'] = uuid

        #virtual env?
        data['virtual_env'] = os.environ.get('VIRTUAL_ENV')

        lg.debug("submit to pbs with uuid %s", uuid)
        for info in self.buffer:

            #for logging.
            info['mode'] = 'asynchronous'
            info['submitted'] = arrow.utcnow()
            info['pbs_uuid'] = uuid
            info['pbs_script_file'] = pbs_script

        if not self.app.kea_args.pbs_nodes is None:
            data['nodes'] = self.app.kea_args.pbs_nodes
        elif not data['nodes']:
            data['nodes'] = 1

        if self.app.kea_args.pbs_ppn:
            data['ppn'] = self.app.kea_args.pbs_ppn
        elif not data['ppn']:
            data['ppn'] = self.cl_per_job

        with open(pbs_script, 'w') as F:
            data['name']
            F.write(template.render(**data))
            F.write("\n")
            for info in self.buffer:
                F.write("( " + " ".join(get_deferred_cl(info)))
                F.write(" ) & \n")
            F.write("wait\n")
            F.write('echo "done"\n')

        self.clno += 1

        #fire & forget the pbs job
        pbs_cl = ['qsub', pbs_script]

        if self.app.kea_args.pbs_dry_run:
            print " ".join(pbs_cl)
        else:
            P = sp.Popen(pbs_cl, stdout=sp.PIPE)
            o, e = P.communicate()
            pid = o.strip().split('.')[0]

            for info in self.buffer:
                info['pbs_jobid'] = pid

            lg.warning("Starting job: %s with pbs pid %s", pbs_script, pid)

        self.buffer = []
        self.batch += 1

    def fire(self, info):
        self.buffer.append(info)
        if len(self.buffer) >= self.cl_per_job:
            lg.info("submitting pbs job. No commands: %d",
                    len(self.buffer))
            self.submit_to_pbs()

    def finish(self):
        if len(self.buffer) > 0:
            lg.info("submitting pbs job. No commands: %d", len(self.buffer))
            self.submit_to_pbs()


@leip.hook('pre_argparse')
def prep_sge_exec(app):
    app.executors['pbs'] = PbsExecutor
    for a in '--pbs_nodes --pbs_ppn --pbs_account'.split():
        app.kea_arg_harvest_extra[a] = 1

    app.kea_argparse.add_argument('--pbs_nodes',
                                  help='No nodes requested (default=jobs '
                                  + 'submitted)', type=int)
    app.kea_argparse.add_argument('--pbs_ppn',
                                  help='No ppn requested (default=cl per '
                                  + 'job)', type=int)
    app.kea_argparse.add_argument('--pbs_account',
                                  help='Account requested (default none)')
    app.kea_argparse.add_argument('--pbs_dry_run',
                                  action='store_true',
                                  help='create script, do not submit)')





#pre_argparse
