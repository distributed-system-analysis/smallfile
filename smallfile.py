#!/usr/bin/python
# -*- coding: utf-8 -*-


'''
smallfile.py -- SmallfileWorkload class used in each workload thread
Copyright 2012 -- Ben England
Licensed under the Apache License at http://www.apache.org/licenses/LICENSE-2.0
See Appendix on this page for instructions pertaining to license.
Created on Apr 22, 2009
'''


# repeat a file operation N times
# allow for multi-thread tests with stonewalling
# we can launch any combination of these to simulate more complex workloads
# possible enhancements:
#    embed parallel python and thread launching logic so we can have both
#    CLI and GUI interfaces to same code
#
# to run just one of unit tests do
#   python -m unittest smallfile.Test.your-unit-test
# "unittest" regression test API has changed,
# unittest2 is there for backwards compatibility
# so it now uses unittest2,
# but it isn't installed by default so we have to conditionalize its use
# we only need it installed where we want to run regression test this way
# on Fedora:
#   yum install python-unittest2
# alternative single-test syntax:
#   python smallfile.py -v Test.test_c1_Mkdir


import os
import os.path
from os.path import exists, join
import sys
import time
import copy
import random
import logging
import threading
import socket
import errno
import codecs

OK = 0  # system call return code for success
NOTOK = 1
KB_PER_GB = 1 << 20
pct_files_min = 90  # min % of files considered acceptable for a test run

# we have to support a variety of python environments,
# so for optional features don't blow up if they aren't there, just remember

xattr_installed = True
try:
    import xattr
    xattr_installed = True
except ImportError as e:
    pass

fadvise_installed = False
try:
    import drop_buffer_cache
    fadvise_installed = True
except ImportError as e:
    pass

fallocate_installed = False
try:
    import fallocate  # not yet in python os module
    fallocate_installed = True
except ImportError as e:
    pass

unittest2_installed = False
try:
    import unittest2
    unittest2_installed = True
except ImportError as e:
    import unittest

# Windows 2008 server seemed to have this environment variable
# didn't check if it's universal

is_windows_os = (os.getenv('HOMEDRIVE') is not None)

# O_BINARY variable means we don't need to special-case windows
# in every open statement

O_BINARY = 0
if is_windows_os:
    O_BINARY = os.O_BINARY


# FIXME: pass in file pathname instead of file number

class MFRdWrExc(Exception):

    def __init__(self, opname_in, filenum_in, rqnum_in, bytesrtnd_in):
        self.opname = opname_in
        self.filenum = filenum_in
        self.rqnum = rqnum_in
        self.bytesrtnd = bytesrtnd_in

    def __str__(self):
        return 'file ' + str(self.filenum) + ' request ' \
            + str(self.rqnum) + ' byte count ' + str(self.bytesrtnd) \
            + ' ' + self.opname


class SMFResultException(Exception):

    def __init__(self, msg):
        Exception.__init__(self)
        self.msg = msg

    def __str__(self):
        return self.msg


# avoid exception if file we wish to delete is not there

def ensure_deleted(fn):
    try:
        if os.path.lexists(fn):
            os.unlink(fn)
    except Exception as e:
        # could be race condition with other client processes/hosts
        # if was race condition, file will no longer be there
        if os.path.exists(fn):
            raise Exception('exception while ensuring %s deleted: %s'
                            % (fn, str(e)))


# just create an empty file
# leave exception handling to caller

def touch(fn):
    with open(fn, 'w'):
        pass


# abort routine just cleans up threads

def abort_test(abort_fn, thread_list):
    if not os.path.exists(abort_fn):
        touch(abort_fn)


# create directory if it's not already there

def ensure_dir_exists(dirpath):
    if not os.path.exists(dirpath):
        parent_path = os.path.dirname(dirpath)
        if parent_path == dirpath:
            raise Exception('ensure_dir_exists: ' +
                            'cannot obtain parent path ' +
                            'of non-existent path: ' +
                            dirpath)
        ensure_dir_exists(parent_path)
        try:
            os.mkdir(dirpath)
        except os.error as e:
            if e.errno != errno.EEXIST:  # workaround for filesystem bug
                raise e
    else:
        if not os.path.isdir(dirpath):
            raise Exception('%s already exists and is not a directory!'
                            % dirpath)


# next two routines are for asynchronous replication
# we remember the time when a file was completely written
# and its size using xattr,
# then we read xattr in do_await_create operation
# and compute latencies from that

def remember_ctime_size_xattr(filedesc):
    nowtime = str(time.time())
    st = os.fstat(filedesc)
    xattr.setxattr(filedesc, 'user.smallfile-ctime-size', nowtime + ','
                   + str(st.st_size / SmallfileWorkload.BYTES_PER_KB))


def recall_ctime_size_xattr(pathname):
    (ctime, size_kb) = (None, None)
    try:
        with open(pathname, 'r') as fd:
            xattr_str = xattr.getxattr(fd, 'user.smallfile-ctime-size')
            token_pair = str(xattr_str).split(',')
            ctime = float(token_pair[0][2:])
            size_kb = int(token_pair[1].split('.')[0])
    except IOError as e:
        eno = e.errno
        if eno != errno.ENODATA:
            raise e
    return (ctime, size_kb)


def get_hostname(h):
    if h is None:
        h = socket.gethostname()
    return h


def hostaddr(h):    # return the IP address of a hostname
    if h is None:
        a = socket.gethostbyname(socket.gethostname())
    else:
        a = socket.gethostbyname(h)
    return a


def hexdump(b):
    s = ''
    for j in range(0, len(b)):
        s += '%02x' % b[j]
    return s


def binary_buf_str(b):      # display a binary buffer as a text string
    if sys.version < '3':
        return codecs.unicode_escape_decode(b)[0]
    else:
        if isinstance(b, str):
            return bytes(b).decode('UTF-8', 'backslashreplace')
        else:
            return b.decode('UTF-8', 'backslashreplace')


