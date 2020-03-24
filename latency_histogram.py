#!/usr/bin/env python
# record response times  via histogram to eliminate need to save all response times to a file
# modelled on fio's histogram feature
# for writeup of that, see https://github.com/axboe/fio/blob/master/doc/fio-histo-log-pctiles.pdf
# all buckets within a bucket group have same tMax-tMin
# first and second bucket group have same tMax-tMin
# after that, the k+1'th group has double the tMax-tMin of the k'th group
# so beginning time for each group is a power of 2

import copy
from copy import deepcopy
import math
import time
import os
from bisect import bisect_left

class LatencyHistException(Exception):
    pass

def tokenize_line(f):
    return [ t.strip() for t in f.readline().split(':') ]

class latency_histogram:

    # caller has to specify which thread is generating the data

    def __init__(self, thread, bucket_groups=29, bucket_bits=6, smallest_interval=0.000001):
        self.thread = thread
        self.bucket_groups = bucket_groups
        self.bucket_bits = bucket_bits
        self.smallest_interval = smallest_interval
        self.buckets_per_group = 1 << self.bucket_bits
        self.total_buckets = self.bucket_groups * self.buckets_per_group
        self.last_time = time.time()
        bgroup = [ 0 for j in range(0, self.buckets_per_group) ]
        self.bg_histos = [ bgroup[:] for k in range(0, self.bucket_groups) ]
        self.bg_histos_prev = [ bgroup[:] for k in range(0, self.bucket_groups) ]
        bgroup_interval = [
            self.smallest_interval * k for k in range(0, self.buckets_per_group) ]
        smallest_bucket_group_width = self.smallest_interval * self.buckets_per_group
        self.group_intervals = []
        self.group_intervals.append(bgroup_interval[:])
        bgroup_interval = [
            bgroup_interval[k] + smallest_bucket_group_width
            for k in range(0, self.buckets_per_group) ]
        self.group_intervals.append( bgroup_interval[:] )
        for k in range(2, self.bucket_groups):
            bgroup_interval = list(map( lambda t: 2 * t, bgroup_interval))
            self.group_intervals.append( bgroup_interval[:] )
        self.bg_ranges =  list(map(lambda lst: lst[0], self.group_intervals))

    def add_to_histo(self, t):
        # known to be correct
        #bg_index = bisect_left(self.bg_ranges, t) - 1
        log2t = int(math.log2(t/self.smallest_interval)) - self.bucket_bits + 1
        if log2t < 0:
            log2t = 0
        elif log2t >= self.bucket_groups:
            log2t = self.bucket_groups - 1
        #assert(log2t == bg_index)
        bg = self.group_intervals[log2t]
        bg_width = bg[1] - bg[0]
        b_index = int((t - bg[0]) / bg_width)
        if t > bg[0] + (self.buckets_per_group * bg_width):
            b_index = self.buckets_per_group - 1
        self.bg_histos[log2t][b_index] += 1
        return log2t, b_index

    def total_samples(self):
        return sum( [ sum(self.bg_histos[k]) for k in range(0, self.bucket_groups) ] )

    def last_total_samples(self):
        return sum( [ sum(self.bg_histos_prev[k]) for k in range(0, self.bucket_groups) ] )

    # store latency histogram in file
    # note that multiple samples can be written
    # to measure percentiles as a function of time

    def dump_to_file(self, f):
        nl = '\n'
        f.write('latency-histogram-version: 1.0\n')
        f.write('thread: %s\n' % self.thread)
        f.write('time-sec: %d\n' % time.time() )
        f.write('bucket-bits: ' + str(self.bucket_bits) + nl)
        f.write('bucket-groups: ' + str(self.bucket_groups) + nl)
        f.write('smallest-interval: ' + str(self.smallest_interval) + nl)
        f.write('total-samples: ' + str(self.total_samples() - self.last_total_samples()) + nl)

        for bg in range(0, self.bucket_groups):
            # write change in counters
            delta_bg = [ self.bg_histos[bg][k] - self.bg_histos_prev[bg][k] for k in range(0, self.buckets_per_group) ]
            csv_buckets = ','.join([ str(b) for b in delta_bg ])
            f.write('group-%d: %s%s' % (bg, csv_buckets, nl))
        for bg in range(0, self.bucket_groups):
            self.bg_histos_prev[bg] = self.bg_histos[bg][:]
        # save this set of counters so we can output change in counters next time
        self.bg_histos_prev = [ self.bg_histos[k][:] for k in range(0, self.bucket_groups) ]

        f.write(nl)
        f.flush()
        
    # returns a latency histogram read from file

    def load_from_file(f):
        exc = LatencyHistException

        tokens = tokenize_line(f)
        if tokens[0] != 'latency-histogram-version' or tokens[1] != '1.0':
            raise exc('wrong version: ' + str(tokens))

        tokens = tokenize_line(f)
        if tokens[0] != 'thread':
            raise exc('expecting thread, saw %s' % tokens[0])
        thread = tokens[1]

        tokens = tokenize_line(f)
        if tokens[0] != 'time-sec':
            raise exc('expecting timestamp, saw %s' % tokens[0])
        last_time = float(tokens[1])

        tokens = tokenize_line(f)
        if tokens[0] != 'bucket-bits':
            raise exc('missing: bucket-bits')
        bucket_bits_read = int(tokens[1])

        tokens = tokenize_line(f)
        if tokens[0] != 'bucket-groups':
            raise exc('missing: bucket-groups')
        bucket_groups_read = int(tokens[1])

        tokens = tokenize_line(f)
        if tokens[0] != 'smallest-interval' and tokens [1] != '0.000001':
            raise exc('missing: smallest-interval')

        tokens = tokenize_line(f)
        if tokens[0] != 'total-samples':
            raise exc('missing: total-samples')
        read_total_samples = int(tokens[1])

        new_histo = latency_histogram(thread, bucket_bits=bucket_bits_read, bucket_groups=bucket_groups_read)
        new_histo.last_time = last_time
        bgh = new_histo.bg_histos

        for bg in range(0, bucket_groups_read):
            tokens = tokenize_line(f)
            group_str = 'group-%d' % bg
            if tokens[0] != group_str:
                raise exc('missing: ' + group_str)
            bucket_group = [ int(bval) for bval in tokens[1].split(',') ]
            bgh[bg] = bucket_group

        expected_total_samples = new_histo.total_samples()
        if read_total_samples != expected_total_samples:
            raise exc('total samples %d did not match sum of histograms %d' % 
                        (read_total_samples, expected_total_samples))

        tokens = tokenize_line(f)
        if tokens[0] != '':
            raise exc('expecting trailing newline')

        return new_histo

