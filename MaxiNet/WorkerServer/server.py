#!/usr/bin/python2

import argparse
import atexit
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time

from mininet.node import UserSwitch, OVSSwitch
from mininet.link import TCLink, TCIntf
from mininet.net import Mininet
import mininet.term
import Pyro4

from MaxiNet.tools import Tools, MaxiNetConfig
from MaxiNet.WorkerServer.ssh_manager import SSH_Manager


def exit_handler(signal, frame):
    # I have absolutely no clue why but without this print atexit sometimes
    # doesn't seem to wait for called functions to finish...
    print "exiting..."
    sys.exit()


class WorkerServer(object):
    """Manages the Worker

    The WorkerServer class connects to the nameserver and registers
    itself with the MaxiNetManager instance. It is used by the Cluster instances
    to start mininet instances, manage the ssh daemon and run commands etc.

    Attributes:
        logger: logging instance
        mnManager: instance of class MininetManager which is used to create mininet
            instances
        sshManager: instance of class SSH_Manager which is used to manage the ssh
            daemon.
        ssh_folder: folder which holds configuration files for the ssh daemon.
        ip: ip address of Worker
    """
    def __init__(self):
        self._ns = None
        self._pyrodaemon = None
        self.logger = logging.getLogger(__name__)
        self._manager = None
        self.mnManager = MininetManager()
        self.sshManager = None
        self.ssh_folder = tempfile.mkdtemp()
        atexit.register(subprocess.call, ["rm", "-rf", self.ssh_folder])
        logging.basicConfig(level=logging.DEBUG)
        self.ip = None
        self._shutdown = False
        #Pyro4.config.COMMTIMEOUT = 2

    def start(self, ip, port, password, retry=float("inf")):
        """Start WorkerServer and ssh daemon and connect to nameserver."""
        self.logger.info("starting up and connecting to  %s:%d"
                         % (ip, port))
        #Pyro4.config.HMAC_KEY = password
        tries=1
        self._ns = None
        while not self._ns:
            try:
                self._ns = Pyro4.locateNS(ip, port, hmac_key=password)
            except Pyro4.errors.NamingError:
                if tries < retry:
                    self.logger.warn("Unable to locate Nameserver. Trying again in %s seconds..." % tries)
                    time.sleep(tries)
                    tries += 1
                else:
                    self.logger.error("Unable to locate Nameserver.")
                    sys.exit()
        self.config = Pyro4.Proxy(self._ns.lookup("config"))
        self.config._pyroHmacKey=password
        self.ip = self.config.get_worker_ip(self.get_hostname())
        if(not self.ip):
            self.ip = Tools.guess_ip()
            if not self.config.has_section(self.get_hostname()):
                self.config.add_section(self.get_hostname())
            self.config.set(self.get_hostname(), "ip", self.ip)
            self.logger.warn("""FrontendServer did not know IP of this host.
                             Guessed: %s""" % self.ip)
        self.logger.info("configuring and starting ssh daemon...")
        self.sshManager = SSH_Manager(folder=self.ssh_folder, ip=self.ip, port=self.config.get_sshd_port(), user=self.config.get("all", "sshuser"))
        self.sshManager.start_sshd()
        self._pyrodaemon = Pyro4.Daemon(host=self.ip)
        self._pyrodaemon._pyroHmacKey=password
        uri = self._pyrodaemon.register(self)
        self._ns.register(self._get_pyroname(), uri)
        uri = self._pyrodaemon.register(self.mnManager)
        self._ns.register(self._get_pyroname()+".mnManager", uri)
        uri = self._pyrodaemon.register(self.sshManager)
        self._ns.register(self._get_pyroname()+".sshManager", uri)
        atexit.register(self._stop)
        self.logger.info("looking for manager application...")
        manager_uri = self._ns.lookup("MaxiNetManager")
        if(manager_uri):
            self._manager = Pyro4.Proxy(manager_uri)
            self._manager._pyroHmacKey=password
            self.logger.info("signing in...")
            if(self._manager.worker_signin(self._get_pyroname(), self.get_hostname())):
                self.logger.info("done. Entering requestloop.")
                self._started = True
                self._pyrodaemon.requestLoop()
            else:
                self.logger.error("signin failed.")
        else:
            self.logger.error("no manager found.")

    def _get_pyroname(self):
        return "MaxiNetWorker_%s" % self.get_hostname()

    def get_hostname(self):
        return subprocess.check_output(["hostname"]).strip()

    def _stop(self):
        self.logger.info("signing out...")
        if(self._manager):
            self._manager.worker_signout(self.get_hostname())
        self.logger.info("shutting down...")
        self._ns.remove(self._get_pyroname())
        self._ns.remove(self._get_pyroname()+".mnManager")
        self._pyrodaemon.unregister(self)
        self._pyrodaemon.shutdown()
        self._pyrodaemon.close()

    def remoteShutdown(self):
        self._pyrodaemon.shutdown()

    def _check_shutdown(self):
        return self._shutdown

    def stop(self):
        (signedin, assigned) = self._manager.get_worker_status(self.get_hostname())
        if(assigned):
            self.logger.warn("can't shut down as worker is still assigned to id %d" % assigned)
            return False
        else:
            self._stop()
            return True

    def check_output(self, cmd):
        self.logger.debug("Executing %s" % cmd)
        return subprocess.check_output(cmd, shell=True,
                                       stderr=subprocess.STDOUT).strip()

    def script_check_output(self, cmd):
        # Prefix command by our worker directory
        cmd = Tools.get_script_dir() + cmd
        return self.check_output(cmd)

    def run_cmd(self, command):
        subprocess.call(command, shell=True)

    def daemonize(self, cmd):
        p = subprocess.Popen(cmd, shell=True)
        atexit.register(p.terminate)

    def daemonize_script(self, script, args):
        cmd = Tools.get_script_dir()+script+" "+args
        p = subprocess.Popen(cmd, shell=True)
        atexit.register(p.terminate)


