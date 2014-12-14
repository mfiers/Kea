
from collections import OrderedDict
import logging
from datetime import datetime, timedelta
import calendar


import humanize
from lockfile import FileLock


import leip

lg = logging.getLogger(__name__)

def to_str(s):
    return str(s)
    # if isinstance(s, madfile.MadFile):
    #     if 'sha1sum' in s:
    #         return '{} (sha1: {})'.format(s['inputfile'], s['sha1sum'])
    #     else:
    #         return '{}'.format(s['inputfile'])
    # else:
    #     return str(s)
    
FSIZEKEYS = ["ps_meminfo_max_rss", "ps_meminfo_max_vms",
             "ps_sys_swap_free", "ps_sys_swap_sin",
             "ps_sys_swap_sout", "ps_sys_swap_total",
             "ps_sys_swap_used", "ps_sys_vmem_active",
             "ps_sys_vmem_available", "ps_sys_vmem_buffers",
             "ps_sys_vmem_cached", "ps_sys_vmem_free",
             "ps_sys_vmem_inactive", "ps_sys_vmem_total",
             "ps_sys_vmem_used"]


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
            yaml.safe_dump(dict(jinf), F)
    
    if not app.args.report_screen:
        return

    def nicetime(t):
        """
        assuming t is in utc
        """
        
        timestamp = calendar.timegm(t.timetuple())
        loct = datetime.fromtimestamp(timestamp)
        assert t.resolution >= timedelta(microseconds=1)
        loct.replace(microsecond=t.microsecond)
        
        return '{} ({})'.format(humanize.naturaltime(loct), t)
        
    def dictprint(d, pref=""):
        mxkyln = max([len(x) for x in d.keys()])
        fs = pref + '{:<' + str(mxkyln) + '} : {}'
        for k in sorted(d.keys()):        
            v = d[k]
            if k in ['cl', 'template_cl']:
                v = " ".join(v)
                
            if v is None: continue
            if v == "": continue
            if k in FSIZEKEYS:
                v = "{} ({})".format(humanize.naturalsize(v), v)
            elif k in ['start', 'stop']:
                v = nicetime(v)
            elif k == 'runtime':
                v = '{}s ({})'.format(humanize.intword(v), v)
            elif k.endswith('_percent'):
                v = '{}%'.format(v)
            
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
