#!/usr/bin/python
"""MaxiNet main file

This file holds the main components of MaxiNet and is intended to be the
only part of MaxiNet which needs to be used by the user or third-party
applications.

Classes in this file:

Experiment: Use this class to specify an experiment. Experiments are
    created for one-time-usage and have to be stopped in the end. One
    cluster instance can run several experiments in sequence.

Cluster: Manage a set of Workers via this class. A cluster can run one
    Experiment at a time. If you've got several Experiments to run do
    not destroy/recreate this class but define several Experiment
    instances and run them sequentially.

NodeWrapper: Wrapper that allows most commands that can be used in
    mininet to be used in MaxiNet as well. Whenever you call for example
    > exp.get("h1")
    you'll get an instance of NodeWrapper which will forward calls to
    the respective mininet node.

TunHelper: Helper class to manage tunnel interface names.

Worker: A Worker is part of a Cluster and runs a part of the emulated
    network.
"""

import atexit
import functools
import logging
import random
import re
import subprocess
import sys
import time
import warnings
import threading

from mininet.node import RemoteController, UserSwitch
from mininet.link import TCIntf, Intf, Link, TCLink
import Pyro4

from MaxiNet.Frontend.cli import CLI
from MaxiNet.tools import Tools, MaxiNetConfig, SSH_Tool
from MaxiNet.Frontend.partitioner import Partitioner


logger = logging.getLogger(__name__)


# the following block is to support deprecation warnings. this is really
# not solved nicely and should probably be somewhere else

def deprecated(func):
    '''This is a decorator which can be used to mark functions
    as deprecated. It will result in a warning being emitted
    when the function is used.'''

    @functools.wraps(func)
    def new_func(*args, **kwargs):
        logger.warn("Call to deprecated function {}.".format(func.__name__))
        warnings.warn_explicit(
            "Call to deprecated function {}.".format(func.__name__),
            category=DeprecationWarning,
            filename=func.func_code.co_filename,
            lineno=func.func_code.co_firstlineno + 1)
        return func(*args, **kwargs)
    return new_func


def run_cmd(cmd):
    """Run cmd on frontend machine.

    See also: rum_cmd_shell(cmd)

    Args:
        cmd: Either a string of program name or sequence of program
            arguments.

    Returns:
        Stdout of cmd call as string.
    """
    return subprocess.check_output(cmd, shell=False)


def run_cmd_shell(cmd):
    """Run cmd on frontend machine.

    See also: rum_cmd(cmd)

    Args:
        cmd: Either a string of program name and arguments or sequence
            of program name and arguments.

    Returns:
        Stdout of cmd call as string.
    """
    return subprocess.check_output(cmd, shell=True)