class SmallfileWorkload:

    rename_suffix = '.rnm'
    all_op_names = [
        'create',
        'delete',
        'append',
        'overwrite',
        'read',
        'readdir',
        'rename',
        'delete-renamed',
        'cleanup',
        'symlink',
        'mkdir',
        'rmdir',
        'stat',
        'chmod',
        'setxattr',
        'getxattr',
        'swift-get',
        'swift-put',
        'ls-l',
        'await-create',
        ]
    OK = 0
    NOTOK = 1
    BYTES_PER_KB = 1024
    MICROSEC_PER_SEC = 1000000.0

    # number of files between stonewalling check at smallest file size
    max_files_between_checks = 100

    # default for UNIX
    tmp_dir = os.getenv('TMPDIR')
    if tmp_dir is None:  # windows case
        tmp_dir = os.getenv('TEMP')
    if tmp_dir is None:  # assume POSIX-like
        tmp_dir = '/var/tmp'

    # constant file size
    fsdistr_fixed = -1
    # a file size distribution type that results in a few files much larger
    # than the mean and mostly files much smaller than the mean
    fsdistr_random_exponential = 0

    # multiply mean size by this to get max file size

    random_size_limit = 8

    # large prime number used to randomly select directory given file number

    some_prime = 900593

    # build largest supported buffer, and fill it full of random hex digits,
    # then just use a substring of it below

    biggest_buf_size_bits = 20
    random_seg_size_bits = 10
    biggest_buf_size = 1 << biggest_buf_size_bits

    # initialize files with up to this many different random patterns
    buf_offset_range = 1 << 10

    loggers = {}  # so we only instantiate logger for a given thread name once

    # constructor sets up initial, default values for test parameters
    # user overrides these values using CLI interface parameters
    # for boolean parameters,
    # preceding comment describes what happens if parameter is set to True

    def __init__(self):

        # all threads share same directory
        self.is_shared_dir = False

        # file operation type, default idempotent
        self.opname = 'cleanup'

        # how many files accessed, default = quick test
        self.iterations = 200

        # top of directory tree, default always exists on local fs
        top = join(self.tmp_dir, 'smf')

        # file that tells thread when to start running
        self.starting_gate = None

        # transfer size (KB), 0 = default to file size
        self.record_sz_kb = 0

        # total data read/written in KB
        self.total_sz_kb = 64

        # file size distribution, default = all files same size
        self.filesize_distr = self.fsdistr_fixed

        # how many directories to use
        self.files_per_dir = 100

        # fanout if > 1 dir/thread needed
        self.dirs_per_dir = 10

        # size of xattrs to read/write
        self.xattr_size = 0

        # number of xattrs to read/write
        self.xattr_count = 0

        # test-over polling rate
        self.files_between_checks = 20

        # prepend this to file name
        self.prefix = ''

        # append this to file name
        self.suffix = ''

        # directories are accessed randomly
        self.hash_to_dir = False

        # fsync() issued after a file is modified
        self.fsync = False

        # update xattr with ctime+size
        self.record_ctime_size = False

        # end test as soon as any thread finishes
        self.stonewall = True

        # finish remaining requests after test ends
        self.finish_all_rq = True

        # append response times to .rsptimes
        self.measure_rsptimes = False

        # write/expect binary random (incompressible) data
        self.incompressible = False

        # , compare read data to what was written
        self.verify_read = True

        # how many microsec to sleep between each file
        self.pause_between_files = 0

        # same as pause_between_files but in floating-point seconds
        self.pause_sec = 0.0

        # which host the invocation ran on
        self.onhost = get_hostname(None)

        # thread ID
        self.tid = ''

        # debug to screen
        self.log_to_stderr = False

        # print debug messages
        self.verbose = False

        # create directories as needed
        self.dirs_on_demand = False

        # for internal use only

        self.set_top([top])

        # logging level, default is just informational, warning or error
        self.log_level = logging.INFO

        # will be initialized later with thread-safe python logging object
        self.log = None

        # buffer for reads and writes will be here
        self.buf = None

        # copy from here on writes, compare to here on reads
        self.biggest_buf = None

        # random seed used to control sequence of random numbers,
        # default to different sequence every time
        self.randstate = random.Random()

        # reset object state variables

        self.reset()

    # convert object to string for logging, etc.

    def __str__(self):
        s = ' opname=' + self.opname
        s += ' iterations=' + str(self.iterations)
        s += ' top_dirs=' + str(self.top_dirs)
        s += ' src_dirs=' + str(self.src_dirs)
        s += ' dest_dirs=' + str(self.dest_dirs)
        s += ' network_dir=' + str(self.network_dir)
        s += ' shared=' + str(self.is_shared_dir)
        s += ' record_sz_kb=' + str(self.record_sz_kb)
        s += ' total_sz_kb=' + str(self.total_sz_kb)
        s += ' filesize_distr=' + str(self.filesize_distr)
        s += ' files_per_dir=%d' % self.files_per_dir
        s += ' dirs_per_dir=%d' % self.dirs_per_dir
        s += ' dirs_on_demand=' + str(self.dirs_on_demand)
        s += ' xattr_size=%d' % self.xattr_size
        s += ' xattr_count=%d' % self.xattr_count
        s += ' starting_gate=' + str(self.starting_gate)
        s += ' prefix=' + self.prefix
        s += ' suffix=' + self.suffix
        s += ' hash_to_dir=' + str(self.hash_to_dir)
        s += ' fsync=' + str(self.fsync)
        s += ' stonewall=' + str(self.stonewall)
        s += ' files_between_checks=' + str(self.files_between_checks)
        s += ' verify_read=' + str(self.verify_read)
        s += ' incompressible=' + str(self.incompressible)
        s += ' finish_all_rq=' + str(self.finish_all_rq)
        s += ' rsp_times=' + str(self.measure_rsptimes)
        s += ' tid=' + self.tid
        s += ' loglevel=' + str(self.log_level)
        s += ' filenum=' + str(self.filenum)
        s += ' filenum_final=' + str(self.filenum_final)
        s += ' rq=' + str(self.rq)
        s += ' rq_final=' + str(self.rq_final)
        s += ' start=' + str(self.start_time)
        s += ' end=' + str(self.end_time)
        s += ' elapsed=' + str(self.elapsed_time)
        s += ' host=' + str(self.onhost)
        s += ' status=' + str(self.status)
        s += ' abort=' + str(self.abort)
        s += ' log_to_stderr=' + str(self.log_to_stderr)
        s += ' verbose=' + str(self.verbose)
        return s

    # if you want to use the same instance for multiple tests
    # call reset() method between tests

    def reset(self):

        # results returned in variables below
        self.filenum = 0  # how many files have been accessed so far
        self.filenum_final = 0  # how many files accessed when test ended
        self.rq = 0  # how many reads/writes have been attempted so far
        self.rq_final = 0  # how many reads/writes completed when test ended
        self.abort = False
        self.file_dirs = []  # subdirectores within per-thread dir
        self.status = self.NOTOK
        self.pause_sec = self.pause_between_files / self.MICROSEC_PER_SEC

        # to measure per-thread elapsed time
        self.start_time = None
        self.end_time = None
        self.elapsed_time = 0

        # to measure file operation response times
        self.op_start_time = None
        self.rsptimes = []
        self.rsptime_filename = None

    # given a set of top-level directories (e.g. for NFS benchmarking)
    # set up shop in them
    # we only use one directory for network synchronization

    def set_top(self, top_dirs, network_dir=None):
        self.top_dirs = top_dirs
        # create/read files here
        self.src_dirs = [join(d, 'file_srcdir') for d in top_dirs]
        # rename files to here
        self.dest_dirs = [join(d, 'file_dstdir') for d in top_dirs]

        # directory for synchronization files shared across hosts
        self.network_dir = join(top_dirs[0], 'network_shared')
        if network_dir:
            self.network_dir = network_dir

    # create per-thread log file
    # we have to avoid getting the logger for self.tid more than once,
    # or else we'll add a handler more than once to this logger
    # and cause duplicate log messages in per-invoke log file

    def start_log(self):
        try:
            self.log = self.loggers[self.tid]
        except KeyError:
            self.log = logging.getLogger(self.tid)
            self.loggers[self.tid] = self.log
            if self.log_to_stderr:
                h = logging.StreamHandler()
            else:
                h = logging.FileHandler(self.log_fn())
            log_format = (self.tid +
                          ' %(asctime)s - %(levelname)s - %(message)s')
            formatter = logging.Formatter(log_format)
            h.setFormatter(formatter)
            self.log.addHandler(h)
        self.loglevel = logging.INFO
        if self.verbose:
            self.loglevel = logging.DEBUG
        self.log.setLevel(self.loglevel)

    # indicate start of an operation

    def op_starttime(self, starttime=None):
        if self.measure_rsptimes:
            if not starttime:
                self.op_start_time = time.time()
            else:
                self.op_start_time = starttime

    # indicate end of an operation,
    # this appends the elapsed time of the operation to .rsptimes array

    def op_endtime(self, opname):
        if self.measure_rsptimes:
            end_time = time.time()
            rsp_time = end_time - self.op_start_time
            self.rsptimes.append((opname, self.op_start_time, rsp_time))
            self.op_start_time = None

    # save response times seen by this thread

    def save_rsptimes(self):
        fname = 'rsptimes_' + str(self.tid) + '_' + get_hostname(None) \
            + '_' + self.opname + '_' + str(self.start_time) + '.csv'
        rsptime_fname = join(self.network_dir, fname)
        with open(rsptime_fname, 'w') as f:
            for (opname, start_time, rsp_time) in self.rsptimes:
                # time granularity is microseconds, accuracy is less
                f.write('%8s, %9.6f, %9.6f\n' %
                        (opname, start_time - self.start_time, rsp_time))
            os.fsync(f.fileno())  # particularly for NFS this is needed

    # determine if test interval is over for this thread

    # each thread uses this to signal that it is at the starting gate
    # (i.e. it is ready to immediately begin generating workload)

    def gen_thread_ready_fname(self, tid, hostname=None):
        return join(self.tmp_dir, 'thread_ready.' + tid + '.tmp')

    # each host uses this to signal that it is
    # ready to immediately begin generating workload
    # each host places this file in a directory shared by all hosts
    # to indicate that this host is ready

    def gen_host_ready_fname(self, hostname=None):
        if not hostname:
            hostname = self.onhost
        return join(self.network_dir, 'host_ready.' + hostname + '.tmp')

    # abort file tells other threads not to start test
    # because something has already gone wrong

    def abort_fn(self):
        return join(self.network_dir, 'abort.tmp')

    # stonewall file stops test measurement
    # (does not stop worker thread unless --finish N is used)

    def stonewall_fn(self):
        return join(self.network_dir, 'stonewall.tmp')

    # log file for this worker thread goes here

    def log_fn(self):
        return join(self.tmp_dir, 'invoke_logs-%s.log' % self.tid)

    # file for result stored as pickled python object

    def host_result_filename(self, result_host=None):
        if result_host is None:
            result_host = self.onhost
        return join(self.network_dir, result_host + '_result.pickle')

    # we use the seed function to control per-thread random sequence
    # we want seed to be saved
    # so that operations subsequent to initial create will know
    # what file size is for thread T's file j without having to stat the file

    def init_random_seed(self):
        if self.filesize_distr == self.fsdistr_fixed:
            return
        fn = self.gen_thread_ready_fname(self.tid,
                                         hostname=self.onhost) + '.seed'
        thread_seed = str(time.time())
        self.log.debug('seed opname: ' + self.opname)
        if self.opname == 'create' or self.opname == 'swift-put':
            thread_seed = str(time.time()) + ' ' + self.tid
            ensure_deleted(fn)
            with open(fn, 'w') as seedfile:
                seedfile.write(str(thread_seed))
                self.log.debug('write seed %s ' % thread_seed)
        elif ['append', 'read', 'swift-get'].__contains__(self.opname):
            with open(fn, 'r') as seedfile:
                thread_seed = seedfile.readlines()[0].strip()
                self.log.debug('read seed %s ' % thread_seed)
        self.randstate.seed(thread_seed)

    def get_next_file_size(self):
        next_size = self.total_sz_kb
        if self.filesize_distr == self.fsdistr_random_exponential:
            next_size = max(1, min(int(self.randstate.expovariate(1.0
                            / self.total_sz_kb)), self.total_sz_kb
                            * self.random_size_limit))
            if self.log_level == logging.DEBUG:
                self.log.debug('rnd expn file size %d KB' % next_size)
            else:
                self.log.debug('fixed file size %d KB' % next_size)
        return next_size

    # tell test driver that we're at the starting gate
    # this is a 2 phase process
    # first wait for each thread on this host to reach starting gate
    # second, wait for each host in test to reach starting gate
    # in case we have a lot of threads/hosts, sleep 1 sec between polls
    # also, wait 2 sec after seeing starting gate to maximize probability
    # that other hosts will also see it at the same time

    def wait_for_gate(self):
        if self.starting_gate:
            gateReady = self.gen_thread_ready_fname(self.tid)
            touch(gateReady)
            while not os.path.exists(self.starting_gate):
                if os.path.exists(self.abort_fn()):
                    raise Exception('thread ' + str(self.tid)
                                    + ' saw abort flag')
                # wait a little longer so that
                # other clients have time to see that gate exists
                time.sleep(0.3)

    # record info needed to compute test statistics

    def end_test(self):
        self.rq_final = self.rq
        self.filenum_final = self.filenum
        self.end_time = time.time()
        if self.filenum >= self.iterations \
           and not os.path.exists(self.stonewall_fn()):
            try:
                touch(self.stonewall_fn())
                self.log.info('stonewall file written by thread %s on host %s'
                              % (self.tid, get_hostname(None)))
            except IOError as e:
                err = e.errno
                if err != errno.EEXIST:
                    # workaround for possible bug in Gluster
                    if err != errno.EINVAL:
                        raise e
                    else:
                        self.log.info('saw EINVAL on stonewall, ignoring it')

    def test_ended(self):
        return self.end_time > self.start_time

    # see if we should do one more file
    # to minimize overhead, do not check stonewall file before every iteration

    def do_another_file(self):
        if self.stonewall and self.filenum % self.files_between_checks == 0:
            if not self.test_ended() and os.path.exists(self.stonewall_fn()):
                self.log.info('stonewalled after ' + str(self.filenum)
                              + ' iterations')
                self.end_test()

        # if user doesn't want to finish all requests and test has ended, stop

        if not self.finish_all_rq and self.test_ended():
            return False
        if self.filenum >= self.iterations:
            if not self.test_ended():
                self.end_test()
            return False
        if self.abort:
            raise Exception('thread ' + str(self.tid)
                            + ' saw abort flag')
        self.filenum += 1
        if self.pause_sec > 0.0:
            time.sleep(self.pause_sec)
        return True

    # in this method of directory selection, as filenum increments upwards,
    # we place F = files_per_dir files into directory,
    # then next F files into directory D+1, etc.
    # we generate directory pathnames like radix-D numbers
    # where D is subdirectories per directory
    # see URL http://gmplib.org/manual/Binary-to-Radix.html#Binary-to-Radix
    # this algorithm should take O(log(F))

    def mk_seq_dir_name(self, file_num):
        dir_in = file_num // self.files_per_dir
        # generate powers of self.files_per_dir not greater than dir_in
        level_dirs = []
        dirs_for_this_level = self.dirs_per_dir
        while dirs_for_this_level <= dir_in:
            level_dirs.append(dirs_for_this_level)
            dirs_for_this_level *= self.dirs_per_dir

        # generate each "digit" in radix-D number as result of quotients
        # from dividing remainder by next lower power of D (think of base 10)

        levels = len(level_dirs)
        level = levels - 1
        pathlist = []
        while level > -1:
            dirs_in_level = level_dirs[level]
            quotient = dir_in // dirs_in_level
            dir_in = dir_in - quotient * dirs_in_level
            dirnm = 'd_' + str(quotient).zfill(3)
            pathlist.append(dirnm)
            level -= 1
        pathlist.append('d_' + str(dir_in).zfill(3))
        return os.sep.join(pathlist)

    def mk_hashed_dir_name(self, file_num):
        pathlist = []
        random_hash = file_num * self.some_prime % self.iterations
        dir_num = random_hash // self.files_per_dir
        while dir_num > 1:
            dir_num_hash = dir_num * self.some_prime % self.dirs_per_dir
            pathlist.insert(0, 'h_' + str(dir_num_hash).zfill(3))
            dir_num //= self.dirs_per_dir
        return os.sep.join(pathlist)

    def mk_dir_name(self, file_num):
        if self.hash_to_dir:
            return self.mk_hashed_dir_name(file_num)
        else:
            return self.mk_seq_dir_name(file_num)

    # generate file name to put in this directory
    # prefix can be used for process ID or host ID for example
    # names are unique to each thread
    # automatically computes subdirectory for file based on
    # files_per_dir, dirs_per_dir and placing file as high in tree as possible
    # for multiple-mountpoint tests,
    # we need to select top-level dir based on file number
    # to spread load across mountpoints,
    # so we use round-robin mountpoint selection
    # NOTE: this routine is called A LOT,
    # so need to optimize by avoiding lots of os.path.join calls

    def mk_file_nm(self, base_dirs, filenum=-1):
        if filenum == -1:
            filenum = self.filenum
        listlen = len(base_dirs)
        tree = base_dirs[filenum % listlen]
        components = [
            tree,
            os.sep,
            self.file_dirs[filenum],
            os.sep,
            self.prefix,
            '_',
            self.onhost,
            '_',
            self.tid,
            '_',
            str(filenum),
            '_',
            self.suffix,
            ]
        return ''.join(components)

    # generate buffer contents, use these on writes and
    # compare against them for reads where random data is used,

    def create_biggest_buf(self, contents_random):

        # generate random byte sequence if desired.

        random_segment_size = 1 << self.random_seg_size_bits
        if not self.incompressible:

            # generate a random byte sequence of length 2^random_seg_size_bits
            # and then repeat the sequence
            # until we get to size 2^biggest_buf_size_bits in length

            if contents_random:
                biggest_buf = bytearray([self.randstate.randrange(0, 127)
                                         for k in
                                         range(0, random_segment_size)])
            else:
                biggest_buf = bytearray([k % 128 for k in
                                         range(0, random_segment_size)])

            # to prevent confusion in python when printing out buffer contents
            # WARNING: this line breaks PythonTidy utility
            biggest_buf = biggest_buf.replace(b'\\', b'!')

            # keep doubling buffer size until it is big enough

            next_power_2 = (self.biggest_buf_size_bits -
                            self.random_seg_size_bits)
            for j in range(0, next_power_2):
                biggest_buf.extend(biggest_buf[:])

        else:  # if incompressible

            # for buffer to be incompressible,
            # we can't repeat the same (small) random sequence
            # FIXME: why shouldn't we always do it this way?

            # initialize to a single random byte
            biggest_buf = bytearray([self.randstate.randrange(0, 255)])
            assert len(biggest_buf) == 1
            powerof2 = 1
            powersum = 1
            for j in range(0, self.biggest_buf_size_bits - 1):
                assert len(biggest_buf) == powersum
                powerof2 *= 2
                powersum += powerof2
                # biggest_buf length is now 2^j - 1
                biggest_buf.extend(
                    bytearray([self.randstate.randrange(0, 255)
                              for k in range(0, powerof2)]))
            biggest_buf.extend(
                bytearray([self.randstate.randrange(0, 255)]))

        # add extra space at end
        # so that we can get different buffer contents
        # by just using different offset into biggest_buf

        biggest_buf.extend(biggest_buf[0:self.buf_offset_range])
        assert (len(biggest_buf) ==
                self.biggest_buf_size + self.buf_offset_range)
        return biggest_buf

    # allocate buffer of correct size with offset based on filenum, tid, etc.

    def prepare_buf(self):

        # determine max record size of I/Os

        total_space_kb = self.record_sz_kb
        if self.record_sz_kb == 0:
            if self.filesize_distr != self.fsdistr_fixed:
                total_space_kb = self.total_sz_kb * self.random_size_limit
            else:
                total_space_kb = self.total_sz_kb

        total_space = total_space_kb * self.BYTES_PER_KB
        if total_space > SmallfileWorkload.biggest_buf_size:
            total_space = SmallfileWorkload.biggest_buf_size

        # ensure pre-allocated pre-initialized buffer space
        # big enough for xattr ops
        # use +, not *, see way buffers are used

        total_xattr_space = self.xattr_size + self.xattr_count
        if total_xattr_space > total_space:
            total_space = total_xattr_space

        # create a buffer with somewhat unique contents for this file,
        # so we'll know if there is a read error
        # FIXME: think harder about this

        unique_offset = (hash(self.tid) + self.filenum) % 1024
        assert total_space + unique_offset < len(self.biggest_buf)
        # NOTE: this means self.biggest_buf must be
        # 1K larger than SmallfileWorkload.biggest_buf_size
        self.buf = self.biggest_buf[unique_offset:total_space + unique_offset]
        # assert len(self.buf) == total_space

    # determine record size to use in test
    # if record size is 0, that means to use largest possible value
    # we try to use the file size as the record size, but
    # if the biggest_buf_size is less than the file size, use it instead.

    def get_record_size_to_use(self):
        rszkb = self.record_sz_kb
        if rszkb == 0:
            rszkb = self.total_sz_kb
        if rszkb > SmallfileWorkload.biggest_buf_size // self.BYTES_PER_KB:
            rszkb = SmallfileWorkload.biggest_buf_size // self.BYTES_PER_KB
        return rszkb

    # make all subdirectories needed for test in advance,
    # don't include in measurement
    # use set to avoid duplicating operations on directories

    def make_all_subdirs(self):
        self.log.debug('making all subdirs')
        abort_filename = self.abort_fn()
        if self.tid != '00' and self.is_shared_dir:
            return
        dirset = set()

        # FIXME: we could check to see if
        # self.dest_dirs is actually used before we include it

        for tree in [self.src_dirs, self.dest_dirs]:
            tree_range = range(0, len(tree))

            # if we are hashing into directories,
            # we can't make any assumptions about
            # which directories will be used first

            if self.hash_to_dir:
                dir_range = range(0, self.iterations + 1)
            else:
                # optimization: if not hashing into directories,
                # we put files_per_dir files into each directory, so
                # we only need to check every files_per_dir filenames
                # for a new directory name
                dir_range = range(0,
                                  self.iterations + self.files_per_dir,
                                  self.files_per_dir)

            # we need this range because
            # we need to create directories in each top dir
            for k in tree_range:
                for j in dir_range:
                    fpath = self.mk_file_nm(tree, j + k)
                    dpath = os.path.dirname(fpath)
                    dirset.add(dpath)

        # since we put them into a set, duplicates are filtered out

        for unique_dpath in dirset:
            if exists(abort_filename):
                break
            if not exists(unique_dpath):
                try:
                    os.makedirs(unique_dpath, 0o777)
                except OSError as e:
                    if not (e.errno == errno.EEXIST
                            and self.is_shared_dir):
                        raise e

    # clean up all subdirectories
    # algorithm same as make_all_subdirs

    def clean_all_subdirs(self):
        self.log.debug('cleaning all subdirs')
        if self.tid != '00' and self.is_shared_dir:
            return
        for tree in [self.src_dirs, self.dest_dirs]:

            # for efficiency, when we are not using --hash-to-dirs option,
            # we only make filename for every files_per_dir files

            if self.hash_to_dir:
                dir_range = range(0, self.iterations + 1)
            else:
                dir_range = range(0,
                                  self.iterations + self.files_per_dir,
                                  self.files_per_dir)

            # construct set of directories

            tree_range = range(0, len(tree))
            dirset = set()
            for k in tree_range:
                for j in dir_range:
                    fpath = self.mk_file_nm(tree, j + k)
                    dpath = os.path.dirname(fpath)
                    dirset.add(dpath)

            # now clean them up if empty,
            # and do this recursively on parent directories also
            # until top directory or non-empty directory is reached

            for unique_dpath in dirset:
                # determine top directory (i.e. one of list passed in --top)
                topdir = None
                for t in tree:
                    if unique_dpath.startswith(t):
                        topdir = t
                        break
                if not topdir:
                    raise Exception(('directory %s is not part of ' +
                                     'any top-level directory in %s')
                                    % (unique_dpath, str(tree)))

                # delete this directory and
                # parent directories if empty and below top

                while len(unique_dpath) > len(topdir):
                    if not exists(unique_dpath):
                        unique_dpath = os.path.dirname(unique_dpath)
                        continue
                    else:
                        try:
                            os.rmdir(unique_dpath)
                        except OSError as e:
                            err = e.errno
                            if err == errno.ENOTEMPTY:
                                break
                            if err == errno.EACCES:
                                break
                            if err == errno.EBUSY:  # might be mountpoint
                                break
                            self.log.error('deleting directory dpath: %s' % e)
                            if err != errno.ENOENT and not self.is_shared_dir:
                                raise e
                        unique_dpath = os.path.dirname(unique_dpath)
                        if len(unique_dpath) <= len(self.src_dirs[0]):
                            break

    # operation-specific test code goes in do_<opname>()
    # whatever record size sequence we use in do_create
    # must also be attempted in do_read

    def do_create(self):
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            self.op_starttime()
            fd = -1
            try:
                fd = os.open(fn,
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY | O_BINARY)
                if fd < 0:
                    raise MFRdWrExc(self.opname, self.filenum, 0, 0)
                remaining_kb = self.get_next_file_size()
                self.prepare_buf()
                rszkb = self.get_record_size_to_use()
                while remaining_kb > 0:
                    next_kb = min(rszkb, remaining_kb)
                    rszbytes = next_kb * self.BYTES_PER_KB
                    written = os.write(fd, self.buf[0:rszbytes])
                    if written != rszbytes:
                        raise MFRdWrExc(self.opname, self.filenum,
                                        self.rq, written)
                    self.rq += 1
                    remaining_kb -= next_kb
                if self.record_ctime_size:
                    remember_ctime_size_xattr(fd)
            except OSError as e:
                if e.errno == errno.ENOENT and self.dirs_on_demand:
                    os.makedirs(os.path.dirname(fn))
                    self.filenum -= 1  # retry this file now that dir. exists
                    continue
                raise e
            finally:
                if fd >= 0:
                    if self.fsync:
                        os.fsync(fd)
                    os.close(fd)
            self.op_endtime(self.opname)

    def do_mkdir(self):
        while self.do_another_file():
            dir = self.mk_file_nm(self.src_dirs) + '.d'
            self.op_starttime()
            try:
                os.mkdir(dir)
            except OSError as e:
                if e.errno == errno.ENOENT and self.dirs_on_demand:
                    os.makedirs(os.path.dirname(dir))
                    self.filenum -= 1
                    continue
            finally:
                self.op_endtime(self.opname)

    def do_rmdir(self):
        while self.do_another_file():
            dir = self.mk_file_nm(self.src_dirs) + '.d'
            self.op_starttime()
            os.rmdir(dir)
            self.op_endtime(self.opname)

    def do_symlink(self):
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            fn2 = self.mk_file_nm(self.dest_dirs) + '.s'
            self.op_starttime()
            os.symlink(fn, fn2)
            self.op_endtime(self.opname)

    def do_stat(self):
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            self.op_starttime()
            os.stat(fn)
            self.op_endtime(self.opname)

    def do_chmod(self):
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            self.op_starttime()
            os.chmod(fn, 0o646)
            self.op_endtime(self.opname)

    # we use "prefix" parameter to provide a list of characters
    # to use as extended attribute name suffixes
    # so that we can do multiple xattr operations per node

    def do_getxattr(self):
        if not xattr_installed:
            raise Exception('xattr module not present, ' +
                            'getxattr and setxattr operations will not work')

        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            self.op_starttime()
            self.prepare_buf()
            for j in range(0, self.xattr_count):
                v = xattr.getxattr(fn, 'user.smallfile-%d' % j)
                if self.buf[j:self.xattr_size + j] != v:
                    raise MFRdWrExc('getxattr: value contents wrong',
                                    self.filenum, j, len(v))
            self.op_endtime(self.opname)

    def do_setxattr(self):
        if not xattr_installed:
            raise Exception('xattr module not present, ' +
                            'getxattr and setxattr operations will not work')

        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            self.prepare_buf()
            self.op_starttime()
            fd = os.open(fn, os.O_WRONLY | O_BINARY)
            for j in range(0, self.xattr_count):
                # make sure each xattr has a unique value
                xattr.setxattr(fd, 'user.smallfile-%d' % j,
                               binary_buf_str(self.buf[j:self.xattr_size + j]))
            if self.fsync:  # fsync also flushes xattr values and metadata
                os.fsync(fd)
            os.close(fd)
            self.op_endtime(self.opname)

    def do_append(self):
        return self.do_write(append=True)

    def do_overwrite(self):
        return self.do_write()

    def do_write(self, append=False):
        if self.record_ctime_size and not xattr_installed:
            raise Exception('xattr module not present ' +
                            'but record-ctime-size specified')
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            self.op_starttime()
            fd = -1
            try:
                # don't use O_APPEND, it has different semantics!
                fd = os.open(fn, os.O_WRONLY | O_BINARY)
                if append: os.lseek(fd, 0, os.SEEK_END)
                remaining_kb = self.get_next_file_size()
                self.prepare_buf()
                rszkb = self.get_record_size_to_use()
                while remaining_kb > 0:
                    next_kb = min(remaining_kb, rszkb)
                    rszbytes = next_kb * self.BYTES_PER_KB
                    written = os.write(fd, self.buf[0:rszbytes])
                    self.rq += 1
                    if written != rszbytes:
                        raise MFRdWrExc(self.opname, self.filenum,
                                        self.rq, written)
                    remaining_kb -= next_kb
                if self.record_ctime_size:
                    remember_ctime_size_xattr(fd)
                if self.fsync:
                    os.fsync(fd)
            finally:
                if fd >= 0:
                    os.close(fd)
            self.op_endtime(self.opname)

    def do_read(self):
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            self.op_starttime()
            fd = -1
            try:
                next_fsz = self.get_next_file_size()
                fd = os.open(fn, os.O_RDONLY | O_BINARY)
                self.prepare_buf()
                rszkb = self.get_record_size_to_use()
                remaining_kb = next_fsz
                while remaining_kb > 0:
                    next_kb = min(rszkb, remaining_kb)
                    rszbytes = next_kb * self.BYTES_PER_KB
                    bytesread = os.read(fd, rszbytes)
                    self.rq += 1
                    if len(bytesread) != rszbytes:
                        raise MFRdWrExc(self.opname, self.filenum,
                                        self.rq, len(bytesread))
                    if self.verify_read and self.verbose:
                        self.log.debug(('read fn %s next_fsz %u remain %u ' +
                                        'rszbytes %u bytesread %u')
                                       % (fn, next_fsz, remaining_kb,
                                          rszbytes, len(bytesread)))
                        if self.buf[0:rszbytes] != bytesread:
                            raise MFRdWrExc('read: buffer contents wrong',
                                            self.filenum,
                                            self.rq,
                                            len(bytesread))
                    remaining_kb -= next_kb
            finally:
                if fd > -1:
                    os.close(fd)
            self.op_endtime(self.opname)

    def do_readdir(self):
        if self.hash_to_dir:
            raise Exception('cannot do readdir test with ' +
                            '--hash-into-dirs option')
        prev_dir = ''
        dir_map = {}
        file_count = 0
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            dir = os.path.dirname(fn)
            common_dir = None
            for d in self.top_dirs:
                if dir.startswith(d):
                    common_dir = dir[len(self.top_dirs[0]):]
                    break
            if not common_dir:
                raise Exception(('readdir: filename %s is not ' +
                                 'in any top dir in %s')
                                % (fn, str(self.top_dirs)))
            if common_dir != prev_dir:
                if file_count != len(dir_map):
                    raise MFRdWrExc(('readdir: not all files in ' +
                                     'directory %s were found')
                                    % prev_dir, self.filenum, self.rq, 0)
                self.op_starttime()
                dir_contents = []
                for t in self.top_dirs:
                    next_dir = t + common_dir
                    dir_contents.extend(os.listdir(next_dir))
                self.op_endtime(self.opname)
                prev_dir = common_dir
                dir_map = {}
                for listdir_filename in dir_contents:
                    if not listdir_filename[0] == 'd':
                        dir_map[listdir_filename] = True  # only include files
                file_count = 0
            if not fn.startswith('d'):
                file_count += 1  # only count files, not directories
            if os.path.basename(fn) not in dir_map:
                raise MFRdWrExc('readdir: file missing from directory %s'
                                % prev_dir, self.filenum, self.rq, 0)

    # this operation simulates a user doing "ls -lR" on a big directory tree
    # eventually we'll be able to use readdirplus() system call
    # if python supports it?

    def do_ls_l(self):
        if self.hash_to_dir:
            raise Exception('cannot do readdir test with ' +
                            '--hash-into-dirs option')
        prev_dir = ''
        dir_map = {}
        file_count = 0
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            dir = os.path.dirname(fn)
            common_dir = None
            for d in self.top_dirs:
                if dir.startswith(d):
                    common_dir = dir[len(self.top_dirs[0]):]
                    break
            if not common_dir:
                raise Exception('ls-l: filename %s is not in any top dir in %s'
                                % (fn, str(self.top_dirs)))
            if common_dir != prev_dir:
                self.op_starttime()
                dir_contents = []
                for t in self.top_dirs:
                    next_dir = t + common_dir
                    dir_contents.extend(os.listdir(next_dir))
                self.op_endtime(self.opname + '-readdir')
                prev_dir = common_dir
                dir_map = {}
                for listdir_filename in dir_contents:
                    if not listdir_filename[0] == 'd':
                        dir_map[listdir_filename] = True  # only include files
                file_count = 0
            # per-file stat timing separate readdir timing
            self.op_starttime()
            os.stat(fn)
            self.op_endtime(self.opname + '-stat')
            if not fn.startswith('d'):
                file_count += 1  # only count files, not directories
            if os.path.basename(fn) not in dir_map:
                raise MFRdWrExc('readdir: file missing from directory %s'
                                % prev_dir, self.filenum, self.rq, 0)

    # await-create is used for Gluster (async) geo-replication testing
    # instead of creating the files, we wait for them to appear
    # (e.g. on the slave geo-rep volume)
    # and measure throughput (and someday latency)

    def do_await_create(self):
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            self.log.debug('awaiting file %s' % fn)
            while not os.path.exists(fn):
                time.sleep(1.0)
            self.log.debug('awaiting original ctime-size xattr for file %s'
                           % fn)
            while True:
                (original_ctime, original_sz_kb) = recall_ctime_size_xattr(fn)
                if original_ctime is not None:
                    break
                time.sleep(1.0)
            self.log.debug(('waiting for file %s created ' +
                            'at %f to grow to original size %u')
                           % (fn, original_ctime, original_sz_kb))
            while True:
                st = os.stat(fn)
                if st.st_size > original_sz_kb * self.BYTES_PER_KB:
                    raise Exception(('asynchronously created replica ' +
                                     'in %s is %u bytes, ' +
                                     'larger than original %u KB')
                                    % (fn, st.st_size, original_sz_kb))
                elif st.st_size == original_sz_kb * self.BYTES_PER_KB:
                    break
            self.op_starttime(starttime=original_ctime)
            self.op_endtime(self.opname)

    def do_rename(self):
        in_same_dir = self.dest_dirs == self.src_dirs
        while self.do_another_file():
            fn1 = self.mk_file_nm(self.src_dirs)
            fn2 = self.mk_file_nm(self.dest_dirs)
            if in_same_dir:
                fn2 = fn2 + self.rename_suffix
            self.op_starttime()
            os.rename(fn1, fn2)
            self.op_endtime(self.opname)

    def do_delete(self):
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            self.op_starttime()
            os.unlink(fn)
            self.op_endtime(self.opname)

    # we only need this method because filenames after rename are different,

    def do_delete_renamed(self):
        in_same_dir = self.dest_dirs == self.src_dirs
        while self.do_another_file():
            fn = self.mk_file_nm(self.dest_dirs)
            if in_same_dir:
                fn = fn + self.rename_suffix
            self.op_starttime()
            os.unlink(fn)
            self.op_endtime(self.opname)

    # this operation tries to emulate a OpenStack Swift GET request behavior

    def do_swift_get(self):
        if not xattr_installed:
            raise Exception('xattr module not present, ' +
                            'getxattr and setxattr operations will not work')
        l = self.log
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            l.debug('swift_get fn %s ' % fn)
            next_fsz = self.get_next_file_size()
            self.op_starttime()
            fd = os.open(fn, os.O_RDONLY | O_BINARY)
            rszkb = self.get_record_size_to_use()
            remaining_kb = next_fsz
            self.prepare_buf()
            try:
                while remaining_kb > 0:
                    next_kb = min(rszkb, remaining_kb)
                    rszbytes = next_kb * self.BYTES_PER_KB
                    l.debug('swift_get fd ' +
                            '%d next_fsz %u remain %u rszbytes %u ' %
                            (fd, next_fsz, remaining_kb, rszbytes))
                    bytesread = os.read(fd, rszbytes)
                    if len(bytesread) != rszbytes:
                        raise MFRdWrExc(self.opname,
                                        self.filenum,
                                        self.rq,
                                        len(bytesread))
                    if self.verify_read:
                        if self.verbose:
                            l.debug('swift_get bytesread %u' % len(bytesread))
                        if self.buf[0:rszbytes] != bytesread:
                            xpct_buf = self.buf[0:rszbytes]
                            l.debug('expect buf: ' + binary_buf_str(xpct_buf))
                            l.debug('saw buf: ' + binary_buf_str(bytesread))
                            raise MFRdWrExc('read: buffer contents wrong',
                                            self.filenum,
                                            self.rq,
                                            len(bytesread))
                    remaining_kb -= next_kb
                    self.rq += 1
                for j in range(0, self.xattr_count):
                    try:
                        v = xattr.getxattr(fd, 'user.smallfile-all-%d' % j)
                        if self.verbose:
                            l.debug('xattr[%d] = %s' % (j, v))
                    except IOError as e:
                        if e.errno != errno.ENODATA:
                            raise e
            finally:
                os.close(fd)
            self.op_endtime(self.opname)

    # this operation type tries to emulate what a Swift PUT request does

    def do_swift_put(self):
        if not xattr_installed or \
           not fallocate_installed or \
           not fadvise_installed:
            raise Exception('one of necessary modules not available')

        l = self.log
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs) + '.tmp'
            next_fsz = self.get_next_file_size()
            self.prepare_buf()
            self.op_starttime()
            fd = -1  # so we know to not close it if file never got opened
            try:
                fd = os.open(fn, os.O_WRONLY | os.O_CREAT | O_BINARY)
                os.fchmod(fd, 0o667)
                fszbytes = next_fsz * self.BYTES_PER_KB
                # os.ftruncate(fd, fszbytes)
                ret = fallocate.fallocate(fd, 0, 0, fszbytes)
                if ret != OK:
                    raise Exception('fallocate call returned %d' % ret)
                rszkb = self.get_record_size_to_use()
                remaining_kb = next_fsz
                while remaining_kb > 0:
                    next_kb = min(rszkb, remaining_kb)
                    rszbytes = next_kb * self.BYTES_PER_KB
                    l.debug('reading %d bytes' % rszbytes)
                    if rszbytes != len(self.buf):
                        l.debug('swift put self.buf: ' +
                                binary_buf_str(self.buf[0:rszbytes]))
                        written = os.write(fd, self.buf[0:rszbytes])
                    else:
                        l.debug('swift put entire self.buf: ' +
                                binary_buf_str(self.buf[0:rszbytes]))
                        written = os.write(fd, self.buf[:])
                    if written != rszbytes:
                        l.error('written byte count ' +
                                '%u not correct byte count %u' %
                                (written, rszbytes))
                        raise MFRdWrExc(self.opname, self.filenum,
                                        self.rq, written)
                    remaining_kb -= next_kb
                for j in range(0, self.xattr_count):
                    xattr_nm = 'user.smallfile-all-%d' % j
                    try:
                        v = xattr.getxattr(fd, xattr_nm)
                    except IOError as e:
                        if e.errno != errno.ENODATA:
                            raise e
                        l.error('xattr %s does not exist' % xattr_nm)
                for j in range(0, self.xattr_count):
                    xattr_nm = 'user.smallfile-all-%d' % j
                    v = binary_buf_str(self.buf[j:self.xattr_size + j])
                    xattr.setxattr(fd, xattr_nm, v)
                    # l.debug('xattr ' + xattr_nm + ' set to ' + v)

                # alternative to ftruncate/fallocate is
                # close then open to prevent preallocation
                # since in theory close wipes out the preallocation and
                # fsync on re-opened file can then proceed without a problem
                # os.close(fd)
                # fd = os.open(fn, os.O_WRONLY)

                # another alternative that solves fragmentation problem
                # fd2 = os.open(fn, os.O_WRONLY)
                # os.close(fd2)

                if self.fsync:
                    # flush both data and metadata with one fsync
                    os.fsync(fd)
                if fadvise_installed:
                    # we assume here that data will not be read anytime soon
                    drop_buffer_cache.drop_buffer_cache(fd, 0, fszbytes)
                fn2 = self.mk_file_nm(self.src_dirs)
                os.rename(fn, fn2)
                self.rq += 1
            except Exception as e:
                ensure_deleted(fn)
                if self.verbose:
                    print('exception on %s' % fn)
                raise e
            finally:
                if fd > -1:
                    os.close(fd)
            self.op_endtime('swift-put')

    # unlike other ops, cleanup must always finish regardless of other threads

    def do_cleanup(self):
        save_stonewall = self.stonewall
        self.stonewall = False
        save_finish = self.finish_all_rq
        self.finish_all_rq = True
        while self.do_another_file():
            sym = self.mk_file_nm(self.dest_dirs) + '.s'
            ensure_deleted(sym)
            basenm = self.mk_file_nm(self.src_dirs)
            fn = basenm
            ensure_deleted(fn)
            fn += self.rename_suffix
            ensure_deleted(fn)
            fn = self.mk_file_nm(self.dest_dirs)
            ensure_deleted(fn)
            fn = basenm + self.rename_suffix
            ensure_deleted(fn)
            dir = basenm + '.d'
            if os.path.exists(dir):
                os.rmdir(dir)
        self.clean_all_subdirs()
        self.stonewall = save_stonewall
        self.finish_all_rq = save_finish
        self.status = ok

    def do_workload(self):
        self.reset()
        for j in range(0, self.iterations + self.files_per_dir):
            self.file_dirs.append(self.mk_dir_name(j))
        self.start_log()
        self.log.info('do_workload: ' + str(self))
        ensure_dir_exists(self.network_dir)
        if ['create', 'mkdir', 'swift-put'].__contains__(self.opname):
            self.make_all_subdirs()
        self.init_random_seed()
        self.biggest_buf = self.create_biggest_buf(False)
        if self.total_sz_kb > 0:
            self.files_between_checks = \
                max(10, self.max_files_between_checks - self.total_sz_kb / 100)
        try:
            self.end_time = 0.0
            self.start_time = time.time()
            self.wait_for_gate()
            o = self.opname
            try:
                func = SmallfileWorkload.workloads[o]
            except KeyError as e:
                raise Exception('invalid workload type ' + o)
            func(self)  # call the do_ function for that workload type
            self.status = ok
        except KeyboardInterrupt as e:
            self.log.error('control-C (SIGINT) signal received, ending test')
            self.status = ok
        except OSError as e:
            self.status = e.errno
            self.log.exception(e)
        if self.measure_rsptimes:
            self.save_rsptimes()
        if self.status != ok:
            self.log.error('invocation did not complete cleanly')
        if self.filenum != self.iterations:
            self.log.info('recorded throughput after '
                          + str(self.filenum) + ' files')
        if self.rq_final < 0:
            self.end_test()
        self.elapsed_time = self.end_time - self.start_time

        # this next call works fine with python 2.7
        # but not with python 2.6, why? do we need it?
        #    logging.shutdown()

        return self.status

    # we look up the function for the workload type
    # by workload name in this dictionary (hash table)

    workloads = {
        'create': do_create,
        'delete': do_delete,
        'symlink': do_symlink,
        'mkdir': do_mkdir,
        'rmdir': do_rmdir,
        'readdir': do_readdir,
        'ls-l': do_ls_l,
        'stat': do_stat,
        'getxattr': do_getxattr,
        'setxattr': do_setxattr,
        'chmod': do_chmod,
        'append': do_append,
        'overwrite': do_overwrite,
        'read': do_read,
        'rename': do_rename,
        'delete-renamed': do_delete_renamed,
        'cleanup': do_cleanup,
        'swift-put': do_swift_put,
        'swift-get': do_swift_get,
        'await-create': do_await_create,
        }


