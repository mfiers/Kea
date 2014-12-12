
from collections import OrderedDict
import logging

import arrow
from mad2 import madfile
import leip
from lockfile import FileLock

lg = logging.getLogger(__name__)

def to_str(s):
    if isinstance(s, madfile.MadFile):
        if 'sha1sum' in s:
            return '{} (sha1: {})'.format(s['inputfile'], s['sha1sum'])
        else:
            return '{}'.format(s['inputfile'])
    else:
        return str(s)


@leip.hook('pre_argparse')
def logger_arg_define(app):
    app.parser.add_argument('-S', '--report_screen', action='store_true')
    app.parser.add_argument('-Y', '--report_yaml', action='store_true')

@leip.hook('post_fire')
def log_screen(app, jinf):
    
    if app.args.report_yaml:
        import yaml
        fn = '{}.report.yaml'.format(jinf['run_uid'])
        with open(fn, 'w') as F:
            yaml.dump(jinf, F, default_flow_style=False)
        
    
    if not app.args.report_screen:
        return

    def dictprint(d, pref=""):
        mxkyln = max([len(x) for x in d.keys()])
        fs = pref + '{:<' + str(mxkyln) + '} : {}'
        for k in sorted(d.keys()):        
            v = d[k]
            if k in ['cl', 'template_cl']:
                v = " ".join(v)
                
            if v is None: continue
            if v == "": continue
            if not isinstance(v, dict):
                print fs.format(k, v)
            else:
                dictprint(v, '{}.'.format(k))
                
    print '--KEA-REPORT' + '-' * 68
    dictprint(jinf)
    print '-' * 80
    
@leip.hook('post_run')
def log_cl(app):
    all_jinf = app.all_jinf
    try:
        with FileLock('kea.log'):
            for i, info in enumerate(all_jinf):
                with open('kea.log', 'a') as F:
                    F.write("-" * 80 + "\n")
                    for i in info:
                        F.write("{}: ".format(i))
                        val = info[i]
                        if i == 'cl':
                            F.write(" ".join(val) + "\n")
                        elif isinstance(val, list):
                            F.write("\n")
                            for lv in val:
                                F.write(' - {}\n'.format(to_str(lv)))
                        else:
                            F.write(" {}\n".format(to_str(val)))

    except:
        lg.warning("Cannot write to log file")
