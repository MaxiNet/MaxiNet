#!/usr/bin/python2

#
# For performance monitoring, MaxiNet has build-in functions to log
# CPU-, memory-, and network usage of the workers.
# By calling the monitor() function of an experiment object the workers
# are monitored.
# All data is stored on the Frontend under /tmp/maxinet_logs/ and can
# be plotted using the maxinet_plot.py script.
#

import time

from MaxiNet.Frontend import maxinet
from MaxiNet.tools import FatTree


topo = FatTree(4, 10, 0.1)
cluster = maxinet.Cluster()

exp = maxinet.Experiment(cluster, topo)
exp.setup()

exp.monitor()  # start monitoring

time.sleep(5)
print exp.get_node("h4").cmd("iperf -s &")  # open iperf server on h4
# generate traffic between h1 and h4
print exp.get_node("h1").cmd("iperf -c 10.0.0.4")
time.sleep(2)
exp.stop()

# we dont call maxinet_plot.py here. Run it from the console at the
# frontend after this script has been executed.
