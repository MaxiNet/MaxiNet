import atexit
import os
import sys
import thread
import threading
import Pyro4
import logging
from ConfigParser import RawConfigParser

# Make Mininets classes import on OS X
if sys.platform == "darwin":
    class DarwinMiniNetHack:
        pass

    import select
    select.poll = DarwinMiniNetHack
    select.POLLIN =1
    select.POLLHUP = 16



class Config:
    def __init__(self,nameserverip="127.0.0.1",nameserverport=9090,register = True):
        self.userconfig = RawConfigParser()
        self.userconfig.read([os.path.expanduser("~/.MaxiNet"),])
        if(register):
            self.nameserver = Pyro4.locateNS(nameserverip,nameserverport)
            self.nsIP=nameserverip
            self.nsPort=nameserverport
            self.last_id=0
            self.lock = thread.allocate_lock()
            self.register()
            atexit.register(self._stop)

    def register(self):
        ownip=self.nsIP
        self.daemon = Pyro4.Daemon(ownip)
        uri = self.daemon.register(self)
        self.daemon_thread = threading.Thread(target=self.daemon.requestLoop)
        self.daemon_thread.daemon = True
        self.daemon_thread.start()
        self.nameserver.register("config",uri)

    def _stop(self):
        self.nameserver.remove("config")
        self.daemon.shutdown()
        self.daemon.close()
        self.daemon = None
        self.daemon_thread.join()
        self.daemon_thread = None

    def getIP(self,hn):
        if(self.userconfig.has_section(hn)):
            return self.userconfig.get(hn,"ip")

    def getShare(self,hn):
        if(self.userconfig.has_section(hn)):
            return self.userconfig.getint(hn,"share")
            
    def runWith1500MTU(self):
        return self.userconfig.getboolean("MaxiNet","runWith1500MTU")

    def getID(self,hn):
        self.lock.acquire()
        self.last_id = self.last_id +1
        x = self.last_id
        self.lock.release()
        return x

    def getWorkerDir(self):
        return os.path.join(self.getMaxiNetBasedir(), "Worker")

    def getMaxiNetBasedir(self):
        return os.path.abspath(os.path.dirname(os.path.abspath(__file__))+os.sep+".."+os.sep)
        
    def getWorkerScript(self, cmd):
        d= self.getMaxiNetBasedir()
        return os.path.join(d,"Worker", "bin", cmd)

    def getHosts(self):
        return filter(lambda x: x!="MaxiNet",self.userconfig.sections())
        
    def getController(self):
        return self.userconfig.get("MaxiNet","controller")
        
    def debugPyroOnWorker(self):
        return self.userconfig.get("MaxiNet","debugPyroOnWorker")

    def keepScreenOpenOnError(self):
        return self.userconfig.getboolean("MaxiNet","keepScreenOpenOnError")
        
    def getLoggingLevel(self):
        lvl = self.userconfig.get("MaxiNet","debugLevel")
        lvls = {"CRITICAL": logging.CRITICAL,
                "ERROR": logging.ERROR,
                "WARNING": logging.WARNING,
                "INFO": logging.INFO,
                "DEBUG": logging.DEBUG }
        return lvls[lvl]
