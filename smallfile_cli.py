#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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

"""
smallfile_cli.py
CLI user interface for generating metadata-intensive workloads
Copyright 2012 -- Ben England
Licensed under the Apache License at http://www.apache.org/licenses/LICENSE-2.0
See Appendix on this page for instructions pertaining to license.
"""

import errno
import os
import os.path
import pickle
import sys
import time

import launcher_thread
import multi_thread_workload
import output_results
import parse
import smallfile
import ssh_thread
import sync_files
from smallfile import (
    NOTOK,
    OK,
    SMFResultException,
    SMFRunException,
    ensure_deleted,
    use_isAlive,
)

# smallfile modules


# FIXME: should be monitoring progress, not total elapsed time

min_files_per_sec = 15
pct_files_min = 70  # minimum percentage of files for valid test


# run a multi-host test


def run_multi_host_workload(prm):

    prm_host_set = prm.host_set
    prm_permute_host_dirs = prm.permute_host_dirs
    master_invoke = prm.master_invoke

    starting_gate = master_invoke.starting_gate
    verbose = master_invoke.verbose

    if os.getenv("PYPY"):
        python_prog = os.getenv("PYPY")
    elif sys.version.startswith("2"):
        python_prog = "python"
    elif sys.version.startswith("3"):
        python_prog = "python3"
    else:
        raise SMFRunException("unrecognized python version %s" % sys.version)

    # construct list of ssh threads to invoke in parallel

    master_invoke.create_top_dirs(True)
    pickle_fn = os.path.join(prm.master_invoke.network_dir, "param.pickle")

    # if verbose: print('writing ' + pickle_fn))

    sync_files.write_pickle(pickle_fn, prm)

    # print('python_prog = %s'%python_prog)

    remote_thread_list = []
    host_ct = len(prm_host_set)
    for j in range(0, len(prm_host_set)):
        remote_host = prm_host_set[j]
        smf_remote_pgm = os.path.join(prm.remote_pgm_dir, "smallfile_remote.py")
        this_remote_cmd = "%s %s --network-sync-dir %s " % (
            python_prog,
            smf_remote_pgm,
            prm.master_invoke.network_dir,
        )

        # this_remote_cmd = remote_cmd

        if prm_permute_host_dirs:
            this_remote_cmd += " --as-host %s" % prm_host_set[(j + 1) % host_ct]
        else:
            this_remote_cmd += " --as-host %s" % remote_host
        if verbose:
            print(this_remote_cmd)
        if smallfile.is_windows_os or prm.launch_by_daemon:
            remote_thread_list.append(
                launcher_thread.launcher_thread(prm, remote_host, this_remote_cmd)
            )
        else:
            remote_thread_list.append(
                ssh_thread.ssh_thread(remote_host, this_remote_cmd)
            )

    # start them

    for t in remote_thread_list:
        if not prm.launch_by_daemon:
            # pace starts so that we don't get ssh errors
            time.sleep(0.1)
        t.start()

    # wait for hosts to arrive at starting gate
    # if only one host, then no wait will occur
    # as starting gate file is already present
    # every second we resume scan from last host file not found
    # FIXME: for very large host sets,
    # timeout only if no host responds within X seconds

    exception_seen = None
    hosts_ready = False  # set scope outside while loop
    abortfn = master_invoke.abort_fn()
    last_host_seen = -1
    sec = 0.0
    sec_delta = 0.5
    host_timeout = prm.host_startup_timeout
    if smallfile.is_windows_os:
        host_timeout += 20
    h = None

    try:
        while sec < host_timeout:
            # HACK to force directory entry coherency for Gluster
            ndirlist = os.listdir(master_invoke.network_dir)
            if master_invoke.verbose:
                print("shared dir list: " + str(ndirlist))
            hosts_ready = True
            if os.path.exists(abortfn):
                raise SMFRunException("worker host signaled abort")
            for j in range(last_host_seen + 1, len(prm_host_set)):
                h = prm_host_set[j]
                fn = master_invoke.gen_host_ready_fname(h.strip())
                if verbose:
                    print("checking for host filename " + fn)
                if not os.path.exists(fn):
                    hosts_ready = False
                    break
                last_host_seen = j  # saw this host's ready file
                # we exit while loop only if no hosts in host_timeout seconds
                sec = 0.0
            if hosts_ready:
                break

            # if one of ssh threads has died, no reason to continue

            kill_remaining_threads = False
            for t in remote_thread_list:
                if not smallfile.thrd_is_alive(t):
                    print("thread %s on host %s has died" % (t, str(h)))
                    kill_remaining_threads = True
                    break
            if kill_remaining_threads:
                break

            # be patient for large tests
            # give user some feedback about
            # how many hosts have arrived at the starting gate

            time.sleep(sec_delta)
            sec += sec_delta
            sec_delta += 1
            if verbose:
                print("last_host_seen=%d sec=%d" % (last_host_seen, sec))
    except KeyboardInterrupt as e:
        print("saw SIGINT signal, aborting test")
        exception_seen = e
        hosts_ready = False
    except Exception as e:
        exception_seen = e
        hosts_ready = False
        print("saw exception %s, aborting test" % str(e))
    if not hosts_ready:
        smallfile.abort_test(abortfn, [])
        if h != None:
            print("ERROR: host %s did not reach starting gate" % h)
        else:
            print("no host reached starting gate")
        if not exception_seen:
            raise SMFRunException(
                "hosts did not reach starting gate "
                + "within %d seconds" % host_timeout
            )
        else:
            print("saw exception %s, aborting test" % str(exception_seen))
        sys.exit(NOTOK)
    else:

        # ask all hosts to start the test
        # this is like firing the gun at the track meet

        try:
            sync_files.write_sync_file(starting_gate, "hi")
            prm.test_start_time = time.time()
            print(
                "starting all threads by creating starting gate file %s" % starting_gate
            )
        except IOError as e:
            print("error writing starting gate: %s" % os.strerror(e.errno))

    # wait for them to finish

    for t in remote_thread_list:
        t.join()
        if t.status != OK:
            print(
                "ERROR: ssh thread for host %s completed with status %d"
                % (t.remote_host, t.status)
            )

    # attempt to aggregate results by reading pickle files
    # containing SmallfileWorkload instances
    # with counters and times that we need

    try:
        all_ok = NOTOK
        invoke_list = []
        one_shot_delay = True
        for h in prm_host_set:  # for each host in test

            # read results for each thread run in that host
            # from python pickle of the list of SmallfileWorkload objects

            pickle_fn = master_invoke.host_result_filename(h)
            if verbose:
                print("reading pickle file: %s" % pickle_fn)
            host_invoke_list = []
            try:
                if one_shot_delay and not os.path.exists(pickle_fn):

                    # all threads have joined already, they are done
                    # we allow > 1 sec
                    # for this (NFS) client to see other clients' files

                    time.sleep(1.2)
                    one_shot_delay = False
                with open(pickle_fn, "rb") as pickle_file:
                    host_invoke_list = pickle.load(pickle_file)
                if verbose:
                    print(" read %d invoke objects" % len(host_invoke_list))
                invoke_list.extend(host_invoke_list)
                ensure_deleted(pickle_fn)
            except IOError as e:
                if e.errno != errno.ENOENT:
                    raise e
                print("  pickle file %s not found" % pickle_fn)

        output_results.output_results(invoke_list, prm)
        all_ok = OK
    except IOError as e:
        print("host %s filename %s: %s" % (h, pickle_fn, str(e)))
    except KeyboardInterrupt as e:
        print("control-C signal seen (SIGINT)")

    sys.exit(all_ok)


# main routine that does everything for this workload


def run_workload():

    # if a --host-set parameter was passed,
    # it's a multi-host workload
    # each remote instance will wait
    # until all instances have reached starting gate

    try:
        params = parse.parse()
    except parse.SmfParseException as e:
        print("ERROR: " + str(e))
        print("use --help option to get CLI syntax")
        sys.exit(NOTOK)

    # for multi-host test

    if params.host_set and not params.is_slave:
        return run_multi_host_workload(params)
    return multi_thread_workload.run_multi_thread_workload(params)


# for future windows compatibility,
# all global code (not contained in a class or subroutine)
# must be moved to within a routine unless it's trivial (like constants)
# because windows doesn't support fork().

if __name__ == "__main__":
    run_workload()
