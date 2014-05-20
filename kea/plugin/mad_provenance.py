
import leip
import sys
import subprocess as sp

from mad2.recrender import recrender
#from mad2.plugin.checksum import apply_checksum_madfile

# @leip.hook('finish')
# def annotate_provenance(app):

#     if not app.conf['output_files']:
#         #no output files - nothing to annotate - move on
#         return

#     #sha1:
#     for a in app.conf['output_files']:
#         apply_checksum_madfile({}, a, 'sha1')

#     # for tool in app.conf['annotate']:
#     #     tinfo = app.conf['annotate'][tool]
#     #     key = tinfo['key']
#     #     key = recrender(key, app.conf)
#     #     val = None
#     #     if 'value' in tinfo:
#     #         val = tinfo['value']
#     #         val = recrender(val, app.conf)
#     #     elif 'command' in tinfo:
#     #         comm = tinfo['command']
#     #         comm = recrender(comm, app.conf)
#     #         val = sp.Popen(comm, shell=True,
#     #                        stdout=sp.PIPE).communicate().strip()
#     #     if val:
#     #         kvpairs.append((key, val))

#     # print kvpairs
#     # # if 'provenance.version_command' in app.conf:
#     # #     vcm = app.conf['provenance.version_command']
#     # #     vcm = recrender(vcm, app.conf)
#     # #     version, _ = sp.Popen(vcm, shell=True, stdout=sp.PIPE).communicate()
#     # #     version = version.strip()

#     # cl.append('-g')
#     # cl.append("{}".format(app.conf['appname']))
#     # cl.append("{}".format(app.conf['executable']))
#     # cl.append("{}".format('1'))

#     # for i in app.conf['input_files']:

#     #     cl.append('--derived_from')
#     #     cl.append(i)

#     # for o in app.conf['output_files']:
#     #     cl.append(o)
#     # #print " ".join(cl)
#     # if app.conf.get('command_echo'):
#     #     print " ".join(cl)

#     #sp.Popen(cl).communicate()
