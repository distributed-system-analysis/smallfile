#!/usr/bin/python
# -*- coding: utf-8 -*-
# this class represents the entire set of test parameters

# calculate timeouts to allow for initialization delays
# while directory tree is created

import sys, os, smallfile

# convert boolean value into 'Y' or 'N'

def bool2YN(boolval):
    if boolval:
        return 'Y'
    return 'N'

class smf_test_params:

    def __init__(self,
                 host_set = None, 
                 thread_count = 2, 
                 remote_pgm_dir = os.path.abspath(os.path.dirname(sys.argv[0])),
                 top_dirs = None,
                 network_sync_dir = None, 
                 slave = False, 
                 size_distribution = 'fixed',
                 permute_host_dirs = False,
                 output_json = None):

        # this field used to calculate timeouts
        self.min_directories_per_sec = 50
        self.output_json = output_json
        self.version = '3.1'
        self.as_host = None
        self.host_set = host_set
        self.thread_count = thread_count
        self.master_invoke = smallfile.SmallfileWorkload()
        self.remote_pgm_dir = remote_pgm_dir
        self.top_dirs = top_dirs
        if top_dirs:
            self.master_invoke.set_top(top_dirs)
        self.network_sync_dir = network_sync_dir
        if network_sync_dir:
            self.master_invoke.network_dir = network_sync_dir
        self.is_slave = slave
        self.size_distribution = size_distribution
        self.permute_host_dirs = permute_host_dirs
        self.startup_timeout = 0
        self.host_startup_timeout = 0

    # calculate timeouts assuming 2 directories per second

    def recalculate_timeouts(self):
        total_files = self.master_invoke.iterations * self.thread_count
        # ignore subdirs per dir, this is a good estimate
        if self.host_set is not None:
            total_files *= len(self.host_set)
        dirs = total_files // self.master_invoke.files_per_dir

        # we have to create both src_dir and dst_dir trees so times 2
        # allow some time for thread synchronization
        dir_creation_overhead = (self.thread_count // 30) + ((dirs * 2) // self.min_directories_per_sec)

        # allow for creating list of pathnames if millions of files per dir
        file_creation_overhead = max(1, self.master_invoke.files_per_dir // 300000)

        # allow no less than 2 seconds to account for NTP inaccuracy
        self.startup_timeout = 2 + file_creation_overhead + dir_creation_overhead
        
        self.host_startup_timeout = self.startup_timeout
        if self.host_set is not None:
            # allow extra time for inter-host synchronization
            self.host_startup_timeout += 5 + (len(self.host_set) // 2)

    def __str__(self):
        fmt = 'smf_test_params: version=%s json=%s as_host=%s host_set=%s '
        fmt += 'thread_count=%d remote_pgm_dir=%s'
        fmt += 'slave=%s permute_host_dirs=%s startup_timeout=%d '
        fmt += 'host_timeout=%d smf_invoke=%s '
        return fmt % (
            str(self.version),
            str(self.output_json),
            str(self.as_host),
            str(self.host_set),
            self.thread_count,
            self.remote_pgm_dir,
            str(self.is_slave),
            str(self.permute_host_dirs),
            self.startup_timeout,
            self.host_startup_timeout,
            str(self.master_invoke),
            )

    # display results of parse so user knows what default values are
    # most important parameters come first
    # display host set first because this can be very long,
    # this way the rest of the parameters appear together on the screen
    # this function returns a list of (name, value) pairs for each param.

    def human_readable(self):
        inv = self.master_invoke
        prm_list = [
            ('version', self.version),
            ('hosts in test', '%s' % self.host_set),
            ('top test directory(s)', str(self.top_dirs)),
            ('operation', inv.opname),
            ('files/thread', '%d' % inv.iterations),
            ('threads', '%d' % self.thread_count),
            ('record size (KB, 0 = maximum)', '%d' % inv.record_sz_kb),
            ('file size (KB)', '%d' % inv.total_sz_kb),
            ('file size distribution', self.size_distribution),
            ('files per dir', '%d' % inv.files_per_dir),
            ('dirs per dir', '%d' % inv.dirs_per_dir),
            ('threads share directories?', '%s' % bool2YN(inv.is_shared_dir)),
            ('filename prefix', inv.prefix),
            ('filename suffix', inv.suffix),
            ('hash file number into dir.?', bool2YN(inv.hash_to_dir)),
            ('fsync after modify?', bool2YN(inv.fsync)),
            ('pause between files (microsec)', '%d' % inv.pause_between_files),
            ('minimum directories per sec', '%d' 
             % int(self.min_directories_per_sec)),
            ('finish all requests?', '%s' % bool2YN(inv.finish_all_rq)),
            ('stonewall?', '%s' % bool2YN(inv.stonewall)),
            ('measure response times?', '%s' % bool2YN(inv.measure_rsptimes)),
            ('verify read?', '%s' % bool2YN(inv.verify_read)),
            ('verbose?', inv.verbose),
            ('log to stderr?', inv.log_to_stderr),
            ]
        if smallfile.xattr_installed:
            prm_list.extend([('ext.attr.size', '%d' % inv.xattr_size),
                            ('ext.attr.count', '%d' % inv.xattr_count)])
        if self.host_set:
            prm_list.extend([('permute host directories?', '%s'
                            % bool2YN(self.permute_host_dirs))])
            if self.remote_pgm_dir:
                prm_list.append(('remote program directory',
                                self.remote_pgm_dir))
            if self.network_sync_dir:
                prm_list.append(('network thread sync. dir.',
                                self.network_sync_dir))
        return prm_list

    # add any parameters that might be relevant to 
    # data analysis here, can skip parameters that
    # don't affect test results
    # don't convert to JSON here, so that caller
    # can insert test results before conversion

    def to_json(self):

        # put params a level down so results can be 
        # inserted at same level

        json_dictionary = {}
        p = {}
        json_dictionary['params'] = p

        inv = self.master_invoke

        # put host-set at top because it can be very long
        # and we want rest of parameters to be grouped together

        p['host-set'] = self.host_set
        p['version'] = self.version
        p['top'] = ','.join(self.top_dirs)
        p['operation'] = inv.opname
        p['files-per-thread'] = inv.iterations
        p['threads'] = self.thread_count
        p['file-size'] = inv.total_sz_kb
        p['file-size-distr'] = self.size_distribution
        p['files-per-dir'] = inv.files_per_dir
        p['share-dir'] = bool2YN(inv.is_shared_dir)
        p['fname-prefix'] = inv.prefix
        p['fname-suffix'] = inv.suffix
        p['hash-to-dir'] = bool2YN(inv.hash_to_dir)
        p['fsync-after-modify'] = bool2YN(inv.fsync)
        p['pause-between-files'] = str(inv.pause_between_files)
        p['finish-all-requests'] = bool2YN(inv.finish_all_rq)
        p['stonewall'] = bool2YN(inv.stonewall)
        p['verify-read'] = bool2YN(inv.verify_read)
        p['xattr-size'] = str(inv.xattr_size)
        p['xattr-count'] = str(inv.xattr_count)
        p['permute-host-dirs'] = bool2YN(self.permute_host_dirs)
        p['network-sync-dir'] = self.network_sync_dir
        p['min-directories-per-sec'] = self.min_directories_per_sec

        # include startup-timeout and host-timeout to make possible
        # diagnosis of timeout problems, but we don't normally need them 
        # so don't include in human-readable output

        p['startup-timeout'] = self.startup_timeout
        p['host-timeout'] = self.host_startup_timeout

        return json_dictionary
