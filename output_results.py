# -*- coding: utf-8 -*-

import json
import os
import time
from copy import deepcopy

import smallfile
from smallfile import KB_PER_GB, OK, SMFResultException

BYTES_PER_KiB = 1024.0
KiB_PER_MiB = 1024.0


class result_stats:

    # start with zeroing because we'll add
    # other objects of this type to it

    def __init__(self):
        self.status = OK
        self.elapsed = 0.0
        self.files = 0
        self.records = 0
        self.files_per_sec = 0.0
        self.IOPS = 0.0
        self.MiBps = 0.0

    def get_from_invoke(self, invk, record_sz_kb):
        if invk.elapsed_time is None:
            print(
                "WARNING: thread %s on host %s never completed"
                % (invk.tid, invk.onhost)
            )
        self.status = invk.status
        self.elapsed = (
            invk.elapsed_time if invk.elapsed_time is not None else 100000000.0
        )
        self.files = invk.filenum_final if invk.filenum_final is not None else 0
        self.records = invk.rq_final if invk.rq_final is not None else 0
        if invk.elapsed_time is not None and invk.elapsed_time > 0.0:
            self.files_per_sec = invk.filenum_final / invk.elapsed_time
            if invk.rq_final > 0:
                self.IOPS = invk.rq_final / invk.elapsed_time
                self.MiBps = (
                    invk.rq_final * record_sz_kb / KiB_PER_MiB
                ) / invk.elapsed_time

    # add component's fields to this object

    def add_to(self, component):
        # status is not ok if any component's status is not ok
        if self.status == OK:
            self.status = component.status
        # elapsed time is max of any component's elapsed time
        self.elapsed = max(self.elapsed, component.elapsed)
        self.files += component.files
        self.records += component.records
        if component.elapsed > 0.0:
            self.files_per_sec += component.files_per_sec
            try:
                self.IOPS += component.IOPS
                self.MiBps += component.MiBps
            except KeyError:
                pass

    # insert values into dictionary

    def add_to_dict(self, target):
        if self.status != OK:
            target["status"] = os.strerror(self.status)
        target["elapsed"] = self.elapsed
        target["files"] = self.files
        target["records"] = self.records
        target["filesPerSec"] = self.files_per_sec
        if self.records > 0:
            target["IOPS"] = self.IOPS
            target["MiBps"] = self.MiBps


def output_results(invoke_list, test_params):
    if len(invoke_list) < 1:
        raise SMFResultException("no pickled invokes read, so no results")
    my_host_invoke = invoke_list[0]  # pick a representative one
    rszkb = my_host_invoke.record_sz_kb
    if rszkb == 0:
        rszkb = my_host_invoke.total_sz_kb
    if rszkb * my_host_invoke.BYTES_PER_KB > my_host_invoke.biggest_buf_size:
        rszkb = my_host_invoke.biggest_buf_size / my_host_invoke.BYTES_PER_KB

    rslt = {}
    rslt["host"] = {}
    stats_by_host = {}
    cluster = stats_by_host["stats"] = result_stats()

    for invk in invoke_list:  # for each parallel SmallfileWorkload

        # add up work that it did
        # and determine time interval over which test ran

        if not isinstance(invk, smallfile.SmallfileWorkload):
            raise SMFResultException("invoke is of wrong type: %s" % str(invk))
        if invk.status:
            status = "ERR: " + os.strerror(invk.status)
        else:
            status = "ok"
        fmt = "host = %s,thr = %s,elapsed = %s"
        fmt += ",files = %s,records = %s,status = %s"
        print(
            fmt
            % (
                invk.onhost,
                invk.tid,
                str(invk.elapsed_time),
                str(invk.filenum_final),
                str(invk.rq_final),
                status,
            )
        )

        per_thread = result_stats()
        per_thread.get_from_invoke(invk, rszkb)

        # for JSON, show nesting of threads within hosts

        try:
            per_host = stats_by_host[invk.onhost]
        except KeyError:
            # first time this host was seen
            stats_by_host[invk.onhost] = per_host = {}
            per_host["thread"] = {}
            per_host["stats"] = result_stats()
        per_host["thread"][invk.tid] = per_thread
        per_host["stats"].add_to(per_thread)
        cluster.add_to(per_thread)

    # now counters are all added up, generate JSON

    for invk in invoke_list:  # for each parallel SmallfileWorkload
        per_host = stats_by_host[invk.onhost]
        try:
            per_host_json = rslt["host"][invk.onhost]
        except KeyError:
            rslt["host"][invk.onhost] = per_host_json = {}
            per_host["stats"].add_to_dict(per_host_json)
            per_host_json["thread"] = {}
        per_host_json["thread"][invk.tid] = per_thread_json = {}
        per_thread = per_host["thread"][invk.tid]
        per_thread.add_to_dict(per_thread_json)

    cluster.add_to_dict(rslt)

    # if there is only 1 host in results,
    # and no host was specified,
    # then remove that level from
    # result hierarchy, not needed

    if len(rslt["host"].keys()) == 1 and test_params.host_set is None:
        hostkey = list(rslt["host"].keys())[0]
        threads_in_host = rslt["host"][hostkey]["thread"]
        rslt["thread"] = threads_in_host
        del rslt["host"]

    print("total threads = %d" % len(invoke_list))
    rslt["totalhreads"] = len(invoke_list)

    print("total files = %d" % cluster.files)

    if cluster.records > 0:
        print("total IOPS = %d" % cluster.IOPS)
        total_data_gb = cluster.records * rszkb * 1.0 / KB_PER_GB
        print("total data = %9.3f GiB" % total_data_gb)
        rslt["totalDataGB"] = total_data_gb

    if not test_params.host_set:
        test_params.host_set = ["localhost"]
    json_test_params = deepcopy(test_params)
    json_test_params.host_set = ",".join(test_params.host_set)

    if len(invoke_list) < len(test_params.host_set) * test_params.thread_count:
        print("WARNING: failed to get some responses from workload generators")
    max_files = my_host_invoke.iterations * len(invoke_list)
    pct_files = 100.0 * cluster.files / max_files
    print(
        "%6.2f%% of requested files processed, warning threshold is %6.2f%%"
        % (pct_files, smallfile.pct_files_min)
    )
    rslt["pctFilesDone"] = pct_files

    print("elapsed time = %9.3f" % cluster.elapsed)
    rslt["startTime"] = test_params.test_start_time
    rslt["status"] = os.strerror(cluster.status)

    # output start time in elasticsearch-friendly format

    rslt["date"] = time.strftime(
        "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(test_params.test_start_time)
    )

    # don't output meaningless fields

    if cluster.elapsed < 0.001:  # can't compute rates if it ended too quickly
        print("WARNING: test must run longer than a millisecond")
    else:
        print("files/sec = %f" % cluster.files_per_sec)
        if cluster.records > 0:
            print("IOPS = %f" % cluster.IOPS)
            print("MiB/sec = %f" % cluster.MiBps)

    # if JSON output requested, generate it here

    if test_params.output_json:
        json_obj = json_test_params.to_json()
        json_obj["results"] = rslt
        with open(test_params.output_json, "w") as jsonf:
            json.dump(json_obj, jsonf, indent=4)

    # finally, throw exceptions if something bad happened
    # wait until here to do it so we can see test results

    if cluster.status != OK:
        print("WARNING: at least one thread encountered error, test may be incomplete")
    elif pct_files < smallfile.pct_files_min:
        print(
            "WARNING: not enough total files processed before 1st thread finished, change test parameters"
        )
