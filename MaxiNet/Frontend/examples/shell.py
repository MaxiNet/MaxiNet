#!/usr/bin/python2

#
# This example shows how to use MaxiNet's CommandLineInterface (CLI).
# Using the CLI, commands can be run interactively at emulated hosts. Thanks to our build-in py command you can even dynamically change the topology.
#

import sys
sys.path.append("..")
from MaxiNet.Frontend import maxinet
import time
from fatTree import FatTree

topo = FatTree(4,10,0.1)
cluster = maxinet.Cluster()
cluster.start()

exp = maxinet.Experiment(cluster, topo)
exp.setup()

exp.CLI(locals(),globals())


exp.stop()
