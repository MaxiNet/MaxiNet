import atexit
from ConfigParser import RawConfigParser
import logging
import os
import random
import re
import sys
import thread
import threading
import time

import Pyro4
from mininet.topo import Topo


# Make Mininets classes import on OS X
if sys.platform == "darwin":
    class DarwinMiniNetHack:
        pass
    import select
    select.poll = DarwinMiniNetHack
    select.POLLIN = 1
    select.POLLHUP = 16


class Config:
    def __init__(self, nameserverip="127.0.0.1", nameserverport=9090,
                 register=True):
        self.userconfig = RawConfigParser()
        self.userconfig.read([os.path.expanduser("~/.MaxiNet"), ])
        if(register):
            self.nameserver = Pyro4.locateNS(nameserverip, nameserverport)
            self.nsIP = nameserverip
            self.nsPort = nameserverport
            self.last_id = 0
            self.lock = thread.allocate_lock()
            self.register()
            atexit.register(self._stop)

    def register(self):
        ownip = self.nsIP
        self.daemon = Pyro4.Daemon(ownip)
        uri = self.daemon.register(self)
        self.daemon_thread = threading.Thread(target=self.daemon.requestLoop)
        self.daemon_thread.daemon = True
        self.daemon_thread.start()
        self.nameserver.register("config", uri)

    def _stop(self):
        self.nameserver.remove("config")
        self.daemon.shutdown()
        self.daemon.close()
        self.daemon = None
        self.daemon_thread.join()
        self.daemon_thread = None

    def getIP(self, hn):
        if(self.userconfig.has_section(hn)):
            return self.userconfig.get(hn, "ip")

    def getShare(self, hn):
        if(self.userconfig.has_section(hn)):
            return self.userconfig.getint(hn, "share")

    def runWith1500MTU(self):
        return self.userconfig.getboolean("MaxiNet", "runWith1500MTU")

    def getID(self, hn):
        self.lock.acquire()
        x = 0
        # Note: User must either:
        #              * Use preconfigured ids for ALL workers
        # or           * Use no preconfigured ids AT ALL.
        if (self.userconfig.has_option(hn, "id")):
            x = self.userconfig.get(hn, "id")
        else:
            self.last_id = self.last_id + 1
            x = self.last_id
        self.lock.release()
        return x

    def getWorkerDir(self):
        return os.path.join(self.getMaxiNetBasedir(), "Worker")

    def getMaxiNetBasedir(self):
        return os.path.abspath(os.path.dirname(os.path.abspath(__file__)) +
                               os.sep + ".." + os.sep)

    def getWorkerScript(self, cmd):
        d = self.getMaxiNetBasedir()
        return os.path.join(d, "Worker", "bin", cmd)

    def getHosts(self):
        return filter(lambda x: x != "MaxiNet", self.userconfig.sections())

    def getController(self):
        return self.userconfig.get("MaxiNet", "controller")

    def debugPyroOnWorker(self):
        return self.userconfig.get("MaxiNet", "debugPyroOnWorker")

    def keepScreenOpenOnError(self):
        return self.userconfig.getboolean("MaxiNet", "keepScreenOpenOnError")

    def getLoggingLevel(self):
        lvl = self.userconfig.get("MaxiNet", "debugLevel")
        lvls = {"CRITICAL": logging.CRITICAL,
                "ERROR": logging.ERROR,
                "WARNING": logging.WARNING,
                "INFO": logging.INFO,
                "DEBUG": logging.DEBUG}
        return lvls[lvl]


#
# Fat-tree topology implemention for mininet
#
class FatTree(Topo):
    def randByte(self):
        return hex(random.randint(0, 255))[2:]

    def makeMAC(self, i):
        return self.randByte() + ":" + self.randByte() + ":" + \
               self.randByte() + ":00:00:" + hex(i)[2:]

    def makeDPID(self, i):
        a = self.makeMAC(i)
        dp = "".join(re.findall(r'[a-f0-9]+', a))
        return "0" * (12 - len(dp)) + dp

    # args is a string defining the arguments of the topology!
    # has be to format: "x,y,z" to have x hosts and a bw limit of y for
    # those hosts each and a latency of z (in ms) per hop
    def __init__(self, hosts=2, bwlimit=10, lat=0.1, **opts):
        Topo.__init__(self, **opts)
        tor = []
        numLeafes = hosts
        bw = bwlimit
        s = 1
        #bw = 10
        for i in range(numLeafes):
            h = self.addHost('h' + str(i + 1), mac=self.makeMAC(i),
                            ip="10.0.0." + str(i + 1))
            sw = self.addSwitch('s' + str(s), dpid=self.makeDPID(s),
                                **dict(listenPort=(13000 + s - 1)))
            s = s + 1
            self.addLink(h, sw, bw=bw, delay=str(lat) + "ms")
            tor.append(sw)
        toDo = tor  # nodes that have to be integrated into the tree
        while len(toDo) > 1:
            newToDo = []
            for i in range(0, len(toDo), 2):
                sw = self.addSwitch('s' + str(s), dpid=self.makeDPID(s),
                                    **dict(listenPort=(13000 + s - 1)))
                s = s + 1
                newToDo.append(sw)
                self.addLink(toDo[i], sw, bw=bw, delay=str(lat) + "ms")
                if len(toDo) > (i + 1):
                    self.addLink(toDo[i + 1], sw, bw=bw, delay=str(lat) + "ms")
            toDo = newToDo
            bw = 2.0 * bw


class Tools:

    @staticmethod
    def randByte():
        return hex(random.randint(0, 255))[2:]

    @staticmethod
    def makeMAC(i):
        return Tools.randByte() + ":" + Tools.randByte() + ":" +\
               Tools.randByte() + ":00:00:" + hex(i)[2:]

    @staticmethod
    def makeDPID(i):
        a = Tools.makeMAC(i)
        dp = "".join(re.findall(r'[a-f0-9]+', a))
        return "0" * (12 - len(dp)) + dp

    @staticmethod
    def makeIP(i):
        return "10.0.0." + str(i)

    @staticmethod
    def time_to_string(t):
        if(t):
            return time.strftime("%Y-%m-%d_%H:%M:%S", t)
        else:
            return time.strftime("%Y-%m-%d_%H:%M:%S")
