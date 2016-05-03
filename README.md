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

* manages workload generators on multiple hosts
* calculates aggregate throughput for entire set of hosts
* can start and stop workload generator threads at approximately same time
* useful for generating "pure" workloads (as opposed to mixed workloads)
* easy to extend to new workload types
* provides CLI for scripted use, but workload generator is separate so a GUI is
  possible
* supports either fixed file size or random exponential file size
* can capture response time data in .csv format, provides utility to reduce
  this data to statistics
* supports Windows (different launching method, see below)
* writes unique data pattern in all files, can verify data read against this
  pattern
* can write random data pattern that is incompressible
* can measure time required for files to appear in a directory tree (for async
  replication)
* in multi-host tests, can force all clients to read files written by different
  client

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
* Have only tested Windows XP and Windows 7, but any Win32-compatible Windows
  would probably work with this.


