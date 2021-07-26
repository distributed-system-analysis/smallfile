#!/bin/bash
set -xeo
# smallfile regression test
#
# you can set the environment variable PYTHON_PROG 
# to switch between python3 and python2
# for example: # PYTHON_PROG=python3 bash regtest.sh
# python3 at present doesn't seem to support xattr module 
# so some smallfile operations are not yet supported under python3, 
# the regression test knows how to deal with that.
#
# you can have it use a directory in a tmpfs mountpoint, 
# this is recommended so as not to wear out laptop drive.
# by default, newer distros have /run tmpfs mountpoint with sufficient space 
# so this is default, but TMPDIR environment variable overrides
# xattrs won't be tested if you use tmpfs for $testdir
#
# for really long runs you can't fit in tmpfs mountpoint so
# $bigtmp defaults to /var/tmp, but you can override with BIGTMP
# environment variable.  Recommend you use SSD for $bigtmp
#
# ext4 doesn't support xattrs by default.  
# To run a test on xattr-related operation types,  
# set TMPDIR to an XFS filesystem.  
# You can create an XFS filesystem by using a loopback device, for example:
#
#   dd if=/dev/zero of=/var/tmp/xfs-fs.img bs=1024k count=1k
#   losetup /dev/loop4 /var/tmp/xfs-fs.img
#   mkfs -t xfs /dev/loop4
#   mkdir -p /mnt/xattrtest
#   mount -t xfs -o noatime,inode64 /dev/loop4 /mnt/xattrtest
#   export TMPDIR=/mnt/xattrtest/smf
#   mkdir /mnt/xattrtest/smf
#   -- run test ---
#   unset TMPDIR
#   umount /mnt/xattrtest
#   losetup -e /dev/loop4
#   rm -fv /var/tmp/xfs-fs.img
#
# we don't use "tee" program to display results as they are happening 
# because this erases any failure status code returned by smallfile, 
# and this status code is vital to regression test.  
# Instead we log all smallfile output to smfregtest.log 
# where it can be analyzed later  if failure occurs
#

localhost_name="$1"
if [ -z "$localhost_name" ] ; then localhost_name="localhost" ; fi

nfs_svc="nfs"
(find /etc/systemd/system | grep nfs-server) && nfs_svc="nfs-server"

# xattrs must be set to zero if using tmpfs, since tmpfs doesn't support xattrs

testdir="${TMPDIR:-/var/tmp}/smf"
xattrs=0
if [ -d $testdir ] ; then
	(df $testdir | grep -q tmpfs) || xattrs=1
fi
bigtmp="${BIGTMP:-/var/tmp}/smf"
nfsdir=/var/tmp/smfnfs
OK=0
NOTOK=1
GREP="grep -q "
PYTHON=${PYTHON_PROG:-python3}
f=smfregtest.log
iam=$USER
echo "see end of $f for cause of failures" 

assertfail() {
  status=$1
  if [ $status == $OK ] ; then
    echo "ERROR: unexpected success status $status"
    exit $NOTOK
  fi
}

runsmf() {
  smfcmd="$1"
  echo "$smfcmd"
  $smfcmd > $f 2>&1
}

cleanup() {
  grep -q $nfsdir /proc/mounts 
  if [ $? = $OK ] ; then sudo umount $nfsdir || exit $NOTOK ; fi
  sudo exportfs -ua
  rm -rf /var/tmp/invoke*.log
  mkdir -pv $testdir
  chown -v $iam:$iam $testdir $testdir/..
  chmod -v 777 $testdir
  touch $testdir/letmein
  sudo exportfs -v -o rw,no_root_squash,sync,fsid=15 localhost:$testdir
  sudo rm -rf $nfsdir
  mkdir -p $nfsdir
  chown -v $iam:$iam $nfsdir
  chmod -v 777 $nfsdir
  sleep 1
  sudo mount -t nfs -o nfsvers=3,tcp,actimeo=1 $localhost_name:$testdir $nfsdir
  sudo chmod -v 777 $nfsdir
  sudo exportfs -v | grep -q $testdir 2>/tmp/ee
  df $nfsdir
  touch $nfsdir/letmein
}