class Worker(object):

    """Worker class used to manage an individual Worker host.

    A Worker is part of a Cluster and runs a part of the emulated
    network. A Worker is identified by its hostname.
    The Worker class is instanciated when a Worker is added to a Cluster.

    Attributes:
        config: instance of class MaxiNetConfig
        mininet: remote instance of class MininetManager which is used to
            create and manage mininet on the Worker machine.
        server: remote instance of class WorkerServer which is used to run
            commands on the Worker machine.
        switch: default mininet switch class to use in mininet instances.
        ssh: instance of class SSH_Manager used to configure the ssh daemon
            on the worker.
        sshtool: instance of class SSH_Tool used to manage the ssh client on
            the frontend machine.
    """

    def __init__(self, nameserver, pyroname, pyropw, sshtool, switch=UserSwitch):
        """Init Worker class."""
        self.server = Pyro4.Proxy(nameserver.lookup(pyroname))
        self.server._pyroHmacKey=pyropw
        self.mininet = Pyro4.Proxy(nameserver.lookup(pyroname+".mnManager"))
        self.mininet._pyroHmacKey=pyropw
        self.ssh = Pyro4.Proxy(nameserver.lookup(pyroname+".sshManager"))
        self.ssh._pyroHmacKey=pyropw
        self.config = Pyro4.Proxy(nameserver.lookup("config"))
        self.config._pyroHmacKey=pyropw
        if(not self.config.run_with_1500_mtu()):
            self._fix_mtus()
        self.switch = switch
        self.sshtool = sshtool
        self.sshtool.add_known_host(self.ip())
        self._x11tunnels = []
        self.run_script("load_tunneling.sh")
        self._add_ssh_key()

    def _add_ssh_key(self):
        """add ssh key of frontend machine to worker ssh daemon"""
        k = self.sshtool.get_pub_ssh_key()
        self.ssh.add_key(k)


    def hn(self):
        """Get hostname of worker machine."""
        return self.server.get_hostname()

    def set_switch(self, switch):
        """Set default switch class."""
        self.switch = switch


    def configLinkStatus(self, src, dst, status):
        """Wrapper for configLinkStatus method on remote mininet.

        Used to enable and disable links.

        Args:
            src: name of source node
            dst: name of destination node
            status: string {up|down}

        """
        self.mininet.configLinkStatus(src, dst, status)


    def ip(self, classifier=None):
        """Get public ip adress of worker machine.

        Args:
            classifier: if multiple ip addresses are configured for a worker
                a classifier can be used to hint which ip address should be used.
        """
        return self.config.get_worker_ip(self.hn(), classifier)


    def start(self, topo, tunnels, controller=None):
        """Start mininet instance on worker machine.

        Start mininet emulating the in  argument topo specified topology.
        if controller is not specified mininet will start an own
        controller for this net.

        Args:
            topo: Topology to emulate on this worker.
            tunnels: List of tunnels in format: [[tunnelname, switch,
                    options],].
            controller: optional mininet controller class to use in this
                    network.
        """
        STT = self.config.use_stt_tunneling()
        if controller:
            self.mininet.create_mininet(topo=topo, tunnels=tunnels,
                                        controller=controller,
                                        switch=self.switch, STT=STT)
        else:
            self.mininet.create_mininet(topo=topo, tunnels=tunnels,
                                        switch=self.switch, STT=STT)


    def daemonize(self, cmd):
        """run command in background and terminate when MaxiNet is shut
        down."""
        self.server.daemonize(cmd)

    def daemonize_script(self, script, args):
        """run script from script folder in background and terminate when MaxiNet is shut
        down.

        Args:
            script: Script name to call
            args: string of args which will be appended to script name call
        """
        self.server.daemonize_script(script, args)


    def tunnelX11(self, node):
        """Create X11 tunnel from Frontend to node on worker to make
        x-forwarding work.

        This is used in CLI class to allow calls to wireshark etc.
        For each node only one tunnel will be created.

        Args:
            node: nodename

        Returns:
            boolean whether tunnel was successfully created.
        """
        if(not node in self._x11tunnels):
            try:
                display = subprocess.check_output(
                            self.sshtool.get_ssh_cmd(targethostname=self.hn(),
                                                     cmd="env | grep DISPLAY",
                                                     opts=["-Y"]))[8:]
                self.mininet.tunnelX11(node, display)
                self._x11tunnels.append(node)
            except subprocess.CalledProcessError:
                return False
        return True


    def run_cmd_on_host(self, host, cmd):
        """Run cmd in context of host and return output.

        Args:
            host: nodename
            cmd: string of program name and arguments to call.

        Returns:
            Stdout of program call.
        """
        return self.mininet.runCmdOnHost(host, cmd)


    def run_cmd(self, cmd):
        """run cmd on worker machine and return output.

        Args:
            cmd: string of program name and arguments to call.

        Returns:
            Stdout of program call.
        """
        return self.server.check_output(cmd)


    def run_script(self, cmd):
        """Run MaxiNet script on worker machine and return output.

        Args:
            cmd: String of name of MaxiNet script and arguments.

        Returns:
            Stdout of program call.
        """
        return self.server.script_check_output(cmd)


    def rpc(self, host, cmd, *params1, **params2):
        """Do rpc call to mininet node.

        MaxiNet uses this function to do rpc calls on remote nodes in
        NodeWrapper class.

        Args:
            host: Nodename
            cmd: Method of node to call.
            *params1: Unnamed parameters to call.
            **params2: Named parameters to call.

        Returns:
            Return of host.cmd(*params1,**params2).
            WARNING: if returned object is not serializable this might
                     crash.
        """
        return self.mininet.rpc(host, cmd, *params1, **params2)


    def rattr(self, host, name):
        """Get attributes of mininet node.

        MaxiNet uses this function to get attributes of remote nodes in
        NodeWrapper class.

        Args:
            host: Nodename

        Returns:
            host.name
            WARNING: if the attribute is not serializable this might
                     crash.
        """
        return self.mininet.attr(host, name)


    def _fix_mtus(self):
        """If mtu of Worker is lower than 1600 set it to 1600.

        In order to transfer 1500 byte long packets over GRE tunnels
        the MTU of the interface which "transfers" the tunnel has to be
        set to 1600.
        This method tries to determine the correct network interface and
        sets its MTU. This method is not needed if MaxiNet is configured
        to use MTUs lower than 1451 on the mininet nodes.
        """
        if self.ip(classifier="backend") is None:
            logger.warn("no ip configured - can not fix MTU ")
            return 0
        intf = self.run_cmd("ip addr show to " + self.ip(classifier="backend") +
                            "/24 | head -n1 | cut -d' ' -f2 | tr -d :").strip()
        if intf == "":
            logger.warn("could not find eth device - can not fix MTU")
            return 0
        mtu = int(self.run_cmd("ip li show dev " + intf +
                               " | head -n1 | cut -d ' ' -f5"))
        if(mtu < 1600):
            self.run_cmd("ip li se dev " + intf + " mtu 1600")

    def stop(self):
        """Stop mininet instance on this worker."""
        return self.mininet.destroy_mininet()

    def get_file(self, src, dst):
        """Transfer file specified by src on worker to dst on Frontend.

        Transfers file src to filename or folder dst on Frontend machine
        via scp.

        Args:
            src: string of path to file on Worker
            dst: string of path to file or folder on Frontend
        """
        cmd_get = self.sshtool.get_scp_get_cmd(targethostname=self.hn(),
                                               remote=src,
                                               local=dst)
        subprocess.call(cmd_get)

    def put_file(self, src, dst):
        """transfer file specified by src on Frontend to dst on worker.

        Transfers file src to filename or folder dst on Worker machine
        via scp.
        Args:
            src: string of path to file on Frontend
            dst: string of path to file or folder on Worker
        """
        cmd_put = self.sshtool.get_scp_put_cmd(targethostname=self.hn(),
                                               local=src,
                                               remote=dst)
        subprocess.call(cmd_put)

    def sync_get_file(self, src, dst):
        """Transfer file specified by src on worker to dst on Frontend.

        Transfers file src to filename or folder dst on Frontend machine
        via rsync. Does not transfer anything if dst already exists and
        is the same as src.

        Args:
            src: string of path to file on Worker
            dst: string of path to file or folder on Frontend
        """
        cmd_get = self.sshtool.get_rsync_get_cmd(targethostname=self.hn(),
                                                 remote=src,
                                                 local=dst)
        subprocess.call(cmd_get)

    def sync_put_file(self, src, dst):
        """transfer file specified by src on Frontend to dst on worker.

        Transfers file src to filename or folder dst on Worker machine
        via rsync. Does not transfer anything if dst already exists and
        is the same as src.

        Args:
            src: string of path to file on Frontend
            dst: string of path to file or folder on Worker
        """
        cmd_put = self.sshtool.get_rsync_put_cmd(targethostname=self.hn(),
                                                 local=src,
                                                 remote=dst)
        subprocess.call(cmd_put)

    def addHost(self, name, cls=None, **params):
        """Add host at runtime.

        You probably want to use Experiment.addHost as this does some
        bookkeeping of nodes etc.

        Args:
            name: Nodename to add. Must not already exist on Worker.
            cls: Node class to use.
            **params: Additional parameters for cls instanciation.

        Returns:
            nodename
        """
        return self.mininet.addHost(name, cls, **params)


    def addSwitch(self, name, cls=None, **params):
        """Add switch at runtime.

        You probably want to use Experiment.addSwitch as this does some
        bookkeeping on nodes etc.

        Args:
            name: switchname to add. Must not already exist on Worker.
            cls: Node class to use.
            **params: Additional parameters for cls instanciation.

        Returns:
            nodename
        """
        return self.mininet.addSwitch(name, cls, **params)


    def addController(self, name="c0", controller=None, **params):
        """Add controller at runtime.

        You probably want to use Experiment.addController as this does
        some bookkeeping on nodes etc.

        Args:
            name: controllername to add. Must not already exist on Worker.
            controller: mininet controller class to use.
            **params: Additional parameters for cls instanciation.

        Returns:
            controllername
        """
        return self.mininet.addHost(name, controller, **params)


    def addTunnel(self, name, switch, port, intf, **params):
        """Add tunnel at runtime.

        You probably want to use Experiment.addLink as this does some
        bookkeeping on tunnels etc.

        Args:
            name: tunnelname (must be unique on Worker)
            switch: name of switch to which tunnel will be connected.
            port: port number to use on switch.
            intf: Intf class to use when creating the tunnel.
        """
        self.mininet.addTunnel(name, switch, port, intf, **params)


    def addLink(self, node1, node2, port1=None, port2=None,
                cls=None, **params):
        """Add link at runtime.

        You probably want to use Experiment.addLink as this does some
        bookkeeping.

        Args:
            node1: nodename
            node2: nodename
            port1: optional port number to use on node1.
            port2: optional port number to use on node2.
            cls: optional class to use when creating the link.

        Returns:
            Tuple of the following form: ((node1,intfname1),
            (node2,intfname2)) where intfname1 and intfname2 are the
            names of the interfaces which where created for the link.
        """
        return self.mininet.addLink(node1, node2, port1, port2, cls,
                                    **params)


