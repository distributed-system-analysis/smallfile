import yaml
import smallfile
import argparse
import parser_data_types
from parser_data_types import SmfParseException, TypeExc
from parser_data_types import boolean, positive_integer, non_negative_integer
from parser_data_types import host_set, directory_list, file_size_distrib
import smf_test_params
import os

# module to parse YAML input file containing smallfile parameters
# YAML parameter names are identical to CLI parameter names
#  except that the leading "--" is removed
# modifies test_params object with contents of YAML file

def parse_yaml(test_params, input_yaml_file):
    inv = test_params.master_invoke
    with open(input_yaml_file, 'r') as f:
        try:
            y = yaml.safe_load(f)
            if y == None:
                y = {}
        except yaml.YAMLError as e:
            emsg = "YAML parse error: " + str(e)
            raise SmfParseException(emsg)
    
    try:
        for k in y.keys():
            v = y[k]
            if k == 'yaml-input-file':
                raise SmfParseException('cannot specify YAML input file from within itself!')
            elif k == 'output-json':
                test_params.output_json = v
            elif k == 'response-times':
                inv.measure_rsptimes = boolean(v)
            elif k == 'response-time-histogram':
                inv.measure_rsptime_histogram = boolean(v)
            elif k == 'network-sync-dir':
                inv.network_dir = boolean(v)
            elif k == 'operation':
                if not smallfile.SmallfileWorkload.all_op_names.__contains__(v):
                    raise SmfParseException('operation "%s" not recognized')
                inv.opname = v
            elif k == 'top':
                test_params.top_dirs = [ os.path.abspath(p) for p in y['top'].split(',') ]
            elif k == 'host-set':
                test_params.host_set = host_set(v)
            elif k == 'files':
                inv.iterations = positive_integer(v)
            elif k == 'threads':
                test_params.thread_count = positive_integer(v)
            elif k == 'files-per-dir':
                inv.files_per_dir = positive_integer(v)
            elif k == 'dirs-per-dir':
                inv.dirs_per_dir = positive_integer(v)
            elif k == 'record-size':
                inv.record_sz_kb = positive_integer(v)
            elif k == 'file-size':
                inv.total_sz_kb = non_negative_integer(v)
            elif k == 'file-size-distribution':
                test_params.size_distribution = inv.filesize_distr = file_size_distrib(v)
            elif k == 'fsync':
                inv.fsync = boolean(v)
            elif k == 'xattr-size':
                inv.xattr_size = positive_integer(v)
            elif k == 'xattr-count':
                inv.xattr_count = positive_integer(v)
            elif k == 'pause':
                inv.pause_between_files = non_negative_integer(v)
            elif k == 'stonewall':
                inv.stonewall = boolean(v)
            elif k == 'finish':
                inv.finish_all_rq = boolean(v)
            elif k == 'prefix':
                inv.prefix = v
            elif k == 'suffix':
                inv.suffix = v
            elif k == 'hash-into-dirs':
                inv.hash_to_dir = boolean(v)
            elif k == 'same-dir':
                inv.is_shared_dir = boolean(v)
            elif k == 'verbose':
                inv.verbose = boolean(v)
            elif k == 'permute-host-dirs':
                test_params.permute_host_dirs = boolean(v)
            elif k == 'record-time-size':
                inv.record_ctime_size = boolean(v)
            elif k == 'verify-read':
                inv.verify_read = boolean(v)
            elif k == 'incompressible':
                inv.incompressible = boolean(v)
            elif k == 'min-dirs-per-sec':
                test_params.min_directories_per_sec = positive_integer(v)
            elif k == 'log-to-stderr':
                raise SmfParseException('%s: not allowed in YAML input' % k)
            elif k == 'remote-pgm-dir':
                raise SmfParseException('%s: not allowed in YAML input' % k)
            else:
                raise SmfParseException('%s: unrecognized input parameter name' % k)
    except TypeExc as e:
        emsg = 'YAML parse error for key "%s" : %s' % (k, str(e))
        raise SmfParseException(emsg)


if __name__ == '__main__':
    import unittest2
    class YamlParseTest(unittest2.TestCase):
        def setUp(self):
            self.params = smf_test_params.smf_test_params()

        def tearDown(self):
            self.params = None

        def test_parse_all(self):
            fn = '/tmp/sample_parse.yaml'
            with open(fn, 'w') as f:
                f.write('operation: create\n')
            parse_yaml(self.params, fn)
            assert(self.params.master_invoke.opname == 'create')

        def test_parse_negint(self):
            fn = '/tmp/sample_parse_negint.yaml'
            with open(fn, 'w') as f:
                f.write('files: -3\n')
            try:
                parse_yaml(self.params, fn)
            except SmfParseException as e:
                msg = str(e)
                if not msg.__contains__('greater than zero'):
                    raise e

        def test_parse_hostset(self):
            fn = '/tmp/sample_parse_hostset.yaml'
            with open(fn, 'w') as f:
                f.write('host-set: host-foo,host-bar\n')
            parse_yaml(self.params, fn)
            assert(self.params.host_set == [ 'host-foo', 'host-bar' ])

        def test_parse_fsdistr_exponential(self):
            fn = '/tmp/sample_parse_fsdistr_exponential.yaml'
            with open(fn, 'w') as f:
                f.write('file-size-distribution: exponential\n')
            parse_yaml(self.params, fn)
            assert(self.params.master_invoke.filesize_distr == smallfile.SmallfileWorkload.fsdistr_random_exponential)

        def test_parse_dir_list(self):
            fn = '/tmp/sample_parse_dirlist.yaml'
            with open(fn, 'w') as f:
                f.write('top: foo,bar \n')
            parse_yaml(self.params, fn)
            mydir=os.getcwd()
            topdirs = [ os.path.join(mydir, d) for d in [ 'foo', 'bar' ] ]
            assert(self.params.top_dirs == topdirs)

    unittest2.main()
