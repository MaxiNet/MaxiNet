#!/usr/bin/python2

#
# This example shows how to sync files between workers and the frontend.
# At first, we create a file on the worker and rsync it to the frontend.
# Then, we rsync the same file back from the frontend to the worker
# Afterwards, we compare both files on the worker to confirm that the
# operation was successful.
# This method should be used for huge files, for faster startup.
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

testfile = "/tmp/testfile1"
w3.run_cmd("dd if=/dev/urandom of=%s bs=1024 count=2048" % testfile)
w3.sync_get_file(testfile, testfile)

print(w3.run_cmd("md5sum %s" % testfile).strip())
# compare files
print(subprocess.check_output(["md5sum", testfile]).strip())

time.sleep(2)

exp.stop()  # stop experiment