'''
parse.py -- parses CLI commands for smallfile_cli.py
Copyright 2012 -- Ben England
Licensed under the Apache License at http://www.apache.org/licenses/LICENSE-2.0
See Appendix on this page for instructions pertaining to license.
'''

import sys
import os
import smallfile
from smallfile import smf_invocation

version = '1.9.11'

def usage(msg):  # call if CLI syntax error or invalid parameter
    print
    print 'ERROR: ' + msg
    print 'usage: smallfile_cli.py '
    print '  --operation create|append|read|rename|delete|delete-renamed|symlink|mkdir|rmdir|stat|chmod|setxattr|getxattr'
    print '  --top top-dir | top-dir1,top-dir2,...,top-dirN'
    print '  --host-set h1,h2,...,hN'
    print '  --network-sync-dir directory-path'
    print '  --files positive-integer'
    print '  --files-per-dir positive-integer'
    print '  --dirs-per-dir positive-integer'
    print '  --threads positive-integer'
    print '  --record-size non-negative-integer-KB'
    print '  --xattr-size non-negative-integer-bytes'
    print '  --xattr-count non-negative-integer-bytes'
    print '  --file-size-distribution exponential'
    print '  --permute-host-dirs Y|N'
    print '  --hash-into-dirs Y|N'
    print '  --file-size non-negative-integer-KB'
    print '  --prefix alphanumeric-string'
    print '  --suffix alphanumeric-string'
    print '  --finish Y|N'
    print '  --verify-read Y|N'
    print '  --response-times Y|N'
    print '  --same-dir Y|N'
    print '  --pause microsec'
    print '  --remote-pgm-dir directory-pathname'
    sys.exit(1)

# convert boolean command line parameter value into True/False 

def str2bool(val, prmname):
    if((val == 'y') or (val == 'Y')): return True
    if((val == 'n') or (val == 'N')): return False
    usage('boolean parameter "%s" must be either Y or N'%prmname)

# convert boolean value into 'Y' or 'N'

def bool2YN(boolval):
    if boolval: return 'Y'
    return 'N'

# ensure that input integer is non-negative

def chkNonNegInt(intval, prm):
    try:
        v = int(intval)
    except ValueError, e:
        usage('parameter "%s" must be an integer'%prm)
    if v < 0: 
        usage('integer parameter "%s" must be non-negative'%prm)

# ensure that input integer is positive

def chkPositiveInt(intval, prm):
    chkNonNegInt(intval, prm)
    if int(intval) == 0:
        usage('integer parameter "%s" must be positive'%prm)

# return tuple containing:
#   list of hosts participating in test
#   list of subprocess instances initialized with test parameters
#   top directory
#   remote command to pass to client host via ssh
#   are we slave or master?

