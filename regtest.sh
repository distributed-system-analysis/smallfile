#!/bin/bash
# smallfile regression test
# NOTE: this expects you to have /var/tmp in a filesystem that supports extended attributes
# and it expects NFS to support extended attributes

localhost_name="$1"
if [ -z "$localhost_name" ] ; then localhost_name="localhost" ; fi

testdir='$TMPDIR/smfregtest'
if [ "$TMPDIR" = "" ] ; then
  testdir='/var/tmp/smfregtest'
fi
nfsdir=/var/tmp/smfnfs
OK=0
NOTOK=1
GREP="grep -q "

assertfail() {
  status=$1
  if [ $status == $OK ] ; then
    echo "ERROR: unexpected success status $status"
    exit $NOTOK
  fi
}

assertok() {
  status=$1
  if [ $status != $OK ] ; then
    echo "ERROR: unexpected failure status $status"
    exit $NOTOK
  fi
}

cleanup() {
  rm -rf /var/tmp/invoke*.log $testdir/*
  mkdir -p $testdir
}


# set up NFS mountpoint

$GREP $nfsdir /proc/mounts
if [ $? != $OK ] ; then
  mkdir -pv $nfsdir
  rm -rf $testdir
  mkdir -p $testdir
  sudo service nfs restart
  if [ $? != $OK ] ; then 
    echo "NFS service startup failed!"
    exit $NOTOK
  fi
  sudo exportfs -v -o rw,no_root_squash,sync localhost:$testdir
  sudo mount -v -t nfs -o actimeo=1 $localhost_name:$testdir $nfsdir
  if [ $? != $OK ] ; then 
    echo "NFS mount failed!"
    exit $NOTOK
  fi
fi

# run the smallfile.py module's unit test

echo "running smallfile.py unit test"
python smallfile.py
assertok $?

# run the invoke_process.py unit test

echo "running invoke_process.py unit test"
python invoke_process.py
assertok $?

# run drop_buffer_cache.py unit test

echo "running drop_buffer_cache.py unit test"
python drop_buffer_cache.py
assertok $?

# test parsing

echo "testing parsing"
scmd="./smallfile_cli.py --top $testdir "
f=smfregtest.log
cleanup
$scmd --files 0 > $f
assertfail $?
$GREP 'non-negative' $f
assertok $?

cleanup
$scmd --threads 0 > $f
assertfail $?
$GREP 'non-negative' $f
assertok $?

$scmd --files -1 > $f
assertfail $?
$scmd --record-size -1 > $f
assertfail $?
$scmd --file-size -1 > $f
assertfail $?
$scmd --files-per-dir 0 > $f
assertfail $?
$scmd --dirs-per-dir 0 > $f
assertfail $?
$scmd --record-size -1  > $f
assertfail $?
$scmd --record-size a > $f
assertfail $?
$scmd --top / > $f
assertfail $?
$scmd --response-times foo > $f
assertfail $?
$scmd --stonewall foo > $f
assertfail $?
$scmd --finish foo > $f
assertfail $?

# run a command with all CLI options and verify that they were successfully parsed

cleanup
mkdir -p $nfsdir/smf
$scmd --verify-read N --response-times Y --finish N --stonewall N --permute-host-dirs Y --top $nfsdir/smf --same-dir Y --operation cleanup --threads 5 --files 20 --files-per-dir 5 --dirs-per-dir 3 --record-size 6 --file-size 30 --file-size-distribution exponential --prefix a --suffix b --hash-into-dirs Y --pause 5 --host-set $localhost_name | tee $f
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
  assertok $s
done

common_params="$scmd --files 100 --files-per-dir 5 --dirs-per-dir 2 --threads 4 --file-size 4 --record-size 16 --file-size 32  --response-times N --pause 1000 --xattr-count 9 --xattr-size 253"

allops=\
"cleanup create append read readdir ls-l chmod stat setxattr getxattr symlink mkdir rmdir rename delete-renamed swift-put swift-get "

# with NFS, any operation using extended attributes is not supported
nfs_allops=\
"cleanup create append read readdir ls-l chmod stat symlink mkdir rmdir rename delete-renamed "

# for debug: allops="create cleanup"

echo "******** testing non-distributed operations"
for op in $allops ; do
  rm -rf /var/tmp/invoke*.log
  $common_params --top $testdir --operation $op
  assertok $?
done

echo "******** testing distributed operations"
for op in $nfs_allops ; do
  rm -rf /var/tmp/invoke*.log
  $common_params --top $nfsdir/smf --host-set $localhost_name --operation $op
  assertok $?
done

$GREP $nfsdir /proc/mounts
if [ $? == $OK ] ; then
  sudo umount -v $nfsdir
fi
rm -rf $testdir

