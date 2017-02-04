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

node_wrapper = exp.get_node("d1")

print("Testing methods:")
print("=================")
print("updateCpuLimit():")
print("\t" + str(node_wrapper.updateCpuLimit(10000, 10000, 1, "0-1")))

print("updateMemoryLimit():")
print("\t" + str(node_wrapper.updateMemoryLimit(300000)))

print("cgroupGet():")
print("\t" + str(node_wrapper.cgroupGet('cpus', resource='cpuset')))

print("_check_image_exists():")
print("\t" + str(node_wrapper._check_image_exists("ubuntu:trusty", "false")))

print("_image_exists():")
print("\t" + str(node_wrapper._image_exists("ubuntu", "trusty")))

print("_pull_image():")
print("\t" + str(node_wrapper._pull_image("ubuntu", "trusty")))

print("")
print("Testing attributes:")
print("====================")
print("dimage = " + str(node_wrapper.dimage))
print("cpu_quota = " + str(node_wrapper.cpu_quota))
print("cpu_period = " + str(node_wrapper.cpu_period))
print("cpu_shares = " + str(node_wrapper.cpu_shares))
print("cpuset = " + str(node_wrapper.cpuset))
print("mem_limit = " + str(node_wrapper.mem_limit))
print("memswap_limit = " + str(node_wrapper.memswap_limit))
print("volumes = " + str(node_wrapper.volumes))

exp.stop()
