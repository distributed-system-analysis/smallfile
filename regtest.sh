#!/bin/bash
# smallfile regression test
#
# NOTE: this expects you to have /var/tmp in a filesystem that supports extended attributes
# and it expects NFS to support extended attributes
#
# you can set the environment variable PYTHON_PROG to switch between python3 and python2
# for example: # PYTHON_PROG=python3 bash regtest.sh
# python3 at present doesn't seem to support xattr module so some smallfile operations
# are not yet supported under python3, the regression test knows how to deal with that.
#
# you can have it use a directory in a tmpfs mountpoint, this is recommended so as not to wear out laptop drive.
# by default, Fedora 17 has /run tmpfs mountpoint with sufficient space so this is default, but TMPDIR overrides
#
# we don't use "tee" program to display results as they are happening because this erases any failure status code
# returned by smallfile, and this status code is vital to regression test.  
# Instead we log all smallfile output to smfregtest.log where it can be analyzed later  if failure occurs
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

# make sure sshd is running on this node

is_systemctl=1
which systemctl
if [ $? != $OK ] ; then  # chances are it's pre-systemctl Linux distro, use "service" instead
  ssh localhost pwd || sudo service sshd start
  is_systemctl=0
else
  ssh localhost pwd || sudo systemctl start sshd
fi

# set up NFS mountpoint

cleanup
$GREP $nfsdir /proc/mounts
if [ $? != $OK ] ; then
  sudo mkdir -pv $nfsdir
  sudo chown $USER $nfsdir
  sudo rm -rf $testdir
  sudo mkdir -p $testdir
  sudo chown $USER $testdir
  if [ $is_systemctl -eq 1 ] ; then
    sudo systemctl start nfs-server
  else
    sudo service nfs restart
  fi
  if [ $? != $OK ] ; then 
    echo "NFS service startup failed!"
    exit $NOTOK
  fi
  sudo exportfs -v -o rw,no_root_squash,sync,fsid=15 localhost:$testdir
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
$scmd --verify-read N --response-times Y --finish N --stonewall N --permute-host-dirs Y --same-dir Y --operation cleanup --threads 5 --files 20 --files-per-dir 5 --dirs-per-dir 3 --record-size 6 --file-size 30 --file-size-distribution exponential --prefix a --suffix b --hash-into-dirs Y --pause 5 --host-set $localhost_name >> $f
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
        'record size (KB) : 6' \
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

common_params="--files 100 --files-per-dir 5 --dirs-per-dir 2 --threads 4 --file-size 4 --record-size 16 --file-size 32  --response-times N --xattr-count 9 --xattr-size 253 "

python2_only_ops="setxattr getxattr swift-put swift-get"
if [ "$PYTHON" = "python3" -o "$PYTHON" = "pypy" ] ; then
  python2_only_ops=''
fi

allops=\
"cleanup create append read readdir ls-l chmod stat $python2_only_ops symlink mkdir rmdir rename delete-renamed "

allops_noxattrs=\
"cleanup create append read readdir ls-l chmod stat symlink mkdir rmdir rename delete-renamed "

# with NFS or tmpfs, any operation using extended attributes is not supported
nfs_allops="$allops_noxattrs"
local_allops="$allops"
if [ $xattrs = 0 ] ; then
  local_allops="$allops_noxattrs"
fi
# for debug: allops="create cleanup"

echo "******** testing non-distributed operations"
scmd="$PYTHON smallfile_cli.py --top $testdir "
for op in $local_allops ; do
  rm -rf /var/tmp/invoke*.log
  echo "testing local op $op"
  $scmd $common_params --top $testdir --stonewall N --operation $op >> $f
  assertok $?
done

echo "******** testing distributed operations"
mkdir -pv $nfsdir/smf
scmd="$PYTHON smallfile_cli.py --top $nfsdir/smf "
for op in $nfs_allops ; do
  rm -rf /var/tmp/invoke*.log
  echo "testing distributed op $op"
  $scmd $common_params --top $nfsdir/smf --host-set $localhost_name --pause 4000 --operation $op >> $f
  assertok $?
done

echo "******* testing distributed operation with a host-local fs"

scmd="$PYTHON smallfile_cli.py --top $testdir --network-sync-dir $nfsdir/sync "
for op in $local_allops ; do
  rm -rf /var/tmp/invoke*.log
  rm -rf $nfsdir/sync
  echo "testing remote-but-local op $op"
  $scmd $common_params --host-set $localhost_name --stonewall N --operation $op >> $f
  assertok $?
done

$GREP $nfsdir /proc/mounts
if [ $? == $OK ] ; then
  sudo umount -v $nfsdir
fi
sudo rm -rf $testdir

