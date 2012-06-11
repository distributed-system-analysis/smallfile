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
}

# test parsing

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
#$s --verify-read N --response-times Y --finish N --same-dir Y --pause 100 --operation cleanup --threads 5 --files 20 --files-per-dir 5 --dirs-per-dir 3 --record-size 6 --file-size 30 --host-set $localhost_name > $f
$s --verify-read N --response-times Y --finish N --same-dir Y --pause 100 --operation cleanup --threads 5 --files 20 --files-per-dir 5 --dirs-per-dir 3 --record-size 6 --file-size 30 --host-set $localhost_name > $f
assertok $?
expect_strs=( 'verify read? : N' \
        'response times? : Y' \
        'finish all requests? : N' \
        'files in same directory? : Y' \
        'pause between files (microsec) : 100' \
        "top test directory : $testdir" \
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
  expected_str=${expect_strs[$k]}
  grep "$expected_str" $f
  assertok $?
done

pass1="$s --files 1000 --files-per-dir 20 --dirs-per-dir 3 --threads 4 --file-size 4 --record-size 16 --file-size 32  --response-times N --pause 1000"

allops="cleanup create append read chmod stat setxattr getxattr symlink mkdir rmdir rename delete-renamed cleanup"

for op in $allops ; do
  rm -rf /var/tmp/invoke*.log
  $pass1 --operation $op
  assertok $?
done

pass1="$pass1 --host-set $localhost_name"
for op in $allops ; do
  rm -rf /var/tmp/invoke*.log
  $pass1 --operation $op
  assertok $?
done

rm -rf $testdir

