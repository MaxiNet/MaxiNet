import atexit
import sys
import thread
import threading
import Pyro4
import config

# Make Mininets classes import on OS X
if sys.platform == "darwin":
    class DarwinMiniNetHack:
        pass

    import select
    select.poll = DarwinMiniNetHack
    select.POLLIN =1
    select.POLLHUP = 16



class Config:
    def __init__(self,nameserverip,nameserverport):
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
        if(hn in config.cfg):
            return config.cfg[hn]["ip"]
        else:
            return config.defaults["ip"]

    def getShare(self,hn):
        if((hn in config.cfg) and ("share" in config.cfg[hn].keys())):
            return config.cfg[hn]["share"]
        else:
            return config.defaults["share"]

    def runWith1500MTU(self):
        return config.runWith1500MTU

    def getID(self,hn):
        self.lock.acquire()
        self.last_id = self.last_id +1
        x = self.last_id
        self.lock.release()
        return x

