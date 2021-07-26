# -*- coding: utf-8 -*-
import os
import sys
import time
import random
import copy

import smallfile
from smallfile import ensure_deleted, ensure_dir_exists, OK, NOTOK, \
    SMFResultException, abort_test
import invoke_process
import sync_files
import output_results


def create_worker_list(prm):

    # for each thread set up SmallfileWorkload instance,
    # create a thread instance, and delete the thread-ready file

    thread_list = []
    for k in range(0, prm.thread_count):
        nextinv = copy.copy(prm.master_invoke)
        nextinv.tid = '%02d' % k
        if not prm.master_invoke.is_shared_dir:
            nextinv.src_dirs = [d + os.sep + prm.master_invoke.onhost
                                + os.sep + 'thrd_' + nextinv.tid
                                for d in nextinv.src_dirs]
            nextinv.dest_dirs = [d + os.sep + prm.master_invoke.onhost
                                 + os.sep + 'thrd_' + nextinv.tid
                                 for d in nextinv.dest_dirs]
        t = invoke_process.subprocess(nextinv)
        thread_list.append(t)
        ensure_deleted(nextinv.gen_thread_ready_fname(nextinv.tid))
    return thread_list


# what follows is code that gets done on each host

def run_multi_thread_workload(prm):

    master_invoke = prm.master_invoke
    prm_slave = prm.is_slave
    verbose = master_invoke.verbose
    host = master_invoke.onhost

    if not prm_slave:
        sync_files.create_top_dirs(master_invoke, False)

    if prm_slave:
        time.sleep(1.1)
        for d in master_invoke.top_dirs:
            ensure_dir_exists(d)
        for dlist in [master_invoke.src_dirs, master_invoke.dest_dirs]:
            for d in dlist:
                ensure_dir_exists(d)
                if verbose:
                    print(host + ' saw ' + str(d))

    # for each thread set up SmallfileWorkload instance,
    # create a thread instance, and delete the thread-ready file

    thread_list = create_worker_list(prm)
    my_host_invoke = thread_list[0].invoke

    # start threads, wait for them to reach starting gate
    # to do this, look for thread-ready files

    for t in thread_list:
        ensure_deleted(t.invoke.gen_thread_ready_fname(t.invoke.tid))
    for t in thread_list:
        t.start()
    if verbose:
        print('started %d worker threads on host %s' %
              (len(thread_list), host))

    # wait for all threads to reach the starting gate
    # this makes it more likely that they will start simultaneously

    startup_timeout = prm.startup_timeout
    if smallfile.is_windows_os:
        print('adding time for Windows synchronization')
        startup_timeout += 30
    abort_fname = my_host_invoke.abort_fn()
    thread_count = len(thread_list)
    thread_to_wait_for = 0
    for sec in range(0, startup_timeout * 2):
        for k in range(thread_to_wait_for, thread_count):
            t = thread_list[k]
            fn = t.invoke.gen_thread_ready_fname(t.invoke.tid)
            if not os.path.exists(fn):
                if verbose:
                    print('thread %d thread-ready file %s not found...' % (k, fn))
                break
            thread_to_wait_for = k + 1
        if thread_to_wait_for == thread_count:
            break
        if os.path.exists(abort_fname):
            break
        time.sleep(0.5)

    # if all threads didn't make it to the starting gate

    if thread_to_wait_for < thread_count:
        abort_test(abort_fname, thread_list)
        raise Exception('only %d threads reached starting gate within %d sec'
                        % (thread_to_wait_for, startup_timeout))

    # declare that this host is at the starting gate

    if prm_slave:
        host_ready_fn = my_host_invoke.gen_host_ready_fname()
        if my_host_invoke.verbose:
            print('host %s creating ready file %s' %
                  (my_host_invoke.onhost, host_ready_fn))
        smallfile.touch(host_ready_fn)

    sg = my_host_invoke.starting_gate
    if not prm_slave:  # special case of no --host-set parameter
        try:
            sync_files.write_sync_file(sg, 'hi there')
            if verbose:
                print('wrote starting gate file')
        except IOError as e:
            print('error writing starting gate for threads: %s' % str(e))
        prm.test_start_time = time.time()

    # wait for starting_gate file to be created by test driver
    # every second we resume scan from last host file not found

    if verbose:
        print('awaiting ' + sg)
    if prm_slave:
        for sec in range(0, prm.host_startup_timeout + 10):
            # hack to ensure that directory is up to date
            #   ndlist = os.listdir(my_host_invoke.network_dir)
            # if verbose: print(str(ndlist))
            if os.path.exists(sg):
                break
            time.sleep(0.5)
        if not os.path.exists(sg):
            abort_test(my_host_invoke.abort_fn(), thread_list)
            raise Exception('starting signal not seen within %d seconds'
                            % prm.host_startup_timeout)
    if verbose:
        print('starting test on host ' + host + ' in 2 seconds')
    time.sleep(2 + random.random())  # let other hosts see starting gate file

    # FIXME: don't timeout the test,
    # instead check thread progress and abort if you see any of them stalled
    # but if servers are heavily loaded you can't rely on filesystem

    # wait for all threads on this host to finish

    for t in thread_list:
        if verbose:
            print('waiting for thread %s' % t.invoke.tid)
        t.invoke = t.receiver.recv()  # to get results from sub-process
        t.join()

    # if not a slave of some other host, print results (for this host)

    exit_status = OK
    if not prm_slave:
        try:
            invoke_list = [t.invoke for t in thread_list]
            output_results.output_results(invoke_list, prm)
        except SMFResultException as e:
            print('ERROR: ' + str(e))
            exit_status = NOTOK
    else:

        # if we are participating in a multi-host test
        # then write out this host's result in pickle format
        # so test driver can pick up result

        result_filename = \
            master_invoke.host_result_filename(prm.as_host)
        if verbose:
            print('writing invokes to: ' + result_filename)
        invok_list = [t.invoke for t in thread_list]
        if verbose:
            print('saving result to filename %s' % result_filename)
        for ivk in invok_list:
            ivk.buf = None
            ivk.biggest_buf = None
        sync_files.write_pickle(result_filename, invok_list)
        time.sleep(1.2)  # for benefit of NFS with actimeo=1

    sys.exit(exit_status)
