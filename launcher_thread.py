#!/usr/bin/python
# -*- coding: utf-8 -*-

'''
launcher_thread.py
manages parallel execution of shell commands on remote hosts
it assumes there is a poller on each remote host, launch_smf_host.py,
it waits for files of form '*.smf_launch' in the shared directory
and when it finds one,
it reads in the command to start the worker from it and launches it.
This takes the place of an sshd thread launching it.
Copyright 2012 -- Ben England
Licensed under the Apache License at http://www.apache.org/licenses/LICENSE-2.0
See Appendix on this page for instructions pertaining to license.
'''

import threading
import os
import time
import smallfile
from smallfile import ensure_deleted


# this class is just used to create a python thread
# for each remote host that we want to use as a workload generator
# the thread just executes an ssh command to run this program on a remote host

class launcher_thread(threading.Thread):

    def __init__(self, prm, remote_host, remote_cmd_in):
        threading.Thread.__init__(self)
        self.prm = prm  # test parameters
        self.remote_host = remote_host
        self.remote_cmd = remote_cmd_in
        self.status = None

    def run(self):
        master_invoke = self.prm.master_invoke
        launch_fn = os.path.join(master_invoke.network_dir,
                                 self.remote_host) + '.smf_launch'
        pickle_fn = master_invoke.host_result_filename(self.remote_host)
        abortfn = master_invoke.abort_fn()
        ensure_deleted(launch_fn)
        ensure_deleted(pickle_fn)
        with open(launch_fn, 'w') as launch_file:
            launch_file.write(self.remote_cmd)
            launch_file.close()
        pickle_fn = master_invoke.host_result_filename(self.remote_host)
        # print('waiting for pickle file %s'%pickle_fn)
        self.status = master_invoke.NOTOK  # premature exit means failure
        while not os.path.exists(pickle_fn):
            # print('%s not seen'%pickle_fn)
            if os.path.exists(abortfn):
                if master_invoke.verbose:
                    print('test abort seen by host ' + self.remote_host)
                return
            time.sleep(3)
        self.status = master_invoke.OK  # success!
