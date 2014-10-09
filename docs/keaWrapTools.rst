Wrapping tools with Kea
=======================

There are basically two methods of doing this:

  1. Link to the Kea executable.
  2. Write a short python script with the instructions.

The second approach gives you a lot more more flexibility in, for example, dealing with command line interpretation. However, the first option is enough for the majority of the commands.

Using symbolic links
--------------------

The first step is to find out where the Kea executable lives::

    which kea

Now, you want to create a link to the Kea executable. This link will serve as the executable that you will henceforth use instead of sleep. So, this needs to live in a convenient location. I tend to use `~/bin/kea` to group all my Kea tools together::

  mkdir -p ~/bin/kea
  cd ~/bin/kea

Kea knows which tool we're wanting to use by the name of the link. As an utterly boring example, we'll use the unix `sleep` command::

    ln -s sleep $(which kea)

Now you have a link called sleep. You can execute this


Dealing with subcommands
------------------------

We'll wrap, for example `Samtools <http://www.htslib.org//>`_ with Kea. Samtools has a subcommand structure. The following configuration instructs Kea how to use (a part of) samtools::

    samtools:
      version_command: "{{executable}} 2>&1 | grep 'Version:' | cut -f 2 -d' '"
      pbs:
        walltime: '01:00:00'
      subcommand:
        flagstat:
          filefind:
            input:
              position: 1
            output:
              pipe: stdout
        faidx:
          filefind:
            input:
              position: 1
            output:
              render: '{{files.input.filename}}.fai'