is_systemctl=1
systemctl > /tmp/junk
if [ $? != $OK ] ; then  # chances are it's pre-systemctl Linux distro, use "service" instead
  is_systemctl=0
fi

start_service()
{
svcname=$1
echo "attempting to start service $svcname"
if [ $is_systemctl == 1 ] ; then
  sudo systemctl restart $svcname
else
  sudo service $svcname restart
fi
s=$?
if [ $? != $OK ] ; then
  echo "FAILED to start service $svcname"
fi
return $s
}

start_service sshd || exit $NOTOK
start_service $nfs_svc || exit $NOTOK

# set up NFS mountpoint

cleanup

# test assertion mechanism

cp -r /foo/bar/no-such-dir /tmp/ >> $f 2>&1 || assertfail $?

# before running unit tests, install whatever python module provides unittest feature
# package install may fail on distros like Fedora 33 because it's already there
(echo 'import unittest' | $PYTHON) || \
 sudo yum install -y python-unittest2 || \
 sudo yum install -y python-unittest || \
 sudo yum install -y python3-unittest || \
 (echo 'import unittest' | $PYTHON) || \
  exit $NOTOK

# run the smallfile.py module's unit test

echo "running smallfile.py unit test"
$PYTHON smallfile.py

# run the invoke_process.py unit test

echo "running invoke_process.py unit test"
$PYTHON invoke_process.py

# run drop_buffer_cache.py unit test

echo "running drop_buffer_cache.py unit test"
$PYTHON drop_buffer_cache.py

# run yaml parser unit test

echo "running YAML parser unit test"
$PYTHON yaml_parser.py

# test simplest smallfile_cli commands, using non-default dirs

echo "simplest smallfile_cli.py commands"

scmd="$PYTHON smallfile_cli.py "
cleanup
rm -fv $testdir/{starting_gate,stonewall}.tmp 2>/tmp/e || \
  assertfail $?
runsmf "$scmd"
ls -l $testdir/{starting_gate,stonewall}.tmp || \

non_dflt_dir=/var/tmp/foo
scmd="$PYTHON smallfile_cli.py --top $non_dflt_dir "
cleanup
rm -rf $non_dflt_dir
mkdir $non_dflt_dir
runsmf "$scmd"
(cd $non_dflt_dir/network_shared ; ls -l {starting_gate,stonewall}.tmp)

scmd="$scmd --host-set localhost"
cleanup
rm -rf $non_dflt_dir
mkdir $non_dflt_dir
runsmf "$scmd"
(cd $non_dflt_dir/network_shared ; \
 ls -l {starting_gate,stonewall}.tmp param.pickle host_ready.localhost.tmp) 2>/tmp/e

# test parsing

nonnegmsg="integer value greater than zero expected"
echo "testing parsing"
scmd="$PYTHON smallfile_cli.py --top $testdir "
cleanup
runsmf "$scmd --files 0" || \
  assertfail $?
$GREP "$nonnegmsg" $f

cleanup
runsmf "$scmd --threads 0" || \
  assertfail $?
$GREP "$nonnegmsg" $f

runsmf "$scmd --files -1" 		|| assertfail $?
runsmf "$scmd --record-size -1" 	|| assertfail $?
runsmf "$scmd --file-size -1" 		|| assertfail $?
runsmf "$scmd --files-per-dir 0" 	|| assertfail $?
runsmf "$scmd --dirs-per-dir 0" 	|| assertfail $?
runsmf "$scmd --record-size -1" 	|| assertfail $?
runsmf "$scmd --record-size a" 		|| assertfail $?
runsmf "$scmd --top /" 			|| assertfail $?
runsmf "$scmd --response-times foo"	|| assertfail $?
runsmf "$scmd --stonewall foo" 		|| assertfail $?
runsmf "$scmd --finish foo"		|| assertfail $?
runsmf "$scmd --host-count -5" 		|| assertfail $?
runsmf "$scmd --auto-pause foo"		|| assertfail $?

