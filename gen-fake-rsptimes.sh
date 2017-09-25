#!/bin/bash
# script to generate artificial response time files for regression test

dir=`dirname $0`
if [ -z "$dir" ] ; then
	dir='.'
fi
RSPTIMES_POSTPROCESSOR=$dir/smallfile_rsptimes_stats.py
rspdir=/tmp/$$.tmp
rm -rf $rspdir
mkdir $rspdir
start=0 
for n in `seq 1 40` ; do 
	(( start = $start + $n )) 
	for t in `seq -f "%02g" 1 4` ; do 
		for h in host-21.foo.com host-22.foo.com ; do 
			echo some-operation,$start,$n >> \
			  $rspdir/rsptimes_${t}_${h}_op-name_`date +%s.00`.csv
		done
	done
done
$RSPTIMES_POSTPROCESSOR --common-hostname-suffix foo.com $rspdir
