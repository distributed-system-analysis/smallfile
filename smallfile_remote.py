#!/usr/bin/python
'''
smallfile_cli.py -- CLI user interface for generating metadata-intensive workloads
Copyright 2012 -- Ben England
Licensed under the Apache License at http://www.apache.org/licenses/LICENSE-2.0
See Appendix on this page for instructions pertaining to license.
'''

# because it uses the "multiprocessing" python module instead of "threading"
# module, it can scale to many cores
# all the heavy lifting is done in "invocation" module,
# this script just adds code to run multi-process tests
# this script parses CLI commands, sets up test, runs it and prints results
#
# how to run:
#
# ./smallfile_cli.py 
#
import sys
import os
import os.path
import errno
import threading
import time
import socket
import string
import parse
import pickle
import math
import random
import shutil

# smallfile modules
import ssh_thread
import smallfile
from smallfile import smf_invocation, ensure_deleted, ensure_dir_exists, get_hostname, hostaddr
from smallfile import OK, NOTOK
import invoke_process
import sync_files
import output_results
import smf_test_params
import multi_thread_workload
import parse_slave

# main routine that does everything for this workload

def run_workload():
  # if a --host-set parameter was passed, it's a multi-host workload
  # each remote instance will wait until all instances have reached starting gate
   
  params = parse_slave.parse()
  if params.master_invoke.verbose: print 'slave params: %s'%str(params)
  return multi_thread_workload.run_multi_thread_workload(params)

# for future windows compatibility, all global code (not contained in a class or subroutine)
# must be moved to within a routine unless it's trivial (like constants)
# because windows doesn't support fork().

if __name__ == "__main__":
  run_workload()
