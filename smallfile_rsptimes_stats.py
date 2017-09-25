#!/usr/bin/python
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
# 
import sys
import os
import string
import re
import numpy
import scipy
import scipy.stats
from scipy.stats import tmean, tstd
from sys import argv

# edit this list if you want additional percentiles

percentiles = [ 50, 90, 95, 99 ]
min_rsptime_samples = 10
 

def usage( msg ):
  print('ERROR: %s' % msg)
  print('usage: python smallfile_rsptimes_stats.py [ --common-hostname-suffix my.suffix ] directory' )
  sys.exit(1)


# generate stats for a set of threads (could be just 1)

def reduce_thread_set( result_dir, csv_pathname_list ):
  records = []
  for csvfn in csv_pathname_list:
    with open(os.path.join(result_dir, csvfn), "r") as f:
      records.extend([ l.strip() for l in f.readlines() ])

  if len(records) < min_rsptime_samples:
    usage('%d is less than %d, too few response time samples to analyze!' % 
          (len(records), min_rsptime_samples))
  times = numpy.array( [ float(r.strip().split(',')[2]) for r in records ] )
  sorted_times = sorted(times)
  samples = len(sorted_times)
  mintime = sorted_times[0]
  maxtime = sorted_times[samples-1]
  mean = scipy.stats.tmean(sorted_times)
  stdev = scipy.stats.tstd(sorted_times)
  pctdev = 100.0*stdev/mean
  record = '%d, %f, %f, %f, %f,' % (samples, mintime, maxtime, mean, pctdev)
  for p in percentiles:
    record += '%f, ' % sorted_times[int(samples * (p/100.0))]
  return record


# define default parameter values

hosts = {}
suffix = ''
argindex = 1
argcount = len(argv)

# parse any optional parameters

while argindex < argcount:
  pname = argv[argindex]
  if not pname.startswith('--'):
    break
  if argindex == argcount - 1:
    usage('every parameter consists of a --name and a value')
  pval = argv[argindex + 1]
  argindex += 2
  pname = pname[2:]
  if pname == 'common-hostname-suffix':
    suffix = pval
    if not suffix.startswith('.'):
      suffix = '.' + pval
  else:
    usage('--%s: no such optional parameter defined' % pname)

if suffix != '':
  print('filtering out suffix %s from hostnames' % suffix)

# this regex plucks out a tuple of 2 values:
#
## thread number
## hostname

regex = \
 'rsptimes_([0-9]{2})_([a-z]{1}[0-9,a-z,\-,\.]*)%s_[-,a-z]*_[.,0-9]*.csv'

# filter out redundant suffix, if any, in hostname

new_regex = regex % suffix

# now parse hostnames and files

if argindex != argcount - 1:
  usage('need directory where response time files are')

directory = argv[argindex]
if not os.path.isdir(directory):
  usage('%s: directory containing result csv files was not provided' % directory)

# process the results
# we show individual threads, per-host groupings and all threads together

hosts = {}
pathnames = filter(lambda path : path.endswith('.csv'), os.listdir(directory))
max_thread = 0
for p in pathnames:
  m = re.match(new_regex, p)
  if not m:
    sys.stderr.write("warning: pathname could not be matched by regex: %s\n" % p)
    continue
  (threadstr, host) = m.group(1,2)
  thread = int(threadstr)
  if max_thread < thread: max_thread = thread
  try:
    perhost_dict = hosts[host]
  except KeyError:
    perhost_dict = {}
    hosts[host] = perhost_dict
  perhost_dict[threadstr] = p

hostcount = len(hosts.keys())
if hostcount == 0:
  usage('%s: no .csv response time log files were found' % directory)

summary_pathname = os.path.join(directory, '../rsptime-summary.csv')
header = 'host:thread, samples, min, max, mean, %dev, '
for p in percentiles:
  header += '%d %%ile, ' % p
with open(summary_pathname, 'w') as outf:
  outf.write(header + '\n')
  if len(hosts.keys()) > 1:
    all_pathnames = []
    for per_host_dict in hosts.values():
      all_pathnames.extend(per_host_dict.values())
    outf.write('all:all,' + reduce_thread_set(directory, sorted(all_pathnames)) + '\n')
  outf.write('\n')
  for h in sorted(hosts.keys()):
    if len(hosts[h].keys()) > 1:
      outf.write(h + ':' + 'all' + ',' + reduce_thread_set(directory, hosts[h].values()) + '\n')
  outf.write('\n')
  for h in sorted(hosts.keys()):
    for t in sorted(hosts[h].keys()):
      outf.write(h + ':' + t + ',' + reduce_thread_set(directory, [hosts[h][t]]) + '\n')

print('rsp. time result summary at: %s' % summary_pathname)
