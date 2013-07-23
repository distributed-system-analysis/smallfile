import os
import pickle

def write_sync_file(fpath, contents):
    with open(fpath, "w") as sgf: 
      sgf.write(contents)
      sgf.flush()
      os.fsync(sgf.fileno())
      sgf.close()

def write_pickle(fpath, obj):
    with open(fpath, 'w') as result_file:
      pickle.dump(obj, result_file)
      result_file.flush()
      os.fsync(result_file.fileno())  # have to do this or reader may not see data

