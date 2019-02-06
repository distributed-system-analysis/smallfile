FROM docker.io/centos:7
MAINTAINER Ben England <bengland@redhat.com>
RUN yum install -y python git
RUN git clone https://github.com/distributed-system-analysis/smallfile
RUN ln -sv /smallfile/smallfile_remote.py /usr/local/bin
COPY launch.sh /
CMD /launch.sh
