# -*- coding: utf-8 -*-

"""
parse_slave.py -- parses SSH cmd for invocation of smallfile_remote.py
Copyright 2012 -- Ben England
Licensed under the Apache License at http://www.apache.org/licenses/LICENSE-2.0
See Appendix on this page for instructions pertaining to license.
"""

import argparse
import errno
import os
import pickle
import sys
import time

import smallfile

# parse command line and return unpickled test params
# pass via --network-sync-dir option
# optionally pass host identity of this remote invocation


def parse():

    parser = argparse.ArgumentParser(description="parse remote smallfile parameters")
    parser.add_argument(
        "--network-sync-dir", help="directory used to synchronize with test driver"
    )
    parser.add_argument(
        "--as-host",
        default=smallfile.get_hostname(None),
        help="directory used to synchronize with test driver",
    )
    args = parser.parse_args()

    param_pickle_fname = os.path.join(args.network_sync_dir, "param.pickle")
    if not os.path.exists(param_pickle_fname):
        time.sleep(1.1)
    params = None
    with open(param_pickle_fname, "rb") as pickled_params:
        params = pickle.load(pickled_params)
    params.is_slave = True
    params.as_host = args.as_host
    params.master_invoke.onhost = args.as_host
    return params
