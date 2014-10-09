Mad Installation
================

Prerequisites
-------------

Mad requires MongoDb running. Currently, (this will change), MongoDb is expected to run without any form of authentication.


Install Mad2
------------
I suggest to install Mad inside a virtual environment. See:

* http://docs.python-guide.org/en/latest/dev/virtualenvs/
* https://virtualenv.pypa.io/en/latest/


Mad can be installed using::

    pip install mad2

After installation,


Configure Mad
-------------

If MongoDb runs on the same server as Mad2, no configuratino is necessary. Otherwise, you will need to run::

    mad conf set plugin.mongo.host: <HOSTNAME>
    mad conf set store.mongo.host: <HOSTNAME>

