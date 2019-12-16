# -*- coding: utf-8 -*-
import os
import pickle
import shutil
import time

import smallfile

notyet = '.notyet'

def write_sync_file(fpath, contents):
    with open(fpath+notyet, 'w') as sgf:
        sgf.write(contents)
        sgf.flush()
        os.fsync(sgf.fileno())  # file should close when you exit with block
        os.rename(fpath+notyet, fpath)

def write_pickle(fpath, obj):
    with open(fpath+notyet, 'wb') as result_file:
        pickle.dump(obj, result_file)
        result_file.flush()
        os.fsync(result_file.fileno())  # or else reader may not see data
        os.rename(fpath+notyet, fpath)

def create_top_dirs(master_invoke, is_multi_host):
    if os.path.exists(master_invoke.network_dir):
        shutil.rmtree(master_invoke.network_dir)
        if is_multi_host:
            # so all remote clients see that directory was recreated
            time.sleep(2.1)
    smallfile.ensure_dir_exists(master_invoke.network_dir)
    for dlist in [master_invoke.src_dirs, master_invoke.dest_dirs]:
        for d in dlist:
            smallfile.ensure_dir_exists(d)
    if is_multi_host:
        # workaround to force cross-host synchronization
        os.listdir(master_invoke.network_dir)
        time.sleep(1.1)  # lets NFS mount option actimeo=1 take effect
