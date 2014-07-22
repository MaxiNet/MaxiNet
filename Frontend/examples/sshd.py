#!/usr/bin/python2

#
# Start sshd on the emulated hosts and create a specialized host emulated at the Frontend which tunnels ssh 
# from the Frontend to the emulated hosts.
#

import sys
sys.path.append("..")
import maxinet,subprocess
from mininet.topo import Topo
from mininet.node import OVSSwitch
topo = Topo()

topo.addSwitch("s1")
topo.addSwitch("s2")
topo.addHost("h1",ip=maxinet.Tools.makeIP(1), mac=maxinet.Tools.makeMAC(1))
topo.addHost("h2",ip=maxinet.Tools.makeIP(2), mac=maxinet.Tools.makeMAC(2))
topo.addLink("h1","s1")
topo.addLink("s1","s2")
topo.addLink("h2","s2")

cluster = maxinet.Cluster()
cluster.start()
# we need to add the root node after the simulation has started as we do not know
# which worker id the frontend machine will get. Therefore we need a dynamic
# topology which is only supported in openvswitch
exp = maxinet.Experiment(cluster, topo, switch=OVSSwitch)
exp.setup()

# Start ssh servers
h1=exp.get("h1")
h1.cmd("echo \"Welcome to %s at %s\n\" > /tmp/%s.banner" % (h1.name, h1.IP(), h1.name))
h1.cmd("/usr/sbin/sshd -o UseDNS=no -u0 -o \"Banner /tmp/%s.banner\"" % h1.name)

h2=exp.get("h2")
h2.cmd("echo \"Welcome to %s at %s\n\" > /tmp/%s.banner" % (h2.name, h2.IP(), h2.name))
h2.cmd("/usr/sbin/sshd -o UseDNS=no -u0 -o \"Banner /tmp/%s.banner\"" % h2.name)

# Locate worker which runs on Frontend
for w in cluster.workers():
    if w.run_cmd("hostname")==subprocess.check_output(["hostname"]):
        wid=w.wid
# Add host and switch on Frontend worker.
# Switch is needed as tunnels are only possible between switches
exp.addHost("root",inNamespace=False,wid=wid)
exp.addSwitch("s3",wid=wid)
exp.addLink("s3","root", autoconf=True) # adding Links to Switches is cumbersome in mininet. We let autoconf do it for us.
exp.addLink("s3","s1", autoconf=True)
exp.get("root").setIP("10.0.0.3",8) # The interface of the root node gets created when link is created. Therefore we cannot set the IP before.

print "*** You may now ssh into", h1.name, "at", h1.IP(), "or", h2.name, "at", h2.IP()
print "Press [Enter] to end MaxiNet"
raw_input()
exp.stop()