# threads used to do multi-threaded unit testing

class TestThread(threading.Thread):

    def __init__(self, my_invocation, my_name):
        threading.Thread.__init__(self, name=my_name)
        self.invocation = my_invocation

    def __str__(self):
        return 'TestThread ' + str(self.invocation) + ' ' + \
            threading.Thread.__str__(self)

    def run(self):
        try:
            self.invocation.do_workload()
        except Exception as e:
            self.invocation.log.error(str(e))


# below are unit tests for SmallfileWorkload
# including multi-threaded test
# this should be designed to run without any user intervention
# to run just one of these tests do
#   python -m unittest2 smallfile.Test.your-unit-test

ok = 0
if unittest2_installed:
    unittest_class = unittest2.TestCase
else:
    unittest_class = unittest.TestCase


class Test(unittest_class):

    def setUp(self):
        self.invok = SmallfileWorkload()
        self.invok.opname = 'create'
        self.invok.iterations = 50
        self.invok.files_per_dir = 5
        self.invok.dirs_per_dir = 2
        self.invok.verbose = True
        self.invok.prefix = 'p'
        self.invok.suffix = 's'
        self.invok.tid = 'regtest'
        self.deltree(self.invok.network_dir)
        ensure_dir_exists(self.invok.network_dir)

    def deltree(self, topdir):
        if not os.path.exists(topdir):
            return
        if not os.path.isdir(topdir):
            return
        for (dir, subdirs, files) in os.walk(topdir, topdown=False):
            for f in files:
                os.unlink(join(dir, f))
            for d in subdirs:
                os.rmdir(join(dir, d))
        os.rmdir(topdir)

    def chk_status(self):
        if self.invok.status != ok:
            raise Exception('test failed, check log file %s'
                            % self.invok.log_fn())

    def runTest(self, opName):
        self.invok.opname = opName
        self.invok.do_workload()
        self.chk_status()

    def file_size(self, fn):
        st = os.stat(fn)
        return st.st_size

    def checkDirEmpty(self, emptyDir):
        self.assertTrue(os.listdir(emptyDir) == [])

    def lastFileNameInTest(self, tree):
        return self.invok.mk_file_nm(tree, self.invok.filenum - 1)

    def checkDirListEmpty(self, emptyDirList):
        for d in emptyDirList:
            if exists(d):
                assert os.listdir(d) == []

    def cleanup_files(self):
        self.runTest('cleanup')

    def mk_files(self):
        self.cleanup_files()
        self.runTest('create')
        lastfn = self.lastFileNameInTest(self.invok.src_dirs)
        self.assertTrue(exists(lastfn))
        assert os.path.getsize(lastfn) == \
            self.invok.total_sz_kb * self.invok.BYTES_PER_KB

    def test1_recreate_src_dest_dirs(self):
        for s in self.invok.src_dirs:
            self.deltree(s)
            os.mkdir(s)
        for s in self.invok.dest_dirs:
            self.deltree(s)
            os.mkdir(s)

    def test_a_MkFn(self):
        self.mk_files()
        ivk = self.invok
        fn = ivk.mk_file_nm(ivk.src_dirs, 1)
        lastfn = ivk.mk_file_nm(ivk.src_dirs, ivk.iterations)

        expectedFn = join(join(self.invok.src_dirs[0], 'd_000'),
                          ivk.prefix + '_' + 
                          ivk.onhost + '_' + 
                          ivk.tid + '_1_' + 
                          ivk.suffix)
        self.assertTrue(fn == expectedFn)
        self.assertTrue(exists(fn))
        self.assertTrue(exists(lastfn))
        self.assertTrue(ivk.filenum == ivk.iterations)
        os.unlink(fn)
        self.assertTrue(not exists(fn))

    def test_b_Cleanup(self):
        self.cleanup_files()

    def test_c_Create(self):
        self.mk_files()  # depends on cleanup_files
        fn = self.lastFileNameInTest(self.invok.src_dirs)
        assert exists(fn)

    def test_c1_Mkdir(self):
        self.cleanup_files()
        self.runTest('mkdir')
        last_dir = self.lastFileNameInTest(self.invok.src_dirs) + '.d'
        self.assertTrue(exists(last_dir))

    def test_c2_Rmdir(self):
        self.cleanup_files()
        self.runTest('mkdir')
        self.runTest('rmdir')
        last_dir = self.lastFileNameInTest(self.invok.src_dirs) + '.d'
        self.assertTrue(not exists(last_dir))

    def test_c3_Symlink(self):
        if is_windows_os:
            return
        self.cleanup_files()
        self.mk_files()
        self.runTest('symlink')
        lastSymlinkFile = self.lastFileNameInTest(self.invok.dest_dirs)
        lastSymlinkFile += '.s'
        self.assertTrue(exists(lastSymlinkFile))

    def test_c4_Stat(self):
        self.cleanup_files()
        self.mk_files()
        self.runTest('stat')

    def test_c44_Readdir(self):
        self.cleanup_files()
        self.mk_files()
        self.runTest('readdir')

    def test_c45_Ls_l(self):
        self.cleanup_files()
        self.mk_files()
        self.runTest('ls-l')

    def test_c5_Chmod(self):
        self.cleanup_files()
        self.mk_files()
        self.runTest('chmod')

    def test_c6_xattr(self):
        if xattr_installed:
            self.cleanup_files()
            self.mk_files()
            self.fsync = True
            self.xattr_size = 256
            self.xattr_count = 10
            self.runTest('setxattr')
            self.runTest('getxattr')

    def test_d_Delete(self):
        self.invok.measure_rsptimes = True
        self.mk_files()
        self.runTest('delete')
        self.invok.clean_all_subdirs()
        self.checkDirListEmpty(self.invok.src_dirs)

    def test_e_Rename(self):
        self.invok.measure_rsptimes = False
        self.mk_files()
        self.runTest('rename')
        fn = self.invok.mk_file_nm(self.invok.dest_dirs)
        self.assertTrue(exists(fn))

    def test_f_DeleteRenamed(self):
        self.mk_files()
        self.runTest('rename')
        self.runTest('delete-renamed')
        # won't delete any files or directories that contain them
        self.invok.clean_all_subdirs()
        self.checkDirListEmpty(self.invok.src_dirs)
        self.checkDirListEmpty(self.invok.dest_dirs)

    def test_g0_Overwrite(self):
        self.mk_files()
        orig_kb = self.invok.total_sz_kb
        self.runTest('overwrite')
        fn = self.lastFileNameInTest(self.invok.src_dirs)
        self.assertTrue(self.file_size(fn) == orig_kb
                        * self.invok.BYTES_PER_KB)

    def test_g1_Append(self):
        self.mk_files()
        orig_kb = self.invok.total_sz_kb
        self.invok.total_sz_kb *= 2
        self.runTest('append')
        fn = self.lastFileNameInTest(self.invok.src_dirs)
        self.assertTrue(self.file_size(fn) == 3 * orig_kb
                        * self.invok.BYTES_PER_KB)

    def test_g2_Append_Rsz_0_big_file(self):
        self.mk_files()
        orig_kb = self.invok.total_sz_kb
        self.invok.total_sz_kb = 2048
        # boundary condition where we want record size < max buffer space
        self.invok.record_sz_kb = 0
        self.runTest('append')
        fn = self.lastFileNameInTest(self.invok.src_dirs)
        self.assertTrue(self.file_size(fn) == (orig_kb + 2048)
                        * self.invok.BYTES_PER_KB)

    def test_h00_read(self):
        if not xattr_installed:
            return
        self.invok.record_ctime_size = True
        self.mk_files()
        self.invok.verify_read = True
        self.runTest('read')

    # this test inherits files from preceding test

    def test_h0_await_create(self):
        if not xattr_installed:
            return
        self.runTest('await-create')

    def test_h1_Read_Rsz_0_big_file(self):
        self.test_g2_Append_Rsz_0_big_file()
        ivk = self.invok
        ivk.total_sz_kb = 2048
        ivk.iterations = 5
        # boundary condition where we want record size < max buffer space
        ivk.record_sz_kb = 0
        self.runTest('read')
        self.assertTrue(ivk.total_sz_kb * ivk.BYTES_PER_KB
                        > ivk.biggest_buf_size)
        expected_reads_per_file = ivk.total_sz_kb * ivk.BYTES_PER_KB \
            // ivk.biggest_buf_size
        self.assertTrue(ivk.rq == ivk.iterations
                        * expected_reads_per_file)

    def test_h2_read_bad_data(self):
        self.mk_files()
        self.invok.verify_read = True
        fn = self.lastFileNameInTest(self.invok.src_dirs)
        fd = os.open(fn, os.O_WRONLY | O_BINARY)
        os.lseek(fd, 5, os.SEEK_SET)

        os.write(fd, b'!')

        os.close(fd)
        try:
            self.runTest('read')
        except MFRdWrExc:
            pass
        self.assertTrue(self.invok.status != ok)

    def test_z1_create(self):
        self.cleanup_files()
        self.invok.filesize_distr = self.invok.fsdistr_random_exponential
        self.invok.incompressible = True
        self.invok.verify_read = True
        self.invok.invocations = 40
        self.invok.record_sz_kb = 0
        self.invok.total_sz_kb = 16
        self.runTest('create')

    # inherits files from the z1_create test

    def test_z2_read(self):
        self.invok.filesize_distr = self.invok.fsdistr_random_exponential
        self.invok.incompressible = True
        self.invok.verify_read = True
        self.invok.invocations = 40
        self.invok.record_sz_kb = 0
        self.invok.total_sz_kb = 16
        self.runTest('read')

    # inherits files from the z1_create test

    def test_z3_append(self):
        self.invok.filesize_distr = \
            self.invok.fsdistr_random_exponential
        self.invok.incompressible = True
        self.invok.verify_read = True
        self.invok.invocations = 40
        self.invok.record_sz_kb = 0
        self.invok.total_sz_kb = 16
        self.runTest('append')

    def test_i1_do_swift_put(self):
        if not xattr_installed:
            return
        self.cleanup_files()
        self.invok.invocations = 10
        self.invok.record_sz_kb = 5
        self.invok.total_sz_kb = 64
        self.invok.xattr_size = 128
        self.invok.xattr_count = 2
        self.invok.fsync = True
        self.invok.filesize_distr = self.invok.fsdistr_random_exponential
        self.runTest('swift-put')

    # inherits files from the i1_do_swift_put test

    def test_i2_do_swift_get(self):
        if not xattr_installed:
            return
        self.invok.invocations = 10
        self.invok.record_sz_kb = 5
        self.invok.total_sz_kb = 64
        self.invok.xattr_size = 128
        self.invok.xattr_count = 2
        self.invok.filesize_distr = self.invok.fsdistr_random_exponential
        self.runTest('swift-get')

    def test_j0_dir_name(self):
        self.invok.files_per_dir = 20
        self.invok.dirs_per_dir = 3
        d = self.invok.mk_dir_name(29 * self.invok.files_per_dir)
        expected = join('d_001', join('d_000', join('d_000', 'd_002')))
        self.assertTrue(d == expected)
        self.invok.dirs_per_dir = 7
        d = self.invok.mk_dir_name(320 * self.invok.files_per_dir)
        expected = join(join('d_006', 'd_003'), 'd_005')
        self.assertTrue(d == expected)

    def test_j1_deep_tree(self):
        self.invok.total_sz_kb = 0
        self.invok.record_sz_kb = 0
        self.invok.files_per_dir = 10
        self.invok.dirs_per_dir = 3
        self.invok.iterations = 200
        self.invok.prefix = ''
        self.invok.suffix = 'deep'
        self.mk_files()
        self.assertTrue(exists(self.lastFileNameInTest(self.invok.src_dirs)))
        self.cleanup_files()

    def test_j2_deep_hashed_tree(self):
        self.invok.suffix = 'deep_hashed'
        self.invok.total_sz_kb = 0
        self.invok.record_sz_kb = 0
        self.invok.files_per_dir = 5
        self.invok.dirs_per_dir = 4
        self.invok.iterations = 500
        self.invok.hash_to_dir = True
        self.mk_files()
        fn = self.lastFileNameInTest(self.invok.src_dirs)
        expectedFn = os.sep.join([self.invok.src_dirs[0], 'h_001',
                                  'h_000', 'h_001',
                                  'p_%s_regtest_499_deep_hashed' % self.invok.onhost])
        self.assertTrue(fn == expectedFn)
        self.assertTrue(exists(fn))
        self.cleanup_files()

    def test_z_multithr_stonewall(self):
        self.invok.stonewall = True
        self.invok.finish = True
        self.invok.prefix = 'thr_'
        self.invok.suffix = 'foo'
        self.invok.iterations = 400
        self.invok.files_per_dir = 10
        self.invok.dirs_per_dir = 3
        sgate_file = join(self.invok.network_dir, 'starting_gate.tmp')
        self.invok.starting_gate = sgate_file
        thread_ready_timeout = 4
        thread_count = 4
        self.test1_recreate_src_dest_dirs()
        self.checkDirListEmpty(self.invok.src_dirs)
        self.checkDirListEmpty(self.invok.dest_dirs)
        self.checkDirEmpty(self.invok.network_dir)
        invokeList = []
        for j in range(0, thread_count):
            s = copy.copy(self.invok)  # test copy constructor
            s.tid = str(j)
            s.src_dirs = [join(d, 'thrd_' + s.tid) for d in s.src_dirs]
            s.dest_dirs = [join(d, 'thrd_' + s.tid) for d in
                           s.dest_dirs]
            invokeList.append(s)
        threadList = []
        for s in invokeList:
            ensure_deleted(s.gen_thread_ready_fname(s.tid))
            threadList.append(TestThread(s, s.prefix + s.tid))
        for t in threadList:
            t.start()
        time.sleep(0.3)
        threads_ready = True  # define scope outside loop
        for i in range(0, thread_ready_timeout):
            threads_ready = True
            for s in invokeList:
                thread_ready_file = s.gen_thread_ready_fname(s.tid)
                if not os.path.exists(thread_ready_file):
                    threads_ready = False
                    break
            if threads_ready:
                break
            time.sleep(1.1)
        if not threads_ready:
            abort_test(self.invok.abort_fn(), threadList)
            for t in threadList:
                t.join(1.1)
            raise Exception('threads did not show up within %d seconds'
                            % thread_ready_timeout)
        touch(sgate_file)
        for t in threadList:
            t.join()
            if t.isAlive():
                raise Exception('thread join timeout:' + str(t))
            if t.invocation.status != ok:
                raise Exception('thread did not complete iterations: '
                                + str(t))


# so you can just do "python smallfile.py" to test it

if __name__ == '__main__':
    if unittest2_installed:
        unittest2.main()
    else:
        unittest.main()
