To run this example, first build a container image.  First I created a "fedora-basic" container image with python2 
and git packages pre-installed.   I tagged it bengland2/fedora:28 and that is what the smallfile container Docker file expects.
Next I built the smallfile image using

    # docker build smallfile
    # docker tag <image> bengland/smallfile:20190115

Tag it however you want.  This is the image consumed by the run script.  To run the containers, 
just edit the parameters at the top of run-smallfile-client-tests.sh as needed and then:

    # ./run-smallfile-client-tests <your-smallfile-dir> bengland/smallfile:20190115

This should put all its output in the *logs* subdir.  You can set the KEEP_OLD_CONTAINERS environment variables to re-use existing containers,
and you can set the LEAVE_CONTAINERS_RUNNING environment variable to leave the containers 
running when the script exits so that you can run your own smallfile commands or debug any problems with the containers.
