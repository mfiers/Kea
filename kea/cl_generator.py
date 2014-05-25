import sys


def basic_command_line_generator(app):
    """
    Most basic command line generator possible
    """
    cl = [app.conf['executable']] + sys.argv[1:]
    yield cl
