#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import json
import smallfile
from smallfile import SMFResultException, KB_PER_GB


def output_results(invoke_list, test_params):
    if len(invoke_list) < 1:
        raise SMFResultException('no pickled invokes read, so no results'
                                 )
    my_host_invoke = invoke_list[0]  # pick a representative one
    total_files = 0
    total_records = 0
    max_elapsed_time = 0.0
    status = 'ok'
    rslt = {}
    rslt['hosts'] = {}

    for invk in invoke_list:  # for each parallel SmallfileWorkload

        # add up work that it did
        # and determine time interval over which test ran

        assert isinstance(invk, smallfile.SmallfileWorkload)
        if invk.status:
            status = 'ERR: ' + os.strerror(invk.status)
        fmt = 'host = %s,thr = %s,elapsed = %f'
        fmt += ',files = %d,records = %d,status = %s'
        print(fmt %
              (invk.onhost, invk.tid, invk.elapsed_time,
               invk.filenum_final, invk.rq_final, status))
        per_thread_obj = {}
        per_thread_obj['elapsed'] = invk.elapsed_time,
        per_thread_obj['filenum-final'] = invk.filenum_final
        per_thread_obj['records'] = invk.rq_final
        per_thread_obj['status'] = status

        # for JSON, show nesting of threads within hosts

        try:
            per_host_results = rslt['hosts'][invk.onhost]
        except KeyError:
            per_host_results = { 'threads':{} }
            rslt['hosts'][invk.onhost] = per_host_results
        per_host_results['threads'][invk.tid] = per_thread_obj

        # aggregate to get stats for whole run

        total_files += invk.filenum_final
        total_records += invk.rq_final
        max_elapsed_time = max(max_elapsed_time, invk.elapsed_time)

    print('total threads = %d' % len(invoke_list))
    rslt['total-threads'] = len(invoke_list)

    print('total files = %d' % total_files)
    rslt['total-files'] = total_files

    print('total IOPS = %d' % total_records)
    rslt['total-io-requests'] = total_records

    rszkb = my_host_invoke.record_sz_kb
    if rszkb == 0:
        rszkb = my_host_invoke.total_sz_kb
    if rszkb * my_host_invoke.BYTES_PER_KB > my_host_invoke.biggest_buf_size:
        rszkb = my_host_invoke.biggest_buf_size / my_host_invoke.BYTES_PER_KB
    if total_records > 0:
        total_data_gb = total_records * rszkb * 1.0 / KB_PER_GB
        print('total data = %9.3f GiB' % total_data_gb)
        rslt['total-data-GB'] = total_data_gb
    if not test_params.host_set:
        test_params.host_set = ['localhost']
    if len(invoke_list) < len(test_params.host_set) * test_params.thread_count:
        print('WARNING: failed to get some responses from workload generators')
    max_files = my_host_invoke.iterations * len(invoke_list)
    pct_files = 100.0 * total_files / max_files
    print('%6.2f%% of requested files processed, minimum is %6.2f' %
          (pct_files, smallfile.pct_files_min))
    rslt['pct-files-done'] = pct_files
    print('elapsed time = %9.3f' % max_elapsed_time)
    rslt['elapsed-time'] = max_elapsed_time
    if max_elapsed_time > 0.001:  # can't compute rates if it ended too quickly
        files_per_sec = total_files / max_elapsed_time
        print('files/sec = %f' % files_per_sec)
        rslt['files-per-sec'] = files_per_sec
        if total_records > 0:
            iops = total_records / max_elapsed_time
            print('IOPS = %f' % iops)
            rslt['total-IOPS'] = iops
            mb_per_sec = iops * rszkb / 1024.0
            print('MiB/sec = %f' % mb_per_sec)
            rslt['total-MiBps'] = mb_per_sec

    # if JSON output requested, generate it here

    if test_params.output_json:
        json_obj = test_params.to_json()
        json_obj['results'] = rslt
        with open(test_params.output_json, 'w') as jsonf:
            json.dump(json_obj, jsonf, indent=4)

    # finally, throw exceptions if something bad happened
    # wait until here to do it so we can see test results

    if status != 'ok':
        raise SMFResultException(
            'at least one thread encountered error, test may be incomplete')
    if status == 'ok' and pct_files < smallfile.pct_files_min:
        raise SMFResultException(
            'not enough total files processed before 1st thread finished, change test parameters')
