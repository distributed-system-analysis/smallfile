#!/bin/bash -x
# this script is run by a container which should be launched 
# something like this:
#
#  #  d run -v /var/tmp/smfdocker:/var/tmp/smfdocker:z \
#         -e topdir=/var/tmp/smfdocker \
#         -e smf_launch_id=container_1 \
#          bengland/smallfile:20190115
#
# specifically you have to pass 2 environment variables:
#   topdir - points to container-local directory
#   smf_launch_id - what container name should be
#   the -v volume option just imports a directory from the
#   host with SELinux set up to allow this (:z suffix)
#
launcher=/smallfile/launch_smf_host.py
ls -l $launcher
echo "topdir: $topdir"
echo "container_id: $smf_launch_id"
ls -l $topdir
rpm -q python2
LOGLEVEL_DEBUG=1 /usr/bin/python $launcher --top ${topdir} --as-host ${smf_launch_id}
