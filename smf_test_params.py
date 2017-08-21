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
                 permute_host_dirs = False):

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

        # calculate timeouts
        # make sure dirs is never zero
        # or you will break host_startup_timeout calculation

        self.startup_timeout = 10
        dirs = 1
        dirs += (self.master_invoke.iterations * self.thread_count
                 // self.master_invoke.files_per_dir)
        self.startup_timeout += dirs // 3
        self.host_startup_timeout = self.startup_timeout
        if self.host_set:
            self.host_startup_timeout += 5 + dirs * len(self.host_set) // 3

    def __str__(self):
        fmt = 'smf_test_params: as_host=%s host_set=%s '
        fmt += 'thread_count=%d remote_pgm_dir=%s'
        fmt += 'slave=%s permute_host_dirs=%s startup_timeout=%d '
        fmt += 'host_timeout=%d smf_invoke=%s '
        return fmt % (
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
            ('threads share directories?', '%s'
             % bool2YN(inv.is_shared_dir)),
            ('filename prefix', inv.prefix),
            ('filename suffix', inv.suffix),
            ('hash file number into dir.?', bool2YN(inv.hash_to_dir)),
            ('fsync after modify?', bool2YN(inv.fsync)),
            ('pause between files (microsec)', '%d'
             % inv.pause_between_files),
            ('finish all requests?', '%s' % bool2YN(inv.finish_all_rq)),
            ('stonewall?', '%s' % bool2YN(inv.stonewall)),
            ('measure response times?', '%s'
             % bool2YN(inv.measure_rsptimes)),
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

