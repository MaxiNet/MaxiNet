import socket
import logging
import thread
import threading
import Pyro4
import os
import time
import atexit

logging.basicConfig(level=logging.INFO)
cfg = { "debian-vm1" :  { "ip" : "192.168.123.1"},
        "debian-vm2" : { "ip" : "192.168.123.2"},
        "debian-vm3" : { "ip" : "192.168.123.3"}
}
defaults = { "ip":None, "ls": "192.168.0.1", "share": 1 }
controller = "192.168.123.1:6633" # default controller
runWith1500MTU = False

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
        if(hn in cfg):
            return cfg[hn]["ip"]
        else:
            return defaults["ip"]
    def getShare(self,hn):
        if((hn in cfg) and ("share" in cfg[hn].keys())):
            return cfg[hn]["share"]
        else:
            return defaults["share"]
    
    def runWith1500MTU(self):
        return runWith1500MTU
        
    def getLogServerIP(self,hn):
        if(hn in cfg) and ("ls" in cfg[hn]):
            return cfg[hn]["ls"]
        else:
            return defaults["ls"]
    
    def getID(self,hn):
        self.lock.acquire()
        self.last_id = self.last_id +1
        x = self.last_id
        self.lock.release()
        return x



# historic config for logserver
logserverip = '192.168.0.4'
logdirectory = '/tmp/logs'
if not os.path.exists(logdirectory):
    os.makedirs(logdirectory)
