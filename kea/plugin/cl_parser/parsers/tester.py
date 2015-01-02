#!/usr/bin/env python

import argparse
import collections
import glob
import imp
import logging
import os
from pprint import pprint
import sys

import yaml


#import grako.exception
parser = argparse.ArgumentParser()
parser.add_argument('-x', action='store_true')
parser.add_argument('names', nargs='*')

args = parser.parse_args()


logging.basicConfig(level=logging.INFO)
lg = logging.getLogger(__name__)

def runtest(x):

    base = x.replace('.test', '')
    
    lg.info("loading module %s", base)
    modinf = imp.find_module(base)
    mod = imp.load_module(base, *modinf)
    parser = getattr(mod, '{}Parser'.format(base))()

    def lineparser(F):
        line = F.readline()
        nextline = F.readline()

        while True:
            
            if nextline[0] == '>':
                
                tdata = yaml.load(nextline[1:].strip())
                def listifykeys(d):
                    for k, v in d.items():
                        if isinstance(v, dict):
                            listifykeys(v)
                        elif not isinstance(v, list):
                            d[k] = [v]
                listifykeys(tdata)
                yield line.strip(), tdata
                nextline = F.readline()
            else:
                yield line.strip(), None
            
            if not nextline:
                break
                
            line = nextline
            nextline = F.readline()

        if nextline is None and line:
            yield line, None
        elif nextline:
            yield nextline, None
                

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


    with open(x) as F:

        for line, test in lineparser(F):
            
            if test is None:
                tres = '.'

            mustfail = '+'
            if line[0] == '-':
                #must fail!
                mustfail = '-'
                line = line[1:].strip()

            if line[0] == '#': continue

            try:
                res = parser.parse(line, rule_name="start")
                success = '+'
            except Exception as e: #grako.exception.FailedParse as e:
                if args.x and mustfail != '-':
                    raise
                success = '-'
                
            if success == '+':
                data = astparse(res, data = {})
                if not test is None:
                    if test == data:
                        tres = '+'
                    else:
                        tres = '-'


            testresult = '+:' if success == mustfail else '-:'
            if tres == '-':
                testresult = '-'

            print "{}{}{}{} : {}".format(testresult, mustfail, success, tres, line)

            if not '+' in testresult and success == '+':
                pprint(data)
            if tres == '-':
                pprint(test)
            



if not args.names:
    for x in glob.glob('*.test'):
        runtest(x)
else:
    for x in args.names:
        runtest(x)
    
