# -*- coding: utf-8 -*-

'''
ssh_thread.py -- manages parallel execution of shell commands on remote hosts
Copyright 2012 -- Ben England
Licensed under the Apache License at http://www.apache.org/licenses/LICENSE-2.0
See Appendix on this page for instructions pertaining to license.
'''

import threading
import os


# this class is just used to create a python thread
# for each remote host that we want to use as a workload generator
# the thread just executes an ssh command to run this program on a remote host

class ssh_thread(threading.Thread):

    ssh_prefix = 'ssh -x -o StrictHostKeyChecking=no '

    def __str__(self):
        return 'ssh-thread:%s:%s:%s' % \
            (self.remote_host, str(self.status), self.remote_cmd)

    def __init__(self, remote_host, remote_cmd_in):
        threading.Thread.__init__(self)
        self.remote_host = remote_host
        self.remote_cmd = '%s %s "%s"' % \
            (self.ssh_prefix, self.remote_host, remote_cmd_in)
        # print('thread cmd %s'%self.remote_cmd)
        self.status = None

    def run(self):
        self.status = os.system(self.remote_cmd)
