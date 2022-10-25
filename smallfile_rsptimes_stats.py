#!/usr/bin/env python3
#
# smallfile_rsptimes_stats.py -- python program to reduce response time sample data from smallfile benchmark to
# statistics.
#
# in addition to stats for individual thread, it shows per-client and cluster-wide stats
# smallfile at present produces response time data in the /var/tmp/ directory
# within each workload generator
# it is the user's responsibility to copy the data back
# to a directory (on the test driver perhaps).
# this means that the files from each workload generator have to have
# the workload generator hostname embedded in them
# so that they can all be co-located in a single directory.
# since there is no standard method for this yet,
# this program has to be adjusted to parse the filenames
# and extract 2 fields, thread number and short hostname
#
# the start-time parameter is optional but if it is specified
# the percentiles-vs-time time column will have this added to it
# this could be useful for ingesting data into a repository like
# elastic search and displaying it side-by-side with other performance
# data collected during a test run.  The default of 0 just outputs
# time since start of test (like before).  The start time as
# seconds since the epoch (1970) can be obtained from the JSON
# output in the 'start-time' field.


import bisect
import os
import re
import sys
from sys import argv

import numpy
import scipy
import scipy.stats

time_infinity = 1 << 62

# edit this list if you want additional percentiles

percentiles = [50, 90, 95, 99]
min_rsptime_samples = 5
start_time = 0.0


def usage(msg):
    print("ERROR: %s" % msg)
    print("usage: python smallfile_rsptimes_stats.py ")
    print("           [--common-hostname-suffix my.suffix] ")
    print("           [--time-interval positive-integer-seconds] ")
    print("           [--start-time seconds-since-1970] ")
    print("           directory")
    sys.exit(1)


# parse files once, we assume here that we can hold them in RAM
# so we don't have to keep reading them
# by keeping them in RAM we allow binary search for starting
# time since we want to isolate set of samples in a time interval


def parse_rsptime_file(result_dir, csv_pathname):
    samples = []
    with open(os.path.join(result_dir, csv_pathname), "r") as f:
        records = [line.strip() for line in f.readlines()]
        for sample in records:
            components = sample.split(",")
            op = components[0]
            at_time = float(components[1])
            if start_time > 0:
                at_time += start_time
            rsp_time = float(components[2])
            samples.append((op, at_time, rsp_time))
    return samples


# to be used for sorting based on tuple components


def get_at_time(rsptime_tuple):
    (_, at_time, _) = rsptime_tuple
    return at_time


def get_rsp_time(rsptime_tuple):
    (_, _, rsp_time) = rsptime_tuple
    return rsp_time


def do_sorting(sample_set, already_sorted=False):
    """
    this function avoids duplication of sorting
    """
    if not already_sorted:
        sorted_samples = sorted(sample_set, key=get_at_time)
    else:
        sorted_samples = sample_set
    sorted_keys = list(map(get_at_time, sorted_samples))
    sorted_rsptimes = sorted(list(map(get_rsp_time, sample_set)))
    return (sorted_samples, sorted_keys, sorted_rsptimes)


# leverage python binary search module "bisect"
# obtained from https://docs.python.org/2/library/bisect.html#searching-sorted-lists


def find_le(a, x):
    # find highest index with value < x
    i = bisect.bisect_right(a, x)
    return i


def find_gt(a, x):
    # find lowest index with value >= x
    i = bisect.bisect_left(a, x)
    if i < len(a):
        return i
    # since the only thing we are doing with this result
    # is to extract a slice of an array,
    # returning len(a) is a valid thing
    # raise ValueError


# if you want this to calculate stats for a time_interval
# t specify from_time and to_time


def reduce_thread_set(sorted_samples_tuple, from_time=0, to_time=time_infinity):
    # FIXME: need binary search to
    # efficiently find beginning of time interval
    (sorted_samples, sorted_keys, sorted_times) = sorted_samples_tuple
    if to_time < time_infinity:
        start_index = find_le(sorted_keys, from_time)
        end_index = find_gt(sorted_keys, to_time)
        # replace sorted_times with just the response times in time interval
        sorted_times = sorted(map(get_rsp_time, sorted_samples[start_index:end_index]))
    sample_count = len(sorted_times)
    if sample_count < min_rsptime_samples:
        return None
    mintime = sorted_times[0]
    maxtime = sorted_times[-1]
    mean = scipy.stats.tmean(sorted_times)
    stdev = scipy.stats.tstd(sorted_times)
    pctdev = 100.0 * stdev / mean
    pctiles = []
    for p in percentiles:
        pctiles.append(numpy.percentile(sorted_times, float(p), overwrite_input=True))
    return (sample_count, mintime, maxtime, mean, pctdev, pctiles)


# format the stats for output to a csv file


def format_stats(all_stats):
    if all_stats is None:
        return " 0,,,,," + ",,,,,,,,,,,,,,,,"[0 : len(percentiles) - 1]
    (sample_count, mintime, maxtime, mean, pctdev, pctiles) = all_stats
    partial_record = "%d, %f, %f, %f, %f, " % (
        sample_count,
        mintime,
        maxtime,
        mean,
        pctdev,
    )
    for p in pctiles:
        partial_record += "%f, " % p
    return partial_record


# FIXME: convert to argparse module, more compact and standard
# define default parameter values

hosts = {}
suffix = ""
argindex = 1
argcount = len(argv)
time_interval = 10

# parse any optional parameters

while argindex < argcount:
    pname = argv[argindex]
    if not pname.startswith("--"):
        break
    if argindex == argcount - 1:
        usage("every parameter consists of a --name and a value")
    pval = argv[argindex + 1]
    argindex += 2
    pname = pname[2:]
    if pname == "common-hostname-suffix":
        suffix = pval
        if not suffix.startswith("."):
            suffix = "." + pval
    elif pname == "time-interval":
        time_interval = int(pval)
    elif pname == "start-time":
        start_time = float(pval)
    else:
        usage("--%s: no such optional parameter defined" % pname)

