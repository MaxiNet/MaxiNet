#!/usr/bin/python2

#
# This example shows how to transfer files between workers and the frontend.
# At first, we create a file on the worker and copy it to the frontend.
# Then, we copy the same file back from the frontend to the worker
# (using a different name).
# Afterwards, we compare both files on the worker to confirm that the
# operation was successful.
#

import subprocess
import time

from MaxiNet.Frontend import maxinet
from MaxiNet.tools import FatTree


topo = FatTree(4, 10, 0.1)

# start maxinet cluster
cluster = maxinet.Cluster()

# create experiment on cluster with FatTree topology
exp = maxinet.Experiment(cluster, topo)
exp.setup()
time.sleep(2)

h3 = exp.get_node("h3")  # get node object "h3"
w3 = exp.get_worker("h3")  # get worker-machine running node "h3"
# create file on worker machine
w3.run_cmd("dd if=/dev/urandom of=/tmp/testfile1 bs=1024 count=1024")
# get_file transfers a file from the file system of a worker to the file
# system of the frontend
w3.get_file("/tmp/testfile1", "/tmp/")
# put_file transfers a file from file system of the frontend to the file
# system of the worker
w3.put_file("/tmp/testfile1", "/tmp/testfile2")

print w3.run_cmd("md5sum /tmp/testfile1").strip()
print w3.run_cmd("md5sum /tmp/testfile2").strip()
# compare files
print subprocess.check_output(["md5sum", "/tmp/testfile1"]).strip()

w3.run_cmd("rm /tmp/testfile1")  # remove file from worker
w3.run_cmd("rm /tmp/testfile2")  # remove file from worker
subprocess.call(["rm", "/tmp/testfile1"])  # remove file from the frontend
time.sleep(2)

exp.stop()  # stop experiment
