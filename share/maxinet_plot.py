#!/usr/bin/python2

import os
import subprocess
import sys

import matplotlib as mpl
import numpy as np


try:
    subprocess.check_output("env | grep DISPLAY", shell=True)
except:
    mpl.use("Agg")

import matplotlib.pyplot as plt

#framealpha is only availabe for matplotlib version >= 1.2.0
oldversion = False
if(int(mpl.__version__.split(".")[0]) <= 1 and
        int(mpl.__version__.split(".")[1]) < 2):
    oldversion = True

if(not len(sys.argv) in [2, 3]):
    print "ERROR: Invalid number of parameters.\nSyntax: " + sys.argv[0] +\
          " LOGFILE_FOLDER [IMAGE_FILENAME] "
    sys.exit(1)

folder = sys.argv[1]
intflogs = []
memlogs = []
cpulogs = []
for filename in os.listdir(folder):
    if filename[:13] == "maxinet_intf_":
        intflogs.append(filename)
    elif filename[:12] == "maxinet_mem_":
        memlogs.append(filename)
    elif filename[:12] == "maxinet_cpu_":
        cpulogs.append(filename)
    else:
        print "unknown file: " + filename

numworkers = len(memlogs)

graph = 0
# CPU
fig, ax = plt.subplots(2 + numworkers, sharex=True)
fig.set_size_inches(8.3, 1.5 * numworkers + 5)
for filename in cpulogs:
    sfilename = filename.split("_")
    workerID = sfilename[2]
    workerHN = sfilename[3][1:-5]
    axis_x = []
    axis_y = []
    for line in open(os.path.join(folder, filename)):
        line = line.split()
        if("all" in line):
            timestamp = int(line[0])
            idle = float(line[-1])
            used = 100 - idle
            axis_x.append(timestamp)
            axis_y.append(used)
    ax[graph].plot(axis_x, axis_y, label=workerHN)
print ax[graph]
xmin, xmax = map(lambda x: int(x), ax[graph].get_xaxis().get_data_interval())
xticks = range(xmin, xmax)[0::10]
xlabels = map(lambda x: x - xmin, xticks)
ax[graph].get_xaxis().set_ticks(xticks)
ax[graph].get_xaxis().set_ticklabels(xlabels)
ax[graph].set_ylabel("CPU utilization [%]")
if oldversion:
    ax[graph].legend(loc="best")
else:
    ax[graph].legend(framealpha=0.5, loc="best")


#Intf
graph += 1
for filename in intflogs:
    sfilename = filename.split("_")
    workerID = sfilename[3]
    workerHN = sfilename[4][1:-5]
    axis_x = []
    axis_y_rx = []
    axis_y_tx = []
    for line in open(os.path.join(folder, filename)):
        line = line.split(",")
        timestamp = int(line[0])
        rx_bytes = int(line[1])
        tx_bytes = int(line[2])
        axis_x.append(timestamp)
        axis_y_rx.append((rx_bytes / 1000000.0) * 8.0)
        axis_y_tx.append((tx_bytes / 1000000.0) * 8.0)
    ax[graph].plot(axis_x, axis_y_rx, label=workerHN + " RX")
    ax[graph].plot(axis_x, axis_y_tx, label=workerHN + " TX")
ax[graph].set_ylabel("Data rate [Mbit/s]")
if oldversion:
    ax[graph].legend(loc="best")
else:
    ax[graph].legend(framealpha=0.5, loc="best")


#Mem
for filename in memlogs:
    graph += 1
    sfilename = filename.split("_")
    workerID = sfilename[2]
    workerHN = sfilename[3][1:-5]
    axis_x = []
    axis_y_free = []
    axis_y_buffers = []
    axis_y_cached = []
    for line in open(os.path.join(folder, filename)):
        line = line.split(",")
        timestamp = line[0]
        free = int(line[1])
        buffers = int(line[2])
        cached = int(line[3])
        axis_x.append(int(timestamp))
        axis_y_free.append(free / 1024.0)
        axis_y_buffers.append(buffers / 1024.0)
        axis_y_cached.append(cached / 1024.0)
    axis_y = np.row_stack((axis_y_free, axis_y_buffers, axis_y_cached))
    axis_y_stack = np.cumsum(axis_y, axis=0)
    print axis_y_stack
    axis_x = np.array(axis_x)
    print axis_x
    ax[graph].fill_between(axis_x, 0, axis_y_stack[0, :], facecolor="#CC6666")
    ax[graph].fill_between(axis_x, axis_y_stack[0, :], axis_y_stack[1, :],
                           facecolor="#1DACD6")
    ax[graph].fill_between(axis_x, axis_y_stack[1, :], axis_y_stack[2, :],
                           facecolor="#6E5160")
    ax[graph].set_ylabel("Memory [MB]")
    ax[graph].set_ylim(bottom=0)
    if(graph == numworkers + 1):
        ax[graph].set_xlabel("Time [s]")
    if oldversion:
        ax[graph].legend([mpl.patches.Rectangle((0, 0), 1, 1, fc="#CC6666"),
                          mpl.patches.Rectangle((0, 0), 1, 1, fc="#1DACD6"),
                          mpl.patches.Rectangle((0, 0), 1, 1, fc="#6E5160")
                         ],
                         ["MemFree", "Buffers", "Cached"], loc="best")
    else:
        ax[graph].legend([mpl.patches.Rectangle((0, 0), 1, 1, fc="#CC6666"),
                          mpl.patches.Rectangle((0, 0), 1, 1, fc="#1DACD6"),
                          mpl.patches.Rectangle((0, 0), 1, 1, fc="#6E5160")
                         ],
                         ["MemFree", "Buffers", "Cached"], framealpha=0.5,
                         loc="best")


if(len(sys.argv) == 3):
    plt.savefig(sys.argv[2])
try:
    plt.show()
except:
    pass  # Fail silently if no x is avaiable
