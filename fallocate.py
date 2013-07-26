import ctypes
import ctypes.util
import os

# reserve space for the contents of file before you write it (hope to disable preallocation)

OK = 0
NOTOK = 1

# the mode argument to fallocate is defined in /usr/include/linux/falloc.h

FALLOC_FL_KEEP_SIZE = 0x01    # default is extend size 
FALLOC_FL_PUNCH_HOLE = 0x02   # de-allocates range 

# this function is used if we can't load the real libc function

def noop_libc_function(*args):
   return 0

# I have no idea what this code really does, but strace says it works.
# does this code work under Cygwin?

def load_libc_function(func_name):
  try:
    libc = ctypes.CDLL(ctypes.util.find_library('c'))
    return getattr(libc, func_name)
  except AttributeError:
    #print "Unable to locate %s in libc.  Leaving as a no-op."% func_name
    return None

# do this at module load time 

_posix_fallocate = load_libc_function('fallocate64')

# mode is one of FALLOC constants above

def fallocate(fd, mode, offset, length):
  ret = NOTOK
  if _posix_fallocate:
    ret = _posix_fallocate(fd, mode, ctypes.c_uint64(offset), ctypes.c_uint64(length))
  return ret

# unit test

if __name__ == "__main__":
  fd = os.open('/tmp/foo', os.O_WRONLY|os.O_CREAT)
  assert(fd > 2)
  ret = fallocate(fd, FALLOC_FL_KEEP_SIZE, 0, 8)
  assert(ret == OK)
  ret = os.write(fd, 'hi there')
  assert(ret == 8)
  os.close(fd)

