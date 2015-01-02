"""
Parse command lines using grako generated parsers
"""
import collections
import importlib
import logging
import pkg_resources
import re
import shlex
import time

import grako
import leip
import yaml

lg = logging.getLogger(__name__)
# lg.setLevel(logging.DEBUG)

#thanks: http://tinyurl.com/nttpj9
def convert_to_str(data):
    if isinstance(data, basestring):
        return str(data)
    elif isinstance(data, collections.Mapping):
        return dict(map(convert_to_str, data.iteritems()))
    elif isinstance(data, collections.Iterable):
        return type(data)(map(convert_to_str, data))
    else:
        return data

def astparse(ast, data={}):
    if isinstance(ast, list):
        [astparse(x, data) for x in ast]
    elif isinstance(ast, dict):
        data.update(convert_to_str(ast))
    elif isinstance(ast, (str, unicode)):
        pass
    else:
        print('x' * 80, ast)
    return data


class KeaSemantics:
    def __init__(self, meta):
        self.meta = meta
        self.options = {}
        self.files = {}

    def _default(self, ast):
        if not isinstance(ast, grako.ast.AST):
            return

        for k, v in ast.iteritems():
            if not isinstance(v, list):
                continue
            if len(v) == 0:
                continue
            if not k in self.meta:
                continue

            v = map(str, v)

            kmeta = self.meta[k]
            ktype = kmeta['type']
            if ktype in ['option', 'other']:
                if not k in self.options:
                    self.options[k] = []
                self.options[k].extend(v)
            elif ktype in ['file']:
                if not k in self.files:
                    self.files[k] = dict(category=kmeta['category'],
                                         path = [])
                self.files[k]['path'].extend(v)

PARSERS = {}

@leip.hook('pre_fire')
def parse_commandline(app, jinf):

    global MODS

    start = time.time()
    
    if app.name in PARSERS:
        parser = PARSER[app.name]
    else:
        modpath = 'kea.plugin.cl_parser.parsers.{}'.format(app.name)
        metamodpath = 'kea.plugin.cl_parser.parsers.{}_meta'.format(app.name)

        mod = importlib.import_module(modpath)
        modm = importlib.import_module(metamodpath)

        parser = getattr(mod, '{}Parser'.format(app.name))()
        parser.meta = modm.meta
        PARSERS[app.name] = parser
        
    cl = " ".join(app.cl)

    semantics = KeaSemantics(modm.meta)

    try:
        ast = parser.parse(cl, rule_name="start", semantics=semantics)
    except Exception as e:
        lg.warning("Cannot cl parse")
        raise

    if not 'files' in jinf:
        jinf['files'] = {}
    jinf['files'].update(semantics.files)
    if not 'optioins' in jinf:
        jinf['options'] = {}
    jinf['options'].update(semantics.options)

    stop = time.time()
    lg.debug("clparse took %s seconds", stop-start)

