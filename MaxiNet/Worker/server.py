__author__ = 'm'

import Pyro4
import logging
import sys, os
import socket 
if hasattr(Pyro4.config, 'SERIALIZERS_ACCEPTED'):
    # From Pyro 4.25, pickle is not supported by default due to security.
    # However, it is required to serialise some objects used by maxinet.
    Pyro4.config.SERIALIZERS_ACCEPTED.add('pickle')
Pyro4.config.SERIALIZER = 'pickle'

class PyroServer():
    def __init__(self, host=None, nsaddress=None, nsport=9090):
	self.logger = logging.getLogger(__name__)
        self.daemon = Pyro4.Daemon(host)
        self.nameserver = Pyro4.locateNS(nsaddress, nsport)     # find the name server
        self.logger.debug("IP: %s, Nameserver: %s", host, self.nameserver)

    def register_obj(self, obj, name):
        self.logger.debug("Registering %s with name %s on NS",obj,name)
        uri = self.daemon.register(obj)   # register the object as a Pyro object
        self.nameserver.register(name, uri)       # register the object with a 
                                                  # name in the name server

    def requestLoop(self):
        self.logger.info("Ready.")
        self.daemon.requestLoop()





def main():
    nss = sys.argv[1].split(":")
    ns = nss[0]
    hmac=None
    if(len(sys.argv)>=3):
        hmac = sys.argv[2]
    if(len(nss)>1):
        nsp=int(nss[1])
    else:
        nsp=9090
    logger = logging.getLogger(__name__)
    workerDir = os.path.abspath(os.path.split(__file__)[0])

    if(hmac):
        Pyro4.config.HMAC_KEY=hmac

    nameserver = Pyro4.locateNS(ns,nsp)
    curi = nameserver.lookup("config")
    config = Pyro4.Proxy(curi)
    hostname = socket.gethostname()
    hostIP = config.getIP(hostname)
    workerID= config.getID(hostname)
    from MaxiNet.Worker.services import MininetCreator, CmdListener
    logger.info("Starting server....")
    logger.info("IP: %s, ID: %s, Nameserver: %s", hostIP, workerID, ns)
    server = PyroServer(host=hostIP, nsaddress=ns, nsport=nsp)
    logger.debug("Registering Objects...")
    server.register_obj(MininetCreator(), 'worker{0}.mnCreator'.format(workerID))
    server.register_obj(CmdListener(workerDir), 'worker{0}.cmd'.format(workerID))
    logger.debug("Entering request loop")
    server.requestLoop()
    # Successful exit
    logger.debug("Exiting server")
    sys.exit(0)
