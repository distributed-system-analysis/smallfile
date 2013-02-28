'''
smallfile.py -- smf_invocation class used in each workload thread
Copyright 2012 -- Ben England
Licensed under the Apache License at http://www.apache.org/licenses/LICENSE-2.0
See Appendix on this page for instructions pertaining to license.
Created on Apr 22, 2009
'''

# repeat a file operation N times
# allow for multi-thread tests with stonewalling
# we can launch any combination of these to simulate more complex workloads
# possible enhancements: 
#    do stonewalling based on I/O request count to get cluster iozone functionality
#    embed parallel python and thread launching logic so we can have both
#    CLI and GUI interfaces to same code
#
# to run just one of unit tests do python -m unittest smallfile.Test.your-unit-test

import os
import os.path
from os.path import exists
import sys
import glob
import string
import time
import exceptions
import unittest
import random
import logging
from logging import ERROR
from logging import INFO
from logging import WARN
from logging import DEBUG
import threading
import socket
import errno

#OS_SEEK_END = 2 # required for python 2.4

xattr_not_installed = True
try:
  import xattr
  xattr_not_installed = False
except ImportError as e:
  pass

is_windows_os = False
if os.getenv("HOMEDRIVE"): is_windows_os = True

class MFRdWrExc(Exception):
    def __init__(self, opname_in, filenum_in, rqnum_in, bytesrtnd_in):
        self.opname = opname_in
        self.filenum = filenum_in
        self.rqnum = rqnum_in
        self.bytesrtnd = bytesrtnd_in
    def __str__(self):
        return "file " + str(self.filenum) + " request " + str(self.rqnum) + " byte count " + str(self.bytesrtnd) + ' ' + self.opname

class MFNotImplYetExc(Exception):
    def __str__(self):
        return "not implemented yet"

# avoid exception if file we wish to delete is not there

def ensure_deleted(fn):
    try:
      if os.path.lexists(fn): os.unlink(fn)
    except Exception, e:
      # could be race condition with other client processes/hosts
      if os.path.exists(fn): # if was race condition, file will no longer be there
         raise Exception("exception while ensuring %s deleted: %s"%(fn, str(e)))

# create directory if it's not already there

def ensure_dir_exists( dirpath ):
    if not os.path.exists(dirpath):
        ensure_dir_exists(os.path.dirname(dirpath))
        try:
            os.mkdir(dirpath)
        except os.error, e:
            if e.errno != errno.EEXIST: # workaround for filesystem bug
                raise e
    else:
        if not os.path.isdir(dirpath):
            raise Exception("%s already exists and is not a directory!"%dirpath)

def short_hostname(h):
  if h == None: h = socket.gethostname()
  return h.split('.')[0]

def hostaddr(h):
  if h == None: a = socket.gethostbyname(socket.gethostname())
  else: a = socket.gethostbyname(h)
  return a

# parameters for test stored here
# initialize with default values
# FIXME: do we need a copy constructor?

invocation_count = 0

