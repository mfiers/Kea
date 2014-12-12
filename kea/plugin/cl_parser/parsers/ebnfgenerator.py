#!/usr/bin/env python

import re
import sys
from collections import OrderedDict

import yaml

psplit = re.compile('#[-]')

clfile = sys.argv[1]

def interject(r, inter = '|'):
    for i, e in enumerate(r):
        if i > 0:
            yield inter
        yield e

def process_endnode(n):
    if not n.strip():
        return "()"
    if n.startswith("sp#"):
        return n[3:]
    if re.search(r'^[a-zA-Z_]+!!', n):
        name, nnode = n.split("!!", 1)
        return "{}:{}".format(name, process_node(nnode))
    if n.startswith("/") and n.endswith("/"):
        return n + " /\s*/"
    else:
        return  '"{}" /\s*/'.format(n)

def process_listnode(n):
    return ["("] + map(process_node, n), [")"]

def process_oneofnode(n):
    return ["("] + list(interject(map(process_node, n), '|')) + [")"]

def process_namednode(n):
    name = n['name']
    value = n['value']
    return "{}:{}".format(name, process_node(value))


def process_zeroormore(n):
    return ["{"] + list(interject(map(process_node, n), '|')) + ["}"]

def process_dictnode(n):
    assert len(n) == 1
    k, v = n.items()[0]
    if k == 'oneof':
        return process_oneofnode(v)
    elif k == 'zeroormore':
        return process_zeroormore(v)
    elif k == 'named':
        return process_namednode(v)
    else:
        print "\n\n\nPROBLEM\n"
        print(k)
        print(v)
        exit()
 

def process_node(n=""):
    if isinstance(n, str):
        return process_endnode(n)
    elif isinstance(n, list):
        return process_listnode(n)
    elif isinstance(n, dict):
        return process_dictnode(n)

def listprint(lst, indent=""):
    for i in lst:
        if isinstance(i, str):
            print indent + i
        elif isinstance(i, list) or isinstance(i, tuple):
            listprint(i, indent+"  ")

def blockparser(F):
    
    for line in F:
    
with open(sys.argv[1]) as F:
    rv = ["start = "]
    for block in blockparser(F):
        print(block)
    
#    listprint(process_node(data))
#    print(" ; ")
