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
        self.options = collections.defaultdict(list)
        self.files = collections.defaultdict(dict)

        for k, m in meta.iteritems():
            if 'default' in m:
                if m['type'] == 'flag':
                    self.set_value(k, True)
                else:
                    self.set_value(k, m['default'])

    def set_value(self, k, v):

        if isinstance(v, collections.Mapping):
            v = map(str, v)
        elif isinstance(v, unicode):
            v = str(v)

        kmeta = self.meta[k]
        ktype = kmeta['type']
        kcard = kmeta.get('cardinality', None)
        if kcard is None:
            kcard = '1' if ktype == 'flag' else '+'

        if kcard == '+' and not isinstance(v, list):
            v = [v]
        if kcard == '1' and isinstance(v, list):
            v = v[0]

        if ktype in ['option', 'other', 'flag']:
            if kcard == '1': 
                self.options[k] = v
            else:
                self.options[k].extend(v)

        if ktype == 'file':
            print k, v, kcard, kmeta
            self.files[k]['category'] = kmeta['category']
            if kcard == '1':
                self.files[k]['path'] = v
            else:
                self.files[k]['path'] = self.files[k].get('path', []) + v

        

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

        
            self.set_value(k, v)

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

