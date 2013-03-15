#!/bin/bash
# smallfile regression test

localhost_name="$1"
if [ -z "$localhost_name" ] ; then localhost_name="`hostname -s`" ; fi

testdir='/var/tmp/smfregtest'

OK=0
NOTOK=1

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
  rm -rf /var/tmp/invoke*.log $testdir
  mkdir $testdir
}

# run the smallfile.py module's unit test

echo "running smallfile.py unit test"
python smallfile.py
assertok $?

# run the invoke_process.py unit test
echo "running invoke_process.py unit test"
python invoke_process.py
assertok $?

# test parsing

echo "testing parsing"
s="./smallfile_cli.py --top $testdir "
f=smfregtest.log
cleanup
$s --files 0 > $f
assertfail $?
grep 'non-negative' $f
assertok $?

cleanup
$s --threads 0 > $f
assertfail $?
grep 'non-negative' $f
assertok $?

$s --files -1 > $f
assertfail $?
$s --record-size -1 > $f
assertfail $?
$s --file-size -1 > $f
assertfail $?
$s --files-per-dir 0 > $f
assertfail $?
$s --dirs-per-dir 0 > $f
assertfail $?
$s --record-size -1  > $f
assertfail $?
$s --record-size a > $f
assertfail $?
$s --top / > $f
assertfail $?
$s --response-times foo > $f
assertfail $?
$s --stonewall foo > $f
assertfail $?
$s --finish foo > $f
assertfail $?

# run a command with all CLI options and verify that they were successfully parsed

cleanup
$s --verify-read N --response-times Y --finish N --stonewall N --permute-host-dirs Y --top $testdir --same-dir Y --operation cleanup --threads 5 --files 20 --files-per-dir 5 --dirs-per-dir 3 --record-size 6 --file-size 30 --file-size-distribution exponential --prefix a --suffix b --hash-into-dirs Y --pause 5 --host-set $localhost_name | tee $f
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
        "top test directory(s) : \['$testdir'\]" \
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
  echo "expecting: $expected_str"
  grep "$expected_str" $f
  assertok $?
done

pass1="$s --files 1000 --files-per-dir 20 --dirs-per-dir 3 --threads 4 --file-size 4 --record-size 16 --file-size 32  --response-times N --pause 1000"

allops="cleanup create append read chmod stat setxattr getxattr symlink mkdir rmdir rename delete-renamed swift-put swift-get cleanup"

echo "******** testing non-distributed operations"
for op in $allops ; do
  rm -rf /var/tmp/invoke*.log
  $pass1 --operation $op
  assertok $?
done

echo "******** testing distributed operations"
pass1="$pass1 --host-set $localhost_name"
for op in $allops ; do
  rm -rf /var/tmp/invoke*.log
  $pass1 --operation $op
  assertok $?
done

rm -rf $testdir

