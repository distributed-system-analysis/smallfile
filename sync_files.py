import os
import pickle
import shutil
import time

import smallfile
from smallfile import ensure_dir_exists

def write_sync_file(fpath, contents):
    with open(fpath, "w") as sgf: 
      sgf.write(contents)
      sgf.flush()
      os.fsync(sgf.fileno())
      # file should close when you exit with block

def write_pickle(fpath, obj):
    with open(fpath, 'w') as result_file:
      pickle.dump(obj, result_file)
      result_file.flush()
      os.fsync(result_file.fileno())  # have to do this or reader may not see data

def create_top_dirs(master_invoke, is_multi_host):
    if os.path.exists( master_invoke.network_dir ): 
      shutil.rmtree( master_invoke.network_dir )
      if is_multi_host: time.sleep(2.1) # hack to ensure that all remote clients can see that directory has been recreated
    ensure_dir_exists( master_invoke.network_dir )
    for dlist in [ master_invoke.src_dirs, master_invoke.dest_dirs ]:
      for d in dlist:
         ensure_dir_exists(d)
    if is_multi_host: 
      os.listdir(master_invoke.network_dir)  # workaround to attempt to force synchronization
      time.sleep(1.1) # hack to let NFS mount option actimeo=1 have its effect
