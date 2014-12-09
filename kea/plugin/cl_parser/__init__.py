"""
Parse command lines using grako generated parsers
"""

import logging
import imp

from grako.exceptions import FailedParse

import leip

lg = logging.getLogger(__name__)
#lg.setLevel(logging.DEBUG)

PMODS = {}


@leip.hook('pre_fire')
def parse_commandline(app, jinf):
    
    global PMODS

    lg.debug("pre_fire start for command: %s", app.name)
        
    if app.name in PMODS:
        parser = PMODS[app.name]
    else:
        #find module
        for ml in app.conf['plugin.cl_parser.parse_locations']:
            modname = '{}.{}'.format(ml, app.name)
            try:
                module = __import__(modname, fromlist=[app.name])
                break
            except ImportError:
                #no module found - ignore
                continue
        else:
            lg.debug("unable to import a parser module for %s", app.name)
            return

        parserclass = getattr(module, '{}Parser'.format(app.name))
        parser = parserclass()

        PMODS[app.name] = parser

        
    cl = " ".join([app.name] + jinf['cl'][1:])
    lg.debug("parsing cl: %s", cl)
    
    try:
        p = parser.parse(cl, rule_name='start')
    except FailedParse:
        lg.info("Cannot parse command line: %s", cl)
        return

    ast = p[1]
    if len(ast) == 0:
        return

    jinf['ast'] = jinf.get('ast', {})
    for k in ast:
        v = ast[k]
        if not v: continue
#        if not isinstance(v, list):
#            v = [v]
        jinf['ast'][k] = v

    
