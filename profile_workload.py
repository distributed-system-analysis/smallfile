#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# python program used by profile.sh to generate profile of smallfile workloads
#

import os
import socket
import smallfile
top = os.getenv('TOP')
count = int(os.getenv('COUNT'))
invk = smallfile.SmallfileWorkload()
invk.tid = '00'
invk.src_dirs = [top + os.sep + 'file_srcdir' + os.sep
                 + socket.gethostname() + os.sep + 'thrd_' + invk.tid]
invk.dest_dirs = [top + os.sep + 'file_dstdir' + os.sep
                  + socket.gethostname() + os.sep + 'thrd_' + invk.tid]
invk.network_dir = top + os.sep + 'network_shared'
invk.record_sz_kb = 0
invk.total_sz_kb = 1
invk.starting_gate = os.path.join(invk.network_dir, 'starting_gate')
invk.stonewall = True
invk.finish_all_rq = True
invk.opname = os.getenv('OPNAME')
invk.iterations = count
print(invk)
invk.do_workload()
print(invk)
