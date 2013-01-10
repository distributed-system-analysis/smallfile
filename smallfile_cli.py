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
import smallfile
from smallfile import smf_invocation, ensure_deleted, short_hostname, hostaddr
import invoke_process
import threading
import time
import socket
import string
import parse
import pickle
import ssh_thread
import math
import random

class SMFResultException(Exception):
  def __init__(self, msg):
    Exception.__init__(self)
    self.msg = msg

  def __str__(self):
    return self.msg


OK = 0  # system call return code for success
NOTOK = 1
KB_PER_GB = (1<<20)
# FIXME: should be monitoring progress, not total elapsed time
min_files_per_sec = 15 
pct_files_min = 70  # minimum percentage of files for valid test

def gen_host_result_filename(master_invoke, invoke_host):
  return os.path.join(master_invoke.network_dir, hostaddr(invoke_host) + '_result.pickle')

# abort routine just cleans up threads

def abort_test(abort_fn, thread_list):
    try:
      open(abort_fn, "w")
    except Exception as e:
      pass
    for t in thread_list:
        t.terminate()

# main routine that does everything for this workload

def run_workload():
  # if a --host-set parameter was passed, it's a multi-host workload
  # and we have to fire up this program in parallel on the remote hosts
  # each remote instance will wait until all instances have reached starting gate
   
  (prm_host_set, prm_thread_count, master_invoke, remote_cmd, prm_slave, prm_permute_host_dirs) = parse.parse()
  starting_gate = master_invoke.starting_gate
  verbose = master_invoke.verbose

  # calculate timeouts to allow for initialization delays while directory tree is created

  startup_timeout = 20
  dirs = master_invoke.iterations / master_invoke.files_per_dir
  if dirs > 20:
    dir_creation_timeout = dirs / 10
    if verbose: print 'extending initialization timeout by %d seconds for directory creation'%dir_creation_timeout
    startup_timeout += dir_creation_timeout
  host_startup_timeout = startup_timeout + 5
  # for multi-host test

  if prm_host_set and not prm_slave:
    host_startup_timeout += len(prm_host_set)/30

    # construct list of ssh threads to invoke in parallel

    rc = os.system('rm -rf ' + master_invoke.network_dir + os.sep + '*.tmp')
    ensure_deleted(master_invoke.abort_fn())
    ensure_deleted(starting_gate)
    remote_cmd += ' --slave Y '
    ssh_thread_list = []
    host_ct = len(prm_host_set)
    for j in range(0, len(prm_host_set)):
        n = prm_host_set[j]
        this_remote_cmd = remote_cmd
        if prm_permute_host_dirs:
          this_remote_cmd += ' --as-host %s'%prm_host_set[(j+1)%host_ct]
        if verbose: print this_remote_cmd
        pickle_fn = gen_host_result_filename(master_invoke, n)
        ensure_deleted(pickle_fn)
        ssh_thread_list.append(ssh_thread.ssh_thread(n, this_remote_cmd))
    time.sleep(2) # give other clients time to see changes

    # start them, pacing starts so that we don't get ssh errors

    for t in ssh_thread_list:
        t.start()

    # wait for hosts to arrive at starting gate
    # if only one host, then no wait will occur as starting gate file is already present
    # every second we resume scan from last host file not found
    # FIXME: for very large host sets, timeout only if no host responds within X seconds
  
    hosts_ready = False  # set scope outside while loop
    last_host_seen=-1
    sec = 0
    sec_delta = 1
    while sec < host_startup_timeout:
      hosts_ready = True
      for j in range(last_host_seen+1, len(prm_host_set)-1):
        h=prm_host_set[j]
        fn = master_invoke.gen_host_ready_fname(h.strip())
        if not os.access(fn, os.R_OK):
            hosts_ready = False
            break
        last_host_seen=j
      if hosts_ready: break
      time.sleep(sec_delta)
      sec += sec_delta
      sec_delta += 1
      print 'last_host_seen=%d sec=%d'%(last_host_seen,sec)
    if not hosts_ready:
      abortfn = master_invoke.abort_fn()
      open(abortfn, "w")
      raise Exception('hosts did not reach starting gate within %d seconds'%host_startup_timeout)

    # ask all hosts to start the test
    # this is like firing the gun at the track meet
    # threads will wait 3 sec after starting gate is opened before 
    # we really apply workload.  This ensures that heavy workload
    # doesn't block some hosts from seeing the starting flag

    try:
      if not os.access(starting_gate, os.R_OK): 
        with open(starting_gate, "w") as f:
          f.close()
        print 'starting gate file %s created by host %s'%(starting_gate, master_invoke.onhost)
    except IOError, e:
        print 'error writing starting gate: %s'%os.strerror(e.errno)

    # wait for them to finish

    all_ok = True
    for t in ssh_thread_list:
        t.join()
        if t.status != OK: 
          all_ok = False
          print 'ERROR: ssh thread for host %s completed with status %d'%(t.remote_host, t.status)
    time.sleep(5) # give response files time to propagate to this host

    # attempt to aggregate results by reading pickle files
    # containing smf_invocation instances with counters and times that we need

    try:
      total_files = 0.0
      total_records = 0.0
      max_elapsed_time = 0.0
      invoke_list = []
      for h in prm_host_set:  # for each host in test

        # read results for each thread run in that host
        # from python pickle of the list of smf_invocation objects

        pickle_fn = gen_host_result_filename(master_invoke, h)
        if verbose: print 'reading pickle file: %s'%pickle_fn
        host_invoke_list = []
        try:
                pickle_file = open(pickle_fn, "r")
                host_invoke_list = pickle.load(pickle_file)
                pickle_file.close()
                if verbose: print ' read %d invoke objects'%len(host_invoke_list)
                invoke_list.extend(host_invoke_list)
                ensure_deleted(pickle_fn)
        except IOError as e:
                if e.errno != errno.ENOENT: raise e
                print '  pickle file %s not found'%pickle_fn
      #print 'invoke_list: %s'%invoke_list

      if len(invoke_list) < 1:
        raise SMFResultException('no pickled invokes read, so no results')
      my_host_invoke = invoke_list[0]  # pick a representative one
      for invk in invoke_list:  # for each parallel smf_invocation

        # add up work that it did
        # and determine time interval over which test ran

        assert isinstance(invk, smallfile.smf_invocation)
        status = 'ok'
        if invk.status != OK: status = 'ERR: ' + os.strerror(invk.status)
        print "host = %s, thread = %s, elapsed sec. = %f, total files = %d, total_records = %d, status = %s"%\
            (invk.onhost, invk.tid, invk.elapsed_time, invk.filenum_final, invk.rq_final, status)
        total_files += invk.filenum_final
        total_records += invk.rq_final
        max_elapsed_time = max(max_elapsed_time, invk.elapsed_time)

      print 'total threads = %d'%len(invoke_list)
      print 'total files = %d'%total_files
      rszkb = my_host_invoke.record_sz_kb
      if rszkb == 0: rszkb = my_host_invoke.total_sz_kb
      if total_records > 0:
        total_data_gb = total_records * rszkb * 1.0 / KB_PER_GB
        print 'total data = %9.3f GB'%total_data_gb
      if len(invoke_list) < len(prm_host_set) * prm_thread_count:
        print 'WARNING: failed to get some responses from per-client workload generators'
      max_files = my_host_invoke.iterations * len(invoke_list)
      pct_files = 100.0 * total_files / max_files
      print '%6.2f%% of requested files processed, minimum is %6.2f'%(pct_files, pct_files_min)
      if (status != 'ok'):
                raise SMFResultException('at least one thread encountered error, test may be incomplete')
      if (max_elapsed_time > 0.001):  # can't compute rates unless test ran for a while

        files_per_sec = total_files / max_elapsed_time
        print "%f files/sec"%files_per_sec
        if total_records > 0: 
          iops = total_records / max_elapsed_time
          print "%f IOPS"%iops
          mb_per_sec = iops * rszkb / 1024.0
          print "%f sec elapsed time, %f MB/sec"%(max_elapsed_time, mb_per_sec)
      if (status == 'ok') and (pct_files < pct_files_min):
                raise SMFResultException('not enough total files processed, change test parameters')

    except IOError, e:
        print 'host %s filename %s: %s'%(h, pickle_fn, str(e))
        all_ok = False
    except KeyboardInterrupt, e:
        print 'control-C signal seen (SIGINT)'
        all_ok = False
    except SMFResultException, e:
        print 'exception: '+str(e)
        all_ok = False
    if not all_ok: 
        sys.exit(NOTOK)
    sys.exit(OK)

  # what follows is code that gets done on each host
  # if --host-set option is not used, then 
  # this is all that gets run

  # for each thread set up smf_invocation instance,
  # create a thread instance, and delete the thread-ready file 

  thread_list=[]
  for k in range(0,prm_thread_count):
    nextinv = smallfile.smf_invocation.clone(master_invoke)
    nextinv.tid = "%02d"%k
    if not master_invoke.is_shared_dir:
        nextinv.src_dir +=  os.sep + master_invoke.onhost + os.sep + "d" + nextinv.tid
        nextinv.dest_dir += os.sep + master_invoke.onhost + os.sep + "d" + nextinv.tid
    t = invoke_process.subprocess(nextinv)
    thread_list.append(t)

  starting_gate = thread_list[0].invoke.starting_gate
  my_host_invoke = thread_list[0].invoke
  host = short_hostname(None)

  # start threads, wait for them to reach starting gate
  # to do this, look for thread-ready files 

  if not prm_slave:
    ensure_deleted(my_host_invoke.stonewall_fn())
    ensure_deleted(starting_gate)
    ensure_deleted(my_host_invoke.abort_fn())
    ensure_deleted(my_host_invoke.gen_host_ready_fname(host))
  for t in thread_list:
    ensure_deleted(t.invoke.gen_thread_ready_fname(t.invoke.tid))
  time.sleep(1)

  for t in thread_list:
    t.start()
  if verbose: print "started %d worker threads on host %s"%(len(thread_list),host)

  # wait for all threads to reach the starting gate
  # this makes it more likely that they will start simultaneously

  threads_ready = False  # really just to set scope of variable
  k=0
  for sec in range(0, startup_timeout):
    threads_ready = True
    for t in thread_list:
        fn = t.invoke.gen_thread_ready_fname(t.invoke.tid)
        if not os.access(fn, os.R_OK): 
            threads_ready = False
            break
    if threads_ready: break
    time.sleep(0.5)

  # if all threads didn't make it to the starting gate

  if not threads_ready: 
    abort_test(my_host_invoke.abort_fn(), thread_list)
    raise Exception('threads did not reach starting gate within %d sec'%startup_timeout)

  # declare that this host is at the starting gate

  with open(my_host_invoke.gen_host_ready_fname(), "w+") as f:
    f.close()
  time.sleep(1)

  sg = my_host_invoke.starting_gate
  if not prm_slave:
    with open(sg, "w") as sgf: sgf.close()

  # wait for starting_gate file to be created by test driver
  # every second we resume scan from last host file not found
  
  if prm_slave:
    if prm_host_set == None: prm_host_set = [ host ]
    for sec in range(0, host_startup_timeout):
      if os.access(sg, os.R_OK):
        break
      time.sleep(1)
    if not os.access(sg, os.R_OK):
      abort_test(my_host_invoke.abort_fn(), thread_list)
      raise Exception('starting signal not seen within %d seconds'%host_startup_timeout)
  if verbose: print "starting test on host " + host + " in 2 seconds"
  time.sleep(2 + random.random())  

  # FIXME: don't timeout the test, 
  # instead check thread progress and abort if you see any of them stalled
  # for long enough
  # problem is: if servers are heavily loaded you can't use filesystem to communicate this

  # wait for all threads on this host to finish

  for t in thread_list: 
    if verbose: print 'waiting for thread %s'%t.invoke.tid
    t.invoke = t.receiver.recv()  # must do this to get results from sub-process
    t.join()

  # if not a slave of some other host, print results (for this host)

  exit_status = OK
  if not prm_slave:
    try: 
      total_files = 0.0
      total_records = 0.0
      max_elapsed_time = 0.0
      threads_failed_to_start = 0
      worst_status = 'ok'
      # FIXME: code to aggregate results from list of invoke objects can be shared by multi-host and single-host cases
      for t in thread_list:
        status = "ok"
        if t.invoke.status != OK: status = os.strerror(t.invoke.status)
        if worst_status == 'ok' and status != 'ok': worst_status = status
        print "host = %s, thread = %s, elapsed time = %f, total files = %d, total_records = %d, status = %s"%\
              (host, t.invoke.tid, t.invoke.elapsed_time, t.invoke.filenum_final, t.invoke.rq_final, status)
        if t.invoke.filenum_final < 1:  threads_failed_to_start += 1
        total_files += t.invoke.filenum_final
        total_records += t.invoke.rq_final
        max_elapsed_time = max(max_elapsed_time, t.invoke.elapsed_time)

      print "elapsed time = %f, total files = %d, total_records = %d"\
                  %(max_elapsed_time, total_files, total_records)
      if threads_failed_to_start:
        raise SMFResultException('at least %d threads did not start'%threads_failed_to_start)
      max_files = my_host_invoke.iterations * len(thread_list)
      pct_files = 100.0 * total_files / max_files
      print '%6.2f%% of requested files processed, minimum is %6.2f'%(pct_files, pct_files_min)
      if worst_status != 'ok':
                raise SMFResultException('at least one thread encountered error, test may be invalid')
      if pct_files < pct_files_min:
                raise SMFResultException('not enough total files processed, change test parameters')
      if (max_elapsed_time > 0):
        files_per_sec = total_files / max_elapsed_time
        print "%d sec elapsed time, %f files/sec"%(max_elapsed_time, files_per_sec)
        if total_records > 0: 
            iops = total_records / max_elapsed_time
            print "%f IOPS"%iops
            rszkb = my_host_invoke.record_sz_kb
            if rszkb == 0: rszkb = my_host_invoke.total_sz_kb
            mb_per_sec = iops * rszkb / 1024.0
            if mb_per_sec > 0: print "%f MB/sec"%mb_per_sec
    except SMFResultException as e:
        print 'ERROR: ' + str(e)
        exit_status = NOTOK


  else:
    # if this is a multi-host test 
    # then write out this host's result in pickle format so test driver can pick up result

    result_filename = gen_host_result_filename(master_invoke, host)
    if verbose: print 'saving result to filename %s'%result_filename
    ensure_deleted(result_filename)
    result_file = open(result_filename, 'w')
    invok_list = []
    for t in thread_list:
        invok_list.append(t.invoke)
    pickle.dump(invok_list, result_file)
    result_file.flush()
    time.sleep(2)
    os.fsync(result_file.fileno())  # have to do this or reader may not see data
    result_file.close()

  sys.exit(exit_status)

# for future windows compatibility, all global code (not contained in a class or subroutine)
# must be moved to within a routine unless it's trivial (like constants)
# because windows doesn't support fork().

if __name__ == "__main__":
  run_workload()
