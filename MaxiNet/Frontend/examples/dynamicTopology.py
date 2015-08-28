#!/usr/bin/python2

#
# This example shows how to dynamically add hosts and switches to a
# running emulation.
# Due to technical limitations it is NOT possible to create a link
# between a switch and a host if these are emulated at DIFFERENT workers
# This limitation does (of course) NOT hold for links between switches.
#
# Dynamic adding and removing of nodes also does not work when using the
# UserSwitch.


import time

from mininet.topo import Topo
from mininet.node import OVSSwitch

from MaxiNet.Frontend import maxinet
from MaxiNet.tools import Tools


# create topology
topo = Topo()
topo.addHost("h1", ip=Tools.makeIP(1), mac=Tools.makeMAC(1))
topo.addHost("h2", ip=Tools.makeIP(2), mac=Tools.makeMAC(2))
topo.addSwitch("s1", dpid=Tools.makeDPID(1))
topo.addLink("h1", "s1")
topo.addLink("h2", "s1")

# start cluster
cluster = maxinet.Cluster(minWorkers=2, maxWorkers=2)

# start experiment with OVSSwitch on cluster
exp = maxinet.Experiment(cluster, topo, switch=OVSSwitch)
exp.setup()

print "waiting 5 seconds for routing algorithms on the controller to converge"
time.sleep(5)

print "pinging h2 from h1 to check network connectivity..."
print exp.get_node("h1").cmd("ping -c 5 10.0.0.2")  # show network connectivity

raw_input("[Continue]")  # wait for user to acknowledge network connectivity
print "adding switch on second worker..."
# Enforce placement of s2 on Worker 2. Otherwise random worker would be chosen
exp.addSwitch("s2", dpid=Tools.makeDPID(2), wid=1)
print "adding hosts h3 and h4 on second worker..."
# Enforce placement of h3 on worker of s2.
# Remember: we cannot have tunnels between hosts and switches
exp.addHost("h3", ip=Tools.makeIP(3), max=Tools.makeMAC(3), pos="s2")
exp.addHost("h4", ip=Tools.makeIP(4), max=Tools.makeMAC(4), pos="s2")
# autoconf parameter configures link-attachment etc for us
exp.addLink("s1", "s2", autoconf=True)
exp.addLink("h3", "s2", autoconf=True)
exp.addLink("h4", "s2", autoconf=True)
time.sleep(2)

print "pinging h4 and h1 from h3 to check connectivity of new host..."
# show network connectivity of new hosts
print exp.get("h3").cmd("ping -c5 10.0.0.4")
print exp.get("h3").cmd("ping -c5 10.0.0.1")
raw_input("[Done]")
exp.stop()