if suffix != "":
    print("filtering out suffix %s from hostnames" % suffix)
print("time interval is %d seconds" % time_interval)

# this regex plucks out a tuple of 2 values:
#
# thread number
# hostname

regex = r"rsptimes_([0-9]{2})_([0-9,a-z,\-,\.]*)%s_[-,a-z]*_[.,0-9]*.csv"

# filter out redundant suffix, if any, in hostname

new_regex = regex % suffix

# now parse hostnames and files

if argindex != argcount - 1:
    usage("need directory where response time files are")

directory = argv[argindex]
if not os.path.isdir(directory):
    usage("%s: directory containing result csv files was not provided" % directory)

# process the results
# we show individual threads, per-host groupings and all threads together

samples_by_thread = {}
hosts = {}

pathnames = filter(
    lambda path: path.startswith("rsptimes") and path.endswith(".csv"),
    os.listdir(directory),
)
max_thread = 0
for p in pathnames:
    m = re.match(new_regex, p)
    if not m:
        sys.stderr.write("warning: pathname could not be matched by regex: %s\n" % p)
        continue
    (threadstr, host) = m.group(1, 2)
    thread = int(threadstr)
    if max_thread < thread:
        max_thread = thread
    try:
        perhost_dict = hosts[host]
    except KeyError:
        perhost_dict = {}
        hosts[host] = perhost_dict
    # load response times for this file into memory
    # save what file it came from too
    samples = parse_rsptime_file(directory, p)
    perhost_dict[threadstr] = (p, samples)

hostcount = len(hosts.keys())
if hostcount == 0:
    usage("%s: no .csv response time log files were found" % directory)

summary_pathname = os.path.join(directory, "stats-rsptimes.csv")
header = "host:thread, samples, min, max, mean, %dev, "
for p in percentiles:
    header += "%d%%ile, " % p

with open(summary_pathname, "w") as outf:
    outf.write(header + "\n")

    # aggregate response times across all threads and whole test duration
    # if there is only 1 host, no need for cluster-wide stats

    cluster_sample_set = None
    if len(hosts.keys()) > 1:
        outf.write("cluster-wide stats:\n")
        cluster_sample_set = []
        for per_host_dict in hosts.values():
            for (_, samples) in per_host_dict.values():
                cluster_sample_set.extend(samples)
        sorted_cluster_tuple = do_sorting(cluster_sample_set)
        cluster_results = reduce_thread_set(sorted_cluster_tuple)
        outf.write("all-hosts:all-thrd," + format_stats(cluster_results) + "\n")
        outf.write("\n")

    # show them if there is variation amongst clients (could be network)
    # if there is only 1 thread per host, no need for per-host stats
    # assumption: all hosts have 1 thread/host or all hosts have > 1 thread/host

    host_keys = list(hosts.keys())
    first_host = host_keys[0]
    if len(first_host) > 1:
        outf.write("per-host stats:\n")
        for h in sorted(hosts.keys()):
            sample_set = []
            for (_, samples) in hosts[h].values():
                sample_set.extend(samples)
            sorted_host_tuple = do_sorting(sample_set)
            host_results = reduce_thread_set(sorted_host_tuple)
            outf.write(h + ":" + "all-thrd" + "," + format_stats(host_results) + "\n")
        outf.write("\n")

    # show per-thread results so we can see if client Cephfs mountpoint is fair

    outf.write("per-thread stats:\n")
    for h in sorted(hosts.keys()):
        threadset = hosts[h]
        for t in sorted(threadset.keys()):
            (_, samples) = threadset[t]
            sorted_thrd_tuple = do_sorting(samples, already_sorted=True)
            thrd_results = reduce_thread_set(sorted_thrd_tuple)
            outf.write(h + ":" + t + "," + format_stats(thrd_results) + "\n")
    outf.write("\n")

    # generate cluster-wide percentiles over time
    # to show if latency spikes occur
    # first get max end time of any request,
    # round that down to quantized time interval

    end_time = -1
    for h in hosts.keys():
        threadset = hosts[h]
        for t in threadset.keys():
            (_, samples) = threadset[t]
            if len(samples) > 0:
                (_, max_at_time, max_rsp_time) = samples[-1]
            else:
                max_at_time = 0.0
                max_rsp_time = 0.0
            end_time = max(end_time, max_at_time + max_rsp_time)
    quantized_end_time = (int(end_time) // time_interval) * time_interval

    # if there is only 1 interval, cannot do percentiles vs time
    # else for each time interval calculate percentiles of samples
    # in that time interval

    if quantized_end_time > 0:
        outf.write("cluster-wide response time stats over time:\n")
        outf.write("time-since-start(sec), " + header + "\n")

        # avoid re-sorting all response time samples
        # if possible (and it often is)

        if cluster_sample_set is None:
            cluster_sample_set = []
            for per_host_dict in hosts.values():
                for (_, samples) in per_host_dict.values():
                    cluster_sample_set.extend(samples)
            sorted_cluster_tuple = do_sorting(cluster_sample_set)
        for from_t in range(int(start_time), quantized_end_time, time_interval):
            to_t = from_t + time_interval
            results_in_interval = reduce_thread_set(
                sorted_cluster_tuple, from_time=from_t, to_time=to_t
            )
            outf.write("%-8d, all-hosts:all-thrd, " % from_t)
            outf.write(format_stats(results_in_interval) + "\n")
        outf.write("\n")


print("rsp. time result summary at: %s" % summary_pathname)
