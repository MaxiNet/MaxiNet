#!/usr/bin/env python2
""" An experiment for testing all methods in attributes available via the NodeWrapper.

Tests which methods and attributes are callable and which do produce errors.
"""

import traceback
from MaxiNet.Frontend import maxinet
from mininet.node import OVSSwitch, CPULimitedHost
from mininet.topo import Topo


def call_method(node, cmd, *params1, **params2):
    print(node.nn + "." + cmd + "()")
    ok = False
    try:
        print("\t->" + str(node._call(cmd, *params1, **params2)))
        ok = True
    except Exception as e:
        print("\tFAILED")
        traceback.print_exc()
    if ok:
        print("\tOKAY")
    print


def get_attribute(node, attribute):
    print(node.nn + "." + attribute)
    ok = False
    try:
        print("\t->" + str(node._get(attribute)))
        ok = True
    except Exception as e:
        print("\tFAILED")
        traceback.print_exc()
    if ok:
        print("\tOKAY")
    print


topo = Topo()
topo.addHost("h1", cls=CPULimitedHost, ip="10.0.0.251")
topo.addHost("h2", cls=CPULimitedHost, ip="10.0.0.252")
topo.addSwitch("s1")
topo.addLink("h1", "s1")
topo.addLink("h2", "s1")

cluster = maxinet.Cluster()
exp = maxinet.Experiment(cluster, topo, switch=OVSSwitch)
exp.setup()

h1 = exp.get_node("h1")
h2 = exp.get_node("h2")
s1 = exp.get_node("s1")

print("#######################################################################")
print("# Test Host methods")
print("#######################################################################")
call_method(h1, "IP")
call_method(h1, "MAC")
call_method(h1, "addIntf", None)  # Won't work, because of parameter type 'Intf'
call_method(h1, "cfsInfo", 1)
call_method(h1, "cgroupGet", "cfs_quota_us")
call_method(h1, "cgroupSet", "cfs_quota_us", 42)
call_method(h1, "chrt")
call_method(h1, "cmd", "echo")
call_method(h1, "cmdPrint", "echo test")
call_method(h1, "config", mac="de:ad:be:ef:00:00")
call_method(h1, "configDefault", ip="10.0.0.2")
call_method(h1, "connectionsTo", h2)
call_method(h1, "defaultIntf")
call_method(h1, "deleteIntfs")
call_method(h1, "intf")
call_method(h1, "intfIsUp")
call_method(h1, "intfNames")
call_method(h1, "newPort")
call_method(h1, "pexec", "echo test")
call_method(h1, "rtInfo", 1)
call_method(h1, "sendCmd", "/bin/echo")
call_method(h1, "sendInt")
call_method(h1, "setARP", "10.0.0.252", "de:ad:be:ef:01:01")
call_method(h1, "setCPUFrac", -1)
call_method(h1, "setCPUs", cores=[1])
call_method(h1, "setIP", "10.0.0.251", 8, "h1-eth0")
call_method(h1, "setup")
call_method(h1, "waitOutput")
call_method(h1, "waitReadable", 1)
call_method(h1, "write", "test")

# Blocking/commands with dependent calls
h1.sendCmd("/bin/echo")
call_method(h1, "read")
h1.sendCmd("/bin/echo")
call_method(h1, "readline")
h1.sendCmd("/bin/echo")
call_method(h1, "monitor", 1)

# Terminating calls
call_method(h1, "cgroupDel")
call_method(h1, "cleanup")
call_method(h1, "terminate")
call_method(h1, "stop")

print("#######################################################################")
print("# Test Host attributes")
print("#######################################################################")
get_attribute(h1, "inNamespace")
get_attribute(h1, "name")
get_attribute(h1, "nameToIntf")
get_attribute(h1, "params")
get_attribute(h1, "waiting")

print("#######################################################################")
print("# Test Switch methods")
print("#######################################################################")
call_method(s1, "attach", "eth3")
call_method(s1, "connected")
call_method(s1, "controllerUUIDs")
call_method(s1, "defaultDpid")
call_method(s1, "detach", "eth3")
call_method(s1, "dpctl", "-V")
call_method(s1, "start", [])

print("#######################################################################")
print("# Test Controller methods")
print("#######################################################################")
# Does not create a controller for some reason.
c0 = exp.addController()
call_method(c0, "checkListening")

exp.stop()
