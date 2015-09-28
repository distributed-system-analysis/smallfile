#!/usr/bin/python
# -*- coding: utf-8 -*-
# launch_smf_host.py
# background process which waits for smallfile_remote.py workload to run
# you must run this process using the python interpreter explicitly.
# This handles the case where we are running windows or other non-linux OS.
# Example: python launch_smf_host.py shared-directory

import sys
import os
import time
import errno
import smallfile

OK = 0
NOTOK = 1


def myabort(msg):
    print(msg)
    sys.exit(NOTOK)


# parse command line

if len(sys.argv) < 3:
    myabort('usage: python launch_smf_host.py \
--shared shared-directory [ --top top-directory ] [ --as-host as-host-name ] ')

shared_dir = None
as_host = smallfile.get_hostname(None)
j = 1
while j < len(sys.argv):
    nm = sys.argv[j]
    if len(nm) < 3:
        myabort('parameter name must be > 3 characters long and start with --')
    nm = nm[2:]
    val = sys.argv[j + 1]
    j += 2
    if nm == 'shared':
        shared_dir = val
        top_dir = shared_dir
    elif nm == 'top':
        top_dir = val
    elif nm == 'as-host':
        as_host = val
    else:
        myabort('unrecognized parameter --%s' % nm)
if not shared_dir:
    myabort('must define --shared parameter')

# look for launch files, read smallfile_remote.py command from them,
# and execute, substituting --shared directory for --top directory,
# to allow samba to work with Linux test driver

launch_fn = os.path.join(shared_dir, as_host) + '.smf_launch'
if os.path.exists(launch_fn):  # avoid left-over launch files
    os.unlink(launch_fn)
print('launch filename ' + launch_fn)
while True:
    try:
        with open(launch_fn, 'r') as f:
            cmd = f.readline().strip()
            f.close()
            os.unlink(launch_fn)
            print('launcher sees cmd: %s' % cmd)
            # substitute --shared directory for --top directory if they are different
            if top_dir != shared_dir:
                cmd = cmd.replace(shared_dir, top_dir)
                print('launcher edits cmd to : %s' % cmd)
            rc = os.system(cmd)
            if rc != OK:
                print('ERROR: return code %d for cmd %s' % (rc, cmd))
    except IOError as e:
        if e.errno != errno.ENOENT:
            raise e
    finally:
        time.sleep(1)
