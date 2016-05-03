smallfile
=========

A distributed workload generator for POSIX-like filesystems.

Copyright [2012] [Ben England]

Licensed under the Apache License, Version 2.0 (the "License");
you may not use files except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Introduction
=========

smallfile is a python-based distributed POSIX workload generator 
which can be used to quickly measure performance for a
variety of metadata-intensive workloads across an entire
cluster.  It has no dependencies on any specific filesystem or implementation 
It was written to complement use of iozone benchmark for measuring performance 
of large-file workloads, and borrows concepts from iozone.
and Ric Wheeler's fs_mark.  It was developed by Ben England starting in March 2009.

What it can do
----------

* multi-host - manages workload generators on multiple hosts
* aggregates throughput - for entire set of hosts
* synchronizes workload generation - can start and stop workload generator threads at approximately same time
* pure workloads - only one kind of operation in each run (as opposed to mixed workloads)
* extensible - easy to extend to new workload types
* scriptable - provides CLI for scripted use, but workload generator is separate so a GUI is possible
* file size distributions - supports either fixed file size or random exponential file size
* traces response times - can capture response time data in .csv format, provides utility to reduce this data to statistics
* Windows support - different launching method, see below
* verification of read data -- writes unique data pattern in all files, can verify data read against this pattern
* incompressibility - can write random data pattern that is incompressible
* async replication support - can measure time required for files to appear in a directory tree
* fs coherency test - in multi-host tests, can force all clients to read files written by different client

both python 2.7 and python 3 are supported.   Limited support is available for
pypy.

Restrictions
--------

* for a multi-host test, all workload generators and the test driver must provide access to the same shared directory
* does not support mixed workloads (mixture of different operation types)
* is not accurate on memory resident filesystem 
* requires all hosts to have the same DNS domain name (plan to remove this
  restriction)
* does not support HTTP access (use COSBench/ssbench for this)
* does not support mixture of Windows and non-Windows clients
* For POSIX-like operating systems, we have only tested with Linux, but there
  is a high probability that it would work with Apple OS and other UNIXes.
* Have only tested Windows XP and Windows 7, but any Win32-compatible Windows would probably work with this.

How to run
-----

You must have password-less ssh access between the test driver node and the
workload generator hosts if you want to run a distributed (multi-host) test.

You must use a directory visible to all participating hosts to run a
distributed test.

To see what parameters are supported by smallfile_cli.py, do 

 python smallfile_cli.py -h

Boolean true/false parameters can be set to either Y
(true) or N (false). Every command consists of a sequence of parameter
name-value pairs with the format --name value .

The parameters are:

* --operation -- operation name, one of the following: 

** create -- create a file and write data to it

** append -- open an existing file and append data to it 
** delete -- delete a file 
** rename -- rename a file 
** delete_renamed -- delete a file that had previously been renamed
** read -- read an existing file 
** stat -- just read metadata from an existing file 
** chmod -- change protection mask for file
** setxattr -- set extended attribute values in each file 
** getxattr - read extended attribute values in each file 
** symlink -- create a symlink pointing to each file (create must be run
beforehand) 
** mkdir -- create a subdirectory with 1 file in it 
** rmdir -- remove a subdirectory and its 1 file
** readdir – scan directories only, don't read files or their metadata
** ls-l – scan directories and read basic file metadata
** cleanup -- delete any pre-existing files from a previous run 
** swift-put – simulates OpenStack Swift behavior when doing PUT operation
** swift-get -- simulates OpenStack Swift behavior for each GET operation. 
* --top -- top-level directory, all file accesses are done inside this
  directory tree. If you wish to use multiple mountpoints,provide a list of
  top-level directories separated by comma (no whitespace).
* --host-set -- comma-separated set of hosts used for this test, no domain
  names allowed. Default: non-distributed test.
* --files -- how many files should each thread process? 
* --threads -- how many workload generator threads should each invocation_cli
  process create? 
* --file-size -- total amount of data accessed per file.   If zero then no
  reads or writes are performed. 
* --file-size-distribution – only supported value today is exponential.
  Default: fixed file size.
* --record-size -- record size in KB, how much data is transferred in a single
  read or write system call.  If 0 then it is set to the minimum of the file
  size and 1-MB record size limit. Default: 0
* --files-per-dir -- maximum number of files contained in any one directory.
  Default: 200
* --dirs-per-dir -- maximum number of subdirectories contained in any one
  directory. Default: 20
* --hash-into-dirs – if Y then assign next file to a directory using a hash
  function, otherwise assign next –files-per-dir files to next directory.
  Default: N
* --permute-host-dirs – if Y then have each host process a different
  subdirectory tree than it otherwise would (see below for directory tree
  structure). Default: N
* --same-dir -- if Y then threads will share a single directory. Default: N
* --network-sync-dir – don't need to specify unless you run a multi-host test
  and the –top parameter points to a non-shared directory (see discussion
  below). Default: network_shared subdirectory under –top dir.
* --xattr-size -- size of extended attribute value in bytes (names begin with
  'user.smallfile-') 
* --xattr-count -- number of extended attributes per file
* --prefix -- a string prefix to prepend to files (so they don't collide with
previous runs for example)
* --suffix -- a string suffix to append to files (so they don't collide with
  previous runs for example)
* --incompressible – (default N) if Y then generate a pure-random file that
  will not be compressible (useful for tests where intermediate network or file
  copy utility attempts to compress data
* --record-ctime-size -- default N, if Y then label each created file with an
  xattr containing a time of creation and a file size. This will be used by
  –await-create operation to compute performance of asynchonous file
  replication/copy.
* --finish -- if Y, thread will complete all requested file operations even if
  measurement has finished. Default: Y
* --stonewall -- if Y then thread will measure throughput as soon as it detects
  that another thread has finished. Default: N
* --verify-read – if Y then smallfile will verify read data is correct.
  Default: Y
* --response-times – if Y then save response time for each file operation in a
  rsptimes\*csv file in the shared network directory. Record format is
  operation-type, start-time, response-time. The operation type is included so
  that you can run different workloads at the same time and easily merge the
  data from these runs. The start-time field is the time that the file
  operation started, down to microsecond resolution. The response time field is
  the file operation duration down to microsecond resolution.
* --remote-pgm-dir – don't need to specify this unless the smallfile software
  lives in a different directory on the target hosts and the test-driver host. 
* --pause -- integer (microseconds) each thread will wait before starting next
  file. Default: 0

For example, if you want to run smallfile_cli.py on 1 host with 8 threads
each creating 2 GB of 1-MB files, you can use these options:

 # python smallfile_cli.py --operation create --threads 8 \
   --file-size 1024 --files 2048 --top /mnt/gfs/smf

To run a 4-host test doing same thing:

 # python smallfile_cli.py --operation create --threads 8 \
   --file-size 1024 --files 2048 --top /mnt/gfs/smf \
   --host-set host1,host2,host3,host4 

Errors encountered by worker threads will be saved in /var/tmp/invoke-N.log where N is the thread number. After each test, a summary of thread results is displayed, and overall test results are aggregated for you, in three ways:

* files/sec – most relevant for smaller file sizes
* IOPS -- application I/O operations per sec, rate of read()/write()
* MB/s -- megabytes/sec, data transfer rate

Users should never need to run smallfile.py -- this is the python class which
implements the workload generator. Developers can run this module to invoke its
unit test however:

 # python smallfile.py 

To run just one unit test module, for example:

 # python -m unittest smallfile.Test.test_c3_Symlink