cat > $nfsdir/bad.yaml <<EOF
--file-size 30
EOF
runsmf "$PYTHON smallfile_cli.py --yaml-input $nfsdir/bad.yaml" || assertfail $?

# run a command with all CLI options and verify that they were successfully parsed

cleanup
rm -rf $nfsdir/smf
mkdir -p $nfsdir/smf
scmd="$PYTHON smallfile_cli.py --top $nfsdir/smf "
scmd="$scmd --verify-read N --response-times Y --finish N --stonewall N --permute-host-dirs Y --verbose Y"
scmd="$scmd --same-dir Y --operation create --threads 5 --files 20 --files-per-dir 5 --dirs-per-dir 3"
scmd="$scmd --record-size 6 --file-size 30 --file-size-distribution exponential --prefix a --suffix b"
scmd="$scmd --hash-into-dirs Y --pause 5 --auto-pause Y --host-set $localhost_name --output-json $nfsdir/smf.json"
runsmf "$scmd"
expect_strs=( 'verify read? : N' \
        "hosts in test : \['$localhost_name'\]" \
        'file size distribution : random exponential'\
        'filename prefix : a' \
        'filename suffix : b' \
        'hash file number into dir.? : Y' \
        'pause between files (microsec) : 5' \
        'finish all requests? : N' \
        'stonewall? : N' \
        'measure response times? : Y' \
        'log to stderr? : False' \
        'permute host directories? : Y' \
        'verbose? : True' \
        'response times? : Y' \
        'finish all requests? : N' \
        'threads share directories? : Y' \
        'pause between files (microsec) : 5' \
	'auto-pause? : Y' \
        "top test directory(s) : \['$nfsdir/smf'\]" \
        'operation : create' \
        'threads : 5' \
        'files/thread : 20' \
        'files per dir : 5' \
        'dirs per dir : 3' \
        'record size (KB, 0 = maximum) : 6' \
        'file size (KB) : 30' )
