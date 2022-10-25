# -*- coding: utf-8 -*-
import errno
import os
import pickle


class SMFSyncFileException(Exception):
    pass


notyet = ".notyet"


def touch(fpath):
    try:
        with open(fpath, "w") as sgf:
            sgf.write("hi")
            sgf.flush()
            os.fsync(sgf.fileno())
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise e


def write_sync_file(fpath, contents):
    with open(fpath + notyet, "w") as sgf:
        sgf.write(contents)
        sgf.flush()
        os.fsync(sgf.fileno())  # file should close when you exit block
        os.rename(fpath + notyet, fpath)


def write_pickle(fpath, obj):
    with open(fpath + notyet, "wb") as result_file:
        pickle.dump(obj, result_file)
        result_file.flush()
        os.fsync(result_file.fileno())  # or else reader may not see data
        os.rename(fpath + notyet, fpath)


# create directory if it's not already there


def ensure_dir_exists(dirpath):
    if not os.path.exists(dirpath):
        parent_path = os.path.dirname(dirpath)
        if parent_path == dirpath:
            raise SMFSyncFileException(
                "ensure_dir_exists: cannot obtain parent path of non-existent path: "
                + dirpath
            )
        ensure_dir_exists(parent_path)
        try:
            os.mkdir(dirpath)
        except os.error as e:
            if e.errno != errno.EEXIST:  # workaround for filesystem bug
                raise e
    else:
        if not os.path.isdir(dirpath):
            raise SMFSyncFileException(
                "%s already exists and is not a directory!" % dirpath
            )


# avoid exception if file we wish to delete is not there


def ensure_deleted(fn):
    try:
        if os.path.lexists(fn):
            os.unlink(fn)
    except Exception as e:
        # could be race condition with other client processes/hosts
        # if was race condition, file will no longer be there
        if os.path.exists(fn):
            raise SMFSyncFileException(
                "exception while ensuring %s deleted: %s" % (fn, str(e))
            )
