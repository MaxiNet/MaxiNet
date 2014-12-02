#!/usr/bin/python2

#
# Minimal example showing how to use MaxiNet with static mapping
#

import sys
import time

from MaxiNet.Frontend import maxinet
from MaxiNet.Frontend.tools import FatTree

topo = FatTree(4, 10, 0.1)

mapping = {"h1": 1,
           "h2": 1,
           "h3": 2,
           "h4": 2,
           "s1": 1,
           "s2": 1,
           "s3": 2,
           "s4": 2,
           "s5": 1,
           "s6": 2,
           "s7": 2
          }

cluster = maxinet.Cluster()
cluster.start()

exp = maxinet.Experiment(cluster, topo, nodemapping=mapping)
exp.setup()


print exp.get_node("h1").cmd("ifconfig")  # call mininet cmd function of h1
print exp.get_node("h4").cmd("ifconfig")

print "waiting 5 seconds for routing algorithms on the controller to converge"
time.sleep(5)

print exp.get_node("h1").cmd("ping -c 5 10.0.0.4")

exp.stop()