expect_ct=${#expect_strs[*]}
for j in $(seq 0 $expect_ct) ; do 
  expected_str="${expect_strs[$j]}"
  $GREP "$expected_str" $f || \
	  (echo "expecting: $expected_str" ; exit $NOTOK)
done

# now do same thing in YAML to verify 

cleanup
rm -rf $nfsdir/smf
mkdir -p $nfsdir/smf
yamlfile=$testdir/regtest.yaml

cat > $yamlfile <<EOF
top: $nfsdir/smf
verify-read: N
response-times: Y
finish: n
stonewall: false
permute-host-dirs: y
verbose: yes
same-dir: Y
operation: create
threads: 5
files: 20
files-per-dir: 5
dirs-per-dir: 3
record-size: 6
file-size: 30
file-size-distribution: exponential
prefix: a
suffix: b
hash-into-dirs:   yes
pause: 5
auto-pause: Y
cleanup-delay-usec-per-file: 500
host-set: $localhost_name
output-json: $nfsdir/smf.json
EOF

# argparse recognizes unambiguous abbreviations of param. names
scmd="$PYTHON smallfile_cli.py --yaml-input $yamlfile"
runsmf "$scmd"
for k in `seq 0 $expect_ct` ; do 
  expected_str="${expect_strs[$k]}"
  $GREP "$expected_str" $f || \
	  (echo "expecting: $expected_str" ; exit $NOTOK)
done


echo "parsing JSON output"
smfpretty=/var/tmp/smfpretty.json
$PYTHON -m json.tool < $nfsdir/smf.json > $smfpretty
json_strs=( 'params' 'file-size' 'file-size-distr' 'files-per-dir' \
	    'files-per-thread' 'finish-all-requests' 'fname-prefix' \
	    'fname-suffix' 'fsync-after-modify' 'hash-to-dir' 'host-set' \
	    'network-sync-dir' 'operation' 'pause-between-files' \
	    'permute-host-dirs' 'share-dir' 'stonewall' 'threads' \
	    'top' 'verify-read' 'xattr-count' 'xattr-size' \
	    'files-per-sec' 'pct-files-done' \
	    'per-thread' '00' 'elapsed' \
	    'in-thread' 'files' 'records' 'status' 'IOPS' 'MiBps' )
	    
expect_ct=${#json_strs[*]}
for j in `seq 1 $expect_ct` ; do
  (( k = $j + 1 ))
  expected_str="${json_strs[$k]}"
  $GREP "$expected_str" $smfpretty ||
	  (echo "expecting: $expected_str" ; exit $NOTOK)
done

supported_ops()
{
        multitop=''
        if [ "$2" = 'multitop' ] ; then multitop='multiple-topdirs' ; fi
 
        # python3 does not support xattr-related ops yet, I forget why
        xattr_ops="setxattr getxattr swift-put swift-get"
        if [ "$PYTHON" = "python3" -o "$PYTHON" = "pypy" ] ; then xattr_ops='' ; fi
        if [ $xattrs -eq 0 ] ; then xattr_ops='' ; fi

        # directory-reading ops do not work with multiple top-level directories at present
        single_topdir_ops='readdir ls-l'
        if [ -n "$multitop" ] ; then single_topdir_ops='' ; fi
        
        # for debug only: ops="create cleanup"
        ops="cleanup create append overwrite read $single_topdir_ops chmod stat $xattr_ops symlink mkdir rmdir rename delete-renamed"
        echo $ops
}

run_one_cmd()
{
  cmd="$1"
  echo "$cmd" | tee -a $f
  $cmd 2>&1 | tee /tmp/onetest.tmp
}

common_params=\
"$PYTHON smallfile_cli.py --files 1000 --files-per-dir 5 --dirs-per-dir 2 --threads 4 --file-size 4 --record-size 16 --file-size 32  --verify-read Y --response-times N --xattr-count 9 --xattr-size 253 --stonewall N"

# also test response time percentile analysis

echo "*** run one long cleanup test with huge directory and 1 thread ***"

cleanup_test_params="$common_params --threads 1 --files 1000000 --files-per-dir 1000000 --file-size 0"
rm -fv /tmp/smf.json $testdir/*rsptime*csv
run_one_cmd "$cleanup_test_params --top $testdir --operation create --response-times Y --output-json /tmp/smf.json"
start_time=$(tr '",' '  ' < /tmp/smf.json | awk '/start-time/{print $NF}')
echo "start time was $start_time"
$PYTHON smallfile_rsptimes_stats.py --start-time $start_time --time-interval 1 $testdir/network_shared
int_start_time=$(echo $start_time | awk -F. '{ print $1 }')
echo "rounded-down start time was $int_start_time"
grep $int_start_time $testdir/network_shared/stats-rsptimes.csv || exit $NOTOK
run_one_cmd "$cleanup_test_params --top $testdir --operation cleanup"

echo "*** run one test with many threads ***"

many_thread_params="$common_params --threads 30 --files 10000 --files-per-dir 10 --file-size 0"
run_one_cmd "$many_thread_params --top $testdir --operation create"
run_one_cmd "$many_thread_params --top $testdir --operation cleanup"

echo "******** testing non-distributed operations" | tee -a $f

cleanup
for op in `supported_ops $xattrs ''` ; do
  echo
  echo "testing local op $op"
  run_one_cmd "$common_params --operation $op"
done

echo "******** simulating distributed operations with launch-by-daemon" | tee -a $f

cleanup
rm -fv $testdir/shutdown_launchers.tmp
python launch_smf_host.py --top $testdir --as-host foo &
worker_pids="$!"
python launch_smf_host.py --top $testdir --as-host bar &
worker_pids="$worker_pids $!"
sleep 2
daemon_params=\
"$PYTHON smallfile_cli.py --launch-by-daemon Y --host-set foo,bar --top $testdir \
--verify-read Y --response-times N --remote-pgm-dir `pwd` \
--files 1000 --files-per-dir 5 --dirs-per-dir 2 --threads 4 --file-size 4"

for op in `supported_ops $xattrs ''` ; do
  echo
  echo "testing local op $op"
  run_one_cmd "$daemon_params --operation $op"
done
touch $testdir/network_shared/shutdown_launchers.tmp
echo "waiting for launcher daemons to shut down..."
for p in $worker_pids ; do
  wait $p || exit $NOTOK
done
echo "launchers shut down"
rm -fv $testdir/network_shared/shutdown_launchers.tmp

# we do these kinds of tests to support non-distributed filesystems and NFS exports of them

echo "******** testing non-distributed ops with multiple top-level directories" | tee -a $f

topdirlist="${testdir}1,${testdir}2,${testdir}3,${testdir}4"
scmd="$PYTHON smallfile_cli.py --top $topdirlist "
topdirlist_nocomma=`echo $topdirlist | sed 's/,/ /g'`
for d in $topdirlist_nocomma ; do
  sudo mkdir -pv $d
  sudo chown -v $iam:$iam $d
  sudo chmod -v 777 $d
done
cleanup
for op in `supported_ops $xattrs 'multitop'` ; do
  echo
  echo "testing local op $op"
  run_one_cmd "$common_params --top $topdirlist --operation $op"
done
for d in $topdirlist_nocomma ; do sudo rm -rf $d ; done

# these kinds of tests are needed for distributed filesystems or NFS/SMB exports

echo "******** testing distributed operations" | tee -a $f

# as long as we use NFS for regression tests, NFS does not support xattrs at present
save_xattrs=$xattrs
xattrs=0

cleanup
for op in `supported_ops $xattrs ''` ; do
  echo
  echo "testing distributed op $op"
  run_one_cmd "$common_params --host-set $localhost_name --stonewall Y --pause 500 --operation $op"
done

# we do these tests for virtualization (many KVM guests or containers, shared storage but no shared fs)

echo "******* testing distributed operation with a host-local fs" | tee -a $f

cleanup
for op in `supported_ops $xattrs ''` ; do
  rm -rf $nfsdir/sync
  mkdir $nfsdir/sync
  echo
  echo "testing remote-but-local op $op"
  run_one_cmd "$common_params --top $testdir --network-sync-dir $nfsdir/sync --host-set $localhost_name --operation $op"
done


echo "*** run one long test of creates and reads ***" | tee -a $f

cleanup
xattrs=$save_xattrs
rm -rf $bigtmp
mkdir -pv $bigtmp
chown -v $iam:$iam $bigtmp
chmod -v 777 $bigtmp
bigtest_params="$common_params --top $bigtmp --files 20000 --file-size 0 --record-size 4 "
bigtest_params="$bigtest_params --files-per-dir 3 --dirs-per-dir 2 --threads 10 --stonewall Y --pause 10"
for op in create read ; do
  echo "big test with op $op"
  run_one_cmd "$bigtest_params --operation $op "
done
# could be out of space on root filesystem, so cleanup
rm -rf /var/tmp/invoke*.log
run_one_cmd "$bigtest_params --operation cleanup "

$GREP $nfsdir /proc/mounts
if [ $? == $OK ] ; then
  sudo umount -v $nfsdir
  sudo rm -rf $nfsdir
fi
sudo exportfs -uav
sudo rm -rf $testdir $bigtmp
sudo systemctl stop $nfs_svc
sudo systemctl stop sshd
echo 'SUCCESS!'
