import atexit
from ConfigParser import RawConfigParser
import logging
import os
from socket import error
import threading
import time

import Pyro4

from MaxiNet.tools import MaxiNetConfig


Pyro4.config.SOCK_REUSE = True

class NameServer(object):
    def __init__(self, config=MaxiNetConfig()):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def start(self):
        """Start namserver instance.

        Will wait for up to 30 seconds if nameserver port is blocked by other
        process. This sometimes happens when nameserver was not shut down
        correctly and OS waits for timeout before freeing the port.
        """
        Pyro4.config.SERVERTYPE = "thread"

        self._ns_thread = threading.Thread(target=Pyro4.naming.startNSloop,
                                kwargs={
                                    "host": self.config.get_nameserver_ip(),
                                    "port": self.config.get_nameserver_port(),
                                    "hmac": self.config.get_nameserver_password()
                                })
        self._ns_thread.daemon = True
        self._ns_thread.start()
        time.sleep(1)
        atexit.register(self.stop)
        self.config.register()

    def stop(self):
        """Shut down nameserver instance.
        """
        self.config.unregister()


class MaxiNetManager(object):
    def __init__(self, config=MaxiNetConfig()):
        self.config = config
        self._worker_dict = {}
        self._worker_dict_lock = threading.Lock()
        self._ns = None
        self._pyrodaemon = None
        self.logger = logging.getLogger(__name__)

    def start(self):
        self.logger.info("starting up and connecting to  %s:%d"
                         % (self.config.get_nameserver_ip(), self.config.get_nameserver_port()))
        #Pyro4.config.HMAC_KEY = self.config.get_nameserver_password()
        self._ns = Pyro4.locateNS(self.config.get_nameserver_ip(), self.config.get_nameserver_port(), hmac_key=self.config.get_nameserver_password())
        #  replace local config with the one from nameserver
        pw = self.config.get_nameserver_password()
        self.config = Pyro4.Proxy(self._ns.lookup("config"))
        self.config._pyroHmacKey=pw
        self._pyrodaemon = Pyro4.Daemon(host=self.config.get_nameserver_ip())
        self._pyrodaemon._pyroHmacKey=self.config.get_nameserver_password()
        uri = self._pyrodaemon.register(self)
        self._ns.register("MaxiNetManager", uri)
        atexit.register(self._stop)
        self._pyrodaemon.requestLoop()

    def _stop(self):
        self.logger.info("shutting down...")
        self._worker_dict_lock.acquire()
        workers = self._worker_dict.keys()
        for worker in workers:
            pn = self._worker_dict[worker]["pyroname"]
            self._worker_dict_lock.release()
            p = Pyro4.Proxy(self._ns.lookup(pn))
            p._pyroHmacKey=self.config.get_nameserver_password()
            p.remoteShutdown()
            self._worker_dict_lock.acquire()
        self._worker_dict_lock.release()
        while(len(self.get_workers()) > 0):
            self.logger.debug("waiting for workers to unregister...")
            time.sleep(0.5)
        self._ns.remove("MaxiNetManager")
        self._pyrodaemon.unregister(self)
        self._pyrodaemon.shutdown()

    def stop(self):
        self._worker_dict_lock.acquire()
        if (len(filter(lambda x: not (x["assigned"] is None),
                       self._worker_dict.values())) > 0):
            self.logger.warn("shutdown not possible as there are still \
                             reserved workers")
            self._worker_dict_lock.release()
            return False
        else:
            self._worker_dict_lock.release()
            self._stop()
            return True

    def worker_signin(self, worker_pyroname, worker_hostname):
        self._worker_dict_lock.acquire()
        if(worker_hostname in self._worker_dict):
            self._worker_dict_lock.release()
            self.logger.warn("failed to register worker %s (pyro: %s) as it is\
                              aready registered."
                             % (worker_hostname, worker_pyroname))
            return False
        self._worker_dict[worker_hostname] = {"assigned": None,
                                              "pyroname": worker_pyroname}
        self._worker_dict_lock.release()
        self.logger.info("new worker signed in: %s (pyro: %s)"
                         % (worker_hostname, worker_pyroname))
        return True

    def _is_assigned(self, worker_hostname):
        return not (self._worker_dict[worker_hostname]["assigned"] is None)

    def get_worker_status(self, worker_hostname):
        signed_in = False
        assigned = None
        self._worker_dict_lock.acquire()
        if(worker_hostname in self._worker_dict):
            signed_in = True
            assigned = self._worker_dict[worker_hostname]["assigned"]
        self._worker_dict_lock.release()
        return (signed_in, assigned)

    def worker_signout(self, worker_hostname):
        self._worker_dict_lock.acquire()
        if(worker_hostname in self._worker_dict):
            if(not self._is_assigned(worker_hostname)):
                del self._worker_dict[worker_hostname]
                self._worker_dict_lock.release()
                self.logger.info("worker signed out: %s" % (worker_hostname))
                return True
            else:
                self._worker_dict_lock.release()
                self.logger.warn("failed to sign out worker %s as it is still \
                                 reserved" % (worker_hostname))
                return False
        self._worker_dict_lock.release()
        return True

    def reserve_worker(self, worker_hostname, id):
        self._worker_dict_lock.acquire()
        if(self._is_assigned(worker_hostname)):
            self._worker_dict_lock.release()
            return None
        else:
            self._worker_dict[worker_hostname]["assigned"] = id
            pyname = self._worker_dict[worker_hostname]["pyroname"]
            self._worker_dict_lock.release()
            self.logger.info("reserved worker %s for id %s"
                             % (worker_hostname, id))
            return pyname

    def free_worker(self, worker_hostname, id, force=False):
        self._worker_dict_lock.acquire()
        if((self._worker_dict[worker_hostname]["assigned"] == id) or force):
            self._worker_dict[worker_hostname]["assigned"] = None
            self._worker_dict_lock.release()
            self.logger.info("worker %s was freed" % worker_hostname)
            return True
        else:
            self._worker_dict_lock.release()
            self.logger.warn("failed to free worker %s as it was either not\
                              reserved or not reserved by freeing id %s"
                             % (worker_hostname, id))
            return False

    def get_free_workers(self):
        rd = {}
        self._worker_dict_lock.acquire()
        w = filter(lambda x: self._worker_dict[x]["assigned"] is None,
                   self._worker_dict)
        for x in w:
            rd[x] = self._worker_dict[x]
        self._worker_dict_lock.release()
        return rd

    def get_workers(self):
        self._worker_dict_lock.acquire()
        w = self._worker_dict.copy()
        self._worker_dict_lock.release()
        return w


def main():
    NameServer().start()
    time.sleep(1)
    MaxiNetManager().start()

if(__name__ == "__main__"):
    main()