def parse():

  # define parameter variables and default parameter values 
  # default does short test in /var/tmp so you can see the program run 
  # store as much as you can in smf_invocation object so per-thread invocations inherit

  inv = smf_invocation()
  inv.iterations = 3
  inv.record_sz_kb = 4
  inv.total_sz_kb = 64
  inv.files_per_dir = 200
  inv.dirs_per_dir = 20
  inv.log_to_stderr = False
  inv.opname = 'create'
  inv.pause_between_files = 0
  inv.verify_read = True
  inv.stonewall = True
  inv.finish_all_rq = True
  inv.measure_rsptimes = False
  inv.is_shared_dir = False

  # parameters that can't be stored in a smf_invocation
  # describe how the smf_invocation threads work together

  prm_thread_count = 2
  prm_host_set = None
  prm_slave = False
  prm_permute_host_dirs = False
  prm_remote_pgm_dir = None
  prm_network_sync_dir = None
  prm_top_dir = None

  # parse command line

  argc = len(sys.argv)

  pass_on_prm_list = ''  # parameters passed to remote hosts if needed
  j=1
  while j < argc:
    rawprm = sys.argv[j]
    if rawprm == '-h' or rawprm == '--help':
      usage('ok, so you need help, we all knew that ;-)')
    if rawprm[0:2] != '--': usage('parameter names begin with "--"')
    prm = rawprm[2:]
    if (j == argc - 1) and (argc%2 != 1): usage('all parameters consist of a name and a value')
    val = sys.argv[j+1]
    if len(rawprm) < 3: usage('parameter name not long enough' )
    pass_on_prm = rawprm + ' ' + val
    j += 2
    if   prm == 'files': 
        chkPositiveInt(val, rawprm)
        inv.iterations = int(val)
    elif prm == 'threads': 
        chkPositiveInt(val, rawprm)
        prm_thread_count = int(val)
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
          usage('unrecognized file size distribution: %s'%val)
        inv.filesize_distr = smf_invocation.filesize_distr_random_exponential
    elif prm == 'xattr-size':
        chkNonNegInt(val, rawprm)
        inv.xattr_size = int(val) 
    elif prm == 'xattr-count':
        chkNonNegInt(val, rawprm)
        inv.xattr_count = int(val) 
    elif prm == 'prefix': inv.prefix = val
    elif prm == 'suffix': inv.suffix = val
    elif prm == 'hash-into-dirs': inv.hash_to_dir = str2bool(val, rawprm)
    elif prm == 'operation': 
        if not smf_invocation.all_op_names.__contains__(val):
            usage('unrecognized operation name: %s'%val)
        inv.opname = val
    elif prm == 'top': 
        prm_top_dir = val.split(',')
    elif prm == 'pause': 
        chkPositiveInt(val, rawprm)
        inv.pause_between_files = int(val)
    elif prm == 'stonewall': inv.stonewall = str2bool(val, rawprm)
    elif prm == 'finish': inv.finish_all_rq = str2bool(val, rawprm)
    elif prm == 'permute-host-dirs': 
        prm_permute_host_dirs = str2bool(val, rawprm)
        pass_on_prm = ''
    elif prm == 'response-times': inv.measure_rsptimes = str2bool(val, rawprm)
    elif prm == 'verify-read': inv.verify_read = str2bool(val, rawprm)
    elif prm == 'same-dir': inv.is_shared_dir = str2bool(val, rawprm)
    elif prm == 'verbose': inv.verbose = str2bool(val, rawprm)
    elif prm == 'log-to-stderr': inv.log_to_stderr = str2bool(val, rawprm)
    elif prm == 'host-set': 
        prm_host_set = val.split(",")
        if len(prm_host_set) < 2: prm_host_set = val.strip().split()
        pass_on_prm = ''
    elif prm == 'remote-pgm-dir': prm_remote_pgm_dir = val
    elif prm == 'network-sync-dir': prm_network_sync_dir = val
    # --slave should not be used by end-user
    elif prm == 'slave': prm_slave = str2bool(val, rawprm)
    # --ashost should not be used by end-user
    elif prm == 'as-host': 
        inv.onhost = smallfile.short_hostname(val)
    else: usage('unrecognized parameter name')

    pass_on_prm_list += ' ' + pass_on_prm  # parameter options that workload generators will need

  # validate parameters further now that we know what they all are

  if inv.record_sz_kb > inv.total_sz_kb and inv.total_sz_kb != 0:
    usage('record size cannot exceed file size')

  if (inv.record_sz_kb != 0) and ((inv.total_sz_kb % inv.record_sz_kb) != 0):
    usage('file size must be multiple of record size if record size is non-zero')

  if prm_top_dir: 
    for d in prm_top_dir:
      if len(d) < 6:
        usage('directory less than 6 characters, cannot use top of filesystem, too dangerous')
  if prm_top_dir:
    inv.set_top(prm_top_dir)
  else:
    prm_top_dir = inv.top_dirs
  if prm_network_sync_dir:
    if not prm_host_set and not prm_slave:
      usage('you do not need to specify a network thread synchronization directory unless you use multiple hosts')
    inv.network_dir = prm_network_sync_dir
  if prm_remote_pgm_dir:
    if not prm_host_set and not prm_slave:
      usage('you do not need to specify a remote program directory unless you use multiple hosts')
  inv.starting_gate = os.path.join(inv.network_dir, 'starting_gate.tmp')   # location of file that signals start, end of test

  if inv.iterations < 10: inv.stonewall = False

  # display results of parse so user knows what default values are
  # most important parameters come first
  # display host set first because this can be very long, 
  # this way the rest of the parameters appear together on the screen

  size_distribution_string = 'fixed'
  if inv.filesize_distr == smf_invocation.filesize_distr_random_exponential: 
    size_distribution_string = 'random exponential'

  prm_list = [ \
             ('hosts in test', '%s'%prm_host_set), \
             ('top test directory(s)', str(prm_top_dir)), \
             ('operation', inv.opname), \
             ('files/thread', '%d'%inv.iterations), \
             ('threads', '%d'%prm_thread_count), \
             ('record size (KB)', '%d'%inv.record_sz_kb), \
             ('file size (KB)', '%d'%inv.total_sz_kb), \
             ('file size distribution', size_distribution_string), \
             ('files per dir', '%d'%inv.files_per_dir), \
             ('dirs per dir', '%d'%inv.dirs_per_dir), \
             ('threads share directories?', '%s'%bool2YN(inv.is_shared_dir)), \
             ('filename prefix', inv.prefix), \
             ('filename suffix', inv.suffix), \
             ('hash file number into dir.?', bool2YN(inv.hash_to_dir)), \
             ('pause between files (microsec)', '%d'%inv.pause_between_files), \
             ('finish all requests?', '%s'%bool2YN(inv.finish_all_rq)), \
             ('stonewall?', '%s'%bool2YN(inv.stonewall)), \
             ('measure response times?', '%s'%bool2YN(inv.measure_rsptimes)), \
             ('verify read?', '%s'%bool2YN(inv.verify_read)), \
             ('verbose?', inv.verbose), \
             ('log to stderr?', inv.log_to_stderr) ]
  if (not smallfile.xattr_not_installed) and (inv.opname == 'setxattr' or inv.opname == 'getxattr'):
    prm_list.extend( [ ('ext.attr.size', '%d'%inv.xattr_size), ('ext.attr.count', '%d'%inv.xattr_count) ] )
  if prm_host_set:
    prm_list.extend( [ \
             ('permute host directories?', '%s'%bool2YN(prm_permute_host_dirs)) ] )
    if prm_remote_pgm_dir: prm_list.append( ('remote program directory', prm_remote_pgm_dir) )
    if prm_network_sync_dir: prm_list.append( ('network thread sync. dir.', prm_network_sync_dir) )

  if not prm_slave:
    print 'smallfile version %s'%version
    for (prm_name, prm_value) in prm_list:
      print '%40s : %s'%(prm_name, prm_value)

  # construct command to run remote slave process using CLI parameters, we have them all here
  if not prm_remote_pgm_dir: prm_remote_pgm_dir = os.getcwd()
  remote_cmd = prm_remote_pgm_dir + os.sep + 'smallfile_cli.py ' + pass_on_prm_list

  # "inv" contains all per-thread parameters
  return (prm_host_set, prm_thread_count, inv, remote_cmd, prm_slave, prm_permute_host_dirs)

