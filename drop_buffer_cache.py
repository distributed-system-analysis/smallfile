import ctypes
import ctypes.util
import os

# Drop 'buffer' cache for the given range of the given file.

POSIX_FADV_DONTNEED = 4
OK = 0

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
    print "Unable to locate %s in libc.  Leaving as a no-op."% func_name
    return noop_libc_function

# do this at module load time 

_posix_fadvise = load_libc_function('posix_fadvise64')

def drop_buffer_cache(fd, offset, length):
  ret = OK
  if _posix_fadvise:
    ret = _posix_fadvise(fd, ctypes.c_uint64(offset), ctypes.c_uint64(length), POSIX_FADV_DONTNEED)
  if ret != OK:
    raise Exception("posix_fadvise64(%s, %s, %s, 4) -> %s" % (fd, offset, length, ret))

# unit test

if __name__ == "__main__":
  fd = os.open('/tmp/foo', os.O_WRONLY|os.O_CREAT)
  ret = os.write(fd, 'hi there')
  assert(ret == 8)
  drop_buffer_cache(fd, 0, 8)
  os.close(fd)

