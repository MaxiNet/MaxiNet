#!/usr/bin/python2

#
# Dynamically remove a link from the topology.
# We dynamically remove a link from the topology using the configLinkStatus
# function.
#

import time

from MaxiNet.Frontend import maxinet
from MaxiNet.tools import FatTree


topo = FatTree(4, 10, 0.1)
cluster = maxinet.Cluster()

exp = maxinet.Experiment(cluster, topo)
exp.setup()

print "waiting 5 seconds for routing algorithms on the controller to converge"
time.sleep(5)

print exp.get_node("h1").cmd("ping -c 5 10.0.0.4")  # check connectivity

raw_input("[Continue]")
print "shutting down link..."

exp.configLinkStatus("s5", "s7", "down")

print exp.get_node("h1").cmd("ping -c 5 10.0.0.4")  # check connectivity
raw_input("[Continue]")

print "reestablishing link..."
exp.configLinkStatus("s5", "s7", "up")

print exp.get_node("h1").cmd("ping -c 5 10.0.0.4")  # check connectivity

raw_input("[Continue]")
exp.stop()