class TunHelper:
    """Class to manage tunnel interface names.

    This class is used by MaxiNet to make sure that tunnel interace
    names are unique.
    WARNING: This class is not designed for concurrent use!

    Attributes:
        tunnr: counter which increases with each tunnel.
        keynr: counter which increases with each tunnel.
    """

    def __init__(self):
        """Inits TunHelper"""
        self.tunnr = 0
        self.keynr = 0

    def get_tun_nr(self):
        """Get tunnel number.

        Returns a number to use when creating a new tunnel.
        This number will only be returned once by this method.
        (see get_last_tun_nr)

        Returns:
            Number to use for tunnel creation.
        """
        self.tunnr = self.tunnr + 1
        return self.tunnr - 1

    def get_key_nr(self):
        """Get key number.

        Returns a number to use when creating a new tunnel.
        This number will only be returned once by this method.
        (see get_last_key_nr)

        Returns:
            Number to use for key in tunnel creation.
        """
        self.keynr = self.keynr + 1
        return self.keynr - 1

    def get_last_tun_nr(self):
        """Get last tunnel number.

        Returns the last number returned by get_tun_nr.

        Returns:
            Number to use for tunnel creation.
        """
        return self.tunnr - 1

    def get_last_key_nr(self):
        """Get last key number.

        Returns the last number returned by get_key_nr.

        Returns:
            Number to use for key in tunnel creation.
        """
        return self.keynr - 1


