#!/usr/bin/python3
# record response times  via histogram to eliminate need to save all response times to a file
# modelled on fio's histogram feature
# for writeup of that, see https://github.com/axboe/fio/blob/master/doc/fio-histo-log-pctiles.pdf
# all buckets within a bucket group have same tMax-tMin
# first and second bucket group have same tMax-tMin
# after that, the k+1'th group has double the tMax-tMin of the k'th group
# so beginning time for each group is a power of 2

import copy
from bisect import bisect_left

class LatencyHistException(Exception):
    pass

class latency_histogram:

    def __init__(self, bucket_groups=29, bucket_bits=6, smallest_interval=0.000001):
        self.bucket_groups = bucket_groups
        self.bucket_bits = bucket_bits
        self.smallest_interval = smallest_interval
        self.buckets_per_group = 1 << self.bucket_bits
        self.total_buckets = self.bucket_groups * self.buckets_per_group
        bgroup = [ 0 for j in range(0, self.buckets_per_group) ]
        self.bg_histos = [ bgroup[:] for k in range(0, self.bucket_groups) ]
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
        bg_index = bisect_left(self.bg_ranges, t) - 1
        bg = self.group_intervals[bg_index]
        bg_width = bg[1] - bg[0]
        b_index = int((t - bg[0]) / bg_width)
        if t > bg[0] + (self.buckets_per_group * bg_width):
            b_index = self.buckets_per_group - 1
        self.bg_histos[bg_index][b_index] += 1
        return bg_index, b_index

    def total_samples(self):
        samples = 0
        for bg in self.bg_histos:
            samples += sum(bg)
        return samples

    # store latency histogram in file

    def dump_to_file(self, f):
        nl = '\n'
        f.write('latency-histogram-version: 1.0' + nl)
        f.write('bucket-bits: ' + str(self.bucket_bits) + nl)
        f.write('bucket-groups:' + str(self.bucket_groups) + nl)
        f.write('smallest-interval:' + str(self.smallest_interval) + nl)
        for bg in range(0, self.bucket_groups):
            csv_buckets = ','.join([ str(b) for b in self.bg_histos[bg] ])
            f.write('group-%d: %s%s' % (bg, csv_buckets, nl))

    # returns a latency histogram read from file

    def load_from_file(f):
        exc = LatencyHistException

        tokens = [ t.strip() for t in f.readline().split(':') ]
        if tokens[0] != 'latency-histogram-version' or tokens[1] != '1.0':
            raise exc('wrong version: ' + str(tokens))

        tokens = [ t.strip() for t in f.readline().split(':') ]
        if tokens[0] != 'bucket-bits':
            raise exc('missing: bucket-bits')
        bucket_bits_read = int(tokens[1])

        tokens = [ t.strip() for t in f.readline().split(':') ]
        if tokens[0] != 'bucket-groups':
            raise exc('missing: bucket-groups')
        bucket_groups_read = int(tokens[1])

        tokens = [ t.strip() for t in f.readline().split(':') ]
        if tokens[0] != 'smallest-interval' and tokens [1] != '0.000001':
            raise exc('missing: smallest-interval')

        new_histo = latency_histogram(bucket_bits=bucket_bits_read, bucket_groups=bucket_groups_read)
        bgh = new_histo.bg_histos

        for bg in range(0, bucket_groups_read):
            tokens = [ t.strip() for t in f.readline().split(':') ]
            group_str = 'group-%d' % bg
            if tokens[0] != group_str:
                raise exc('missing: ' + group_str)
            bucket_group = [ int(bval) for bval in tokens[1].split(',') ]
            bgh[bg] = bucket_group
        return new_histo

def unit_test():
    import random 
    h = latency_histogram()
    bg_ix, b_ix = h.add_to_histo(1.0e-7)
    # guaranteed to be smallest histogram bucket
    assert bg_ix == 0 and b_ix == 0 and h.bg_histos[bg_ix][b_ix] == 1
    bg_ix, b_ix = h.add_to_histo(1.0e-7)
    assert bg_ix == 0 and b_ix == 0 and h.bg_histos[bg_ix][b_ix] == 2
    bg_ix, b_ix = h.add_to_histo(1<<30)
    assert bg_ix == h.bucket_groups - 1 and b_ix == h.buckets_per_group - 1 and h.bg_histos[bg_ix][b_ix] == 1
    random_sample_count = 5000000
    map( lambda t : h.add_to_histo(t) , 
            [ random.expovariate(0.001) for sample in range(0, random_sample_count) ] ) 
    assert h.total_samples() == random_sample_count + 3
    with open('/tmp/latency_histo.yml', 'w') as f:
        h.dump_to_file(f)
    with open('/tmp/latency_histo.yml', 'r') as f:
        read_h = latency_histogram.load_from_file(f)
    assert read_h.total_samples() == random_sample_count + 3
    assert bg_ix == read_h.bucket_groups - 1 and b_ix == read_h.buckets_per_group - 1 and read_h.bg_histos[bg_ix][b_ix] == 1

if __name__ == '__main__':
    unit_test()