class smf_invocation:
    rename_suffix = ".rnm"
    separator = os.sep  # makes it portable to Windows
    all_op_names = [ "create", "delete", "append", "read", "rename", "delete-renamed", "cleanup", "all", "symlink", "mkdir", "rmdir", "stat", "chmod", "setxattr", "getxattr" ]
    #OK = 0
    NOTOK = 1
    BYTES_PER_KB = 1024  # bytes per kilobyte
    MICROSEC_PER_SEC = 1000000.0  
    max_files_between_checks = 100 # number of files between stonewalling check at smallest file size
    tmp_dir = os.getenv("TMPDIR")  # UNIX case
    filesize_distr_fixed = -1 # no file size distribution
    filesize_distr_random_exponential = 0 # a file size distribution type
    if tmp_dir == None: tmp_dir = os.getenv("TEMP") # windows case
    if tmp_dir == None: tmp_dir = "/var/tmp"  # assume POSIX-like
    some_prime = 900593

    # build largest supported buffer, then
    # just use a substring of it below
    biggest_buf = ''
    biggest_buf_size_bits = 24
    random_seg_size_bits = 10
    biggest_buf_size = 1 << biggest_buf_size_bits

    hexdigits='0123456789ABCDEF'
    bigprime=9533
    bigprime2_squared = 34613*34613
    for k in range(1<<random_seg_size_bits):
        biggest_buf += hexdigits[bigprime & 0xf]
        bigprime *= bigprime
        bigprime %= bigprime2_squared  # prevent integer overflow 
    for j in range(0,biggest_buf_size_bits+1-random_seg_size_bits):
        biggest_buf += biggest_buf[:]
    assert len(biggest_buf) == (1<<(biggest_buf_size_bits+1))

    # constructor sets up initial, default values for test parameters

    def __init__(self):
        global invocation_count
        # operation types
        self.is_shared_dir = False    # True if all threads share same directory
        self.opname = "cleanup"       # what kind of file access, default is an idempotent operation
        self.iterations = 1           # how many files to access
        top = os.path.join(self.tmp_dir, 'smf')
        self.set_top([top])
        self.starting_gate = None     # file that tells thread when to start running
        self.record_sz_kb = 8         # record size in KB
        self.total_sz_kb = 64         # total data read/written in KB
        self.filesize_distr = self.filesize_distr_fixed  # original behavior, all files have same size
        self.files_per_dir = 1000       # determines how many directories to use
        self.dirs_per_dir = 100         # fanout if multiple levels of directories are needed, 
        self.xattr_size = 128         # size of extended attribute to read/write
        self.xattr_count = 1          # number of extended attribute to read/write
        self.files_between_checks = 8 # number of files between stonewalling check
        self.prefix = ""              # prepend this to file name
        self.suffix = ""              # append this to file name
        self.hash_to_dir = False      # controls whether directories are accessed sequentially or randomly
        self.stonewall = True         # if so, end test as soon as any thread finishes
        self.finish_all_rq = True     # if so, finish remaining requests after test ends
        self.measure_rsptimes = False # if so, append operation response times to .rsptimes
        self.verify_read = True       # if so, compare read data to what was written
        self.pause_between_files = 0  # how many microsec to sleep between each file
        self.pause_sec = 0.0          # same as pause_between_files but in floating-point seconds
        self.onhost = ""              # record which host the invocation ran on
        self.tid = ""                 # thread ID 
        self.direct = 0               # set for direct I/O
        self.log_to_stderr = False    # set to true for debugging to screen
        self.verbose = False          # set this to true for debugging
         # for internal use only
        self.log_level = logging.INFO
        self.log = None               # use python log module, it is thread safe
        self.buf = ""                 # buffer for reads and writes will be here
        self.randstate = random.Random()
        self.reset()
        invocation_count += 1    # FIXME: not thread-safe
        self.invocation_id = invocation_count - 1 # used to generate unique write/read contents per file

    # copy constructor

    def clone(smf_instance):
        global invocation_count
        s = smf_instance
        new = smf_invocation()
        new.opname = s.opname
        new.iterations = s.iterations
        new.src_dirs = s.src_dirs
        new.dest_dirs = s.dest_dirs
        new.network_dir = s.network_dir
        new.is_shared_dir = s.is_shared_dir
        new.record_sz_kb = s.record_sz_kb
        new.total_sz_kb = s.total_sz_kb
        new.filesize_distr = s.filesize_distr
        new.files_per_dir = s.files_per_dir
        new.dirs_per_dir = s.dirs_per_dir
        new.xattr_size = s.xattr_size
        new.xattr_count = s.xattr_count
        new.files_between_checks = s.files_between_checks
        new.starting_gate = s.starting_gate
        new.prefix = s.prefix
        new.suffix = s.suffix
        new.hash_to_dir = s.hash_to_dir
        new.stonewall = s.stonewall
        new.finish_all_rq = s.finish_all_rq
        new.measure_rsptimes = s.measure_rsptimes
        new.pause_between_files = s.pause_between_files
        new.pause_sec = s.pause_sec
        new.onhost = s.onhost
        new.log_to_stderr = s.log_to_stderr
        new.verbose = s.verbose
        new.direct = s.direct
        new.log_level = s.log_level
        new.log = None
        new.tid = None
        new.randstate = random.Random()
        new.reset()
        return new

    # convert object to string for logging, etc.

    def __str__(self):
        s  = " opname="+self.opname
        s += " iterations="+str(self.iterations)
        s += " src_dirs="+str(self.src_dirs)
        s += " dest_dirs="+str(self.dest_dirs)
        s += " network_dir="+str(self.network_dir)
        s += " shared="+str(self.is_shared_dir)
        s += " record_sz_kb="+str(self.record_sz_kb)
        s += " total_sz_kb="+str(self.total_sz_kb)
        s += " filesize_distr="+str(self.filesize_distr)
        s += " files_per_dir=%d"%self.files_per_dir
        s += " dirs_per_dir=%d"%self.dirs_per_dir
        s += " xattr_size=%d"%self.xattr_size
        s += " xattr_count=%d"%self.xattr_count
        s += " starting_gate="+str(self.starting_gate)
        s += " prefix="+self.prefix
        s += " suffix="+self.suffix
        s += " hash_to_dir="+str(self.hash_to_dir)
        s += " stonewall="+str(self.stonewall)
        s += " files_between_checks="+str(self.files_between_checks)
        s += " finish_all_rq=" + str(self.finish_all_rq)
        s += " rsp_times=" + str(self.measure_rsptimes)
        s += " tid="+self.tid
        s += " direct=" + str(self.direct)
        s += " loglevel="+str(self.log_level)
        s += " filenum=" + str(self.filenum)
        s += " filenum_final=" + str(self.filenum_final)
        s += " rq=" + str(self.rq)
        s += " rq_final=" + str(self.rq_final)
        s += " start=" + str(self.start_time)
        s += " end=" + str(self.end_time)
        s += " elapsed=" + str(self.elapsed_time)
        s += " host=" + str(self.onhost)
        s += " status=" + str(self.status)
        s += " abort=" + str(self.abort)
        s += " log_to_stderr=" + str(self.log_to_stderr)
        s += " verbose=" + str(self.verbose)
        s += ' invk_id=%d'%self.invocation_id
        return s

    # if you want to use the same instance for multiple tests
    # call reset() method between tests

    def reset(self):
        # results returned in variables below
        self.filenum = 0    # how many files have been accessed so far
        self.filenum_final = 0 # how many files accessed when test ended
        self.rq = 0         # how many reads/writes have been attempted so far
        self.rq_final = 0  # how many reads/writes completed when test ended
        #self.start_time = time.time()
        self.start_time = None
        self.end_time = None
        self.op_start_time = None;
        self.elapsed_time = 0
        self.onhost = short_hostname(None)
        self.abort = False
        self.status = self.NOTOK
        self.rsptimes = []
        self.rsptime_filename = None
        self.pause_sec = self.pause_between_files / self.MICROSEC_PER_SEC

    # given a set of top-level directories (e.g. for NFS benchmarking)
    # set up shop in them
    # we only use one directory for network synchronization 

    def set_top(self, top_dirs, network_dir=None):
        self.top_dirs = top_dirs                                    # directories that contain all files used in test
        self.src_dirs = [ os.path.join(d, "file_srcdir") for d in top_dirs ]   # where to create files in
        self.dest_dirs = [ os.path.join(d, "file_dstdir") for d in top_dirs ]   # where to rename files to
        self.network_dir = os.path.join(top_dirs[0], "network_shared") # directory for synchronization files shared across hosts
        if network_dir: self.network_dir = network_dir

    # create per-thread log file

    def start_log(self):
        self.log = logging.getLogger(self.tid)
        if self.log_to_stderr:
          h = logging.StreamHandler()
        else:
          logfilename_base = self.tmp_dir + os.sep + "invoke_logs"
          h = logging.FileHandler(logfilename_base + "-" + self.tid + ".log")
        formatter = logging.Formatter(self.tid + " %(asctime)s - %(levelname)s - %(message)s")
        h.setFormatter(formatter)
        self.log.addHandler(h)
        self.loglevel = logging.INFO
        if self.verbose: self.loglevel = logging.DEBUG
        self.log.setLevel(self.loglevel)

    # indicate start of an operation

    def op_starttime(self):
        if self.measure_rsptimes:
            self.op_start_time = time.time()

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
        fname = 'rsptimes_'+str(self.tid)+'_'+short_hostname(None)+'_'+self.opname+'_'+str(self.start_time)+'.csv'
        rsptime_fname = os.path.join(self.network_dir, fname)
        f = open(rsptime_fname, "w")
        for (opname, start_time, rsp_time) in self.rsptimes:
            # time granularity is microseconds, accuracy is probably less than that
            start_time_str = '%9.6f'%(start_time - self.start_time)
            rsp_time_str = '%9.6f'%rsp_time
            f.write( '%8s, %9.6f, %9.6f\n'%(opname, (start_time - self.start_time),rsp_time))
        f.close()

    # determine if test interval is over for this thread

    # each thread uses this to signal that it is at the starting gate
    # (i.e. it is ready to immediately begin generating workload)

    def gen_thread_ready_fname(self, tid, hostname=None):
        return self.tmp_dir + os.sep + "thread_ready." + short_hostname(hostname) + "_" + tid + ".tmp"

    # each host uses this to signal that it is at the starting gate
    # (i.e. it is ready to immediately begin generating workload)

    def gen_host_ready_fname(self, hostname=None):
        return self.network_dir + os.sep + "host_ready." + hostaddr(hostname) + ".tmp"

    def abort_fn(self):
        return self.network_dir + os.sep + 'abort.tmp'

    def stonewall_fn(self):
        return self.network_dir + os.sep + 'stonewall.tmp'

    # we use the seed function to control per-thread random sequence
    # we want seed to be saved so that operations subsequent to initial create will know
    # what file size is for thread T's file j without having to stat the file

    def init_random_seed(self):
      if self.filesize_distr == self.filesize_distr_fixed: return
      fn = self.gen_thread_ready_fname(self.tid, hostname=self.onhost) + '.seed'
      thread_seed = str(time.time())
      self.log.debug('seed opname: '+self.opname)
      if self.opname == 'create':
          thread_seed = str(time.time()) + ' ' + self.tid
          ensure_deleted(fn)
          with open(fn, "w") as seedfile:
            seedfile.write(str(thread_seed))
            self.log.debug('write seed %s '%thread_seed)
      elif self.opname == 'append' or self.opname == 'read':
          with open(fn, "r") as seedfile:
            thread_seed = seedfile.readlines()[0].strip()
            self.log.debug('read seed %s '%thread_seed)
      self.randstate.seed(thread_seed)

    def get_next_file_size(self):
      next_size = self.total_sz_kb
      if self.filesize_distr == self.filesize_distr_random_exponential:
        next_size = max(1, min(int(self.randstate.expovariate(8.0/self.total_sz_kb)), self.total_sz_kb))
        self.log.debug('rnd expn file size %d KB'%next_size)
      else:
        self.log.debug('fixed file size %d KB'%next_size)
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
            #print 'thread at gate, file ' + gateReady
            with open(gateReady, "w") as f: 
              f.close()
            while not os.path.exists(self.starting_gate):
                if os.path.exists(self.abort_fn()): raise Exception("thread " + str(self.tid) + " saw abort flag")
                # wait a little longer so that other clients have time to see that gate exists
                time.sleep(2.0)

    # record info needed to compute test statistics 

    def end_test(self):
        self.rq_final = self.rq
        self.filenum_final = self.filenum
        self.end_time = time.time()
        if self.filenum >= self.iterations:
         try:
            with open(self.stonewall_fn(), "w") as f: 
                self.log.info('stonewall file written by thread %s on host %s'%(self.tid, short_hostname(None)))
                f.close()
         except IOError as e:
            err = e.errno
            if err != errno.EEXIST: 
              # workaround for possible bug in Gluster
              if err != errno.EINVAL: raise e
              else: self.log.info('saw EINVAL on stonewall, ignoring it')

    def test_ended(self):
        return self.end_time > self.start_time
    
    # see if we should do one more file
    # to minimize overhead we only check starting gate after every 100 files
    
    def do_another_file(self):
        if self.stonewall and (self.filenum % self.files_between_checks == 0):
                if (not self.test_ended()) and (os.path.exists(self.stonewall_fn())):
                    self.log.info("stonewalled after " + str(self.filenum) + " iterations")
                    self.end_test()
        # if user doesn't want to finish all requests and test has ended, stop
        if (not self.finish_all_rq) and self.test_ended():
            return False
        if (self.filenum >= self.iterations):
            if not self.test_ended(): self.end_test()
            return False
        if self.abort: raise Exception("thread " + str(self.tid) + " saw abort flag")
        self.filenum += 1
        if self.pause_sec > 0.0: time.sleep(self.pause_sec)
        return True

    # in this method of directory selection, as filenum increments upwards, 
    # we place F = files_per_dir files into directory, then next F files into directory D+1, etc.

    def mk_seq_dir_name(self, file_num):
        dir_num = file_num / self.files_per_dir
        path = ''
        while dir_num > 1:
                dir_num_at_level = dir_num % self.dirs_per_dir
                path = ('d_%03d/'%dir_num_at_level) + path
                dir_num = dir_num / self.dirs_per_dir
        return path

    def mk_hashed_dir_name(self, file_num):
        path = ''
        dir_num = file_num / self.files_per_dir
        while dir_num > 1:
                # try using floating point fraction to generate a uniform random distribution on directories
                dir_num_hash = (dir_num * self.some_prime) % self.dirs_per_dir
                path = 'h_%03d/'%dir_num_hash + path
                #print file_num, dirs_in_tree, f, fract, next_dir_num, hashed_path
                #print file_num, dir_num_hash, path
                dir_num /= self.dirs_per_dir
        return path

    def mk_dir_name(self, file_num):
        if self.hash_to_dir: return self.mk_hashed_dir_name(file_num)
        else: return self.mk_seq_dir_name(file_num)

    # for multiple-mountpoint tests, we need to select top-level dir based on file number
    # to spread load across mountpoints, so we use round-robin mountpoint selection

    def select_tree(self, directory_list, filenum):
      listlen = len(directory_list)
      return directory_list[ filenum % listlen ]

    # generate file name to put in this directory
    # prefix can be used for process ID or host ID for example
    # names are unique to each thread
    # automatically computes subdirectory for file based on
    # files_per_dir, dirs_per_dir and placing file as high in tree as possible

    def mk_file_nm(self, base_dirs, filenum=-1):
        if filenum == -1: filenum = self.filenum

        dirpath = self.mk_dir_name(filenum)
        tree = self.select_tree(base_dirs, filenum)

        # implement directory tree fitting files as high in the tree as possible
        # for successive files use same directory when possible

        path = os.path.join(tree, dirpath)
        path += self.prefix + "_" + self.onhost + "_" + self.tid + "_" + str(filenum) + "_" + self.suffix
        #print 'next path: %s'%path
        return path

    # allocate buffer of correct size

    def prepare_buf(self):
        if self.record_sz_kb * 1024 > smf_invocation.biggest_buf_size:
          raise Exception('biggest supported record size is %d bytes'%smf_invocation.biggest_buf_size)
        if self.record_sz_kb == 0:
            rsz = self.total_sz_kb * 1024
        else:
            rsz = self.record_sz_kb * 1024
        if rsz > self.biggest_buf_size:
            raise Exception('record size too big for buffer')
        unique_offset = hash(self.tid)%128 + self.filenum  # FIXME: think harder about this
        assert unique_offset + rsz < len(self.biggest_buf) # so next array access is valid
        self.buf = self.biggest_buf[ unique_offset : rsz + unique_offset ]
        assert len(self.buf) == rsz
        
    # make all subdirectories needed for test in advance, don't include in measurement
    # use set to avoid duplicating operations on directories
    
    def make_all_subdirs(self):
        if (self.tid != '00') and self.is_shared_dir: return
        dirset=set([])
        for tree in [ self.src_dirs, self.dest_dirs ]:
          for j in range(0, self.iterations+1):
            fpath = self.mk_file_nm(tree, j)
            dpath = os.path.dirname(fpath)
            dirset.add(dpath)
        for dpath in dirset:
            if not exists(dpath): 
              try:
                os.makedirs(dpath, 0777)
              except OSError as e:
                if not ((e.errno == errno.EEXIST) and self.is_shared_dir):
                  raise e

    # clean up all subdirectories

    def clean_all_subdirs(self):
        if (self.tid != '00') and self.is_shared_dir: return
        for tree in [ self.src_dirs, self.dest_dirs ]:
         for t in tree:
          subdirs = (self.iterations/self.files_per_dir) + 1
          for j in range(0, subdirs):
            fpath = self.mk_file_nm(t, filenum=j*self.files_per_dir)
            dpath = os.path.dirname(fpath)
            while len(dpath) > len(t) + 1:
                if not exists(dpath):
                        dpath = os.path.dirname(dpath)
                elif os.listdir(dpath) == []:
                        try:
                          os.rmdir(dpath)
                        except OSError as e:
                          self.log.error('deleting directory dpath: %s'%e)
                          if (e.errno != errno.ENOENT) and not self.is_shared_dir: raise e
                        dpath = os.path.dirname(dpath)
                else:
                        break

    # operation-specific test code goes in do_<opname>()
        
    def do_create(self):
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            self.op_starttime()
            fd = -1
            try: 
              fd = os.open( fn, os.O_CREAT|os.O_EXCL|os.O_WRONLY|self.direct )
              if (fd < 0):
                raise MFRdWrExc(self.opname, self.filenum, 0, 0)
              next_fsz = self.get_next_file_size()
              rszkb = self.record_sz_kb
              if rszkb == 0: rszkb = next_fsz
              self.prepare_buf()
              remaining_kb = next_fsz
              while remaining_kb > 0:
                if remaining_kb < (len(self.buf)/self.BYTES_PER_KB): 
                  rszbytes = remaining_kb * self.BYTES_PER_KB
                  written = os.write(fd, self.buf[0:rszbytes])
                else:
                  rszbytes = rszkb * self.BYTES_PER_KB
                  written = os.write(fd, self.buf)
                self.log.debug('create fn %s next_fsz %u remain %u rszbytes %u written %u'%(fn, next_fsz, remaining_kb, rszbytes, written))
                if written != rszbytes:
                    raise MFRdWrExc(self.opname, self.filenum, self.rq, written)
                self.rq += 1
                remaining_kb -= (rszbytes/self.BYTES_PER_KB)
            finally:
              if fd >= 0: os.close(fd)
            self.op_endtime(self.opname)

    def do_mkdir(self):
        while self.do_another_file():
            dir = self.mk_file_nm(self.src_dirs) + '.d'
            self.op_starttime()
            os.mkdir(dir)
            f = dir + os.sep + 'not-empty-directory'
            #os.close(os.opden(f, os.O_CREAT|os.O_EXCL|os.O_WRONLY))
            self.op_endtime(self.opname)

    def do_rmdir(self):
        while self.do_another_file():
            dir = self.mk_file_nm(self.src_dirs) + '.d'
            f = dir + os.sep + 'not-empty-directory'
            self.op_starttime()
            #os.unlink(f)
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
            statinfo = os.stat(fn)
            self.op_endtime(self.opname)

    def do_chmod(self):
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            self.op_starttime()
            os.chmod(fn, 0646)
            self.op_endtime(self.opname)

    # we use "prefix" parameter to provide a list of characters 
    # to use as extended attribute name suffixes
    # so that we can do multiple xattr operations per node

    def do_getxattr(self):
        if xattr_not_installed:
            raise Exception('xattr module not present, getxattr and setxattr operations will not work')
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            self.op_starttime()
            self.prepare_buf()
            xa = xattr.xattr(fn)
            for j in range(0, self.xattr_count):
              v = xa.get('user.smallfile-%d'%j)
              if self.buf[j:self.xattr_size+j] != v:
                raise MFRdWrExc('getxattr: value contents wrong', self.filenum, j, len(v))
            self.op_endtime(self.opname)

    def do_setxattr(self):
        if xattr_not_installed:
            raise Exception('xattr module not present, getxattr and setxattr operations will not work')
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            self.op_starttime()
            self.prepare_buf()
            xa = xattr.xattr(fn)
            for j in range(0, self.xattr_count):
              xa.set('user.smallfile-%d'%j, self.buf[j:self.xattr_size+j])
            self.op_endtime(self.opname)

    def do_append(self):
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            self.op_starttime()
            fd = -1
            try:
              next_fsz = self.get_next_file_size()
              fd = os.open(fn, os.O_WRONLY|self.direct)
              os.lseek(fd, 0, os.SEEK_END )
              rszkb = self.record_sz_kb
              if rszkb == 0: rszkb = next_fsz
              self.prepare_buf()
              remaining_kb = next_fsz
              while remaining_kb > 0:
                if remaining_kb < (len(self.buf)/self.BYTES_PER_KB): 
                  rszbytes = remaining_kb * self.BYTES_PER_KB
                  written = os.write(fd, self.buf[0:rszbytes])
                else:
                  rszbytes = len(self.buf)
                  written = os.write(fd, self.buf)
                self.rq += 1
                if written != rszbytes:
                    raise MFRdWrExc(self.opname, self.filenum, self.rq, written)
                remaining_kb -= (rszbytes/self.BYTES_PER_KB)
            finally:
              if fd >= 0: os.close(fd)
            self.op_endtime(self.opname)
                
    def do_read(self):
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            self.op_starttime()
            fd = -1
            try:
              next_fsz = self.get_next_file_size()
              fd = os.open(fn, os.O_RDONLY|self.direct)
              rszkb = self.record_sz_kb
              if rszkb == 0: rszkb = next_fsz
              self.prepare_buf()
              remaining_kb = next_fsz
              while remaining_kb > 0:
                next_kb = min(rszkb, remaining_kb)
                rszbytes = next_kb * self.BYTES_PER_KB
                bytesread = os.read(fd, rszbytes)
                self.rq += 1
                if len(bytesread) != rszbytes:
                    raise MFRdWrExc(self.opname, self.filenum, self.rq, len(bytesread))
                if self.verify_read:
                  self.log.debug('read fn %s next_fsz %u remain %u rszbytes %u bytesread %u'%(fn, next_fsz, remaining_kb, rszbytes, len(bytesread)))
                  if self.buf[0:rszbytes] != bytesread:
                    raise MFRdWrExc('read: buffer contents wrong', self.filenum, self.rq, len(bytesread))
                remaining_kb -= rszkb
            finally:
              os.close(fd)
            self.op_endtime(self.opname)

    def do_rename(self):
        in_same_dir = (self.dest_dirs == self.src_dirs)
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
            
    def do_delete_renamed(self):
        in_same_dir = (self.dest_dirs == self.src_dirs)
        while self.do_another_file():
            fn = self.mk_file_nm(self.dest_dirs)
            if in_same_dir:
                fn = fn + self.rename_suffix
            self.op_starttime()
            os.unlink(fn)
            self.op_endtime(self.opname)

    # for mixed workloads, do every single thing you can in a single operation
    def do_all(self):
        in_same_dir = (self.dest_dirs == self.src_dirs)
        filename_list = []
        while self.do_another_file():
            fn = self.mk_file_nm(self.src_dirs)
            filename_list.append(fn)
            self.op_starttime()
            fd = os.open(fn, os.O_WRONLY|os.O_CREAT|self.direct)
            rszkb = self.record_sz_kb
            if rszkb == 0: rszkb = self.total_sz_kb
            remaining_kb = self.total_sz_kb
            while remaining_kb > 0:
                written = os.write(fd, self.buf)
                self.rq += 1
                if written != (rszkb * self.BYTES_PER_KB):
                    raise MFRdWrExc(self.opname, self.filenum, self.rq, written)
                remaining_kb -= rszkb
            os.close(fd)
            self.op_endtime('create')

            self.op_starttime()
            os.rename(fn, fn + self.rename_suffix)
            self.op_endtime('rename')

            fn = fn + self.rename_suffix
            self.op_starttime()
            fd = os.open(fn, os.O_RDONLY|self.direct)
            remaining_kb = self.total_sz_kb
            while remaining_kb > 0:
                self.rq += 1
                bytesread = os.read(fd, rszkb * self.BYTES_PER_KB)
                if len(bytesread) != (rszkb * self.BYTES_PER_KB):
                    raise MFRdWrExc(self.opname, self.filenum, self.rq, len(bytesread))
                remaining_kb -= rszkb
            os.close(fd)
            self.op_endtime('read')

            self.op_starttime()
            os.unlink(fn)
            self.op_endtime('delete')

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
            fn = self.mk_file_nm(self.dest_dirs)
            ensure_deleted(fn)
            fn = basenm + self.rename_suffix
            ensure_deleted(fn)
            dir = basenm + '.d'
            if os.path.exists(dir):
              fn = dir + os.sep + 'not-empty-directory'
              ensure_deleted(fn)
              os.rmdir(dir)
        self.clean_all_subdirs()
        self.stonewall = save_stonewall
        self.finish_all_rq = save_finish
        self.status = ok

    def do_workload(self):
        self.reset()
        self.start_log()
        self.log.info('do_workload: ' + str(self))
        ensure_dir_exists(self.network_dir)
        self.make_all_subdirs()
        self.prepare_buf()
        self.init_random_seed()
        if self.total_sz_kb > 0:
            self.files_between_checks = max(10, self.max_files_between_checks - (self.total_sz_kb/100))
        try:
            self.end_time = 0.0
            self.start_time = time.time()
            self.wait_for_gate()
            o = self.opname
            if o == "create":
                self.do_create()
            elif o == "delete":
                self.do_delete()
            elif o == "symlink":
                self.do_symlink()
            elif o == "mkdir":
                self.do_mkdir()
            elif o == "rmdir":
                self.do_rmdir()
            elif o == "stat":
                self.do_stat()
            elif o == "getxattr":
                self.do_getxattr()
            elif o == "setxattr":
                self.do_setxattr()
            elif o == "chmod":
                self.do_chmod()
            elif o == "append":
                self.do_append()
            elif o == "read":
                self.do_read()
            elif o == "rename":
                self.do_rename()
            elif o == "delete-renamed":
                self.do_delete_renamed()
            elif o == "cleanup":
                self.do_cleanup()
            elif o == "all":
                self.do_all()
            else:
                raise MFNotImplYetExc()
            self.status = ok
        except KeyboardInterrupt, e:
            self.log.error( "control-C or equivalent signal received, ending test" )
            self.status = ok
        except OSError, e:
            self.status = e.errno
            self.log.exception(e)
        if self.measure_rsptimes: self.save_rsptimes()
        if self.status != ok: self.log.error("invocation did not complete cleanly")
        if self.filenum != self.iterations: self.log.info("stopped after " + str(self.filenum) + " files")
        if self.rq_final < 0: self.end_test()
        self.elapsed_time = self.end_time - self.start_time
        logging.shutdown()
        return self.status

