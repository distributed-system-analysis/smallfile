#!/usr/bin/python
# -*- coding: utf-8 -*-

'''
parse.py -- parses CLI commands for smallfile_cli.py
Copyright 2012 -- Ben England
Licensed under the Apache License at http://www.apache.org/licenses/LICENSE-2.0
See Appendix on this page for instructions pertaining to license.
'''

import sys
import os
import smallfile
from smallfile import SmallfileWorkload, NOTOK
import smf_test_params
from smf_test_params import bool2YN
import argparse
import yaml_parser
from yaml_parser import parse_yaml
import parser_data_types
from parser_data_types import SmfParseException
from parser_data_types import boolean, positive_integer, non_negative_integer
from parser_data_types import host_set, directory_list, file_size_distrib

# parse command line
# return smf_test_params.smf_test_params instance
# defining all test parameters.
# default does short test in /var/tmp so you can see the program run

def parse():
    # store as much as you can in SmallfileWorkload object
    # so per-thread invocations inherit

    test_params = smf_test_params.smf_test_params()
    inv = test_params.master_invoke  # for convenience

    parser = argparse.ArgumentParser(
            description='parse smallfile CLI parameters')
    add = parser.add_argument
    add('--yaml-input-file',
            help='input YAML file containing all parameters below')
    add('--output-json',
            default=test_params.output_json,
            help='if true then output JSON-format version of results')
    add('--response-times',
            type=boolean, default=inv.measure_rsptimes,
            help='if true then record response time of each file op')
    add('--network-sync-dir',
            help='if --top not shared filesystem, provide shared filesystem directory')
    add('--operation',
            default='cleanup', choices=SmallfileWorkload.all_op_names,
            help='type of operation to perform on each file')
    add('--top',
            type=directory_list, default=inv.top_dirs,
            help='top directory or directories used by smallfile')
    add('--host-set',
            type=host_set, default=test_params.host_set,
            help='list of workload generator hosts (or file containing it) ')
    add('--files',
            type=positive_integer, default=inv.iterations, 
            help='files processed per thread')
    add('--threads',
            type=positive_integer, default=test_params.thread_count, 
            help='threads per client')
    add('--files-per-dir',
            type=positive_integer, default=inv.files_per_dir, 
            help='files per (sub)directory')
    add('--dirs-per-dir',
            type=positive_integer, default=inv.dirs_per_dir, 
            help='subdirectories per directory')
    add('--record-size',
            type=positive_integer, default=inv.record_sz_kb, 
            help='record size (KB)')
    add('--file-size',
            type=non_negative_integer, default=inv.total_sz_kb, 
            help='subdirectories per directory')
    add('--file-size-distribution',
            type=file_size_distrib, default=inv.filesize_distr,
            help='file size can be constant ("fixed") or random ("exponential")')
    add('--fsync',
            type=boolean, default=inv.fsync,
            help='call fsync() after each file is written/modified')
    add('--xattr-size',
            type=non_negative_integer, default=inv.xattr_size, 
            help='extended attribute size (bytes)')
    add('--xattr-count',
            type=non_negative_integer, default=inv.xattr_count, 
            help='number of extended attributes per file')
    add('--pause',
            type=non_negative_integer, default=inv.pause_between_files,
            help='pause between each file (microsec)')
    add('--auto-pause',
            type=boolean, default=inv.auto_pause,
            help='adjust pause between files automatically based on response times')
    add('--stonewall',
            type=boolean, default=inv.stonewall,
            help='stop measuring as soon as first thread is done')
    add('--finish',
            type=boolean, default=inv.finish_all_rq,
            help='stop processing files as soon as first thread is done')
    add('--prefix',
            default=inv.prefix,
            help='filename prefix')
    add('--suffix',
            default=inv.suffix,
            help='filename suffix')
    add('--hash-into-dirs',
            type=boolean, default=inv.hash_to_dir,
            help='if true then pseudo-randomly place files into directories')
    add('--same-dir',
            type=boolean, default=inv.is_shared_dir,
            help='if true then all threads share the same directories')
    add('--verbose',
            type=boolean, default=inv.verbose,
            help='if true then log extra messages about test')
    add('--permute-host-dirs',
            type=boolean, default=test_params.permute_host_dirs,
            help='if true then shift clients to different host directories')
    add('--record-ctime-size',
            type=boolean, default=inv.record_ctime_size,
            help='if true then update file xattr with ctime+size')
    add('--verify-read',
            type=boolean, default=inv.verify_read,
            help='if true then check that data read = data written')
    add('--incompressible',
            type=boolean, default=inv.incompressible,
            help='if true then non-compressible data written')

    # these parameters shouldn't be used by mere mortals

    add('--min-dirs-per-sec',
            type=positive_integer, default=test_params.min_directories_per_sec,
            help=argparse.SUPPRESS)
    add('--log-to-stderr', type=boolean, default=inv.log_to_stderr, 
            help=argparse.SUPPRESS)
    add('--remote-pgm-dir', default=test_params.remote_pgm_dir, 
            help=argparse.SUPPRESS)
    add('--slave',
            help=argparse.SUPPRESS)
    add('--as-host',
            help=argparse.SUPPRESS)
    add('--host-count',
            type=positive_integer, default=0,
            help='total number of hosts/pods participating in smallfile test')

    args = parser.parse_args()

    inv.opname = args.operation
    test_params.top_dirs = [ os.path.abspath(p) for p in args.top ]
    inv.iterations = args.files
    test_params.thread_count = inv.threads = args.threads
    inv.files_per_dir = args.files_per_dir
    inv.dirs_per_dir = args.dirs_per_dir
    inv.record_sz_kb = args.record_size
    inv.total_sz_kb = args.file_size
    test_params.size_distribution = inv.filesize_distr = args.file_size_distribution
    inv.xattr_size = args.xattr_size
    inv.xattr_count = args.xattr_count
    inv.prefix = args.prefix
    inv.suffix = args.suffix
    inv.hash_to_dir = args.hash_into_dirs
    inv.pause_between_files = args.pause
    inv.auto_pause = args.auto_pause
    inv.stonewall = args.stonewall
    inv.finish_all_rq = args.finish
    inv.measure_rsptimes = args.response_times
    inv.fsync = args.fsync
    inv.record_ctime_size = args.record_ctime_size
    test_params.permute_host_dirs = args.permute_host_dirs
    test_params.output_json = args.output_json
    inv.incompressible = args.incompressible
    inv.verify_read = args.verify_read
    test_params.min_directories_per_sec = args.min_dirs_per_sec
    inv.is_shared_dir = args.same_dir
    inv.verbose = args.verbose
    inv.log_to_stderr = args.log_to_stderr
    test_params.remote_pgm_dir = args.remote_pgm_dir
    test_params.network_sync_dir = args.network_sync_dir
    test_params.is_slave = args.slave
    inv.onhost = smallfile.get_hostname(args.as_host)
    test_params.host_set = args.host_set
    inv.total_hosts = args.host_count
    if inv.total_hosts == 0:
        if test_params.host_set != None:
            inv.total_hosts = len(test_params.host_set)
        else:
            inv.total_hosts = 1

    # if YAML input was used, update test_params object with this
    # YAML parameters override CLI parameters

    if args.yaml_input_file:
        yaml_parser.parse_yaml(test_params, args.yaml_input_file)
    if not test_params.network_sync_dir:
        test_params.network_sync_dir = os.path.join(test_params.top_dirs[0], 'network_shared')

    # validate parameters further now that we know what they all are

    sdmsg = 'directory %s containing network sync dir. must exist on all hosts (including this one)'
    parentdir = os.path.dirname(test_params.network_sync_dir)
    if not os.path.isdir(parentdir) and args.host_set != None:
        raise SmfParseException(sdmsg % parentdir)

    if inv.record_sz_kb > inv.total_sz_kb and inv.total_sz_kb != 0:
        usage('record size cannot exceed file size')

    if inv.record_sz_kb == 0 and inv.verbose:
        print(('record size not specified, ' +
               'large files will default to record size %d KB') %
               (SmallfileWorkload.biggest_buf_size / inv.BYTES_PER_KB))

    if test_params.top_dirs:
        for d in test_params.top_dirs:
            if len(d) < 6:
                usage('directory less than 6 characters, ' +
                      'cannot use top of filesystem, too dangerous')
            if not os.path.isdir(d) and not test_params.network_sync_dir:
                usage('you must ensure that shared directory ' + d + 
                      ' is accessible ' +
                      'from this host and every remote host in test')
    if test_params.top_dirs:
        inv.set_top(test_params.top_dirs)
    else:
        test_params.top_dirs = inv.top_dirs

    if test_params.network_sync_dir:
        inv.network_dir = test_params.network_sync_dir
    else:
        test_params.network_sync_dir = inv.network_dir
    inv.starting_gate = os.path.join(inv.network_dir, 'starting_gate.tmp')

    if inv.iterations < 10:
        inv.stonewall = False

    if not test_params.is_slave:
        prm_list = test_params.human_readable()
        for (prm_name, prm_value) in prm_list:
            print('%40s : %s' % (prm_name, prm_value))

    if inv.auto_pause and inv.pause_between_files == 0:
        inv.pause_between_files = 10000
        print(('auto-pause requested but pause param not specified' +
               ', defaulting to %d microseconds') % inv.pause_between_files)

    test_params.recalculate_timeouts()
    return test_params
