To run this example, first build a container image using:

    # docker build smallfile

Tag it however you want.  This is the image consumed by the run script.  To run the containers, 
just edit the parameters at the top of **run-smallfile-client-tests.sh** if needed and then:

    # ./run-smallfile-client-tests <your-smallfile-dir> <your-image>

This should put all its output in the **logs** subdir.  

You can set the **KEEP__OLD__CONTAINERS** environment variables to re-use existing containers,
and you can set the **LEAVE__CONTAINERS__RUNNING** environment variable to leave the containers 
running when the script exits so that you can run your own smallfile commands or debug any problems with the containers.