class MininetManager(object):

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.net = None

    def create_mininet(self, topo, tunnels=[],  switch=UserSwitch,
                       controller=None):
        if(not self.net is None):
            self.logger.warn("running mininet instance detected!\
                              Shutting it down...")
            self.destroy_mininet()

        self.logger.info("Creating mininet instance")
        if controller:
            self.net = Mininet(topo=topo, intf=TCIntf, link=TCLink,
                               switch=switch, controller=controller)
        else:
            self.net = Mininet(topo=topo, intf=TCIntf, link=TCLink,
                               switch=switch)
        self.logger.info("Adding tunnels to mininet instance")
        for tunnel in tunnels:
            port = None
            cls = None
            if "port" in tunnel[2].keys():
                port = tunnel[2]["port"]
                del tunnel[2]["port"]
            if "cls" in tunnel[2].keys():
                cls = tunnel[2]["cls"]
                del tunnel[2]["cls"]
            self.addTunnel(tunnel[0], tunnel[1], port, cls, **tunnel[2])
        self.logger.info("Starting Mininet...")
        self.net.start()
        self.logger.info("Startup complete.")
        self.x11popens = []
        return True

    def destroy_mininet(self):
        if self.net:
            for popen in self.x11popens:
                popen.terminate()
                popen.communicate()
                popen.wait()
            self.net.stop()
            self.logger.info("mininet instance terminated")
            self.net = None

    def configLinkStatus(self, src, dst, status):
        self.net.configLinkStatus(src, dst, status)

    def rpc(self, hostname, cmd, *params1, **params2):
        h = self.net.get(hostname)
        return getattr(h, cmd)(*params1, **params2)

    def attr(self, hostname, name):
        h = self.net.get(hostname)
        return getattr(h, name)

    def addHost(self, name, cls=None, **params):
        self.net.addHost(name, cls, **params)
        return name

    def addSwitch(self, name, cls=None, **params):
        self.net.addSwitch(name, cls, **params)
        #TODO: This should not be done here
        self.net.get(name).start(self.net.controllers)
        return name

    def addController(self, name="c0", controller=None, **params):
        self.net.addController(name, controller, **params)
        return name

    def addTunnel(self, name, switch, port, intf, **params):
        switch = self.net.get(switch)
        if not intf:
            intf = TCIntf
        intf(name, node=switch, port=port, link=None, **params)

    def tunnelX11(self, node, display):
        node = self.net.get(node)
        (tunnel, popen) = mininet.term.tunnelX11(node, display)
        self.x11popens.append(popen)

    def addLink(self, node1, node2, port1=None, port2=None, cls=None,
                **params):
        node1 = self.net.get(node1)
        node2 = self.net.get(node2)
        l = self.net.addLink(node1, node2, port1, port2, cls, **params)
        return ((node1.name, l.intf1.name), (node2.name, l.intf2.name))

    def runCmdOnHost(self, hostname, command, noWait=False):
        '''
            e.g. runCmdOnHost('h1', 'ifconfig')
        '''
        h1 = self.net.get(hostname)
        if noWait:
            return h1.sendCmd(command)
        else:
            return h1.cmd(command)


def getFrontendStatus():
    config = MaxiNetConfig(register=False)
    ip = config.get_nameserver_ip()
    port = config.get_nameserver_port()
    pw = config.get_nameserver_password()
    ns = Pyro4.locateNS(ip, port, hmac_key=pw)
    manager_uri = ns.lookup("MaxiNetManager")
    if(manager_uri):
        manager = Pyro4.Proxy(manager_uri)
        manager._pyroHmacKey=pw
        print manager.print_worker_status()
    else:
        print "Could not contact Frontend Server"


def main():
    parser = argparse.ArgumentParser(description="MaxiNet Worker which hosts a mininet instance")
    parser.add_argument("--ip", action="store", help="Frontend Server IP")
    parser.add_argument("--port", action="store", help="Frontend Server Port", type=int)
    parser.add_argument("--password", action="store", help="Frontend Server Password")
    parser.add_argument("-c", "--config", metavar="FILE", action="store", help="Read configuration from FILE")
    parsed = parser.parse_args()
    signal.signal(signal.SIGINT, exit_handler)
    ip = False
    port = False
    pw = False
    if (parsed.config or
            os.path.isfile("MaxiNet.cfg") or
            os.path.isfile(os.path.expanduser("~/.MaxiNet.cfg")) or
            os.path.isfile("/etc/MaxiNet.cfg")):
        if parsed.config:
            config = MaxiNetConfig(file=parsed.config,register=False)
        else:
            config = MaxiNetConfig(register=False)
        ip = config.get_nameserver_ip()
        port = config.get_nameserver_port()
        pw = config.get_nameserver_password()
    if parsed.ip:
        ip = parsed.ip
    if parsed.port:
        port = parsed.port
    if parsed.password:
        pw = parsed.password

    if not (ip and port and pw):
        print "Please provide MaxiNet.cfg or specify ip, port and password of \
               the Frontend Server."
    else:
        WorkerServer().start(ip=ip, port=port, password=pw)


if(__name__ == "__main__"):
    main()
