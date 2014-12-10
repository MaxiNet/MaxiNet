"""MaxiNet Pyro Frontend server.

The code in this file is used to open and manage a pyro nameserver.

Classes in this file:

Frontend: Pyro Frontend class.
"""

import atexit
import contextlib
import functools
import logging
import random
from socket import error
import subprocess
import sys
import threading
import time

import Pyro4
import Pyro4.util


Pyro4.config.SOCK_REUSE = True


if hasattr(Pyro4.config, 'SERIALIZERS_ACCEPTED'):
    # From Pyro 4.25, pickle is not supported by default due to security.
    # However, it is required to serialise some objects used by maxinet.
    Pyro4.config.SERIALIZERS_ACCEPTED.add('pickle')


Pyro4.config.SERIALIZER = 'pickle'


sys.excepthook = Pyro4.util.excepthook


logger = logging.getLogger(__name__)


@contextlib.contextmanager
def remote_exceptions_logged_and_reraised(logger=logger, level=logging.INFO):
    """Context manager for with statement handling of remote exceptions."""
    try:
        yield
    except Exception as e:
        # Pyro remote exceptions have a _pyroTraceback attribute attached.
        # By default, this is not incorporated into the exception message
        # or local traceback.
        if hasattr(e, "_pyroTraceback"):
            logger.log(level, "".join(Pyro4.util.getPyroTraceback()))
        # Reraise the original exception
        raise


def log_and_reraise_remote_exception(func, logger=logger, level=logging.INFO):
    """Decorator to log remote exceptions to a logger."""
    @functools.wraps(func)
    def newfunc(*args, **kwargs):
        with remote_exceptions_logged_and_reraised(logger=logger, level=level):
            return func(*args, **kwargs)
    return newfunc


class Frontend(object):

    """Pyro Frontend class.

    Management of the pyro nameserver is done here.
    Usually MaxiNet will start a pyro nameserver and manage it by itself.
    However, if it detects a running instance of a nameserver it will use this
    one. Be aware that in this case no HMAC key is supported, which poses a
    significant security risk!

    Attributes:
        logger: Loggin instance.
        nameserver: Pyro nameserver instance.
        nameServerIP: Local IPv4 address.
        nsport: Nameserver port.
        ownns_running: Flag whether nameserver was started by MaxiNet or
                       "extern" namesever instance was used.
        _hmac_key: HMAC key of the nameserver.
    """

    def __init__(self, nameserver, port=9090):
        """Init Frontend.

        Starts nameserver and calculates random hmac key.

        Args:
            nameserver: Local IPv4 address.
            port: Optional port to run nameserver on. Default: 9090
        """
        self.ownns_running = False
        self.logger = logger
        self.nameServerIP = nameserver
        self.nsport = port
        self._hmac_key = str(random.getrandbits(128))
        if(not self.ns_is_running()):
            self.start_nameserver()
        self.locateNS()

    def locateNS(self):
        """Locate and store Pyro name server.

        Initializes nameserver attribute.
        """
        self.nameserver = Pyro4.locateNS(self.nameServerIP, self.nsport)
        atexit.register(self.nameserver._pyroRelease)

    def lookup(self, objectName):
        """Get Pyro URI of object.

        Looks up objectName on nameserver and return URI.
        locateNS must has already been called.

        Args:
            objectname: Object name (string) to look up.

        Returns:
            URI of object on nameserver
        """
        return self.nameserver.lookup(objectName)

    def remove(self, objectName):
        """Unregister object from nameserver.

        Returns:
            number of items removed.
        """
        return self.nameserver.remove(objectName)

    def getObjectProxy(self, objectName):
        """Get pyro proxy object.

        Args:
            objectname: Object name to look up.

        Returns:
            Pyro proxy object.
        """
        objectURI = self.lookup(objectName)
        proxy = Pyro4.Proxy(objectURI)
        atexit.register(proxy._pyroRelease)
        return proxy

    def ns_is_running(self):
        """Find out whether Pyro nameserver is already running."""
        ps = ""
        if(self.ownns_running):
            return True
        try:
            ps = subprocess.check_output(["ps aux | grep \"Pyro[4].naming\""],
                                         shell=True).strip()
        except subprocess.CalledProcessError:
            pass
        if (len(ps) == 0):
            return False
        else:
            return True

    def hmac_key(self):
        """Get HMAC key of nameserver.

        Returns:
            HMAC key of pyro namserver if nameserver was started by MaxiNet.
        """
        if(self.ns_is_running() and not self.ownns_running):
            return None
        return self._hmac_key

    def start_nameserver(self):
        """Start namserver instance.

        Will wait for up to 30 seconds if nameserver port is blocked by other
        process. This sometimes happens when nameserver was not shut down
        correctly and OS waits for timeout before freeing the port.
        """
        Pyro4.config.SERVERTYPE = "thread"
        Pyro4.config.HMAC_KEY = self.hmac_key()
        self.ns = None
        slept = 0
        while(not self.ns):
            try:
                self.ns = Pyro4.naming.startNS(host=self.nameServerIP,
                                               port=self.nsport)
            except error as e:
                if e.errno != 98:
                    raise e
                elif slept >= 30:
                    raise Exception("Timed out waiting for Pyro nameserver")
                else:
                    self.logger.warning("waiting for nameserver port to " +
                                        "become free...")
                    time.sleep(2)
                    slept += 2
        self.ns_thread = threading.Thread(target=self.ns[1].requestLoop)
        self.ns_thread.daemon = True
        self.ns_thread.start()
        self.ownns_running = True
        atexit.register(self._stop_nameserver)

    def _stop_nameserver(self):
        """Stop nameserver.

        Stops nameserver if it was started by MaxiNet.
        """
        if(self.ownns_running):
            self.ns[1].shutdown()
            self.ns[1].close()
            self.ns_thread.join()
            self.ns_thread = None
            self.ns[2].close()
            self.ns = None
            self.ownns_running = False

    def stop(self):
        """Stop nameserver.

        Stops nameserver if it was started by MaxiNet.
        """
        self._stop_nameserver()
