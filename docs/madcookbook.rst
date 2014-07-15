Mad Cookbook
============

Basics
------

Get help::

    mad -h

    mad set -h

Output debugging information::

    mad -v

    mad -v set ...

Note that the -v needs to come before any subcommand


Annotate
--------

Annotate a file with a key value pair::

    mad set sample_name sample_a file_a.txt

You can do this for a bunch of files at the same time::

    mad set sample_name sample_a *.txt

Or even by running::

    find . -size +10k -name '*.txt' | mad set sample_name sample_a


To see which keywords are allowed?::

    mad keywords

It is possible to use a keyword that is not registered using the `-f` flag::

    mad set -f somethink_else anyvalue file_b.txt
