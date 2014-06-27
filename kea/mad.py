



MADAPP = None


def get_madfile(filename):
    global MADAPP

    if MADAPP is None:
        app = leip.app('mad2')
        print app

