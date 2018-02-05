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

def usage(msg):  # call if CLI syntax error or invalid parameter
    opnames = '  --operation '
    for op in SmallfileWorkload.all_op_names:
        opnames += op + '|'
    opnames = opnames[:-1]
    dflts = SmallfileWorkload()
    print('')
    print('ERROR: ' + msg)
    print('usage: smallfile_cli.py ')
    print(opnames)
    print('  --top top-dir | top-dir1,top-dir2,...,top-dirN   (default: %s)' %
          SmallfileWorkload.tmp_dir)
    print('  --host-set h1,h2,...,hN')
    print('  --network-sync-dir directory-path                (default: %s' %
          os.path.join(SmallfileWorkload.tmp_dir, 'network_shared'))
    print('  --files positive-integer                         (default: %d)' %
          dflts.iterations)
    print('  --files-per-dir positive-integer                 (default: %d)' %
          dflts.files_per_dir)
    print('  --dirs-per-dir positive-integer                  (default: %d)' %
          dflts.dirs_per_dir)
    print('  --threads positive-integer                       (default: %d)' %
          2)
    print('  --record-size non-negative-integer-KB            (default: %d)' %
          dflts.record_sz_kb)
    print('  --record-ctime-size                              (default: N)')
    print('  --xattr-size non-negative-integer-bytes          (default: %d)' %
          dflts.xattr_size)
    print('  --xattr-count non-negative-integer-bytes         (default: %d)' %
          dflts.xattr_count)
    print('  --file-size-distribution exponential             ' +
          '(default: fixed-size)')
    print('  --permute-host-dirs Y|N                          (default: N)')
    print('  --hash-into-dirs Y|N                             (default: %s)' %
          bool2YN(dflts.hash_to_dir))
    print('  --file-size non-negative-integer-KB              (default: %d)' %
          dflts.total_sz_kb)
    print('  --prefix alphanumeric-string')
    print('  --suffix alphanumeric-string')
    print('  --fsync Y|N                                      (default: %s)' %
          bool2YN(dflts.fsync))
    print('  --finish Y|N                                     (default: %s)' %
          bool2YN(dflts.finish_all_rq))
    print('  --incompressible Y|N                             (default: %s)' %
          bool2YN(dflts.verify_read))
    print('  --verify-read Y|N                                (default: %s)' %
          bool2YN(dflts.verify_read))
    print('  --output-json pathname                           (default: None)')
    print('  --response-times Y|N                             (default: %s)' %
          bool2YN(dflts.measure_rsptimes))
    print('  --same-dir Y|N                                   (default: %s)' %
          bool2YN(dflts.is_shared_dir))
    print('  --pause microsec                                 (default: %d)' %
          dflts.pause_between_files)
    print('  --remote-pgm-dir directory-pathname              (default: %s)' %
          os.getcwd())
    sys.exit(NOTOK)


# convert boolean command line parameter value into True/False

def str2bool(val, prmname):
    if val == 'y' or val == 'Y':
        return True
    if val == 'n' or val == 'N':
        return False
    usage('boolean parameter "%s" must be either Y or N' % prmname)


# ensure that input integer is non-negative

def chkNonNegInt(intval, prm):
    try:
        v = int(intval)
    except ValueError:
        usage('parameter "%s" must be an integer' % prm)
    if v < 0:
        usage('integer parameter "%s" must be non-negative' % prm)


# ensure that input integer is positive

def chkPositiveInt(intval, prm):
    chkNonNegInt(intval, prm)
    if int(intval) == 0:
        usage('integer parameter "%s" must be positive' % prm)


# return tuple containing:
#   list of hosts participating in test
#   list of subprocess instances initialized with test parameters
#   top directory
#   remote command to pass to client host via ssh
#   are we slave or master?

