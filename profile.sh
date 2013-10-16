#!/bin/bash -x
#
# script to run python profile module to profile some smallfile workloads
#
top=/run/ben/smfprofile
if [ ! -d $top ] ; then
  python ./smallfile_cli.py --top $top --threads 1 --files 100000 --file-size 1 --operation cleanup
  python ./smallfile_cli.py --top $top --threads 1 --files 100000 --file-size 1 --operation create
fi
touch $top/network_shared/starting_gate
OPNAME=read COUNT=100000 TOP=$top python <<EOF > read-profile.log
import profile
profile.run('import profile_workload', 'profile.tmp')
import pstats
p = pstats.Stats('profile.tmp')
p.sort_stats('cumulative').print_stats()
EOF
OPNAME=append COUNT=100000 TOP=$top python <<EOF > append-profile.log
import profile
profile.run('import profile_workload', 'profile.tmp')
import pstats
p = pstats.Stats('profile.tmp')
p.sort_stats('cumulative').print_stats()
EOF
