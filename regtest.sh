#!/bin/bash
# smallfile regression test
#
# NOTE: this expects you to have /var/tmp in a filesystem that 
# supports extended attributes and it expects NFS to support extended attributes
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
# so this is default, but TMPDIR overrides
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

testdir="$TMPDIR/smfregtest"
xattrs=1
if [ "$TMPDIR" = "" ] ; then
  # prefer to use tmpfs so we dont wear out disk on laptop or other system disk
  testdir='/run/smfregtest'
  xattrs=0
fi
nfsdir=/var/tmp/smfnfs
OK=0
NOTOK=1
GREP="grep -q "
PYTHON=${PYTHON_PROG:-python}
f=smfregtest.log

assertfail() {
  status=$1
  if [ $status == $OK ] ; then
    echo "ERROR: unexpected success status $status"
    echo "see end of $f for cause" 
    exit $NOTOK
  fi
}

assertok() {
  status=$1
  if [ $status != $OK ] ; then
    echo "ERROR: unexpected failure status $status"
    echo "see end of $f for cause"
    exit $NOTOK
  fi
}

cleanup() {
  rm -rf /var/tmp/invoke*.log $testdir/*
  sudo mkdir -p $testdir
  grep $nfsdir /proc/mounts 
  if [ $? = $OK ] ; then sudo umount -v $nfsdir ; fi
}

is_systemctl=1
which systemctl
if [ $? != $OK ] ; then  # chances are it's pre-systemctl Linux distro, use "service" instead
  is_systemctl=0
fi

start_service()
{
svcname=$1
echo "attempting to start service $svcname"
if [ $is_systemctl == 1 ] ; then
  sudo systemctl start $svcname
else
  sudo service $svcname start
fi
if [ $? != $OK ] ; then
  echo "FAILED to start service $svcname"
  exit $NOTOK
fi
}

start_service sshd
start_service nfs

# set up NFS mountpoint

cleanup
$GREP $nfsdir /proc/mounts
if [ $? != $OK ] ; then
  sudo mkdir -pv $nfsdir
  sudo chown $USER $nfsdir
  sudo rm -rf $testdir
  sudo mkdir -p $testdir
  sudo chown $USER $testdir
  sudo chmod 777 $testdir
  sleep 1
  sudo exportfs -v -o rw,no_root_squash,sync,fsid=15 localhost:$testdir
  sleep 1
  sudo mount -v -t nfs -o nfsvers=3,tcp,actimeo=1 $localhost_name:$testdir $nfsdir
  if [ $? != $OK ] ; then 
    echo "NFS mount failed!"
    exit $NOTOK
  fi
fi

# test assertion mechanism

cp -r /foo/bar/no-such-dir /tmp/ >> $f 2>&1
assertfail $?

# run the smallfile.py module's unit test

echo "running smallfile.py unit test"
$PYTHON smallfile.py
assertok $?

# run the invoke_process.py unit test

echo "running invoke_process.py unit test"
$PYTHON invoke_process.py
assertok $?

# run drop_buffer_cache.py unit test

echo "running drop_buffer_cache.py unit test"
$PYTHON drop_buffer_cache.py
assertok $?

# test parsing

echo "testing parsing"
scmd="$PYTHON smallfile_cli.py --top $testdir "
cleanup
$scmd --files 0 >> $f
assertfail $?
$GREP 'non-negative' $f
assertok $?

cleanup
$scmd --threads 0 >> $f
assertfail $?
$GREP 'non-negative' $f
assertok $?

$scmd --files -1 >> $f
assertfail $?
$scmd --record-size -1 >> $f
assertfail $?
$scmd --file-size -1 >> $f
assertfail $?
$scmd --files-per-dir 0 >> $f
assertfail $?
$scmd --dirs-per-dir 0 >> $f
assertfail $?
$scmd --record-size -1  >> $f
assertfail $?
$scmd --record-size a >> $f
assertfail $?
$scmd --top / >> $f
assertfail $?
$scmd --response-times foo >> $f
assertfail $?
$scmd --stonewall foo >> $f
assertfail $?
$scmd --finish foo >> $f
assertfail $?

# run a command with all CLI options and verify that they were successfully parsed

cleanup
mkdir -p $nfsdir/smf
scmd="$PYTHON smallfile_cli.py --top $nfsdir/smf "
$scmd --verify-read N --response-times Y --finish N --stonewall N --permute-host-dirs Y \
	--same-dir Y --operation cleanup --threads 5 --files 20 --files-per-dir 5 --dirs-per-dir 3 \
	--record-size 6 --file-size 30 --file-size-distribution exponential --prefix a --suffix b \
	--hash-into-dirs Y --pause 5 --host-set $localhost_name --output-json /var/tmp/smf.json >> $f
assertok $?
expect_strs=( 'verify read? : N' \
        "hosts in test : \['$localhost_name'\]" \
        'top test directory(s) : ' \
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
        'verbose? : False' \
        'response times? : Y' \
        'finish all requests? : N' \
        'threads share directories? : Y' \
        'pause between files (microsec) : 5' \
        "top test directory(s) : \['$nfsdir/smf'\]" \
        'operation : cleanup' \
        'threads : 5' \
        'files/thread : 20' \
        'files per dir : 5' \
        'dirs per dir : 3' \
        'record size (KB, 0 = maximum) : 6' \
        'file size (KB) : 30' )
expect_ct=${#expect_strs[*]}
for j in `seq 1 $expect_ct` ; do 
  ((k = $j - 1))
  expected_str="${expect_strs[$k]}"
  $GREP "$expected_str" $f
  s=$?
  if [ $s != $OK ] ; then 
    echo "expecting: $expected_str"
  fi
  assertok $s $f
done

echo "parsing JSON output"
python -m json.tool < /var/tmp/smf.json > /var/tmp/smfpretty.json
json_strs=( 'params' 'file-size' 'file-size-distr' 'files-per-dir' \
	    'files-per-thread' 'finish-all-requests' 'fname-prefix' \
	    'fname-suffix' 'fsync-after-modify' 'hash-to-dir' 'host-set' \
	    'network-sync-dir' 'operation' 'pause-between-files' \
	    'permute-host-dirs' 'share-dir' 'stonewall' 'threads' \
	    'top' 'verify-read' 'xattr-count' 'xattr-size' \
	    'elapsed-time' 'files-per-sec' 'pct-files-done' \
	    'per-thread' '00' 'elapsed' 'filenum-final' \
	    'onhost' 'records' 'status' 'total-files' \
	    'total-io-requests' 'total-threads')
expect_ct=${#json_strs[*]}
for j in `seq 1 $expect_ct` ; do
  (( k = $j + 1 ))
  expected_str="${json_strs[$k]}"
  $GREP "$expected_str" /var/tmp/smfpretty.json
  s=$?
  if [ $s != $OK ] ; then 
    echo "expecting: $expected_str"
  fi
  assertok $s $f
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
  ( echo "$cmd" ; $cmd ) | tee -a $f
  assertok $?
}

common_params=\
"$PYTHON smallfile_cli.py --files 100 --files-per-dir 5 --dirs-per-dir 2 --threads 4 --file-size 4 --record-size 16 --file-size 32  --verify-read Y --response-times N --xattr-count 9 --xattr-size 253 --stonewall N"

echo "******** testing non-distributed operations"

for op in `supported_ops $xattrs ''` ; do
  rm -rf /var/tmp/invoke*.log
  echo
  echo "testing local op $op"
  run_one_cmd "$common_params --operation $op"
done

# we do these kinds of tests to support non-distributed filesystems and NFS exports of them

echo "******** testing non-distributed ops with multiple top-level directories"

topdirlist="${testdir}1,${testdir}2,${testdir}3,${testdir}4"
scmd="$PYTHON smallfile_cli.py --top $topdirlist "
topdirlist_nocomma=`echo $topdirlist | sed 's/,/ /g'`
for d in $topdirlist_nocomma ; do
  sudo mkdir -pv $d
  sudo chmod 777 $d
done
for op in `supported_ops $xattrs 'multitop'` ; do
  rm -rf /var/tmp/invoke*.log
  echo
  echo "testing local op $op"
  run_one_cmd "$common_params --operation $op"
done
for d in $topdirlist_nocomma ; do sudo rm -rf $d ; done

# these kinds of tests are needed for distributed filesystems or NFS/SMB exports

echo "******** testing distributed operations"

mkdir -pv $nfsdir/smf
# as long as we use NFS for regression tests, NFS does not support xattrs at present
save_xattrs=$xattrs
xattrs=0
for op in `supported_ops $xattrs ''` ; do
  rm -rf /var/tmp/invoke*.log
  echo
  echo "testing distributed op $op"
  run_one_cmd "$common_params --host-set $localhost_name --stonewall Y --pause 4000 --operation $op"
done

# we do these tests for virtualization (many KVM guests or containers, shared storage but no shared fs)

echo "******* testing distributed operation with a host-local fs"

for op in `supported_ops $xattrs ''` ; do
  rm -rf /var/tmp/invoke*.log
  rm -rf $nfsdir/sync
  echo
  echo "testing remote-but-local op $op"
  run_one_cmd "$common_params --top $testdir --network-sync-dir $nfsdir/sync --host-set $localhost_name --operation $op"
done

echo "*** run one long test of creates and reads ***"

xattrs=$save_xattrs
for op in create read cleanup ; do
  rm -rf /var/tmp/invoke*.log
  run_one_cmd "$common_params --top $testdir --files 200000 --file-size 4 --record-size 4 --files-per-dir 3 --dirs-per-dir 2 --threads 10 --stonewall Y --pause 1000"
done

$GREP $nfsdir /proc/mounts
if [ $? == $OK ] ; then
  sudo umount -v $nfsdir
  sudo rm -rf $nfsdir
fi
sudo rm -rf $testdir
sudo exportfs -uav
sudo systemctl stop nfs
sudo systemctl stop sshd
