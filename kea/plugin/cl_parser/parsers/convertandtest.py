#!/usr/bin/env python

import glob
import os
import sys
import tempfile
import subprocess as sp

if len(sys.argv) > 1 and sys.argv[1] == '-v':
    VERBOSE = True
    sys.argv = sys.argv[2:]
else:
    VERBOSE = False

if len(sys.argv) > 1:
    select = " ".join(sys.argv[1:])
else:
    select = ""

for ebnf in glob.glob('*.ebnf'):
    pyfile = ebnf.replace('.ebnf', '.py')

    if os.path.exists(pyfile):
        pyfiletime = os.stat(pyfile).st_mtime
        ebnffiletime = os.stat(ebnf).st_mtime
        if pyfiletime >= ebnffiletime:
            #print pyfiletime
            #print ebnffiletime
            #print pyfiletime > ebnffiletime
            print("skipping %s (not changed" % ebnf)
            continue

    cl = "grako {} > {}".format(ebnf, pyfile)
    P = sp.Popen(cl, shell=True)
    P.communicate()
    if P.returncode != 0:
        print "compilation fail", ebnf
        os.unlink(pyfile)
        exit(-1)

    
    testfile = ebnf.replace('.ebnf', '.test')
    
    testsnippet = ""
    def test(pyfile, snip):

        if select and (not select in snip):
            return
        
        snip = snip.strip()
        
        if not snip: return

        if snip[0] == '-':
            shouldfail = True
            snip = snip[1:].strip()
        else:
            shouldfail = False
            
        tf = tempfile.NamedTemporaryFile('w', delete=False)
        tf.write(snip)
        tf.close()

        cl = "python {} {} start".format(pyfile, tf.name)
        P = sp.Popen(cl, shell=True, stdout=sp.PIPE, stderr=sp.PIPE)
        out, err = P.communicate()
        rc = P.returncode

        if shouldfail and rc != 0:
            print "OK (FAIL)", snip
            if VERBOSE:
                print out
            return True
        elif (not shouldfail) and rc == 0:
            print 'OK', snip
            if VERBOSE:
                print out
            return True
        elif shouldfail and rc == 0:
            print "NOT OK (did not fail)", snip
            print out
            print err
            exit(-1)
        else:
            print "NOT OK", snip
            print out
            print err
            exit(-1)
        
    with open(testfile) as F:
        for line in F:
            line = line.strip()
            if not line:
                test(pyfile, testsnippet)
                testsnippet = ""
            else:
                testsnippet += " " + line
                
    test(pyfile, testsnippet)
        