def unit_test():
    import random 
    h = latency_histogram('thread 1')
    bg_ix, b_ix = h.add_to_histo(1.0e-7)
    # guaranteed to be smallest histogram bucket
    assert bg_ix == 0 and b_ix == 0 and h.bg_histos[bg_ix][b_ix] == 1
    bg_ix, b_ix = h.add_to_histo(1.0e-7)
    assert bg_ix == 0 and b_ix == 0 and h.bg_histos[bg_ix][b_ix] == 2
    bg_ix, b_ix = h.add_to_histo(1<<30)
    assert bg_ix == h.bucket_groups - 1 and b_ix == h.buckets_per_group - 1 and h.bg_histos[bg_ix][b_ix] == 1

    random_sample_count = 50000
    new_count_str = os.getenv('RANDOM_SAMPLE_COUNT')
    if new_count_str:
        random_sample_count = int(new_count_str)
    samples = [ (random.expovariate(0.001) * 100) for k in range(0, random_sample_count) ]
    start_time = time.time()
    indices = [ h.add_to_histo(sample) for sample in samples ] 
    end_time = time.time()
    delta_time = end_time - start_time
    print('elapsed time for histogram of %d samples is %f sec' % (random_sample_count, delta_time))
    assert h.total_samples() == random_sample_count + 3
    f = open('/tmp/latency_histo.yml', 'w')
    h1 = deepcopy(h)
    h.dump_to_file(f)
    time.sleep(1)
    samples2 = [ (random.expovariate(0.001) * 100) for k in range(0, 2*random_sample_count) ]
    indices2 = [ h.add_to_histo(sample) for sample in samples2 ] 
    h2 = deepcopy(h)
    h.dump_to_file(f)
    f.close()
    read_f = open('/tmp/latency_histo.yml', 'r')

    read_h = latency_histogram.load_from_file(read_f)
    assert read_h.total_samples() == random_sample_count + 3
    assert read_h.bucket_groups == h1.bucket_groups
    assert read_h.buckets_per_group == h1.buckets_per_group
    for bg in range(0, read_h.bucket_groups):
        for b in range(0, read_h.buckets_per_group):
            assert read_h.bg_histos[bg][b] == h1.bg_histos[bg][b] - h1.bg_histos_prev[bg][b]

    read_h2 = latency_histogram.load_from_file(read_f)
    assert read_h2.total_samples() == 2*random_sample_count
    assert read_h2.bucket_groups == h.bucket_groups
    assert read_h2.buckets_per_group == h.buckets_per_group
    for bg in range(0, read_h2.bucket_groups):
        for b in range(0, read_h2.buckets_per_group):
            assert read_h2.bg_histos[bg][b] == h2.bg_histos[bg][b] - h2.bg_histos_prev[bg][b]

if __name__ == '__main__':
    unit_test()
