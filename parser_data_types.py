import argparse
import os
import smallfile
from smallfile import SmallfileWorkload

TypeExc = argparse.ArgumentTypeError

# if we throw exceptions, do it with this
# so caller can specifically catch them

class SmfParseException(Exception):
    pass

# the next few routines implement data types
# of smallfile parameters

def boolean(boolstr):
    if boolstr == True:
        return True
    elif boolstr == False:
        return False
    b = boolstr.lower()
    if b == 'y' or b == 'yes' or b == 't' or b == 'true':
        bval = True
    elif b == 'n' or b == 'no' or b == 'f' or b == 'false':
        bval = False
    else:
        raise TypeExc('boolean value must be y|yes|t|true|n|no|f|false')
    return bval

def positive_integer(posint_str):
    intval = int(posint_str)
    if intval <= 0:
        raise TypeExc( 'integer value greater than zero expected')
    return intval

def non_negative_integer(nonneg_str):
    intval = int(nonneg_str)
    if intval < 0:
        raise TypeExc( 'non-negative integer value expected')
    return intval

def host_set(hostname_list_str):
    if os.path.isfile(hostname_list_str):
        with open(hostname_list_str, 'r') as f:
            hostname_list = [ record.strip() for record in f.readlines() ]
    else:
        hostname_list = hostname_list_str.strip().split(',')
        if len(hostname_list) < 2:
            hostname_list = hostname_list_str.strip().split()
        if len(hostname_list) == 0:
            raise TypeExc('host list must be non-empty')
    return hostname_list

def directory_list(directory_list_str):
    directory_list = directory_list_str.strip().split(',')
    if len(directory_list) == 1:
        directory_list = directory_list_str.strip().split()
    if len(directory_list) == 0:
        raise TypeExc('directory list must be non-empty')
    return directory_list

def file_size_distrib(fsdistrib_str):
    # FIXME: should be a data type
    if fsdistrib_str == 'exponential':
        return SmallfileWorkload.fsdistr_random_exponential
    elif fsdistrib_str == 'fixed':
        return SmallfileWorkload.fsdistr_fixed
    else:
        # should never get here
        raise TypeExc(
            'file size distribution must be either "exponential" or "fixed"')

