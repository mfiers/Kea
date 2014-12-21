"""
Parse command lines using grako generated parsers
"""
from collections import OrderedDict
import logging
import pkg_resources
import re
import shlex
import time

import leip
import yaml

lg = logging.getLogger(__name__)
# lg.setLevel(logging.DEBUG)

RULESETS = {}


def ordered_load(stream, Loader=yaml.Loader, object_pairs_hook=OrderedDict):
    class OrderedLoader(Loader):
        pass
    def construct_mapping(loader, node):
        loader.flatten_mapping(node)
        return object_pairs_hook(loader.construct_pairs(node))
    OrderedLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping)
    return yaml.load(stream, OrderedLoader)


class KA(object):
    def __init__(self, *args, **kwargs):
        for k in kwargs:
            v = kwargs[k]
            if isinstance(v, list):
                self.__dict__[k] = v
            elif isinstance(v, unicode):
                self.__dict__[k] = kwargs[k].encode("ASCII")
    def __repr__(self):
        try:
            return "{}({})".format(self.tag, self.data)
        except:
            return "???({})".format(self.data)

class YF(yaml.YAMLObject):
    @classmethod
    def from_yaml(cls, loader, node):
        Kclass = 'K' + cls.__name__[1:]
        if not '|' in node.value:
            data = node.value
            vals = []
            keyvals = {}
        else:
            nodevalsplit = node.value.split('|')
            data = nodevalsplit[0]
            vals = []
            keyvals = {}
            for nvs in nodevalsplit:
                if '=' in nvs:
                    k, v = nvs.split('=', 1)
                    keyvals[k] = v
                else:
                    vals.append(nvs)

        return eval(Kclass)(tag=cls.yaml_tag, data=data, vals=vals, **keyvals)

        
class KSearch(KA):
    def __call__(self, cl, jinf):
        rex = re.compile(self.data)
        found =  rex.search(str(cl))
        if found:
            right = rex.sub("", cl)
            return cl, right
        else:
            return cl, False
            
class KFlagVal(KA):
    def __call__(self, cl, jinf):
        recl = shlex.split(cl)
        rv = None
        for v in self.vals:
            if v in recl:
                flagpos = recl.index(v)
                if flagpos < len(recl):
                    newcl = " ".join(recl[:flagpos] + recl[flagpos+2:])
                    return newcl, recl[flagpos+1]
        if hasattr(self, 'default'):
            return cl, self.default
        return cl, False

                    
class KFlag(KA):
    def __call__(self, cl, jinf):
        recl = shlex.split(cl)
        rv = None
        if self.data in recl:
            flagpos = recl.index(self.data)
            newcl = " ".join(recl[:flagpos] + recl[flagpos+1:])
            return newcl, True
        return cl, False

class KHarvest(KA):    
    def __call__(self, cl, jinf):
        no_to_harvest = self.data
        if no_to_harvest == 'all':
            return "", cl
        no_to_harvest = int(no_to_harvest)
        recl = shlex.split(cl)
        if no_to_harvest > 0:
            harvest = recl[:no_to_harvest]
            remain = recl[no_to_harvest:]
            return " ".join(remain), " ".join(harvest)
        return cl, False

class KEmit(KA):
    def __call__(self, cl, jinf):
        return cl, self.data

class KFormat(KA):
    def __call__(self, cl, jinf):
        return cl, self.data.format(cl)

class KSet(KA):
    def __call__(self, cl, jinf):
        if not str(cl).strip():
            return cl
        p = jinf.get('parameters', {})
        p[self.data] = cl
        jinf['parameters'] = p
        return cl
        
class KSetFile(KA):
    def __call__(self, cl, jinf):
        cat, name = self.data.split('/', 1)
        f = jinf.get('files', {})
        f[name] = dict(file=cl, category=cat)
        jinf['files'] = f
        return cl

class YFlagVal(YF):
    yaml_tag = u"!FlagVal"

class YFlag(YF):
    yaml_tag = u"!Flag"

class YFormat(YF):
    yaml_tag = u"!Format"

class YEmit(YF):
    yaml_tag = u"!Emit"

class YSearch(YF):
    yaml_tag = "!Search"

class YSet(YF):
    yaml_tag = "!Set"

class YHarvest(YF):
    yaml_tag = "!Harvest"

class YSetFile(YF):
    yaml_tag = "!SetFile"


@leip.hook('pre_fire')
def parse_commandline(app, jinf):

    start = time.time()
    
    for ruleloc in app.conf['plugin.cl_parser.parse_locations']:
        try:
            rules = pkg_resources.resource_string(
                ruleloc, '{}.ruleset'.format(app.name))
            break
        except IOError:
            #not found
            continue
    else:
        # no rules found
        return

    cl = " ".join(app.cl)

    parser = yaml.load(rules)

    _mapping_tag = yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG

    def dict_representer(dumper, data):
        return dumper.represent_dict(data.iteritems())

    def dict_constructor(loader, node):
        return OrderedDict(loader.construct_pairs(node))

    yaml.add_representer(OrderedDict, dict_representer)
    yaml.add_constructor(_mapping_tag, dict_constructor)

    parser = yaml.load(rules)
    
    def parse_apply_list(actorlist, cl, jinf):
        for actor in actorlist:
            result = actor(cl, jinf)
            if result is False: break
            lg.debug('actor -- %s -- %s' % (actor, result))
            cl = result

    def parse_apply_dict(parser, cl, jinf):
        for matcher, followup in parser.iteritems():
            cl, right = matcher(cl, jinf)

            lg.debug('match -- %s LEFT: %s RIGHT: %s ' % (matcher, cl, right))

            if right is False:
                continue

            if isinstance(followup, dict):
                parse_apply_dict(followup, right, jinf)
                
            elif isinstance(followup, list):
                parse_apply_list(followup, right, jinf)

    parse_apply_dict(parser, cl, jinf)

    stop = time.time()
    lg.debug("clparse took %s seconds", stop-start)

