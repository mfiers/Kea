
import leip

@leip.command
def list_executors(app, args):
    for x in app.conf['executors']:
        print x
