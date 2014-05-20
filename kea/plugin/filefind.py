
import leip
import sys

MADAPP = None


def flag_find(lst, flg, app):
    if not flg or not flg in lst:
        return []

    p_last = 0
    p = lst.index(flg)

    rv = []
    while p != -1:
        value = lst[p+1]
        madfile = app.get_madfile(value)
        rv.append(madfile)
        p_last = p
        try:
            p = lst.index(flg, p_last+1)
        except ValueError:
            break
    return rv


@leip.hook('prepare')
def prep_filefile(app):
    app.conf['input_files'] = []
    app.conf['output_files'] = []


@leip.hook('pre_run')
def find_input_file(app):

    ff_conf = app.conf.get('filefind')

    if not ff_conf:
        return

    iff = ff_conf['input_file_flag']
    off = ff_conf['output_file_flag']

    app.conf['input_files'].extend(flag_find(sys.argv, iff, app))
    app.conf['output_files'].extend(flag_find(sys.argv, off, app))