def parse():

    # define parameter variables
    # default does short test in /var/tmp so you can see the program run
    # store as much as you can in SmallfileWorkload object
    # so per-thread invocations inherit

    test_params = smf_test_params.smf_test_params()
    inv = test_params.master_invoke  # for convenience

    # parse command line

    argc = len(sys.argv)

    if argc == 1:
        print('''
for additional help add the parameter "--help" to the command
''')
    j = 1
    while j < argc:
        rawprm = sys.argv[j]
        if rawprm == '-h' or rawprm == '--help':
            usage('ok, so you need help, we all knew that ;-)')
        if rawprm[0:2] != '--':
            usage('parameter names begin with "--"')
        prm = rawprm[2:]
        if j == argc - 1 and argc % 2 != 1:
            usage('all parameters consist of a name and a value')
        val = sys.argv[j + 1]
        if len(rawprm) < 3:
            usage('parameter name not long enough')
        pass_on_prm = rawprm + ' ' + val
        j += 2
        if prm == 'files':
            chkPositiveInt(val, rawprm)
            inv.iterations = int(val)
        elif prm == 'threads':
            chkPositiveInt(val, rawprm)
            test_params.thread_count = int(val)
        elif prm == 'files-per-dir':
            chkPositiveInt(val, rawprm)
            inv.files_per_dir = int(val)
        elif prm == 'dirs-per-dir':
            chkPositiveInt(val, rawprm)
            inv.dirs_per_dir = int(val)
        elif prm == 'record-size':
            chkNonNegInt(val, rawprm)
            inv.record_sz_kb = int(val)
        elif prm == 'file-size':
            chkNonNegInt(val, rawprm)
            inv.total_sz_kb = int(val)
        elif prm == 'file-size-distribution':
            if val != 'exponential':
                usage('unrecognized file size distribution: %s' % val)
            inv.filesize_distr = \
                SmallfileWorkload.fsdistr_random_exponential
            test_params.size_distribution = 'random exponential'
        elif prm == 'xattr-size':
            chkNonNegInt(val, rawprm)
            inv.xattr_size = int(val)
        elif prm == 'xattr-count':
            chkNonNegInt(val, rawprm)
            inv.xattr_count = int(val)
        elif prm == 'prefix':
            inv.prefix = val
        elif prm == 'suffix':
            inv.suffix = val
        elif prm == 'hash-into-dirs':
            inv.hash_to_dir = str2bool(val, rawprm)
        elif prm == 'operation':
            if not SmallfileWorkload.all_op_names.__contains__(val):
                usage('unrecognized operation name: %s' % val)
            inv.opname = val
        elif prm == 'top':
            test_params.top_dirs = [os.path.abspath(p) for p in val.split(',')]
            for p in test_params.top_dirs:
                if not os.path.isdir(p):
                    usage('you must ensure that shared directory ' + p + 
                          ' is accessible ' +
                          'from this host and every remote host in test')
        elif prm == 'pause':
            chkPositiveInt(val, rawprm)
            inv.pause_between_files = int(val)
        elif prm == 'stonewall':
            inv.stonewall = str2bool(val, rawprm)
        elif prm == 'finish':
            inv.finish_all_rq = str2bool(val, rawprm)
        elif prm == 'fsync':
            inv.fsync = str2bool(val, rawprm)
        elif prm == 'record-ctime-size':
            inv.record_ctime_size = str2bool(val, rawprm)
        elif prm == 'permute-host-dirs':
            test_params.permute_host_dirs = str2bool(val, rawprm)
            pass_on_prm = ''
        elif prm == 'output-json':
            test_params.output_json = val
        elif prm == 'response-times':
            inv.measure_rsptimes = str2bool(val, rawprm)
        elif prm == 'incompressible':
            inv.incompressible = str2bool(val, rawprm)
        elif prm == 'verify-read':
            inv.verify_read = str2bool(val, rawprm)
        elif prm == 'same-dir':
            inv.is_shared_dir = str2bool(val, rawprm)
        elif prm == 'verbose':
            inv.verbose = str2bool(val, rawprm)
        elif prm == 'log-to-stderr':
            inv.log_to_stderr = str2bool(val, rawprm)
        elif prm == 'host-set':
            if os.path.isfile(val):
                with open(val, 'r') as f:
                    test_params.host_set = [
                        record.strip() for record in f.readlines()]
            else:
                test_params.host_set = val.split(',')
                if len(test_params.host_set) < 2:
                    test_params.host_set = val.strip().split()
                if len(test_params.host_set) == 0:
                    usage('host list must be non-empty when ' +
                          '--host-set option used')
            pass_on_prm = ''
        elif prm == 'remote-pgm-dir':
            test_params.remote_pgm_dir = val
        elif prm == 'network-sync-dir':
            test_params.network_sync_dir = val
        elif prm == 'slave':
            # --slave should not be used by end-user
            test_params.is_slave = str2bool(val, rawprm)
        elif prm == 'as-host':
            # --ashost should not be used by end-user
            inv.onhost = smallfile.get_hostname(val)
        else:
            usage('unrecognized parameter name: %s' % prm)

    # validate parameters further now that we know what they all are

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

    test_params.recalculate_timeouts()
    return test_params
