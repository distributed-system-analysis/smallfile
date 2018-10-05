smallfile
=========

A distributed workload generator for POSIX-like filesystems.

New features:
* JSON output format
* response time post-processing

# Table of contents

[License](#license)

[Introduction](#introduction)

[__What it can do](#what-it-can-do)

[__Restrictions](#restrictions)

[How to specify test](#how-to-specify-test)

[Results](#results)

[__Postprocessing of response time data](#postprocessing-of-response-time-data)

[How to run correctly](#how-to-run-correctly)

[__Avoiding caching effects](#avoiding-caching-effects)

[__Use of pause option](#use-of-pause-option)

[Use with distributed filesystems](#use-with-distributed-filesystems)

[__The dreaded startup timeout error](#the-dreaded-startup-timeout-error)

[Use with local filesystems](#use-with-local-filesystems)

[Use of subdirectories](#use-of-subdirectories)

[Sharing directories across threads](#sharing-directories-across-threads)

[Hashing files into directory tree](#hashing-files-into-directory-tree)

[Random file size distribution option](#random-file-size-distribution-option)

[Asynchronous file copy performance](#asynchronous-file-copy-performance)

[Comparable Benchmarks](#comparable-benchmarks)

[Design principles](#design-principles)

[Synchronization](#synchronization)

[__Test parameter transmission](#test-parameter-transmission)

[__Launching remote worker threads](#launching-remote-worker-threads)

[__Returning results](#returning-results)


License
=========
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
It was written to complement use of fio and iozone benchmark for measuring performance 
of large-file workloads, and borrows some concepts from iozone.
and Ric Wheeler's fs_mark.  It was developed by Ben England starting in March 2009.

What it can do
--------

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

Both python 2.7 and python 3 are supported.   Limited support is available for
pypy, this can be useful for reducing interpreter overhead.

Restrictions
-----------

* for a multi-host test, all workload generators and the test driver must provide access to the same shared directory
* does not support mixed workloads (mixture of different operation types)
* is not accurate on single-threaded tests in memory resident filesystem
* requires all hosts to have the same DNS domain name (plan to remove this
  restriction)
* does not support HTTP access (use COSBench/ssbench for this)
* does not support mixture of Windows and non-Windows clients
* For POSIX-like operating systems, we have only tested with Linux, but there
  is a high probability that it would work with Apple OS and other UNIXes.
* Have only tested Windows XP and Windows 7, but any Win32-compatible Windows would probably work with this.

How to specify test
============

You must have password-less ssh access between the test driver node and the
workload generator hosts if you want to run a distributed (multi-host) test.

You must use a directory visible to all participating hosts to run a
distributed test.

To see what parameters are supported by smallfile_cli.py, do 

    # python smallfile_cli.py --help

Boolean true/false parameters can be set to either Y
(true) or N (false). Every command consists of a sequence of parameter
name-value pairs with the format --name value .  To see what default values are,
use --help option.

The parameters are:

 * --operation -- operation type (see list below for choices)
 * --top -- top-level directory, all file accesses are done inside this
  directory tree. If you wish to use multiple mountpoints,provide a list of
  top-level directories separated by comma (no whitespace).
 * --host-set -- comma-separated set of hosts used for this test, no domain
  names allowed. Default: non-distributed test.
 * --files -- how many files should each thread process? 
 * --threads -- how many workload generator threads should each smallfile_cli.py process create? 
 * --file-size -- total amount of data accessed per file.   If zero then no
  reads or writes are performed. 
 * --file-size-distribution – only supported value today is exponential.
 * --record-size -- record size in KB, how much data is transferred in a single
  read or write system call.  If 0 then it is set to the minimum of the file
  size and 1-MiB record size limit.
 * --files-per-dir -- maximum number of files contained in any one directory.
 * --dirs-per-dir -- maximum number of subdirectories contained in any one
  directory.
 * --hash-into-dirs – if Y then assign next file to a directory using a hash
  function, otherwise assign next –files-per-dir files to next directory.
 * --permute-host-dirs – if Y then have each host process a different
  subdirectory tree than it otherwise would (see below for directory tree
  structure).
 * --same-dir -- if Y then threads will share a single directory.
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
 * --incompressible – if Y then generate a pure-random file that
  will not be compressible (useful for tests where intermediate network or file
  copy utility attempts to compress data
 * --record-ctime-size -- if Y then label each created file with an
  xattr containing a time of creation and a file size. This will be used by
  –await-create operation to compute performance of asynchonous file
  replication/copy.
 * --finish -- if Y, thread will complete all requested file operations even if
  measurement has finished.
 * --stonewall -- if Y then thread will measure throughput as soon as it detects
  that another thread has finished.
 * --verify-read – if Y then smallfile will verify read data is correct.
 * --response-times – if Y then save response time for each file operation in a
  rsptimes\*csv file in the shared network directory. Record format is
  operation-type, start-time, response-time. The operation type is included so
  that you can run different workloads at the same time and easily merge the
  data from these runs. The start-time field is the time that the file
  operation started, down to microsecond resolution. The response time field is
  the file operation duration down to microsecond resolution.
 * --output-json - if specified then write results in JSON format to the specified pathname for easier postprocessing.
 * --remote-pgm-dir – don't need to specify this unless the smallfile software
  lives in a different directory on the target hosts and the test-driver host. 
 * --pause -- integer (microseconds) each thread will wait before starting next
  file.

Operation types are:

* create -- create a file and write data to it
* append -- open an existing file and append data to it 
* delete -- delete a file 
* rename -- rename a file 
* delete_renamed -- delete a file that had previously been renamed
* read -- read an existing file 
* stat -- just read metadata from an existing file 
* chmod -- change protection mask for file
* setxattr -- set extended attribute values in each file 
* getxattr -- read extended attribute values in each file 
* symlink -- create a symlink pointing to each file (create must be run
beforehand) 
* mkdir -- create a subdirectory with 1 file in it 
* rmdir -- remove a subdirectory and its 1 file
* readdir -- scan directories only, don't read files or their metadata
* ls-l -- scan directories and read basic file metadata
* cleanup -- delete any pre-existing files from a previous run 
* swift-put -- simulates OpenStack Swift behavior when doing PUT operation
* swift-get -- simulates OpenStack Swift behavior for each GET operation. 

For example, if you want to run smallfile_cli.py on 1 host with 8 threads
each creating 2 GB of 1-MiB files, you can use these options:

    # python smallfile_cli.py --operation create --threads 8 \  
       --file-size 1024 --files 2048 --top /mnt/gfs/smf

To run a 4-host test doing same thing:

    # python smallfile_cli.py --operation create --threads 8 \  
       --file-size 1024 --files 2048 --top /mnt/gfs/smf \  
       --host-set host1,host2,host3,host4 

Note: You can only perform a read operation on files that were generated with smallfile (using same parameters).

Errors encountered by worker threads will be saved in /var/tmp/invoke-N.log where N is the thread number. After each test, a summary of thread results is displayed, and overall test results are aggregated for you, in three ways:

 * files/sec – most relevant for smaller file sizes
 * IOPS -- application I/O operations per sec, rate of read()/write()
 * MB/s -- megabytes/sec (really MiB/sec), data transfer rate

Users should never need to run smallfile.py -- this is the python class which
implements the workload generator. Developers can run this module to invoke its
unit test however:

    # python smallfile.py 

To run just one unit test module, for example:

    # python -m unittest smallfile.Test.test_c3_Symlink

Results
=======

All tests display a "files/sec" result.  If the test performs reads or writes,
then a "MB/sec" data transfer rate and an "IOPS" result (i.e. total read or
write calls/sec) are also displayed.  Each thread participating in the test
keeps track of total number of files and I/O requests that it processes during
the test measurement interval.  These results are rolled up per host if it is a
single-host test.  For a multi-host test, the per-thread results for each host
are saved in a file within the --top directory, and the test master then reads
in all of the saved results from its slaves to compute the aggregate result
across all client hosts.  The percentage of requested files which were
processed in the measurement interval is also displayed, and if the number is
lower than a threshold (default 70%) then an error is raised.

Postprocessing of response time data
--------

If you specify **--response-times Y** in the command, smallfile will save response time of each operation in per-thread output files in the shared directory as rsptimes*.csv.   For example, you can turn these into an X-Y scatterplot so that you can see how response time varies over time.   For example:

    # python smallfile_cli.py --response-times Y
    # ls -ltr /var/tmp/smf/network_shared/rsptimes*.csv

You should see 1 .csv file per thread.  These files can be loaded into any
spreadsheet application and graphed.  An x-y scatterplot can be useful to see
changes over time in response time.

But if you just want statistics, you can generate these using the postprocessing command:

    # python smallfile_rsptimes_stats.py /var/tmp/smf/network_shared

This will generate statistics summary in ../rsptimes-summary.csv , in this example you would find it in /var/tmp/smf/.  The file is in a form suitable for loading into a spreadsheet and graphing.  A simple example is generated using the regression test **gen-fake-rsptimes.sh** .  The result of this test is output like this:

```
filtering out suffix .foo.com from hostnames
rsp. time result summary at: /tmp/12573.tmp/../rsptime-summary.csv
```
The first line illustrates that you can remove a common hostname suffix in the output so that it is easier to read and graph.  In this test we pass the optional parameter **--common-hostname-suffix foo.com** to smallfile_rsptimes_stats.py.  The inputs to smallfile_rsptimes_stats.py are contained in ```/tmp/12573.tmp/``` and the output looks like this:
```

$ more /tmp/12573.tmp/../rsptime-summary.csv
host:thread, samples, min, max, mean, %dev, 50 %ile, 90 %ile, 95 %ile, 99 %ile, 
all:all,320, 1.000000, 40.000000, 20.500000, 56.397441, 20.500000, 36.100000, 38.050000, 40.000000, 

host-21:all,160, 1.000000, 40.000000, 20.500000, 56.486046, 20.500000, 36.100000, 38.050000, 40.000000, 
host-22:all,160, 1.000000, 40.000000, 20.500000, 56.486046, 20.500000, 36.100000, 38.050000, 40.000000, 

host-21:01,40, 1.000000, 40.000000, 20.500000, 57.026595, 20.500000, 36.100000, 38.050000, 39.610000, 
host-21:02,40, 1.000000, 40.000000, 20.500000, 57.026595, 20.500000, 36.100000, 38.050000, 39.610000, 
host-21:03,40, 1.000000, 40.000000, 20.500000, 57.026595, 20.500000, 36.100000, 38.050000, 39.610000, 
host-21:04,40, 1.000000, 40.000000, 20.500000, 57.026595, 20.500000, 36.100000, 38.050000, 39.610000, 
host-22:01,40, 1.000000, 40.000000, 20.500000, 57.026595, 20.500000, 36.100000, 38.050000, 39.610000, 
host-22:02,40, 1.000000, 40.000000, 20.500000, 57.026595, 20.500000, 36.100000, 38.050000, 39.610000, 
host-22:03,40, 1.000000, 40.000000, 20.500000, 57.026595, 20.500000, 36.100000, 38.050000, 39.610000, 
host-22:04,40, 1.000000, 40.000000, 20.500000, 57.026595, 20.500000, 36.100000, 38.050000, 39.610000, 

```
* record 1 - contains headers for each column
* record 2 - contains aggregate response time statistics for the entire distributed system, if it consists of more than 1 host
* record 4-5 - contains per-host aggregate statistics
* record 7-end - contains per-thread stats, sorted by host then thread

You'll notice that even though all the threads have the same simulated response times, the 99th percentile values for each thread are different than the aggregate stats per host or for the entire test!  How can this be?  Percentiles are computed using the [numpy.percentiles](https://docs.scipy.org/doc/numpy/reference/generated/numpy.percentile.html) function, which linearly interpolates to obtain percentile values.  In the aggregate stats, the 99th percentile is linearly interpolated between two samples of 40 seconds, whereas in the per-thread results the 99th percentile is interpolated between samples of 40 and 39 seconds.  

How to run correctly
=============

Here are some things you need to know in order to get valid results - it is not
enough to just specify the workload that you want.

Avoiding caching effects
==========

THere are two types of caching effects that we wish to avoid, data caching and
metadata caching.  If the average object size is sufficiently large, we need
only be concerned about data caching effects.  In order to avoid data caching
effects during a large-object read test, the Linux buffer cache on all servers
must be cleared. In part this is done using the command: "echo 1 > /proc/sys/vm/drop_caches" on all hosts.  However, some filesystems such as
Gluster have their own internal caches - in that case you might even need to
remount the filesystem or even restart the storage pool/volume.

Use of pause option
==========

Normally, smallfile stops the throughput measurement for the test as soon as
the first thread finishes processing all its files.  In some filesystems, the first thread that starts running will be operating at much higher speed (example: NFS writes) and can easily finish before other threads have a chance to get started.  This immediately invalidates the test.  To make this less likely, it is possible to insert a per-file delay into each
thread with the **--pause** option so that the other threads have a chance to
participate in the test during the measurement interval.    It is preferable to
run a longer test instead, because in some cases you might otherwise restrict
throughput unintentionally.  But if you know that your throughput upper bound
is X files/sec and you have N threads running, then your per-thread throughput
should be no more than N/X, so a reasonable pause would be something like 3X/N
microseconds.  For  example, if you know that you cannot do better than 100000
files/sec and you have 20 threads running,try a 60/100000 = 600 microsecond
pause.  Verify that this isn't affecting throughput by reducing the pause and
running a longer test.


Use with distributed filesystems
---------

With distributed filesystems, it is necessary to have multiple hosts
simultaneously applying workload to measure the performance of a distributed
filesystem. The –host-set parameter lets you specify a comma-separated list of
hosts to use.

For any distributed filesystem test, there must be a single directory which is
shared across all hosts, both test driver and worker hosts, that can be used to
pass test parameters, pass back results, and coordinate activity across the
hosts. This is referred to below as the “shared directory” in what follows. By
default this is the network_shared/ subdirectory of the –top directory, but you
can override this default by specifying the –network-sync-dir directory
parameter, see the next section for why this is useful.

Some distributed filesystems, such as NFS, have relaxed,
eventual-consistency caching of directories; this will cause problems for the
smallfile benchmark. To work around this problem, you can use a separate NFS
mountpoint exported from a Linux NFS server, mounted with the option actimeo=1
(to limit duration of time NFS will cache directory entries and metadata). You
then reference this mountpoint using the –network-sync-dir option of smallfile.
For example:

```
# mount -t nfs -o actimeo=1 your-linux-server:/your/nfs/export /mnt/nfs
# ./smallfile_cli.py –top /your/distributed/filesystem \
    –network-sync-dir /mnt/nfs/smf-shared
```

For non-Windows tests, the user must set up password-less ssh between the test
driver and the host. If security is an issue, a non-root username can be used
throughout, since smallfile requires no special privileges. Edit the
$HOME/.ssh/authorized_keys file to contain the public key of the account on the
test driver. The test driver will bypass the .ssh/known_hosts file by using -o
StrictHostKeyChecking=no option in the ssh command.

For Windows tests, each worker host must be running the launch_smf_host.py
program that polls the shared network directory for a file that contains the
command to launch smallfile_remote.py in the same way that would happen with
ssh on non-Windows tests. The command-line parameters on each Windows host
would be something like this:

    start python launch_smf_host.py –shared z:\smf\network_shared –as-host %hostname%

Then from the test driver, you could run specifying your hosts:

    python smallfile_cli.py –top z:\smf –host-set gprfc023,gprfc024

The dreaded startup timeout error
============

If you get the error "Exception: starting signal not seen within 11 seconds" when running a distributed test with a lot of subdirectories, the problem may be caused by insufficient time for the worker threads to get ready to run the test.   In some cases, this was caused by a flaw in smallfile's timeout calculation (which we believe is fixed).  However, before smallfile actually starts a test, each worker thread must prepare a directory tree to hold the files that will be used in the test.   This ensures that we are not measuring directory creation overhead when running a file create test, for example.  For some filesystems, directory creation can be more expensive at scale.  We take this into account with the --min-dirs-per-sec parameter, which defaults to a value more appropriate for local filesystems.   If we are doing a large distributed filesystem test, it may be necessary to lower this parameter somewhat, based on the filesystem's performance, which you can measure using --operation mkdir, and then use a value of about half what you see there.  This will result in a larger timeout value, which you can obtain using "--output-json your-test.json" -- look for the 'startup-timeout' and 'host-timeout' parameters in this file to see what timeout is being calculated.


Use with local filesystems
-----------

There are cases where you want to use a distributed filesystem test on
host-local filesystems. One such example is virtualization, where the “local”
filesystem is really layered on a virtual disk image which may be stored in a
network filesystem. The benchmark needs to share certain files across hosts to
return results and synchronize threads. In such a case, you specify the
–network-sync-dir directory-pathname parameter to have the benchmark use a
directory in some shared filesystem external to the test directory (specified
with –top parameter). By default, if this parameter is not specified then the
shared directory will be the subdirectory network-dir underneath the directory
specified with the –top parameter.

Use of subdirectories
----------

Before a test even starts, the smallfile benchmark ensures that the
directories needed by that test already exist (there is a specific operation
type for testing performance of subdirectory creation and deletion). If the top
directory (specified by –top parameter) is D, then the top per-thread directory
is D/host/dTT where TT is a 2-digit thread number and “host” is the hostname.
If the test is not a distributed test, then it's just whatever host the
benchmark command was issued on, otherwise it is each of the hosts specified by
the –host-set parameter. The first F files (where F is the value of the
–files-per-dir) parameter are placed in this top per-thread directory. If the
test uses more than F files/thread, then at least one subdirectory from the
first level of subdirectories must be used; these subdirectories have the path
T/host/dTT/dNNN where NNN is the subdirectory number. Suppose the value of the
parameter –subdirs-per-dir is D. Then there are at most D subdirectories of the
top per-thread directory. If the test requires more than D(F+1) files per
thread, then a second level of subdirectories will have to be created, with
pathnames like T/host/dTT/dNNN/dMMM . This process of adding subdirectories
continues in this fashion until there are sufficient subdirectories to hold all
the files. The purpose of this approach is to simulate a mixture of directories
and files, and to not require the user to specify how many levels of
directories are required.

The use of multiple mountpoints is supported. This features is useful for
testing NFS, etc.

Note that the test harness does not have to scan the directories to figure out
which files to read or write – it simply generates the filename sequence
itself. If you want to test directory scanning speed, use readdir or ls-l
operations. 

Sharing directories across threads
---------

Some applications require that many threads, possibly spread across many host
machines, need to share a set of directories. The --same-dir parameter makes it
possible for the benchmark to test this situation. By default this parameter is
set to N, which means each thread has its own non-overlapping directory tree.
This setting provides the best performance and scalability. However, if the
user sets this parameter to Y, then the top per-thread directory for all
threads will be T instead of T/host/dTT as described in preceding section.

Hashing files into directory tree
----------

For applications which create very large numbers of small files (millions for
example), it is impossible or at the very least impractical to place them all
in the same directory, whether or not the filesystem supports so many files in
a single directory. There are two ways which applications can use to solve this
problem:

 * insert files into 1 directory at a time – can create I/O and lock contention for the directory metadata
 * insert files into many directories at the same time – relieves I/O and lock contention for directory metadata, but increases the amount of metadata caching needed to avoid cache misses

The –hash-into-dirs parameter is intended to enable simulation of this latter
mode of operation. By default, the value of this parameter is N, and in this
case a smallfile thread will sequentially access directories one at a time. In
other words, the first D (where D = value of –files-per-dir parameter) files
will be assigned to the top per-thread directory, then the next D files will be
assigned to the next per-thread directory, and so on. However, if the
–hash-into-dirs parameter is set to Y, then the number of the file being
accessed by the thread will be hashed into the set of directories that are
being used by this thread. 

Random file size distribution option
-------------

In real life, users don't create files that all have the same size. Typically
there is a file size distribution with a majority of small files and a lesser
number of larger files. This benchmark supports use of the random exponential
distribution to approximate that behavior. If you specify

     --file-size-distribution exponential --file-size S

The meaning of the –file-size parameter changes to the maximum file size (S
KB), and the mean file size becomes S/8. All file sizes are rounded down to the
nearest kilobyte boundary, and the smallest allowed file size is 1 KB. When
this option is used, the smallfile benchmark saves the seed for each thread's
random number generator object in a .seed file stored in the TMPDIR directory
(typically /var/tmp). This allows the file reader to recreate the sequence of
random numbers used by the file writer to generate file sizes, so that the
reader knows exactly how big each file should be without asking the file system
for this information. The append operation works in the same way. All other
operations are metadata operations and do not require that the file size be
known in advance.


Asynchronous file copy performance
---------

When we want to measure performance of an asynchronous file copy (example:
Gluster geo-replication), we can use smallfile to create the original directory
tree, but then we can use the new await-create operation type to wait for files
to appear at the file copy destination. To do this, we need to specify a
separate network sync directory. So for example, to create the original
directory tree, we could use a command like:

    # ./smallfile_cli.py --top /mnt/glusterfs-master/smf \  
        --threads 16 --files 2000 --file-size 1024 \  
        --operation create –incompressible Y --record-ctime-size Y

Suppose that this mountpoint is connected to a Gluster “master” volume which is
being geo-replicated to a “slave” volume in a remote site asynchronously. We
can measure the performance of this process using a command like this, where
/mnt/glusterfs-slave is a read-only mountpoint accessing the slave volume.

    # ./smallfile_cli.py --top /mnt/glusterfs-slave/smf \  
         --threads 16 --files 2000 --file-size 1024 \  
         --operation await-create –incompressible Y \  
         --network-sync-dir /tmp/other

Requirements:

* The parameters controlling file sizes, directory tree, and number of files must match in the two commands.
* The --incompressible option must be set if you want to avoid situation where async copy software can compress data to exceed network bandwidth.
* The first command must use the –record-ctime-size Y option so that the await-create operation knows when the original file was created and how big it was.

How does this work? The first command records information in a user-defined xattr for each file so that the second command, the await-create operation can calculate time required to copy the file, which is recorded as a “response time”, and so that it knows that the entire file reached the destination.

Comparable Benchmarks
==============

There are many existing performance test benchmarks. I have tried just about
all the ones that I've heard of. Here are the ones I have looked at, I'm sure
there are many more that I failed to include here.

* Bonnie++ -- works well for a single host, but you cannot generate load from multiple hosts because the benchmark will not synchronize its activities, so different phases of the benchmark will be running at the same time, whether you want them to or not.

* iozone -- this is a great tool for large-file testing, but it can only do 1 file/thread in its current form.

* postmark -- works fine for a single client, not as useful for multi-client tests

* grinder -- has not to date been useful for filesystem testing, though it works well for web services testing.

* JMeter – has been used successfully by others in the past.

* fs_mark -- Ric Wheeler's filesystem benchmark, is very good at creating files

* fio -- Linux test tool -- broader coverage of Linux system calls particularly around async. and direct I/O.  Now has multi-host capabilities

* diskperf – open-source tool that generates limited small-file workloads for a single host.

* dbench – developed by samba team

* SPECsfs – not open-source, but "netmist" component has some mixed-workload, multi-host workload generation capabilities, configured similarly to iozone, but with a wider range of workloads.

Design principles
=============

A cluster-aware test tool ideally should:

* start threads on all hosts at same time
* stop measurement of throughput for all threads at the same time
* be easy to use in all file system environments
* be highly portable and be trivial to install
* have very low overhead
* not require threads to synchronize (be embarrassingly parallel) 

Although there may be some useful tests that involve thread synchronization or contention, we don't want the tool to force thread synchronization or contention for resources. 

In order to run prolonged small-file tests (which is a requirement for scalability to very large clusters), each thread has to be able to use more than one directory.   Since some filesystems perform very differently as the files/directory ratio increases, and most applications and users do not rely on having huge file/directory ratios, this is also important for testing the filesystem with a realistic use case.  This benchmark does something similar to Ric Wheeler's fs_mark benchmark with multiple directory levels.   This benchmark imposes no hard limit on how many directories can be used and how deep the directory tree can go.  Instead, it creates directories according to these constraints:

* files (and directories) are placed as close to the root of the directory hierarchy as possible
* no directory contains more than the number of files specified in the --files-per-dir test parameter
* no directory contains more than number of subdirectories specified in the --dirs-per-dir test parameter


Synchronization
--------------

A single directory is used to synchronize the threads and hosts. This may seem
problematic, but we assume here that the file system is not very busy when the
test is run (otherwise why would you run a load test on it?). So if a file is
created by one thread, it will quickly be visible on the others, as long as the
filesystem is not heavily loaded.

If it's a single-host test, any directory is sharable amongst threads, but in a
multi-host test only a directory shared by all participating hosts can be used.
If the –top test directory is in a network-accessible file system (could be NFS
or Gluster for example), then the synchronization directory is by default in
the network_shared subdirectory by default and need not be specified. If the
–top directory is in a host-local filesystem, then the –network-sync-dir option
must be used to specify the synchronization directory. When a network directory
is used, change propagation between hosts cannot be assumed to occur in under
two seconds.

We use the concept of a "starting gate" -- each thread does all preparation for
test, then waits for a special file, the "starting gate", to appear in the
shared area. When a thread arrives at the starting gate, it announces its
arrival by creating a filename with the host and thread ID embedded in it. When
all threads have arrived, the controlling process will see all the expected
"thread ready" files, and will then create the starting gate file. When the
starting gate is seen, the thread pauses for a couple of seconds, then
commences generating workload. This initial pause reduces time required for all
threads to see the starting gate, thereby minimizing chance of some threads
being unable to start on time. Synchronous thread startup reduces the "warmup
time" of the system significantly.

We also need a checkered flag (borrowing from car racing metaphor). Once test
starts, each thread looks for a stonewall file in the synchronization
directory. If this file exists, then the thread stops measuring throughput at
this time (but can (and does by default) optionally continue to perform
requested number of operations). Consequently throughput measurements for each
thread may be added to obtain an accurate aggregate throughput number. This
practice is sometimes called "stonewalling" in the performance testing world.

Synchronization operations in theory do not require the worker threads to read
the synchronization directory. For distributed tests, the test driver host has
to check whether the various per-host synchronization files exist, but this
does not require a readdir operation. The test driver does this check in such a
way that the number of file lookups is only slightly more than the number of
hosts, and this does not require reading the entire directory, only doing a set
of lookup operations on individual files, so it's O(n) scalable as well.

The bad news is that some filesystems do not synchronize directories quickly
without an explicit readdir() operation, so we are at present doing
os.listdir() as a workaround -- this may have to be revisited for very large
tests.


Test parameter transmission
--------

The results of the command line parse are saved in a smf_test_params object and
stored in a python pickle file, which is a representation independent of CPU
architecture or operating system. The file is placed in the shared network
directory. Remote worker processes are invoked via the smallfile_remote.py
command and read this file to discover test parameters.

Launching remote worker threads
----------

For Linux or other non-Windows environments, the test driver launches worker threads using parallel ssh commands to invoke the smallfile_remote.py program, and when this program exits, that is how the test driver discovers that the remote threads on this host have completed.

For Windows environments, ssh usage is more problematic. Sshd requires installation of cygwin, a Windows app that emulates a Linux-like environment, but we really want to test with native win32 environment instead. So a different launching method is used (and this method works on non-Windows environments as well). 

Returning results
-----------------

For either single-host or multi-host tests, each test thread is implemented as
a smf_invocation object and all thread state is kept there.  Results are
returned by using python "pickle" files to serialize the state of these
per-thread objects containing details of each thread's progress during the
test.  The pickle files are stored in the shared synchronization directory.




