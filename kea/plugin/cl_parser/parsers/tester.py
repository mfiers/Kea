#!/usr/bin/env python

import argparse
import glob
import imp
import logging
import os
import sys

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
    with open(x) as F:
        for line in F:
            line = line.strip()
            if not line: continue
            mustfail = '+'
            if line[0] == '-':
                #shoudl fail!
                mustfail = '-'
                line = line[1:].strip()

            if line[0] == '#': continue

            try:
                res = parser.parse(line, rule_name="start", nameguard=False)
                success = '+'
            except Exception as e: #grako.exception.FailedParse as e:
                if args.x and mustfail != '-':
                    raise
                success = '-'


            testresult = '+:' if success == mustfail else '-:'
            print "{}{}{} : {}".format(testresult, mustfail, success, line)

            if not '+' in testresult and success == '+':
                print(res)
            



if not args.names:
    for x in glob.glob('*.test'):
        runtest(x)
else:
    for x in args.names:
        runtest(x)
    