class Cluster(object):
    """Class used to manage a cluster of Workers.

    Manage a set of Workers via this class. A cluster can run one
    Experiment at a time. If you've got several Experiments to run do
    not destroy/recreate this class but define several Experiment
    instances and run them sequentially.

    Attributes:
        config: Instance of Tools.Config to query MaxiNet configuration.
        frontend: Instance of MaxiNet.Frontend.client.Frontend which
            is used to manage the pyro Server.
        hostname_to_worker: dictionary which translates hostnames into Worker
            instances
        hosts: List of worker hostnames.
        ident: random integer which identifies this cluster instance on the
            FrontendServer.
        localIP: IPv4 address of the Frontend.
        logger: Logging instance.
        nameserver: pyro nameserver
        nsport: Nameserver port number.
        manager: MaxiNetManager instance hosted by FrontendServer which manages
            Workers.
        sshtool: SSH_Tool instance which is used to manage ssh client on frontend
            machine.
        tunhelper: Instance of TunHelper to enumerate tunnel instances.
        worker: List of worker instances. Index of worker instance in
            sequence must be equal to worker id.
    """

    def __init__(self, ip=None, port=None, password=None, minWorkers=None, maxWorkers=None):
        """Inits Cluster class.

        Args:
            ip: IP address of FrontendServer nameserver.
            port: port of FrontendServer nameserver.
            password: password of FrontendServer nameserver.
            maxWorkers: number of workers to allocate to this cluster; None for "all you can get".
            minWorkers: minimum number of workers to allocate to this cluster; None for "at least 1"
        """
        self.logger = logging.getLogger(__name__)
        self.tunhelper = TunHelper()
        self.config = MaxiNetConfig()
        if(ip is None):
            ip = self.config.get_nameserver_ip()
        if(port is None):
            port = self.config.get_nameserver_port()
        if(password is None):
            password = self.config.get_nameserver_password()
        self.nameserver = Pyro4.locateNS(host=ip, port=port, hmac_key=password)
        self.config = Pyro4.Proxy(self.nameserver.lookup("config"))
        self.config._pyroHmacKey=password
        self.manager = Pyro4.Proxy(self.nameserver.lookup("MaxiNetManager"))
        self.manager._pyroHmacKey=password
        self.sshtool = SSH_Tool(self.config)
        self.hostname_to_worker={}
        self._create_ident()
        logging.basicConfig(level=self.config.get_loglevel())
        self.hosts = []
        self.worker = []
        atexit.register(self._stop)

        #register this Cluster to the nameserver as key self.ident:
        myIP = subprocess.check_output("ip route get %s | cut -d' ' -f1" % ip, shell=True)
        if (myIP.strip() == "local"):
            myIP = "127.0.0.1"
        else:
            myIP = subprocess.check_output("ip route get %s" % ip, shell=True).split("src")[1].split()[0]

        self._pyrodaemon = Pyro4.Daemon(host=myIP)
        self._pyrodaemon._pyroHmacKey=password
        uri = self._pyrodaemon.register(self)
        self.nameserver.register(self.ident, uri)
        self._pyro_daemon_thread = threading.Thread(target=self._pyrodaemon.requestLoop)
        self._pyro_daemon_thread.daemon = True
        self._pyro_daemon_thread.start()

        if(maxWorkers == None):
            self.add_workers()
        else:
            for i in range(0,maxWorkers):
                self.add_worker()

        if ((minWorkers != None) and (self.num_workers() < minWorkers)):
            raise Exception("Not enough free workers to run this experiment (got %s, required %s). " % (self.num_workers(), minWorkers))


    def _create_ident(self):
        """Create and register identifier to use when communicating with the
        FrontendServer"""
        self.ident = None
        hn = run_cmd("hostname").strip()
        ident = "%s:%s" % (hn, sys.argv[0])
        if not self.manager.register_ident(ident):
            for i in range(2, 10000):
                ident = "%s:%s-%d" % (hn, sys.argv[0], i)
                if self.manager.register_ident(ident):
                    self.ident = ident
                    break
        else:
            self.ident = ident

    @Pyro4.expose
    def get_status_is_alive(self):
        """Get the status of this Cluster object.
            returns true if the object is still alive.
            this function is periodically called from the FrontendServer to check if the cluster still exists
            otherwise its allocated resources (workers) are freed for future use by other clusters
        """
        return True

    @Pyro4.expose
    def get_available_workers(self):
        """Get list of worker hostnames which are not reserved.

        Returns:
            list of hostnames of workers which are registered on the FrontendServer
            but not reserved by this or another Cluster instance.
        """
        return self.manager.get_free_workers()

    @Pyro4.expose
    def add_worker_by_hostname(self, hostname):
        """Add worker by hostname

        Reserves a Worker for this Cluster on the FrontendServer and adds it to
        the Cluster instance. Fails if Worker is reserved by other Cluster or
        no worker with that hostname exists.

        Args:
            hostname: hostname of Worker
        Returns:
            True if worker was successfully added, False if not.
        """
        pyname = self.manager.reserve_worker(hostname, self.ident)
        if(pyname):
            self.worker.append(Worker(self.nameserver, pyname, self.config.get_nameserver_password(), self.sshtool))
            self.hostname_to_worker[hostname] = self.worker[-1]
            self.logger.info("added worker %s" % hostname)
            return True
        else:
            self.logger.warn("adding worker %s failed" % hostname)
            return False

    @Pyro4.expose
    def add_worker(self):
        """Add worker

        Reserves a Worker for this Cluster on the FrontendServer and adds it to
        the Cluster instance. Fails if no unreserved Worker is available on the
        FrontendServer.

        Returns:
            True if worker was successfully added, False if not.
        """
        hns = self.get_available_workers().keys()
        for hn in hns:
            if(self.add_worker_by_hostname(hn)):
                return True
        return False

    @Pyro4.expose
    def add_workers(self):
        """Add all available workers

        Reserves all unreserved Workers for this Cluster on the FrontendServer
        and adds them to the Cluster instance.

        Returns:
            Number of workers added.
        """
        i = 0
        while self.add_worker():
            i = i + 1
        return i

    @Pyro4.expose
    def remove_worker(self, worker):
        """Remove worker from Cluster

        Removes a Worker from the Cluster and makes it available for other
        Cluster instances on the FrontendServer.

        Args:
            worker: hostname or Worker instance of Worker to remove.
        """
        if(not isinstance(worker, Worker)):
            worker = self.hostname_to_worker[worker]
        del self.hostname_to_worker[worker.hn()]
        self.worker.remove(worker)
        worker.run_script("delete_tunnels.sh")
        hn = worker.hn()
        self.manager.free_worker(worker.hn(), self.ident)
        self.logger.info("removed worker %s" % hn)

    @Pyro4.expose
    def remove_workers(self):
        """Remove all workers from this cluster

        Removes all Workers from the Cluster and makes them available for other
        Cluster instances on the FrontendServer.
        """
        while(len(self.worker) > 0):
            self.remove_worker(self.worker[0])

    def _stop(self):
        """Stop Cluster and shut it down.

        Removes all Workers from the Cluster and makes them available for other
        Cluster instances on the FrontendServer.
        """
        self.remove_workers()
        self.manager.unregister_ident(self.ident)

        self.nameserver.remove(self.ident)
        self._pyrodaemon.unregister(self)
        self._pyrodaemon.shutdown()



    @Pyro4.expose
    def num_workers(self):
        """Return number of worker nodes in this Cluster."""
        return len(self.workers())

    @Pyro4.expose
    def workers(self):
        """Return sequence of worker instances for this cluster.

        Returns:
            Sequence of worker instances.
        """
        return self.worker

    @Pyro4.expose
    def get_worker(self, hostname):
        """Return worker instance of worker with hostname hostname.

        Args:
            hostname: worker hostname

        Returns:
            Worker instance
        """
        return self.hostname_to_worker[hostname]

    @Pyro4.expose
    def get_tunnel_metadata(self, w1, w2):
        """Get metadata needed for tunnel creation

        Args:
            w1: Worker instance
            w2: Worker instance

        Returns:
            Tuple of (ip1,ip2,tunnel id, tunnel key, tunnel interface name). Except
            for ips all values are unique to that instance.
        """
        tid = self.tunhelper.get_tun_nr()
        tkey = self.tunhelper.get_key_nr()
        intf = "mn_tun" + str(tid)
        ip1 = w1.ip(classifier="backend")
        ip2 = w2.ip(classifier="backend")
        #use multiple IP addresses for the workers:
        #modern NICs have multiple queues with own IRQs. This is called RSS. The queue a packet is enqueued in is determined by a hashing algorithm using the IP headers.
        #unfortunatelly, most RSS implementations ignore the GRE headers.
        #on GRE, most RSS hashing algorithms only use src-dest IP addresses to assign packets to queues which makes is necessary to provide multiple IP combinations per worker pair
        #otherwise, all packets between a pair of workers would be assigned to the same queue.
        if self.config.getint("all", "useMultipleIPs") > 1:
            ip1_int = [int(a) for a in ip1.split(".")]
            ip2_int = [int(a) for a in ip2.split(".")]
            ip1_int[3] += random.randint(0, self.config.getint("all", "useMultipleIPs")-1)
            ip2_int[3] += random.randint(0, self.config.getint("all", "useMultipleIPs")-1)
            ip1 = "%d.%d.%d.%d" % tuple(ip1_int)
            ip2 = "%d.%d.%d.%d" % tuple(ip2_int)
        return (ip1, ip2, tid, tkey, intf)

    @Pyro4.expose
    def create_tunnel(self, w1, w2):
        """Create GRE tunnel between workers.

        Create gre tunnel connecting worker machine w1 and w2 and return
        name of created network interface. Querys TunHelper instance to
        create name of tunnel.

        Args:
            w1: Worker instance.
            w2: Woker instance.

        Returns:
            Network interface name of created tunnel.
        """
        ip1, ip2, tid, tkey, intf = self.get_tunnel_metadata(w1, w2)
        self.logger.debug("invoking tunnel create commands on " + ip1 +
                          " and " + ip2)
        w1.run_script("create_tunnel.sh " + ip1 + " " + ip2 + " " + intf +
                      " " + str(tkey))
        w2.run_script("create_tunnel.sh " + ip2 + " " + ip1 + " " + intf +
                      " " + str(tkey))
        self.logger.debug("tunnel " + intf + " created.")
        return intf

    @Pyro4.expose
    def remove_all_tunnels(self):
        """Shut down all tunnels on all workers."""
        for worker in self.workers():
            worker.run_script("delete_tunnels.sh")
        #replace tunhelper instance as tunnel names/keys can be reused now.
        self.tunhelper = TunHelper()


