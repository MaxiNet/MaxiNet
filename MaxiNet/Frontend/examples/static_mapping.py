#!/usr/bin/python2

#
# Minimal example showing how to use MaxiNet with static mapping of nodes to workers
#

import time

from MaxiNet.Frontend import maxinet
from MaxiNet.tools import FatTree

topo = FatTree(4, 10, 0.1)

mapping = {"h1": 0,
           "h2": 0,
           "h3": 1,
           "h4": 1,
           "s1": 0,
           "s2": 0,
           "s3": 1,
           "s4": 1,
           "s5": 0,
           "s6": 1,
           "s7": 1
          }

cluster = maxinet.Cluster(minWorkers=2,maxWorkers=2)

exp = maxinet.Experiment(cluster, topo, nodemapping=mapping)
exp.setup()


print exp.get_node("h1").cmd("ifconfig")  # call mininet cmd function of h1
print exp.get_node("h4").cmd("ifconfig")

print "waiting 5 seconds for routing algorithms on the controller to converge"
time.sleep(5)

print exp.get_node("h1").cmd("ping -c 5 10.0.0.4")

exp.stop()
