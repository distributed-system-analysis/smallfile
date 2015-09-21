#!/usr/bin/python
# -*- coding: utf-8 -*-
# this class represents the entire set of test parameters

# calculate timeouts to allow for initialization delays
# while directory tree is created


class smf_test_params:

    def __init__(self,
                 prm_host_set, prm_thread_count, master_invoke, remote_pgm_dir,
                 top_dirs, network_sync_dir, prm_slave, prm_permute_host_dirs):

        self.as_host = None
        self.host_set = prm_host_set
        self.thread_count = prm_thread_count
        self.master_invoke = master_invoke
        self.remote_pgm_dir = remote_pgm_dir
        self.master_invoke.set_top(top_dirs)
        if network_sync_dir:
            self.master_invoke.network_dir = network_sync_dir
        self.is_slave = prm_slave
        self.permute_host_dirs = prm_permute_host_dirs

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