class Experiment(object):
    """Class to manage MaxiNet Experiment.

    Use this class to specify an experiment. Experiments are created for
    one-time-usage and have to be stopped in the end. One cluster
    instance can run several experiments in sequence.

    Attributes:
        cluster: Cluster instance which will be used by this Experiment.
        config: Config instance to queury config file.
        controller: Controller class to use in Experiment.
        hostname_to_workerid: Dict to map hostnames of workers to workerids
        hosts: List of host NodeWrapper instances.
        isMonitoring: True if monitoring is in use.
        logger: Logging instance.
        nodemapping: optional dict to map nodes to specific workers ids.
        nodes: List of NodeWrapper instances.
        node_to_worker: Dict to map node name (string) to worker instance.
        node_to_wrapper: Dict to map node name (string) to NodeWrapper
            instance.
        origtopology: Unpartitioned topology if topology was partitioned
            by MaxiNet.
        shares: list to map worker ids to workload shares. shares[x] is used to
            obtain the share of worker id x.
        starttime: Time at which Experiment was instanciated. Used for
            logfile creation.
        switch: Default mininet switch class to use.
        switches: List of switch NodeWrapper instances.
        topology: instance of MaxiNet.Frontend.paritioner.Clustering
        tunnellookup: Dict to map tunnel tuples (switchname1,switchname2)
            to tunnel names. Order of switchnames can be ignored as both
            directions are covered.
        workerid_to_hostname: dict to map workerids to hostnames of workers to
            worker ids.
    """
    def __init__(self, cluster, topology, controller=None,
                 is_partitioned=False, switch=UserSwitch,
                 nodemapping=None, hostnamemapping=None, sharemapping=None):
        """Inits Experiment.

        Args:
            cluster: Cluster instance.
            topology: mininet.topo.Topo (is_partitioned==False) or
                MaxiNet.Frontend.partitioner.Clustering
                (is_partitioned==True) instance.
            controller: Optional IPv4 address of OpenFlow controller.
                If not set controller IP from MaxiNet configuration will
                be used.
            is_partitioned: Optional flag to indicate whether topology
                is already paritioned or not. Default is unpartitioned.
            switch: Optional Switch class to use in Experiment. Default
                is mininet.node.UserSwitch.
            nodemapping: Optional dict to map nodes to specific worker
                ids (nodename->workerid). If given needs to hold worker
                ids for every node in topology.
            hostnamemapping: Optional dict to map workers by hostname to
                worker ids. If provided every worker hostname has to be mapped
                to exactly one id. If the cluster consists of N workers valid ids
                are 0 to N-1.
            sharemapping: Optional list to map worker ids to workload shares.
                sharemapping[x] is used to obtain the share of worker id x. Takes
                precedence over shares configured in config file. If given needs
                to hold share for every worker.
        """
        self.cluster = cluster
        self.logger = logging.getLogger(__name__)
        self.topology = None
        self.config = self.cluster.config
        self.starttime = time.localtime()
        self._printed_log_info = False
        self.isMonitoring = False
        self.shares = sharemapping
        self.nodemapping = nodemapping
        if is_partitioned:
            self.topology = topology
        else:
            self.origtopology = topology
        self.node_to_worker = {}
        self.node_to_wrapper = {}
        if(self.is_valid_hostname_mapping(hostnamemapping)):
            self.hostname_to_workerid = hostnamemapping
        else:
            if(not hostnamemapping is None):
                self.logger.error("invalid hostnamemapping!")
            self.hostname_to_workerid = self.generate_hostname_mapping()
        self.workerid_to_hostname = {}
        for hn in self.hostname_to_workerid:
            self.workerid_to_hostname[self.hostname_to_workerid[hn]] = hn
        self._update_shares()
        self.nodes = []
        self.hosts = []
        self.tunnellookup = {}
        self.switches = []
        self.switch = switch
        if controller:
            contr = controller
        else:
            contr = self.config.get_controller()
        if contr.find(":") >= 0:
            (host, port) = contr.split(":")
        else:
            host = contr
            port = "6633"
        self.controller = functools.partial(RemoteController, ip=host,
                                            port=int(port))

    def _update_shares(self):
        """helper function which reads workload shares per worker from
        config file. Has no effect if shares are already configured"""
        if(self.shares is None):
            ts = [1] * self.cluster.num_workers()
            for i in range(0, self.cluster.num_workers()):
                if(self._get_config_share(i)):
                    ts[i] = self._get_config_share(i)
            s = sum(ts)
            self.shares = []
            for i in range(0, self.cluster.num_workers()):
                self.shares.append(float(ts[i])/float(s))

    def _get_config_share(self, wid):
        """get workload share of worker with worker id wid"""
        hn = self.workerid_to_hostname[wid]
        if(self.config.has_section(hn) and self.config.has_option(hn, "share")):
            return self.config.getint(hn, "share")
        return None

    def generate_hostname_mapping(self):
        """generates a hostname-> workerid mapping dictionary"""
        i = 0
        d = {}
        for w in self.cluster.workers():
            d[w.hn()] = i
            i += 1
        return d

    def is_valid_hostname_mapping(self, d):
        """checks whether hostname -> workerid mappign is valid
        (every worker has exactly one workerid, workerids are contiguos from 0
        upwards)"""
        if(d is None):
            return False
        if(len(d) != len(self.cluster.workers())):
            return False
        for w in self.cluster.workers():
            if(not w.hn() in d.keys()):
                return False
        for i in range(0, len(self.cluster.workers())):
            if (d.values().count(i) != 1):
                return False
        return True

    def configLinkStatus(self, src, dst, status):
        """Change status of link.

        Change status (up/down) of link between two nodes.

        Args:
           src: Node name or NodeWrapper instance.
           dst: Node name or NodeWrapper instance.
           status: String {up, down}.
       """
        ws = self.get_worker(src)
        wd = self.get_worker(dst)
        if(ws == wd):
            # src and dst are on same worker. let mininet handle this
            ws.configLinkStatus(src, dst, status)
        else:
            src = self.get(src)
            dst = self.get(dst)
            intf = self.tunnellookup[(src.name, dst.name)]
            src.cmd("ifconfig " + intf + " " + status)
            dst.cmd("ifconfig " + intf + " " + status)

    @deprecated
    def find_worker(self, node):
        """Get worker instance which emulates the specified node.

        Replaced by get_worker.

        Args:
            node: nodename or NodeWrapper instance.

        Returns:
            Worker instance
        """
        return self.get_worker(node)

    def get_worker(self, node):
        """Get worker instance which emulates the specified node

        Args:
            node: Nodename or NodeWrapper instance.

        Returns:
            Worker instance
        """
        if(isinstance(node, NodeWrapper)):
            return node.worker
        return self.node_to_worker[node]

    def get_log_folder(self):
        """Get folder to which log files will be saved.

        Returns:
            Logfile folder as String.
        """
        return "/tmp/maxinet_logs/" + Tools.time_to_string(self.starttime) +\
               "/"

    def terminate_logging(self):
        """Stop logging."""
        for worker in self.cluster.workers():
            worker.run_cmd("killall mpstat getRxTx.sh getMemoryUsage.sh")

            #get CPU logs
            worker.get_file("/tmp/maxinet_cpu_" +
                        str(self.hostname_to_workerid[worker.hn()]) + "_(" + worker.hn() + ").log",
                        "/tmp/maxinet_logs/" +
                        Tools.time_to_string(self.starttime) + "/")
            #get memory logs
            worker.get_file("/tmp/maxinet_mem_" +
                            str(self.hostname_to_workerid[worker.hn()]) + "_(" + worker.hn() + ").log",
                            "/tmp/maxinet_logs/" +
                            Tools.time_to_string(self.starttime) + "/")

            #get interface logs
            intf = worker.run_cmd("ip addr show to " + worker.ip(classifier="backend") + "/24 " +
                                  "| head -n1 | cut -d' ' -f2 | tr -d :")\
                                  .strip()
            worker.get_file("/tmp/maxinet_intf_" + intf + "_" +
                        str(self.hostname_to_workerid[worker.hn()]) + "_(" + worker.hn() + ").log",
                        "/tmp/maxinet_logs/" +
                        Tools.time_to_string(self.starttime) + "/")

        self._print_log_info()
        self._print_monitor_info()
        self.isMonitoring = False

    def log_cpu(self):
        """Log cpu useage of workers.

        Places log files in /tmp/maxinet_logs/.
        """
        for worker in self.cluster.workers():
            self.log_cpu_of_worker(worker)

    def log_cpu_of_worker(self, worker):
        """Log cpu usage of worker.

        Places log file in /tmp/maxinet_logs/.
        """
        subprocess.call(["mkdir", "-p", "/tmp/maxinet_logs/" +
                         Tools.time_to_string(self.starttime) + "/"])
        worker.daemonize("LANG=en_EN.UTF-8 mpstat 1 | while read l; " +
                         "do echo -n \"`date +%s`    \" ; echo \"$l \" ;" +
                         " done > \"/tmp/maxinet_cpu_" + str(self.hostname_to_workerid[worker.hn()]) +
                         "_(" + worker.hn() + ").log\"")

    def log_free_memory(self):
        """Log memory usage of workers.

        Places log files in /tmp/maxinet_logs.
        Format is:
        timestamp,FreeMemory,Buffers,Cached
        """
        subprocess.call(["mkdir", "-p", "/tmp/maxinet_logs/" +
                         Tools.time_to_string(self.starttime) + "/"])
        for worker in self.cluster.workers():
            worker.daemonize_script("getMemoryUsage.sh", " > \"/tmp/maxinet_mem_" +
                             str(self.hostname_to_workerid[worker.hn()]) + "_(" + worker.hn() + ").log\"")

    def log_interfaces_of_node(self, node):
        """Log statistics of interfaces of node.

        Places logs in /tmp/maxinet_logs.
        Format is:
        timestamp,received bytes,sent bytes,received packets,sent packets
        """
        subprocess.call(["mkdir", "-p", "/tmp/maxinet_logs/" +
                         Tools.time_to_string(self.starttime) + "/"])
        node = self.get(node)
        worker = self.get_worker(node)
        for intf in node.intfNames():
            self.log_interface(worker, intf)

    def log_interface(self, worker, intf):
        """Log statistics of interface of worker.

        Places logs in /tmp/maxinet_logs.
        Format is:
        timestamp,received bytes,sent bytes,received packets,sent packets
        """
        worker.daemonize_script("getRxTx.sh", " " + intf + " > \"/tmp/maxinet_intf_" +
                         intf + "_" + str(self.hostname_to_workerid[worker.hn()]) + "_(" + worker.hn() +
                         ").log\"")

    def monitor(self):
        """Log statistics of worker interfaces and memory usage.

        Places log files in /tmp/maxinet_logs.
        """
        self.isMonitoring = True
        self.log_free_memory()
        self.log_cpu()
        for worker in self.cluster.workers():
            intf = worker.run_cmd("ip addr show to " + worker.ip(classifier="backend") + "/24 " +
                                  "| head -n1 | cut -d' ' -f2 | tr -d :")\
                                  .strip()
            if(intf == ""):
                self.logger.warn("could not find main eth interface for " +
                                 worker.hn() + ". no logging possible.")
            else:
                self.log_interface(worker, intf)

    def _print_log_info(self):
        """Place log info message in log if log functions where used.

        Prints info one time only even if called multiple times.
        """
        if(not self._printed_log_info):
            self._printed_log_info = True
            self.logger.info("Log files will be placed in /tmp/maxinet_logs/" +
                             Tools.time_to_string(self.starttime) + "/." +
                             " You might want to save them somewhere else.")

    def _print_monitor_info(self):
        """Place monitor info message in log if Experiment was monitored."""
        self.logger.info("You monitored this experiment. To generate a graph" +
                         " from your logs call " +
                         "\"/usr/local/share/MaxiNet/maxinet_plot.py " +
                         "/tmp/maxinet_logs/" +
                         Tools.time_to_string(self.starttime) +
                         "/ plot.png\" ")

    def CLI(self, plocals, pglobals):
        """Open interactive command line interface.

        Arguments are used to allow usage of python commands in the same
        scope as the one where CLI was called.

        Args:
            plocals: Dictionary as returned by locals()
            pglobals: Dictionary as returned by globals()
        """
        CLI(self, plocals, pglobals)

    def addNode(self, name, wid=None, pos=None):
        """Do bookkeeping to add a node at runtime.

        Use wid to specifiy worker id or pos to specify worker of
        existing node. If none is given random worker is chosen.
        This does NOT actually create a Node object on the mininet
        instance but is a helper function for addHost etc.

        Args:
            name: Node name.
            wid: Optional worker id to place node.
            pos: Optional existing node name whose worker should be used
                as host of node.
        """
        if (wid is None):
            wid = random.randint(0, self.cluster.num_workers() - 1)
        if (not pos is None):
            wid = self.hostname_to_workerid[self.node_to_worker[pos].hn()]
        self.node_to_worker[name] = self.cluster.get_worker(self.workerid_to_hostname[wid])
        self.node_to_wrapper[name] = NodeWrapper(name, self.get_worker(name))
        self.nodes.append(self.node_to_wrapper[name])


    def addHost(self, name, cls=None, wid=None, pos=None, **params):
        """Add host at runtime.

        Use wid to specifiy worker id or pos to specify worker of
        existing node. If none is given random worker is chosen.

        Args:
            name: Host name.
            cls: Optional mininet class to use for instanciation.
            wid: Optional worker id to place node.
            pos: Optional existing node name whose worker should be used
                as host of node.
            **params: parameters to use at mininet host class
                instanciation.
        """
        self.addNode(name, wid=wid, pos=pos)
        self.get_worker(name).addHost(name, cls=cls, **params)
        self.hosts.append(self.get(name))

        #deactivate TSO
        if (self.config.deactivateTSO()):
            for intf in self.get_node(name).intfNames():
                self.get_node(name).cmd("sudo ethtool -K %s tso off" % intf)

        #set MTU if necessary
        if (self.config.run_with_1500_mtu()):
            self.setMTU(self.get_node(name), 1450)

        return self.get(name)

    def addSwitch(self, name, cls=None, wid=None, pos=None, **params):
        """Add switch at runtime.

        Use wid to specifiy worker id or pos to specify worker of
        existing node. If none is given random worker is chosen.

        Args:
            name: Switch name.
            cls: Optional mininet class to use for instanciation.
            wid: Optional worker id to place node.
            pos: Optional existing node name whose worker should be used
                as host of node.
            **params: parameters to use at mininet switch class
                instanciation.
        """
        self.addNode(name, wid=wid, pos=pos)
        self.get_worker(name).addSwitch(name, cls, **params)
        self.switches.append(self.get(name))

        #set MTU if necessary
        if (self.config.run_with_1500_mtu()):
            self.setMTU(self.get_node(name), 1450)

        return self.get(name)

    def addController(self, name="c0", controller=None, wid=None, pos=None,
                      **params):
        """Add controller at runtime.

        Use wid to specifiy worker id or pos to specify worker of
        existing node. If none is given random worker is chosen.

        Args:
            name: Controller name.
            controller: Optional mininet class to use for instanciation.
            wid: Optional worker id to place node.
            pos: Optional existing node name whose worker should be used
                as host of node.
            **params: parameters to use at mininet controller class
                instanciation.
        """
        self.addNode(name, wid=wid, pos=pos)
        self.get_worker(name).addController(name, controller, **params)
        return self.get(name)

    def name(self, node):
        """Get name of network node.

        Args:
            node: Node name or NodeWrapper instance.

        Returns:
            String of node name.
        """
        if(isinstance(node, NodeWrapper)):
            return node.nn
        return node

    def addLink(self, node1, node2, port1=None, port2=None, cls=None,
                autoconf=False, **params):
        """Add link at runtime.

        Add link at runtime and create tunnels between workers if
        necessary. Will not work for mininet.node.UserSwitch switches.
        Be aware that tunnels will only work between switches so if you
        want to create a link using a host at one side make sure that
        both nodes are located on the same worker.
        autoconf parameter handles attach() and config calls on switches and
        hosts.

        Args:
            node1: Node name or NodeWrapper instance.
            node2: Node name or NodeWrapper instance.
            port1: Optional port number of link on node1.
            port2: Optional port number of link on node2.
            cls: Optional class to use on Link creation. Be aware that
                only mininet.link.Link and mininet.link.TCLink are
                supported for tunnels.
            autoconf: mininet requires some calls to makIe newly added
                tunnels work. If autoconf is set to True MaxiNet will
                issue these calls automatically.

        Raises:
            RuntimeError: If cls is not None or Link or TCLink and
                tunneling is needed.
        """
        w1 = self.get_worker(node1)
        w2 = self.get_worker(node2)
        if(not isinstance(node1, NodeWrapper)):
            node1 = self.get(node1)
        if(not isinstance(node2, NodeWrapper)):
            node2 = self.get(node2)
        if(w1 == w2):
            self.logger.debug("no tunneling needed")
            l = w1.addLink(self.name(node1), self.name(node2), port1, port2,
                           cls, **params)
        else:
            self.logger.debug("tunneling needed")
            if(not ((node1 in self.switches) and (node2 in self.switches))):
                self.logger.error("We cannot create tunnels between switches" +
                                  " and hosts. Sorry.")
                raise RuntimeError("Can't create tunnel between switch and" +
                                   "host")
            if(not ((cls is None) or isinstance(cls, Link) or
                    isinstance(cls, TCLink))):
                self.logger.error("Only Link or TCLink instances are " +
                                  "supported by MaxiNet")
                raise RuntimeError("Only Link or TCLink instances are " +
                                   "supported by MaxiNet")
            intfn = self.cluster.create_tunnel(w1, w2)
            if((cls is None) or isinstance(cls, TCLink)):
                intf = TCIntf
            else:
                intf = Intf
            w1.addTunnel(intfn, self.name(node1), port1, intf, **params)
            w2.addTunnel(intfn, self.name(node2), port2, intf, **params)
            l = ((self.name(node1), intfn), (self.name(node2), intfn))
        if(autoconf):
            if(node1 in self.switches):
                node1.attach(l[0][1])
            else:
                node1.configDefault()
            if(node2 in self.switches):
                node2.attach(l[1][1])
            else:
                node2.configDefault()
        if(self.config.run_with_1500_mtu()):
            self.setMTU(node1, 1450)
            self.setMTU(node2, 1450)

    def get_node(self, node):
        """Return NodeWrapper instance that is specified by nodename.

        Args:
            node: Nodename or nodewrapper instance.

        Returns:
            NodeWrapper instance with name nodename or None if none is
            found.
        """
        if(node in self.node_to_wrapper):
            return self.node_to_wrapper[node]
        else:
            return None

    def get(self, node):
        """Return NodeWrapper instance that is specified by nodename.

        Alias for get_node.

        Args:
            node: Nodename or nodewrapper instance.

        Returns:
            NodeWrapper instance with name nodename or None if none is
            found.
        """
        return self.get_node(node)

    def setup(self):
        """Start experiment.

        Partition topology (if needed), assign topology parts to workers and
        start mininet instances on workers.

        Raises:
            RuntimeError: If Cluster is too small.
        """
        self.logger.info("Clustering topology...")
        # partition topology (if needed)
        if(not self.topology):
            parti = Partitioner()
            parti.loadtopo(self.origtopology)
            if(self.nodemapping):
                self.topology = parti.partition_using_map(self.nodemapping)
            else:
                self.topology = parti.partition(self.cluster.num_workers(),
                                                shares=self.shares)
            self.logger.debug("Tunnels: " + str(self.topology.getTunnels()))
        subtopos = self.topology.getTopos()
        if(len(subtopos) > self.cluster.num_workers()):
            raise RuntimeError("Cluster does not have enough workers for " +
                               "given topology")
        # initialize internal bookkeeping
        for subtopo in subtopos:
            for node in subtopo.nodes():
                self.node_to_worker[node] = self.cluster.get_worker(self.workerid_to_hostname[subtopos.index(subtopo)])
                self.nodes.append(NodeWrapper(node, self.get_worker(node)))
                self.node_to_wrapper[node] = self.nodes[-1]
                if (not subtopo.isSwitch(node)):
                    self.hosts.append(self.nodes[-1])
                else:
                    self.switches.append(self.nodes[-1])
        # create tunnels
        tunnels = [[] for x in range(len(subtopos))]
        stt_tunnels = []
        for tunnel in self.topology.getTunnels():
            w1 = self.get_worker(tunnel[0])
            w2 = self.get_worker(tunnel[1])
            if not self.config.use_stt_tunneling():
                intf = self.cluster.create_tunnel(w1, w2)
            else:
                ip1, ip2, tid, tkey, intf = self.cluster.get_tunnel_metadata(w1, w2)
                stt_tunnels.append((w1, w2, ip1, ip2, tid, tkey, intf))
            self.tunnellookup[(tunnel[0], tunnel[1])] = intf
            self.tunnellookup[(tunnel[1], tunnel[0])] = intf
            for i in range(0, 2):
                # Assumes that workerid = subtopoid
                tunnels[self.hostname_to_workerid[self.node_to_worker[tunnel[i]].hn()]].append([intf,
                                                                  tunnel[i],
                                                                  tunnel[2]])
        # start mininet instances
        for topo in subtopos:
            wid = subtopos.index(topo)
            worker = self.cluster.get_worker(self.workerid_to_hostname[wid])
            worker.set_switch(self.switch)
            # cache hostname for possible error message
            thn = worker.hn()
            try:
                if(self.controller):
                    worker.start(
                        topo=topo,
                        tunnels=tunnels[subtopos.index(topo)],
                        controller=self.controller)
                else:
                    worker.start(
                        topo=topo,
                        tunnels=tunnels[wid])
            except Pyro4.errors.ConnectionClosedError:
                self.logger.error("Remote " + thn + " exited abnormally. " +
                                  "This is probably due to mininet not" +
                                  " starting up. You might want to have a look"+
                                  " at the output of the MaxiNetWorker calls on"+
                                  " the Worker machines.")
                raise
        # configure network if needed
        if (self.config.run_with_1500_mtu()):
            for topo in subtopos:
                for host in topo.nodes():
                    self.setMTU(self.get(host), 1450)

        #deactivate TSO if needed
        if (self.config.deactivateTSO()):
            for topo in subtopos:
                for host in topo.nodes():
                    for intf in self.get(host).intfNames():
                        self.get(host).cmd("sudo ethtool -K %s tso off" % intf)
        for (w1, w2, ip1, ip2, tid, tkey, intf) in stt_tunnels:
            w1.run_cmd("ovs-vsctl -- set interface %s type=stt options=\"remote_ip=%s,local_ip=%s,key=%i\"" % (intf, ip2, ip1, tkey))
            w2.run_cmd("ovs-vsctl -- set interface %s type=stt options=\"remote_ip=%s,local_ip=%s,key=%i\"" % (intf, ip1, ip2, tkey))
        # start mininet instances

    def setMTU(self, host, mtu):
        """Set MTUs of all Interfaces of mininet host.

        Args:
            host: NodeWrapper instance or nodename.
            mtu: MTU value.
        """
        if(not isinstance(host, NodeWrapper)):
            host = self.get(host)
        for intf in host.intfNames():
            host.cmd("ifconfig %s mtu %i" % (intf, mtu))

    @deprecated
    def run_cmd_on_host(self, host, cmd):
        """Run cmd on mininet host.

        Run cmd on emulated host specified by host and return
        output.
        This function is deprecated and will be removed in a future
        version of MaxiNet. Use Experiment.get(node).cmd() instead.

        Args:
            host: Hostname or NodeWrapper instance.
            cmd: Command to run as String.
        """
        return self.get_worker(host).run_cmd_on_host(host, cmd)

    def stop(self):
        """Stop experiment and shut down emulation on workers."""
        if self.isMonitoring:
            self.terminate_logging()
        for worker in self.cluster.workers():
            worker.stop()
        self.cluster.remove_all_tunnels()


