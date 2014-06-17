
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


def find_input_file(app, info):
    ff_conf = app.conf.get('filefind')

    if not ff_conf:
        return

    iff = ff_conf['input_file_flag']
    off = ff_conf['output_file_flag']

    if not 'input_files' in info:
        info['input_files'] = []
    if not 'output_files' in info:
        info['output_files'] = []

    info['input_files'].extend(flag_find(sys.argv, iff, app))
    info['output_files'].extend(flag_find(sys.argv, off, app))


# @leip.hook('pre_run')
# def hook_pre_run(app):
#     ff_conf = app.conf.get('filefind')
#     print ff_conf


@leip.hook('pre_fire')
def hook_find_input_file(app, info):
    return find_input_file(app, info)


