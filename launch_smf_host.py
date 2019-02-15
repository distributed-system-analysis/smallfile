#!/usr/bin/python
# -*- coding: utf-8 -*-
# launch_smf_host.py
# background process which waits for smallfile_remote.py workload to run
# you must run this process using the python interpreter explicitly.
# This handles the case where we are running windows or other non-linux OS.
# it also handles containers, which typically don't come with sshd
#
# if you are doing all Linux with containers, then
# you need to specify container ID in Docker startup command
# if your mountpoint for the shared storage is /mnt/fs:
#   CMD: python launch_smf_host.py --top $top_dir --as-host container$container_id
# you could include this as the last line in your docker file
# and fill in top_dir and container_id as environment variables in 
# your docker run command using the -e option
# # docker run -e top_dir=/mnt/fs/smf -e container_id="container-2"
#
# we substitute --top directory with --substitute_top directory
# so that Windows clients can run with Linux test drivers,
# which cannot have the same pathname for the shared directory
# as the Windows clients, so you don't need to specify
# --substitute_top in any other situation.
#
# Example for Windows: 
# if mountpoint on Linux test driver is /mnt/cifs/testshare
# and mountpoint on Windows is z:\
# you run:
#   python launch_smf_host.py \
#              --top /mnt/cifs/testshare/smf
#              --substitute_top z:\smf
#
# 
import sys
import os
import time
import errno
import smallfile
import logging
import socket

OK = 0
NOTOK = 1

def start_log(prefix = socket.gethostname()):
    log = logging.getLogger(prefix)
    if os.getenv('LOGLEVEL_DEBUG') != None:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)
    log_format = prefix + '%(asctime)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(log_format)

    h = logging.StreamHandler()
    h.setFormatter(formatter)
    log.addHandler(h)

    h2 = logging.FileHandler('/var/tmp/launch_smf_host.%s.log' % prefix)
    h2.setFormatter(formatter)
    log.addHandler(h2)

    log.info('starting log')
    return log

def usage(msg):
    print(msg)
    print('usage: python launch_smf_host.py'
            '--top top-directory '
            '[ --substitute-top synonym-directory ]'
            '[ --as-host as-host-name ] ')
    sys.exit(NOTOK)


# parse command line

if len(sys.argv) < 3:
    usage('required command line arguments missing')

substitute_dir = None
top_dir = None
as_host = smallfile.get_hostname(None)
j = 1
while j < len(sys.argv):
    if len(sys.argv) == j + 1:
        usage('every parameter name must have a value')
    nm = sys.argv[j]
    if len(nm) < 3:
        usage('parameter name must be > 3 characters long and start with --')
    nm = nm[2:]
    val = sys.argv[j + 1]
    j += 2
    if nm == 'substitute-top':
        substitute_dir = val
    elif nm == 'top':
        top_dir = val
    elif nm == 'as-host':
        as_host = val
    else:
        usage('unrecognized parameter --%s' % nm)
if not top_dir:
    usage('you must specify --top directory')
log = start_log(prefix=as_host)
log.info('substitute-top %s, top directory %s, as-host %s' % 
        (substitute_dir, top_dir, as_host))

# look for launch files, read smallfile_remote.py command from them,
# and execute, substituting --shared directory for --top directory,
# to allow samba to work with Linux test driver

network_shared_path = os.path.join(top_dir, 'network_shared')
launch_fn = os.path.join(network_shared_path, as_host) + '.smf_launch'
if os.path.exists(launch_fn):  # avoid left-over launch files
    os.unlink(launch_fn)
log.info('launch filename ' + launch_fn)
while True:
    try:
        with open(launch_fn, 'r') as f:
            cmd = f.readline().strip()
        os.unlink(launch_fn)
        if substitute_dir != None:
            cmd = cmd.replace(substitute_dir, top_dir)
        log.debug('spawning cmd: %s' % cmd)
        rc = os.system(cmd)
        if rc != OK:
            log.debug('ERROR: return code %d for cmd %s' % (rc, cmd))
    except IOError as e:
        if e.errno != errno.ENOENT:
            raise e
    finally:
        time.sleep(1)
