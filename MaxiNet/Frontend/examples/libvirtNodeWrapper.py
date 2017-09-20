#!/usr/bin/env python2
""" An example showing all available methods and attributes of the NodeWrapper for Docker hosts.
"""

from MaxiNet.Frontend import maxinet
from MaxiNet.Frontend.libvirt import LibvirtHost
from mininet.topo import Topo
from mininet.node import OVSSwitch

topo = Topo()
vm1 = topo.addHost("vm1", cls=LibvirtHost, ip="10.0.0.251", disk_image="/srv/images/ubuntu16.04.qcow2")

cluster = maxinet.Cluster()
exp = maxinet.Experiment(cluster, topo, switch=OVSSwitch)
exp.setup()

try:
    node_wrapper = exp.get_node("vm1")

    print("Testing methods:")
    print("=================")
    print("updateCpuLimit():")
    print("\t" + str(node_wrapper.updateCpuLimit(10000, 10000, 1, {0: "1", 1: "0"})))  # cpu_quota, cpu_period, cpu_shares, cores

    print("updateMemoryLimit():")
    print("\t" + str(node_wrapper.updateMemoryLimit(500)))

    print("")
    print("Testing attributes:")
    print("====================")
    print("dimage = " + str(node_wrapper.disk_image))
    print("resources = " + str(node_wrapper.resources))

finally:
    exp.stop()
