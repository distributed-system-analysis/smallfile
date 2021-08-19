# -*- coding: utf-8 -*-
import ctypes
import ctypes.util
import os
import sys

class DropBufferCacheException(Exception):
    pass

# Drop 'buffer' cache for the given range of the given file.

POSIX_FADV_DONTNEED = 4
OK = 0


# this function is used if we can't load the real libc function

def noop_libc_function(*args):
    return 0


# I have no idea what this code really does, but strace says it works.
# does this code work under Cygwin?

def load_libc_function(func_name):
    func = noop_libc_function
    try:
        libc = ctypes.CDLL(ctypes.util.find_library('c'))
        func = getattr(libc, func_name)
    except AttributeError:
        # print("Unable to locate %s in libc.  Leaving as a no-op."% func_name)
        pass
    return func


# do this at module load time

_posix_fadvise = load_libc_function('posix_fadvise64')


def drop_buffer_cache(fd, offset, length):
    ret = _posix_fadvise(fd,
                         ctypes.c_uint64(offset),
                         ctypes.c_uint64(length),
                         POSIX_FADV_DONTNEED)
    if ret != OK:
        raise DropBufferCacheException('posix_fadvise64(%s, %s, %s, 4) -> %s' %
                        (fd, offset, length, ret))

# unit test

if __name__ == '__main__':
    fd = os.open('/tmp/foo', os.O_WRONLY | os.O_CREAT)
    if sys.version.startswith('3'):
        ret = os.write(fd, bytes('hi there', 'UTF-8'))
    elif sys.version.startswith('2'):
        ret = os.write(fd, 'hi there')
    else:
        raise DropBufferCacheException('unrecognized python version %s' % sys.version)
    assert ret == 8
    drop_buffer_cache(fd, 0, 8)
    os.close(fd)