class NodeWrapper(object):
    """Wrapper that allows most commands that can be used in mininet to be
    used in MaxiNet as well.

    Whenever you call for example
    > exp.get("h1")
    you'll get an instance of NodeWrapper which will forward calls to
    the respective mininet node.

    Mininet method calls that SHOULD work:
    "IP", "MAC", "attach", "cfsInfo", "cgroupGet", "cgroupDel",
    "cgroupSet", "cleanup", "cmd", "cmdPrint", "config",
    "configDefault", "connected", "controllerUUIDs", "defaultDpid",
    "detach", "dpctl", "intfIsUp", "intfNames", "monitor", "newPort",
    "pexec", "read", "readline", "rtInfo", "sendCmd", "sendInt",
    "setARP", "setCPUFrac", "setCPUs", "setIP", "setup", "start",
    "stop", "terminate", "waitOutput", "waitReadable", "write"

    Mininet attributes that SHOULD be gettable:
    "inNamespace", "name", "params", "waiting"

    Containernet Docker Host method calls that SHOULD work:
    "updateCpuLimit", "updateMemoryLimit", "cgroupSet", "cgroupGet",
    "update_resources"

    Containernet Docker Host attributes that SHOULD be gettable:
    "dimage", "resources", "volumes"

    Attributes:
        nn: Node name as String.
        worker: Worker instance on which node is hosted.
    """

    # this feels like doing rpc via rpc...

    def __init__(self, nodename, worker):
        """Inits NodeWrapper.

        The NodeWrapper does not create a node on the worker. For this
        reason the node should already exist on the Worker when
        NodeWrapper.__init__ gets called.

        Args:
            nodename: Node name as String
            worker: Worker instance
        """
        self.nn = nodename
        self.worker = worker

    def is_docker(self):
        """Checks if the node wrapper belongs to a docker host."""
        return self._get("__class__").__name__ == "Docker"

    def is_libvirt(self):
        """Checks if the node wrapper belongs to a LibvirtHost."""
        return self._get("__class__").__name__ == "LibvirtHost"

    def _call(self, cmd, *params1, **params2):
        """Send method call to remote mininet instance and get return.

        Args:
            cmd: method name as String.
            *params1: unnamed parameters for call.
            **params2: named parameters for call.
        """
        return self.worker.rpc(self.nn, cmd, *params1, **params2)

    def _get(self, name):
        """Return attribut name of remote node."""
        return self.worker.rattr(self.nn, name)

    def __getattr__(self, name):
        def method(*params1, **params2):
            return self._call(name, *params1, **params2)

        # The following commands and attributes did NOT work, when last tested.
        # They are deactivated to avoid confusion. This is mostly caused by
        # Pyro4 related serialization problems.
        if name in [
            # methods:
            "addIntf", "checkListening", "chrt", "connectionsTo",
            "defaultIntf", "deleteIntfs", "intf"
            # attributes:
            "nameToIntf"
        ]:
            raise NotImplementedError(
                str(name)
                + ": Explicitly disabled due to serialization problems. "
                + "To force access use the _call or _get methods manually. "
                + "Use at own risk."
            )

        # the following attributes and methods SHOULD work. no guarantee given
        if name in [
            "IP", "MAC", "attach", "cfsInfo", "cgroupGet", "cgroupDel",
            "cgroupSet", "cleanup", "cmd", "cmdPrint", "config",
            "configDefault", "connected", "controllerUUIDs", "defaultDpid",
            "detach", "dpctl", "intfIsUp", "intfNames", "monitor", "newPort",
            "pexec", "read", "readline", "rtInfo", "sendCmd", "sendInt",
            "setARP", "setCPUFrac", "setCPUs", "setIP", "setup", "start",
            "stop", "terminate", "waitOutput", "waitReadable", "write"
        ]:
            return method
        elif name in ["dpid", "inNamespace", "name", "params", "waiting"]:
            return self._get(name)

        # Containernet specific
        elif self.is_docker():
            if name in ["updateCpuLimit", "updateMemoryLimit", "cgroupSet",
                        "cgroupGet", "update_resources"]:
                return method
            elif name in ["dimage", "resources", "volumes"]:
                return self._get(name)
        elif self.is_libvirt():
            if name in ["updateCpuLimit", "updateMemoryLimit", "update_resources"]:
                return method
            elif name in ["disk_image", "resources"]:
                return self._get(name)
        else:
            raise AttributeError(name)

    def __repr__(self):
        return "NodeWrapper (" + self.nn + " at " + str(self.worker) + ")"
