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

from mininet.node import RemoteController, UserSwitch
from mininet.link import TCIntf, Intf, Link, TCLink
import Pyro4

from MaxiNet.Frontend.cli import CLI
from MaxiNet.Frontend.client import Frontend, log_and_reraise_remote_exception
from MaxiNet.Frontend.tools import Tools, Config
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
            of program arguments.

    Returns:
        Stdout of cmd call as string.
    """
    return subprocess.check_output(cmd, shell=True)


class Worker(object):

    """Worker class used to manage an individual Worker host.

    A Worker is part of a Cluster and runs a part of the emulated
    network.

    Attributes:
        cmd: remote instance of class CmdListener which is used to run
            commands on the Worker machine.
        config: remote instance of class Config which is used to query
            configuration settings etc.
        creator: remote instance of class MininetCreator which is used
                to create and manage mininet instances.
        switch: default mininet switch class to use in mininet instances.
        wid: worker id.
    """

    def __init__(self, frontend, wid, switch=UserSwitch):
        """Init Worker class."""
        self.creator = frontend.getObjectProxy(wid + ".mnCreator")
        self.cmd = frontend.getObjectProxy(wid + ".cmd")
        self.config = frontend.getObjectProxy("config")
        if(not self.config.runWith1500MTU()):
            self._fix_mtus()
        self.switch = switch
        self._x11tunnels = []
        self.wid = int(wid[6:])

    @log_and_reraise_remote_exception
    def hn(self):
        """Get hostname of worker machine."""
        return self.cmd.get_hostname()

    def set_switch(self, switch):
        """Set default switch class."""
        self.switch = switch

    @log_and_reraise_remote_exception
    def configLinkStatus(self, src, dst, status):
        """Wrapper for configLinkStatus method on remote mininet.

        Used to enable and disable links.

        Args:
            src: name of source node
            dst: name of destination node
            status: string {up|down}

        """
        self.creator.configLinkStatus(src, dst, status)

    @log_and_reraise_remote_exception
    def ip(self):
        """Get public ip adress of worker machine."""
        return self.config.getIP(self.hn())

    @log_and_reraise_remote_exception
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
        if controller:
            self.creator.create_mininet(topo=topo, tunnels=tunnels,
                                        controller=controller,
                                        switch=self.switch)
        else:
            self.creator.create_mininet(topo=topo, tunnels=tunnels,
                                        switch=self.switch)

    @log_and_reraise_remote_exception
    def daemonize(self, cmd):
        """run command in background and terminate when MaxiNet is shut
        down."""
        self.cmd.daemonize(cmd)

    @log_and_reraise_remote_exception
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
                display = subprocess.check_output("ssh -Y " + self.hn() +
                                                  " env | grep DISPLAY",
                                                  shell=True)[8:]
                self.creator.tunnelX11(node, display)
                self._x11tunnels.append(node)
            except subprocess.CalledProcessError:
                return False
        return True

    @log_and_reraise_remote_exception
    def run_cmd_on_host(self, host, cmd):
        """Run cmd in context of host and return output.

        Args:
            host: nodename
            cmd: string of program name and arguments to call.

        Returns:
            Stdout of program call.
        """
        return self.creator.runCmdOnHost(host, cmd)

    @log_and_reraise_remote_exception
    def run_cmd(self, cmd):
        """run cmd on worker machine and return output.

        Args:
            cmd: string of program name and arguments to call.

        Returns:
            Stdout of program call.
        """
        return self.cmd.check_output(cmd)

    @log_and_reraise_remote_exception
    def run_script(self, cmd):
        """Run MaxiNet script on worker machine and return output.

        Args:
            cmd: String of name of MaxiNet script and arguments.

        Returns:
            Stdout of program call.
        """
        return self.cmd.script_check_output(cmd)

    @log_and_reraise_remote_exception
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
        return self.creator.rpc(host, cmd, *params1, **params2)

    @log_and_reraise_remote_exception
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
        return self.creator.attr(host, name)

    @log_and_reraise_remote_exception
    def _fix_mtus(self):
        """If mtu of Worker is lower than 1600 set it to 1600.

        In order to transfer 1500 byte long packets over GRE tunnels
        the MTU of the interface which "transfers" the tunnel has to be
        set to 1600.
        This method tries to determine the correct network interface and
        sets its MTU. This method is not needed if MaxiNet is configured
        to use MTUs lower than 1451 in the MaxiNet configuration file.
        """
        if self.ip() is None:
            logger.warn("no ip configured - can not fix MTU ")
            return 0
        intf = self.run_cmd("ip addr show to " + self.ip() +
                            "/24 | head -n1 | cut -d' ' -f2 | tr -d :").strip()
        if intf == "":
            logger.warn("could not find eth device - can not fix MTU")
            return 0
        mtu = int(self.run_cmd("ip li show dev " + intf +
                               " | head -n1 | cut -d ' ' -f5"))
        if(mtu < 1600):
            self.run_cmd("ip li se dev " + intf + " mtu 1600")

    @log_and_reraise_remote_exception
    def stop(self):
        """Stop mininet instance on this worker."""
        return self.creator.stop()

    def get_file(self, src, dst):
        """Transfer file specified by src on worker to dst on Frontend.

        Transfers file src to filename or folder dst on Frontend machine
        via scp.

        Args:
            src: string of path to file on Worker
            dst: string of path to file or folder on Frontend
        """
        cmd_get = ["scp", self.hn() + ":\"" + src + "\"", dst]
        subprocess.call(cmd_get)

    def put_file(self, src, dst):
        """transfer file specified by src on Frontend to dst on worker.

        Transfers file src to filename or folder dst on Worker machine
        via scp.
        Args:
            src: string of path to file on Frontend
            dst: string of path to file or folder on Worker
        """
        cmd_put = ["scp", src, self.hn() + ":" + dst]
        subprocess.call(cmd_put)

    @log_and_reraise_remote_exception
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
        return self.creator.addHost(name, cls, **params)

    @log_and_reraise_remote_exception
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
        return self.creator.addSwitch(name, cls, **params)

    @log_and_reraise_remote_exception
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
        return self.creator.addHost(name, controller, **params)

    @log_and_reraise_remote_exception
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
        self.creator.addTunnel(name, switch, port, intf, **params)

    @log_and_reraise_remote_exception
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
        return self.creator.addLink(node1, node2, port1, port2, cls,
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
        hosts: List of worker hostnames.
        localIP: IPv4 address of the Frontend.
        logger: Logging instance.
        nsport: Nameserver port number.
        running: Cluster is initialized and ready to run an experiment.
            Can be queryd by Cluster.is_running() and gets set by
            successfully calling Cluster.start().
        tunhelper: Instance of TunHelper to enumerate tunnel instances.
        worker: List of worker instances. Index of worker instance in
            sequence must be equal to worker id.
    """

    def __init__(self, *hosts):
        """Inits Cluster class.

        Args:
            *hosts: Optional list of Worker hostnames to use in this
                cluster. If not set all configured Workers will be used.
        """
        self.running = False
        self.logger = logging.getLogger(__name__)
        self.tunhelper = TunHelper()
        # we can't open our pyro server yet (we need the local ip first)
        # but need to read the config file. Therefore we do not register
        # the config instance and replace it later on.
        self.config = Config("", "", register=False)
        logging.basicConfig(level=self.config.getLoggingLevel())
        if hosts:
            self.hosts = hosts
        else:
            self.hosts = self.config.getHosts()
        self.worker = []

        #Find local IP
        if(self.hosts[0] != subprocess.check_output(["hostname"]).strip()):
            rhost = self.config.getIP(self.hosts[0])
        else:
            if(len(self.hosts) > 1):
                rhost = self.config.getIP(self.hosts[1])
            else:
                rhost = self.config.getIP(self.hosts[0])
        if sys.platform == "darwin":
            route = subprocess.check_output(["route", "-vn", "get", rhost])\
                    .splitlines()[-1]
            m = re.search(r' (\d+\.\d+\.\d+\.\d+)$', route)
        else:
            route = subprocess.check_output("ip route get " + rhost +
                                            " | head -n1", shell=True).strip()
            m = re.search(r'src (\d+\.\d+\.\d+\.\d+)', route)
        if m is not None:
            self.localIP = m.group(1)
        else:
            self.localIP = "127.0.0.1"

        self.nsport = 9090
        self.frontend = Frontend(self.localIP, self.nsport)
        # now replace self.config with instance that connects to pyro
        self.config = Config(self.localIP, self.nsport)
        atexit.register(run_cmd, self.getWorkerMangerCMD("--stop"))
        atexit.register(self._stop)

    def getWorkerMangerCMD(self, cmd):
        """Get string sequence to call worker_manager.py script with cmd
        argument.

        Returns a string sequence which contains the path to the
        worker_manager.py script enhanced with the arguments nameserver
        ip and port, debugPyro flag (if set in config) and
        keepScreenOpenOnError flag (if set in config). Also includes cmd
        as arguments.

        Args:
            cmd: Sequence of arguments to pass to worker_manager.py.

        Returns:
            Sequence of strings to be passed to eg subprocess.call to
            call worker_manager.py script and configured arguments.
        """
        cmdline = [
            self.config.getWorkerScript("worker_manager.py"), "--ns",
            self.localIP + ":" + str(self.nsport),
            cmd
        ]
        if self.config.debugPyroOnWorker():
            cmdline.append("--debugPyro")

        if self.config.keepScreenOpenOnError():
            cmdline.append("--keepScreenOpenOnError")
        cmdline.extend(self.hosts)
        return cmdline

    def is_running(self):
        """Query self.running flag to check whether cluster was already
        started."""
        return self.running

    def get_worker_shares(self):
        """Returns sequence of workload shares per Worker.

        Will return None if Cluster is not already running. This is due
        to the fact that worker order is not final before Cluster
        statup.

        Returns:
            Sequence of workload shares per worker. Order is same as
            self.workers() order. None if Cluster is not already running.
        """
        shares = None
        if(self.running):
            shares = []
            for w in self.workers():
                shares.append(self.config.getShare(w.hn()))
            wsum = 0
            for w in shares:
                wsum += w
            shares = map(lambda x: x / float(wsum), shares)
        return shares

    def check_reachability(self, ip):
        """Check whether ip is reachable for a packet with MTU > 1500.

        If this check fails either the network needs to be reconfigured
        or runWith1500MTU flag in MaxiNet config needs to be set.
        """
        cmd = ["ping", "-c 2", "-s 1520", ip]
        if(subprocess.call(cmd, stdout=open("/dev/null"),) == 1):
            return False
        else:
            return True

    def start(self):
        """Start cluster (and Workers).

        Start MaxiNet on assigned worker machines and establish
        communication. Sets self.running flag in case of successful
        startup.

        Returns:
            True if startup was successful.
        """
        self.logger.info("starting worker processes")
        #start worker processes
        cmd = self.getWorkerMangerCMD("--start")
        if self.frontend.hmac_key():
            cmd.extend(["--hmac", self.frontend.hmac_key()])
        self.logger.debug(run_cmd(cmd))
        #connect to pyro instances of workers
        timeout = 10  # timeout (seconds) for worker startup
        for i in range(0, len(self.hosts)):
            self.logger.info("waiting for Worker " + str(i + 1) +
                             " to register on nameserver...")
            started = False
            end = time.time() + timeout
            while(not started):
                try:
                    self.frontend.lookup("worker" + str(i + 1) + ".mnCreator")
                    started = True
                except Pyro4.errors.NamingError:
                    if(time.time() > end):
                        raise RuntimeError("Timed out waiting for worker " +
                                           str(i + 1) + ".mnCreator to " +
                                           "register.")
                    time.sleep(0.1)
            started = False
            end = time.time() + timeout
            while(not started):
                try:
                    self.frontend.lookup("worker" + str(i + 1) + ".cmd")
                    started = True
                except Pyro4.errors.NamingError:
                    time.sleep(0.1)
                    if(time.time() > end):
                        raise RuntimeError("Timed out waiting for worker " +
                                           str(i + 1) + ".cmd to register.")
            self.worker.append(Worker(self.frontend, "worker" + str(i + 1)))
        #check reachability
        if(not self.config.runWith1500MTU()):
            for host in self.hosts:
                if(not self.check_reachability(self.config.getIP(host))):
                    self.logger.error("Host " + host +
                                      " is not reachable with an MTU > 1500.")
                    raise RuntimeError("Host " + host +
                                       " is not reachable with an MTU > 1500.")
        #load tunneling kernel modules on workers
        for worker in self.worker:
            worker.run_script("load_tunneling.sh")
        self.logger.info("worker processes started")
        self.running = True
        return True

    def _stop(self):
        """Stop Cluster and shut it down.

        Shuts down cluster and removes pyro nameserver entries but
        DOES NOT shut down workers. Call this after shutting down
        workers via worker_manager.py script.
        """
        if(self.running):
            self.logger.info("removing tunnels...")
            self.remove_all_tunnels()
            #self.logger.info("shutting cluster down...")
            self.logger.info("removing nameserver entries...")
            for i in range(0, self.num_workers()):
                self.frontend.remove("worker" + str(i) + ".mnCreator")
                self.frontend.remove("worker" + str(i) + ".cmd")
            self.logger.info("shutting down frontend...")
            self.logger.info("Goodbye.")
            self.running = False

    def num_workers(self):
        """Return number of worker nodes in this Cluster."""
        return len(self.workers())

    def workers(self):
        """Return sqeuence of worker instances for this cluster.

        Returns empty sequence if Cluster is not running.

        Returns:
            Sequence of worker instances. Empty sequence if cluster is
            not running.
        """
        if(self.is_running()):
            return self.worker
        else:
            return []

    def get_worker(self, wid):
        """Return worker with id wid.

        Args:
            wid: worker id

        Returns:
            Worker with id wid.
        """
        return self.workers()[wid]

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
        tid = self.tunhelper.get_tun_nr()
        tkey = self.tunhelper.get_key_nr()
        intf = "mn_tun" + str(tid)
        ip1 = w1.ip()
        ip2 = w2.ip()
        self.logger.debug("invoking tunnel create commands on " + ip1 +
                          " and " + ip2)
        w1.run_script("create_tunnel.sh " + ip1 + " " + ip2 + " " + intf +
                      " " + str(tkey))
        w2.run_script("create_tunnel.sh " + ip2 + " " + ip1 + " " + intf +
                      " " + str(tkey))
        self.logger.debug("tunnel " + intf + " created.")
        return intf

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
        hosts: List of host NodeWrapper instances.
        isMonitoring: True if monitoring is in use.
        logger: Logging instance.
        nodemapping: optional dict to map nodes to specific workers ids.
        nodes: List of NodeWrapper instances.
        node_to_workerid: Dict to map node name (string) to worker id.
        node_to_wrapper: Dict to map node name (string) to NodeWrapper
            instance.
        origtopology: Unpartitioned topology if topology was partitioned
            by MaxiNet.
        starttime: Time at which Experiment was instanciated. Used for
            logfile creation.
        switch: Default mininet switch class to use.
        switches: List of switch NodeWrapper instances.
        topology: instance of MaxiNet.Frontend.paritioner.Clustering
        tunnellookup: Dict to map tunnel tuples (switchname1,switchname2)
            to tunnel names. Order of switchnames can be ignored as both
            directions are covered.
    """
    def __init__(self, cluster, topology, controller=None,
                 is_partitioned=False, switch=UserSwitch,
                 nodemapping=None):
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
        """
        self.cluster = cluster
        self.logger = logging.getLogger(__name__)
        self.topology = None
        self.config = Config(register=False)
        self.starttime = time.localtime()
        self._printed_log_info = False
        self.isMonitoring = False
        self.nodemapping = nodemapping
        if is_partitioned:
            self.topology = topology
        else:
            self.origtopology = topology
        self.node_to_workerid = {}
        self.node_to_wrapper = {}
        self.nodes = []
        self.hosts = []
        self.tunnellookup = {}
        self.switches = []
        self.switch = switch
        if controller:
            contr = controller
        else:
            contr = self.config.getController()
        if contr.find(":") >= 0:
            (host, port) = contr.split(":")
        else:
            host = contr
            port = "6633"
        self.controller = functools.partial(RemoteController, ip=host,
                                            port=int(port))

    def configLinkStatus(self, src, dst, status):
        """Change status of link.

        Change status (up/down) of link between two nodes.

        Args:
           src: Node name.
           dst: Node name.
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
            node: nodename.

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
        return self.cluster.get_worker(self.node_to_workerid[node])

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
            worker.run_cmd("killall getRxTx.sh getMemoryUsage.sh")
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
        atexit.register(worker.get_file, "/tmp/maxinet_cpu_" +
                        str(worker.wid) + "_(" + worker.hn() + ").log",
                        "/tmp/maxinet_logs/" +
                        Tools.time_to_string(self.starttime) + "/")
        worker.daemonize("LANG=en_EN.UTF-8 mpstat 1 | while read l; " +
                         "do echo -n \"`date +%s`    \" ; echo \"$l \" ;" +
                         " done > \"/tmp/maxinet_cpu_" + str(worker.wid) +
                         "_(" + worker.hn() + ").log\"")
        atexit.register(self._print_log_info)

    def log_free_memory(self):
        """Log memory usage of workers.

        Places log files in /tmp/maxinet_logs.
        Format is:
        timestamp,FreeMemory,Buffers,Cached
        """
        subprocess.call(["mkdir", "-p", "/tmp/maxinet_logs/" +
                         Tools.time_to_string(self.starttime) + "/"])
        for worker in self.cluster.workers():
            atexit.register(worker.get_file, "/tmp/maxinet_mem_" +
                            str(worker.wid) + "_(" + worker.hn() + ").log",
                            "/tmp/maxinet_logs/" +
                            Tools.time_to_string(self.starttime) + "/")
            memmon = worker.config.getWorkerScript("getMemoryUsage.sh")
            worker.daemonize(memmon + " > \"/tmp/maxinet_mem_" +
                             str(worker.wid) + "_(" + worker.hn() + ").log\"")
            atexit.register(self._print_log_info)

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
        atexit.register(worker.get_file, "/tmp/maxinet_intf_" + intf + "_" +
                        str(worker.wid) + "_(" + worker.hn() + ").log",
                        "/tmp/maxinet_logs/" +
                        Tools.time_to_string(self.starttime) + "/")
        ethmon = worker.config.getWorkerScript("getRxTx.sh")
        worker.daemonize(ethmon + " " + intf + " > \"/tmp/maxinet_intf_" +
                         intf + "_" + str(worker.wid) + "_(" + worker.hn() +
                         ").log\"")
        atexit.register(self._print_log_info)

    def monitor(self):
        """Log statistics of worker interfaces and memory usage.

        Places log files in /tmp/maxinet_logs.
        """
        self.isMonitoring = True
        atexit.register(self._print_monitor_info)
        self.log_free_memory()
        self.log_cpu()
        for worker in self.cluster.workers():
            intf = worker.run_cmd("ip addr show to " + worker.ip() + "/24 " +
                                  "| head -n1 | cut -d' ' -f2 | tr -d :")\
                                  .strip()
            if(intf == ""):
                self.logger.warn("could not find main interface for " +
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
        else:
            wid = wid - 1  # internal worker id count starts with 0
        if (not pos is None):
            wid = self.node_to_workerid[pos]
        self.node_to_workerid[name] = wid
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
            autoconf: mininet requires some calls to make newly added
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
                                   "supported by MaxiNe")
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
        if(self.config.runWith1500MTU()):
            self.setMTU(node1, 1450)
            self.setMTU(node2, 1450)

    def get_node(self, nodename):
        """Return NodeWrapper instance that is specified by nodename.

        Args:
            nodename: Nodename.

        Returns:
            NodeWrapper instance with name nodename or None if none is
            found.
        """
        if(nodename in self.node_to_wrapper):
            return self.node_to_wrapper[nodename]
        else:
            return None

    def get(self, nodename):
        """Return NodeWrapper instance that is specified by nodename.

        Alias for get_node.

        Args:
            nodename: Nodename.

        Returns:
            NodeWrapper instance with name nodename or None if none is
            found.
        """
        return self.get_node(nodename)

    def setup(self):
        """Start experiment.

        Start cluster if not yet started, partition topology (if needed)
        and assign topology parts to workers and start workers.

        Raises:
            RuntimeError: If Cluster is too small or won't start.
        """
        # start cluster
        if(not self.cluster.is_running()):
            self.cluster.start()
        if(not self.cluster.is_running()):
            raise RuntimeError("Cluster won't start")
        self.logger.info("Clustering topology...")
        # partition topology (if needed)
        if(not self.topology):
            parti = Partitioner()
            parti.loadtopo(self.origtopology)
            if(self.nodemapping):
                self.topology = parti.partition_using_map(self.nodemapping)
            else:
                # assigning shares to workers requires that the workers
                # are already startet. elsewise we don't have a way to
                # determine the workerid of the worker. topologies are
                # assigned to workers in ascending workerid order
                self.topology = parti.partition(self.cluster.num_workers(),
                                                self.cluster.get_worker_shares())
            self.logger.debug("Tunnels: " + str(self.topology.getTunnels()))
        subtopos = self.topology.getTopos()
        if(len(subtopos) > self.cluster.num_workers()):
            raise RuntimeError("Cluster does not have enough workers for " +
                               "given topology")
        # initialize internal bookkeeping
        for subtopo in subtopos:
            for node in subtopo.nodes():
                self.node_to_workerid[node] = subtopos.index(subtopo)
                self.nodes.append(NodeWrapper(node, self.get_worker(node)))
                self.node_to_wrapper[node] = self.nodes[-1]
                if (not subtopo.isSwitch(node)):
                    self.hosts.append(self.nodes[-1])
                else:
                    self.switches.append(self.nodes[-1])
        self.logger.debug("Nodemapping: %s", self.node_to_workerid)
        # create tunnels
        tunnels = [[] for x in range(len(subtopos))]
        for tunnel in self.topology.getTunnels():
            w1 = self.get_worker(tunnel[0])
            w2 = self.get_worker(tunnel[1])
            intf = self.cluster.create_tunnel(w1, w2)
            self.tunnellookup[(tunnel[0], tunnel[1])] = intf
            self.tunnellookup[(tunnel[1], tunnel[0])] = intf
            for i in range(0, 2):
                # Assumes that workerid = subtopoid
                tunnels[self.node_to_workerid[tunnel[i]]].append([intf,
                                                                  tunnel[i],
                                                                  tunnel[2]])
        # start mininet instances
        for topo in subtopos:
            self.cluster.workers()[subtopos.index(topo)]\
                .set_switch(self.switch)
            # cache hostname for possible error message
            thn = self.cluster.workers()[subtopos.index(topo)].hn()
            try:
                if(self.controller):
                    self.cluster.workers()[subtopos.index(topo)]\
                        .start(topo=topo,
                               tunnels=tunnels[subtopos.index(topo)],
                               controller=self.controller)
                else:
                    self.cluster.workers()[subtopos.index(topo)]\
                        .start(topo=topo,
                               tunnels=tunnels[subtopos.index(topo)])
            except Pyro4.errors.ConnectionClosedError:
                self.logger.error("Remote " + thn + " exited abnormally. " +
                                  "This is probably due to mininet not" +
                                  " starting up. Have a look at " +
                                  "https://github.com/MaxiNet/MaxiNet/wiki/Debugging-MaxiNet#retrieving-worker-output" +
                                  " to debug this.")
                raise
        # configure network if needed
        if (self.config.runWith1500MTU()):
            for topo in subtopos:
                for host in topo.nodes():
                    self.setMTU(host, 1450)

    def setMTU(self, host, mtu):
        """Set MTUs of all Interfaces of mininet host.

        Args:
            host: NodeWrapper instance or nodename.
            mtu: MTU value.
        """
        if(not isinstance(host, NodeWrapper)):
            host = self.get(host)
        for intf in host.intfNames():
            host.cmd("ifconfig " + intf + " mtu " + str(mtu))

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
    "cleanup", "read", "readline", "write", "terminate",
    "stop", "waitReadable", "sendCmd", "sendInt", "monitor",
    "waitOutput", "cmd", "cmdPrint", "pexec", "newPort",
    "addIntf", "defaultIntf", "intf", "connectionsTo",
    "deleteIntfs", "setARP", "setIP", "IP", "MAC", "intfIsUp",
    "config", "configDefault", "intfNames", "cgroupSet",
    "cgroupGet", "cgroupDel", "chrt", "rtInfo", "cfsInfo",
    "setCPUFrac", "setCPUs", "defaultDpid", "defaultIntf",
    "connected", "setup", "dpctl", "start", "stop", "attach",
    "detach", "controllerUUIDs", "checkListening"

    Mininet attributes that SHOULD be queryable:
    "name", "inNamespace", "params", "nameToIntf", "waiting"

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
        # the following commands SHOULD work. no guarantee given
        if name in [
                "cleanup", "read", "readline", "write", "terminate",
                "stop", "waitReadable", "sendCmd", "sendInt", "monitor",
                "waitOutput", "cmd", "cmdPrint", "pexec", "newPort",
                "addIntf", "defaultIntf", "intf", "connectionsTo",
                "deleteIntfs", "setARP", "setIP", "IP", "MAC", "intfIsUp",
                "config", "configDefault", "intfNames", "cgroupSet",
                "cgroupGet", "cgroupDel", "chrt", "rtInfo", "cfsInfo",
                "setCPUFrac", "setCPUs", "defaultDpid", "defaultIntf",
                "connected", "setup", "dpctl", "start", "stop", "attach",
                "detach", "controllerUUIDs", "checkListening"
        ]:
            return method
        elif name in ["name", "inNamespace", "params", "nameToIntf",
                      "waiting"]:
            return self._get(name)
        else:
            raise AttributeError(name)

    def __repr__(self):
        return "NodeWrapper (" + self.nn + " at " + str(self.worker) + ")"
