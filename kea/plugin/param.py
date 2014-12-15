
import os
import re

import leip

import toMaKe.param

@leip.hook('prepare')
def harvest_params(app):
    app.param = toMaKe.param.get_recursive_param(os.getcwd(), 'kea.config')
    
    
@leip.hook('pre_fire')
def render_param(app, info):
    cl = info['cl']
    findpar = re.compile(r'{([a-zA-Z_][a-zA-Z0-9_]*)}')

    for i, argument in enumerate(cl):
        while True:
            done = False
            for fp in findpar.finditer(argument):
                nm = fp.groups()[0]
                repl = app.param[nm]
                
                if not repl:
                    #do not have a value for this variable - continue
                    continue
                    
                argument = findpar.sub(app.param[nm], argument)
                #have  a value - restart, because 'argument' has changed
                break
            else:
                #nothing new found, nothing to replace then, done
                done=True
                break

            if done:
                break

        #replace argument in commandline
        cl[i] = argument

    #replace command line
    info['cl'] = cl


        
#    print(cl)
