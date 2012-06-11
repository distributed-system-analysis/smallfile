'''
parse.py -- parses CLI commands for smallfile_cli.py
Copyright 2012 -- Ben England
Licensed under the Apache License at http://www.apache.org/licenses/LICENSE-2.0
See Appendix on this page for instructions pertaining to license.
'''

import sys
import os
import smallfile

version = '1.9.1'

def usage(msg):  # call if CLI syntax error or invalid parameter
    print
    print 'ERROR: ' + msg
    print 'usage: smallfile_cli.py '
    print '  --operation create|append|read|rename|delete|delete-renamed|symlink|mkdir|rmdir|stat|chmod|setxattr|getxattr'
    print '  --files positive-integer'
    print '  --files-per-dir positive-integer'
    print '  --dirs-per-dir positive-integer'
    print '  --threads positive-integer'
    print '  --record-size non-negative-integer-KB'
    print '  --xattr-size non-negative-integer-bytes'
    print '  --xattr-count non-negative-integer-bytes'
    print '  --permute-host-dirs Y|N'
    print '  --file-size non-negative-integer-KB'
    print '  --prefix alphanumeric-string'
    print '  --top directory-pathname'
    print '  --finish Y|N'
    print '  --verify-read Y|N'
    print '  --response-times Y|N'
    print '  --same-dir Y|N'
    print '  --pause microsec'
    print '  --host-set h1,h2,...,hN'
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

  inv = smallfile.smf_invocation()
  inv.iterations = 3
  inv.record_sz_kb = 4
  inv.total_sz_kb = 64
  inv.files_per_dir = 200
  inv.dirs_per_dir = 20
  inv.prefix = ''
  inv.log_to_stderr = False
  inv.verbose = False
  inv.opname = 'create'
  inv.pause_between_files = 0
  inv.verify_read = True
  inv.stonewall = True
  inv.finish_all_rq = True
  inv.measure_rsptimes = False
  inv.is_shared_dir = False
  inv.do_sync_at_end = False

  # parameters that can't be stored in a smf_invocation
  # describe how the smf_invocation threads work together

  prm_thread_count = 2
  prm_host_set = None
  prm_slave = False
  prm_permute_host_dirs = False
  prm_remote_pgm_dir = os.getcwd()
  prm_top_dir = os.getenv("TMPDIR")
  if prm_top_dir == None: prm_top_dir = os.getenv("TEMP")
  if prm_top_dir == None: prm_top_dir = "/var/tmp"

  # parse command line

  argc = len(sys.argv)
  if argc%2 != 1: usage('all parameters consist of a name and a value')

  pass_on_prm_list = ''  # parameters passed to remote hosts if needed
  j=1
  while j < argc:
    rawprm = sys.argv[j]
    val = sys.argv[j+1]
    if len(rawprm) < 3: usage('parameter name not long enough' )
    if rawprm[0:2] != '--': usage('parameter names begin with "--"')
    prm = rawprm[2:]
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
    elif prm == 'xattr-size':
        chkNonNegInt(val, rawprm)
        inv.xattr_size = int(val) 
    elif prm == 'xattr-count':
        chkNonNegInt(val, rawprm)
        inv.xattr_count = int(val) 
    elif prm == 'prefix': inv.prefix = val
    elif prm == 'operation': 
        if not smallfile.smf_invocation.all_op_names.__contains__(val):
            usage('unrecognized operation name: %s'%val)
        inv.opname = val
    elif prm == 'top': prm_top_dir = val
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
    # --slave should not be used by end-user
    elif prm == 'slave': prm_slave = str2bool(val, rawprm)
    # --ashost should not be used by end-user
    elif prm == 'as-host': 
        inv.onhost = smallfile.short_hostname(val)
    else: usage('unrecognized parameter name')

    pass_on_prm_list += ' ' + pass_on_prm  # parameter options that workload generators will need

  if inv.record_sz_kb > inv.total_sz_kb and inv.total_sz_kb != 0:
    usage('record size cannot exceed file size')

  if (inv.record_sz_kb != 0) and ((inv.total_sz_kb % inv.record_sz_kb) != 0):
    usage('file size must be multiple of record size if record size is non-zero')

  if (prm_top_dir == '/'):
    usage('cannot use filesystem root, too dangerous')

  if inv.iterations < 10: inv.stonewall = False

  # display results of parse so user knows what default values are

  prm_list = [ ('files/thread', '%d'%inv.iterations), \
             ('threads', '%d'%prm_thread_count), \
             ('record size (KB)', '%d'%inv.record_sz_kb), \
             ('file size (KB)', '%d'%inv.total_sz_kb), \
             ('files per dir', '%d'%inv.files_per_dir), \
             ('dirs per dir', '%d'%inv.dirs_per_dir), \
             ('ext.attr.size', '%d'%inv.xattr_size), \
             ('ext.attr.count', '%d'%inv.xattr_count), \
             ('finish all requests?', '%s'%bool2YN(inv.finish_all_rq)), \
             ('stonewall?', '%s'%bool2YN(inv.stonewall)), \
             ('measure response times?', '%s'%bool2YN(inv.measure_rsptimes)), \
             ('verify read?', '%s'%bool2YN(inv.verify_read)), \
             ('permute host directories?', '%s'%bool2YN(prm_permute_host_dirs)), \
             ('pause between files (microsec)', '%d'%inv.pause_between_files), \
             ('files in same directory?', '%s'%bool2YN(inv.is_shared_dir)), \
             ('hosts in test', '%s'%prm_host_set), \
             ('filename prefix', inv.prefix), \
             ('operation', inv.opname), \
             ('top test directory', prm_top_dir), \
             ('remote program directory', prm_remote_pgm_dir), \
             ('verbose?', inv.verbose), \
             ('log to stderr?', inv.log_to_stderr) ]

  if not prm_slave:
    print 'smallfile version %s'%version
    for (prm_name, prm_value) in prm_list:
      print '%40s : %s'%(prm_name, prm_value)

  inv.starting_gate = prm_top_dir + os.sep + 'starting_gate'   # location of file that signals start, end of test
  inv.src_dir = prm_top_dir + os.sep + 'src'
  inv.dest_dir = prm_top_dir + os.sep + 'dst'
  # construct command to run remote slave process using CLI parameters, we have them all here
  remote_cmd = prm_remote_pgm_dir + os.sep + 'smallfile_cli.py ' + pass_on_prm_list

  # "inv" contains all per-thread parameters
  return (prm_host_set, prm_thread_count, inv, remote_cmd, prm_slave, prm_permute_host_dirs)

