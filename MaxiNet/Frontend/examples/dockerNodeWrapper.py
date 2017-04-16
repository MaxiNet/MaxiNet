#!/usr/bin/env python2
""" An example showing all available methods and attributes of the NodeWrapper for Docker hosts.
"""

from MaxiNet.Frontend import maxinet
from MaxiNet.Frontend.container import Docker
from mininet.topo import Topo
from mininet.node import OVSSwitch

topo = Topo()
d1 = topo.addHost("d1", cls=Docker, ip="10.0.0.251", dimage="ubuntu:trusty")

cluster = maxinet.Cluster()
exp = maxinet.Experiment(cluster, topo, switch=OVSSwitch)
exp.setup()

try:
    node_wrapper = exp.get_node("d1")

    print("Testing methods:")
    print("=================")
    print("updateCpuLimit():")
    print("\t" + str(node_wrapper.updateCpuLimit(10000, 10000, 1, "0-1")))  # cpu_quota, cpu_period, cpu_shares, cores

    print("updateMemoryLimit():")
    print("\t" + str(node_wrapper.updateMemoryLimit(300000)))

    print("cgroupGet():")
    print("\t" + str(node_wrapper.cgroupGet('cpus', resource='cpuset')))

    print("")
    print("Testing attributes:")
    print("====================")
    print("dimage = " + str(node_wrapper.dimage))
    print("resources = " + str(node_wrapper.resources))
    print("volumes = " + str(node_wrapper.volumes))

finally:
    exp.stop()