# threads used to do multi-threaded unit testing

class TestThread(threading.Thread):
    def __init__(self, my_invocation, my_name):
        threading.Thread.__init__(self, name=my_name)
        self.invocation = my_invocation

    def __str__(self):
        return "TestThread " + str(self.invocation) + " " + threading.Thread.__str__(self)

    def run(self):
        try:
            self.invocation.do_workload()
        except Exception,e:
            self.invocation.log.error( str(e) )

# below are unit tests for smf_invocation
# including multi-threaded test
# this should be designed to run without any user intervention
# to run just one of these tests do python -m unittest smallfile.Test.your-unit-test

ok=0
class Test(unittest.TestCase):
    def setUp(self):
        self.invok = smf_invocation()
        self.invok.opname = "create"
        self.invok.iterations = 10
        self.invok.verbose = True
        self.invok.prefix = "p"
        self.invok.suffix = "s"
        self.invok.tid = "regtest"
        self.invok.start_log()
        self.invok.log.debug('Test.setup')
        self.deltree(self.invok.network_dir)
        ensure_dir_exists(self.invok.network_dir)

    def deltree(self, topdir):
        if not os.path.exists(topdir): return
        if not os.path.isdir(topdir): return
        for (dir, subdirs, files) in os.walk(topdir, topdown=False):
            for f in files: os.unlink(os.path.join(dir,f))
            for d in subdirs: os.rmdir(os.path.join(dir,d))
        os.rmdir(topdir)
        
    def chk_status(self):
        assert self.invok.status == ok

    def runTest(self, opName):
        self.invok.opname = opName
        self.invok.do_workload()
        self.chk_status()

    def checkDirEmpty(self, emptyDir):
        self.assertTrue(os.listdir(emptyDir) == [])

    def checkDirListEmpty(self, emptyDirList):
        for d in emptyDirList: self.assertTrue(os.listdir(d) == [])

    def cleanup_files(self):
        self.runTest("cleanup")
 
    def mk_files(self):
        self.cleanup_files()
        self.runTest("create")
        self.assertTrue(exists(self.invok.mk_file_nm(self.invok.src_dirs)))
        assert (os.path.getsize(self.invok.mk_file_nm(self.invok.src_dirs)) == self.invok.total_sz_kb * 1024)

    def test1_recreate_src_dest_dirs(self):
        for s in self.invok.src_dirs:
          self.deltree(s)
          os.mkdir(s)
        for s in self.invok.dest_dirs:
          self.deltree(s)
          os.mkdir(s)
     
    def test_a_MkFn(self):
        fn = self.invok.mk_file_nm(self.invok.src_dirs)
        expectedFn = self.invok.src_dirs[0] + os.sep + self.invok.prefix + "_" + short_hostname(None) + '_' + self.invok.tid + "_" + str(self.invok.filenum) + "_" + self.invok.suffix
        self.assertTrue( fn == expectedFn )
        f = open(fn, "w+", 0666)
        f.close()
        assert(os.path.getsize(fn) == 0)
        os.unlink(fn)
    
    def test_b_Cleanup(self):
        self.cleanup_files()
        
    def test_c_Create(self):
        self.mk_files()  # depends on cleanup_files

    def test_c1_Mkdir(self):
        self.cleanup_files()
        self.runTest("mkdir")
        self.assertTrue(exists(self.invok.mk_file_nm(self.invok.src_dirs)+'.d'))

    def test_c2_Rmdir(self):
        self.cleanup_files()
        self.runTest("mkdir")
        self.runTest("rmdir")
        self.assertTrue(not exists(self.invok.mk_file_nm(self.invok.src_dirs)+'.d'))

    def test_c3_Symlink(self):
        if is_windows_os: return
        self.cleanup_files()
        self.mk_files()
        self.runTest("symlink")
        self.assertTrue(exists(self.invok.mk_file_nm(self.invok.dest_dirs)+'.s'))

    def test_c4_Stat(self):
        self.cleanup_files()
        self.mk_files()
        self.runTest("stat")

    def test_c5_Chmod(self):
        self.cleanup_files()
        self.mk_files()
        self.runTest("chmod")

    def test_c6_xattr(self):
        if not xattr_not_installed:
          self.cleanup_files()
          self.mk_files()
          self.runTest("setxattr")
          self.runTest("getxattr")

    def test_d_Delete(self):
        self.invok.measure_rsptimes = True
        self.mk_files()
        self.runTest("delete")
        self.checkDirListEmpty(self.invok.src_dirs)
        
    def test_e_Rename(self):
        self.invok.measure_rsptimes = False
        self.mk_files()
        self.runTest("rename")
        fn = self.invok.mk_file_nm(self.invok.dest_dirs)
        self.assertTrue(exists(fn))
        self.checkDirListEmpty(self.invok.src_dirs)

    def test_f_DeleteRenamed(self):
        self.mk_files()
        self.runTest("rename")
        self.runTest("delete-renamed")
        self.checkDirListEmpty(self.invok.dest_dirs)

    def test_g_Append(self):
        self.mk_files()
        orig_kb = self.invok.total_sz_kb
        self.invok.total_sz_kb *= 2
        self.runTest("append")
        fn = self.invok.mk_file_nm(self.invok.src_dirs)
        st = os.stat(fn)
        self.assertTrue(st.st_size == (3 * orig_kb * self.invok.BYTES_PER_KB))
        
    def test_h_read(self):
        self.mk_files()
        self.invok.verify_read = True
        self.runTest("read")

    def test_h2_read_bad_data(self):
        self.mk_files()
        self.invok.verify_read = True
        fn = self.invok.mk_file_nm(self.invok.src_dirs)
        fd = os.open(fn, os.O_WRONLY)
        os.lseek(fd, 5, os.SEEK_SET)
        os.write(fd, '!')
        os.close(fd)
        try:
          self.runTest("read")
        except MFRdWrExc as e:
          pass
        self.assertTrue(self.invok.status != ok)

    def test_z1_create(self):
        self.cleanup_files()
        self.invok.filesize_distr = self.invok.filesize_distr_random_exponential
        self.invok.invocations = 4
        self.invok.record_sz_kb = 0
        self.invok.total_sz_kb = 16
        self.runTest("create")

    def test_z2_append(self):
        self.invok.filesize_distr = self.invok.filesize_distr_random_exponential
        self.invok.invocations = 4
        self.invok.record_sz_kb = 0
        self.invok.total_sz_kb = 16
        self.runTest("append")

    def test_z3_read(self):
        self.invok.filesize_distr = self.invok.filesize_distr_random_exponential
        self.invok.invocations = 4
        self.invok.record_sz_kb = 0
        self.invok.total_sz_kb = 16
        self.runTest("read")

    def test_i_doall(self):
        self.cleanup_files()
        self.runTest("all")
        self.checkDirListEmpty(self.invok.src_dirs)
        self.checkDirListEmpty(self.invok.dest_dirs)
        self.cleanup_files()

    def test_j0_dir_name(self):
        self.invok.files_per_dir = 20
        self.invok.dirs_per_dir = 3
        d = self.invok.mk_dir_name(29*self.invok.files_per_dir)
        self.assertTrue(d == 'd_000%sd_000%sd_002%s'%(os.sep, os.sep, os.sep))
        self.invok.dirs_per_dir = 7
        d = self.invok.mk_dir_name(320*self.invok.files_per_dir)
        self.assertTrue(d == 'd_006%sd_003%sd_005%s'%(os.sep, os.sep, os.sep))

    def test_j1_deep_tree(self):
        self.invok.total_sz_kb = 0
        self.invok.record_sz_kb = 0
        self.invok.files_per_dir = 10
        self.invok.dirs_per_dir = 3
        self.invok.iterations = 200
        self.invok.prefix = ''
        self.invok.suffix = 'deep'
        self.mk_files()
        self.assertTrue(exists(self.invok.mk_file_nm(self.invok.src_dirs,self.invok.iterations-1)))
        self.cleanup_files()
 
    def test_j2_deep_hashed_tree(self):
        self.invok.suffix = 'deep_hashed'
        self.invok.total_sz_kb = 0
        self.invok.record_sz_kb = 0
        self.invok.files_per_dir = 5 
        self.invok.dirs_per_dir = 4
        self.invok.iterations = 500 
        self.hash_to_dir = True
        self.mk_files()
        self.assertTrue(exists(self.invok.mk_file_nm(self.invok.src_dirs,self.invok.iterations-1)))
        self.cleanup_files()

    def test_multithr_stonewall(self):
        self.invok.log.info('starting stonewall test')
        self.invok.stonewall = True
        self.invok.finish = True
        self.invok.prefix = "thr_"
        self.invok.suffix = "foo"
        self.invok.iterations=10
        sgate_file = os.path.join(self.invok.network_dir, "starting_gate.tmp")
        self.invok.starting_gate = sgate_file
        thread_ready_timeout = 4
        thread_count = 4
        self.test1_recreate_src_dest_dirs()
        self.checkDirListEmpty(self.invok.src_dirs)
        self.checkDirListEmpty(self.invok.dest_dirs)
        self.checkDirEmpty(self.invok.network_dir)
        invokeList = []
        for j in range(0, thread_count):
            s = smf_invocation.clone(self.invok)  # test copy constructor
            s.tid = str(j)
            invokeList.append(s)
        threadList=[]
        for s in invokeList: 
            threadList.append(TestThread(s, s.prefix + s.tid))
        for t in threadList: 
            t.start()
        threads_ready = True
        for i in range(0, thread_ready_timeout):
            threads_ready = True
            for s in invokeList:
                thread_ready_file = s.gen_thread_ready_fname(s.tid)
                #print 'waiting for ' + thread_ready_file
                if not os.path.exists(thread_ready_file): 
                  threads_ready = False
                  break
            if threads_ready: 
              break
            time.sleep(1)
        if not threads_ready: raise Exception("threads did not show up within %d seconds"%thread_ready_timeout)
        time.sleep(1)
        f = open(sgate_file, "w")
        f.close()
        for t in threadList: 
            t.join()
            if t.isAlive(): raise Exception("thread join timeout:" + str(t))
            if t.invocation.status != ok:
                raise Exception("thread did not complete iterations: " + str(t))

# so you can just do "python smallfile.py" to test it

if __name__ == "__main__":
    unittest.main()
