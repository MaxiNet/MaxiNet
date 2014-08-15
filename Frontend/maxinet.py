#!/usr/bin/python
"""
This module is the central part of MaxiNet and is intended to be the only
part of MaxiNet which needs to be used by the user or third-party applications
"""

import os,re, sys
import logging
import tools
import config
from mininet.node import RemoteController, OVSSwitch, UserSwitch
from mininet.topo import Topo
from functools import partial
from client import Frontend, log_and_reraise_remote_exception, remote_exceptions_logged_and_reraised
import time
import Pyro4
import subprocess
import random
import atexit
import traceback
from partitioner import Partitioner
from cli import CLI



# the following block is to support deprecation warnings. this is really not
# solved nicely and should probably be somewhere else
import warnings
import functools
logger = logging.getLogger(__name__)
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
            lineno=func.func_code.co_firstlineno + 1
        )
        return func(*args, **kwargs)
    return new_func


def run_cmd(cmd):
    """
    run cmd on frontend machine
    """
    return subprocess.check_output(cmd,shell=False)

def run_cmd_shell(cmd):
    """
    run cmd on frontend machine with the shell
    """
    return subprocess.check_output(cmd,shell=True)

class Worker:
    """
    represents a worker machine in an running experiment
    """

    def __init__(self,frontend,wid,switch=UserSwitch):
        self.creator = frontend.getObjectProxy(wid+".mnCreator")
        self.cmd = frontend.getObjectProxy(wid+".cmd")
        self.config = frontend.getObjectProxy("config")
        if(not self.config.runWith1500MTU()):
            self._fix_mtus()
        self.switch=switch
        self.x11tunnels=[]
        self.wid=int(wid[6:])
    
    @log_and_reraise_remote_exception
    def hn(self):
        """
        return hostname of worker machine
        """
        return self.cmd.get_hostname()

    def set_switch(self,switch):
        """
        set default switch class
        """
        self.switch=switch

    @log_and_reraise_remote_exception
    def configLinkStatus(self, src, dst, status):
        """
        wrapper for configLinkStatus method on remote mininet"""
        self.creator.configLinkStatus(src,dst,status)
    
    @log_and_reraise_remote_exception
    def ip(self):
        """
        return public ip adress of worker machine
        """
        return self.config.getIP(self.hn())
    
    @log_and_reraise_remote_exception
    def start(self,topo,tunnels, controller=None):
        """
        start mininet instance on worker machine emulating the in topo specified
        topology.
        if controller is not specified mininet will start an own controller for
        this net
        """
        if controller:
            self.creator.create_mininet(topo=topo, tunnels=tunnels, controller = controller, switch=self.switch)
        else:
            self.creator.create_mininet(topo=topo, tunnels=tunnels, switch=self.switch)

    @log_and_reraise_remote_exception
    def daemonize(self,cmd):
        """
        run command in background and terminate when MaxiNet is shut down
        """
        self.cmd.daemonize(cmd)
    
    @log_and_reraise_remote_exception
    def tunnelX11(self,node):
        """
        create X11 tunnel on worker to make x-forwarding work
        """
        if(not node in self.x11tunnels):
            try:
                display = subprocess.check_output("ssh -Y "+self.hn()+ " env | grep DISPLAY",shell=True)[8:]
                self.creator.tunnelX11(node,display)
                self.x11tunnels.append(node)
            except subprocess.CalledProcessError:
                return False
        return True
    
    @log_and_reraise_remote_exception
    def run_cmd_on_host(self,host,cmd):
        """
        run cmd in context of host and return output, where host is the name of an host in 
        the mininet instance running on the worker machine
        """
        return self.creator.runCmdOnHost(host,cmd)
    
    @log_and_reraise_remote_exception
    def run_cmd(self,cmd):
        """
        run cmd on worker machine and return output
        """
        return self.cmd.check_output(cmd)

    @log_and_reraise_remote_exception
    def run_script(self,cmd):
        """
        run cmd on worker machine from the Worker/bin directory return output
        """
        return self.cmd.script_check_output(cmd)

    @log_and_reraise_remote_exception
    def rpc(self, host, cmd, *params1, **params2):
        """
        internal function to do rpc calls
        """
        return self.creator.rpc(host, cmd, *params1, **params2)
    
    @log_and_reraise_remote_exception
    def rattr(self, host,name):
        """
        internal function to get attributes of objects
        """
        return self.creator.attr(host, name)
    
    @log_and_reraise_remote_exception
    def _fix_mtus(self):
        if self.ip() is None :
             logger.warn("no ip configured - can not fix MTU ")
             return 0
        intf = self.run_cmd("ip addr show to "+self.ip()+"/24 | head -n1 | cut -d' ' -f2 | tr -d :").strip()
        if intf == "" :
             logger.warn("could not find eth device - can not fix MTU")
             return 0
        mtu = int(self.run_cmd("ip li show dev "+intf+" | head -n1 | cut -d ' ' -f5"))
        if(mtu<1600):
            self.run_cmd("ip li se dev "+intf+" mtu 1600")

    @log_and_reraise_remote_exception
    def stop(self):
        """
        stop mininet instance on this worker
        """
        return self.creator.stop()

    def get_file(self,src,dst):
        """
        transfer file specified by src on worker to dst on frontend.
        uses scp command to transfer file
        """
        cmd_get = ["scp",self.hn()+":\""+src+"\"",dst]
        subprocess.call(cmd_get)

    def put_file(self,src,dst):
        """
        transfer file specified by src on frontend to dst on worker.
        uses scp command to transfer file
        """
        cmd_put = ["scp",src,self.hn()+":"+dst]
        subprocess.call(cmd_put)

    @log_and_reraise_remote_exception
    def addHost(self,name, cls=None, **params):
        """
        add host at runtime. you probably want to use Experiment.addHost
        """
        return self.creator.addHost(name,cls,**params)
    
    @log_and_reraise_remote_exception
    def addSwitch(self,name, cls=None,**params):
        """
        add switch at runtime. you probably want to use Experiment.addSwitch
        """
        return self.creator.addSwitch(name,cls,**params)

    @log_and_reraise_remote_exception
    def addController(self,name="c0", controller=None, **params):
        """
        add controller at runtime. you probably want to use Experiment.addController
        """
        return self.creator.addHost(name,controller,**params)
    
    @log_and_reraise_remote_exception
    def addTunnel(self,name, switch, port, cls, **params):
        """
        add tunnel at runtime. you probably want to use Experiment.addLink
        """
        return self.creator.addTunnel(name, switch, port, cls,**params)

    @log_and_reraise_remote_exception
    def addLink(self, node1, node2, port1 = None, port2 = None, cls = None, **params):
        """
        add link at runtime. you probably want to use Experiment.addLink
        """
        return self.creator.addLink(node1, node2, port1, port2, cls, **params)

class TunHelper:
    """
    internal class to manage tunnel interface names
    """
    def __init__(self):
        self.tunnr = 0 
        self.keynr = 0

    def get_tun_nr(self):
        self.tunnr = self.tunnr +1
        return self.tunnr -1

    def get_key_nr(self):
        self.keynr = self.keynr+1
        return self.keynr -1

    def get_last_tun_nr(self):
        return self.tunnr - 1

    def get_last_key_nr(self):
        return self.keynr - 1

class Cluster:
    """
    manage a set of workers via this class.
    to create several different topologys do not destroy/recreate this class but
    define several Experiment instances running sequential
    """
    def __init__(self,*hosts):
        """
        create Cluster object. Starting with MaxiNet 0.2 the hosts parameter is
        optional. If None is given all configured hosts will be used
        """
        self.running=False
        self.logger = logging.getLogger(__name__)
        self.tunhelper = TunHelper()
        if hosts:
            self.hosts = hosts
        else:
            self.hosts = config.cfg.keys()
        self.worker=[]
        
        if(self.hosts[0]!=subprocess.check_output(["hostname"]).strip()):
            rhost = config.cfg[self.hosts[0]]["ip"]
        else:
            if(len(self.hosts)>1):
                rhost = config.cfg[self.hosts[1]]["ip"]
            else:
                rhost = config.cfg[self.hosts[0]]["ip"]
        if sys.platform == "darwin":
            route = subprocess.check_output(["route", "-vn", "get", rhost]).splitlines()[-1]
            m = re.search(r' (\d+\.\d+\.\d+\.\d+)$', route)
        else:
            route = subprocess.check_output("ip route get "+rhost+" | head -n1", shell=True).strip()
            m = re.search(r'src (\d+\.\d+\.\d+\.\d+)', route)
        if m is not None:
            self.localIP = m.group(1)
        else:
            self.localIP="127.0.0.1"


        self.nsport=9090
        self.frontend = Frontend(self.localIP, self.nsport)
        self.config = tools.Config(self.localIP,self.nsport)
        atexit.register(run_cmd, self.getWorkerMangerCMD("--stop"))
        atexit.register(self._stop)

    def getWorkerMangerCMD(self,cmd):
        return [self.config.getWorkerScript("worker_manager.py", True), "--ns",
                self.localIP+":" +  str(self.nsport),
                "--workerDir",  self.config.getWorkerDir(),
                cmd] + self.hosts



    def is_running(self):
        return self.running
        
    def get_worker_shares(self):
        """
        returns list of workload shares per worker
        """
        shares=None
        if(self.running):
            shares=[]
            for w in self.worker:
                shares.append(self.config.getShare(w.hn()))
            wsum=0
            for w in shares:
                wsum+=w
            shares = map(lambda x: x/float(wsum),shares)
        return shares
        
    def check_reachability(self,ip):
        """
        check whether ip is reachable for a packet with MTU > 1500
        """
        cmd = ["ping","-c 2","-s 1520",ip]
        if(subprocess.call(cmd,stdout=open("/dev/null"),) == 1):
            return False
        else:
            return True

    def start(self):
        """
        start MaxiNet on assigned worker machines and establish communication. Returns True in case of successful startup.
        """
        self.logger.info("starting worker processes")

        cmd = self.getWorkerMangerCMD("--start")
        if self.frontend.hmac_key():
            cmd.extend(["--hmac",self.frontend.hmac_key()])

        self.logger.debug(run_cmd(cmd))

        timeout = 10
        for i in range(0,len(self.hosts)):
            self.logger.info("waiting for Worker "+str(i+1)+" to register on nameserver...")
            started=False
            end = time.time()+timeout
            while(not started):
                try:
                    self.frontend.lookup("worker"+str(i+1)+".mnCreator")
                    started=True
                except Pyro4.errors.NamingError:
                    if(time.time()>end):
                        raise RuntimeError("Timed out waiting for worker "+str(i+1)+".mnCreator to register.")
                    time.sleep(0.1)
            started=False
            end=time.time()+timeout
            while(not started):
                try:
                    self.frontend.lookup("worker"+str(i+1)+".cmd")
                    started=True
                except Pyro4.errors.NamingError:
                    time.sleep(0.1)
                    if(time.time()>end):
                        raise RuntimeError("Timed out waiting for worker "+str(i+1)+".cmd to register.")
            self.worker.append(Worker(self.frontend,"worker"+str(i+1)))
            
        if(not config.runWith1500MTU):
            for host in self.hosts:
                if(not self.check_reachability(config.cfg[host]["ip"])):
                    self.logger.error("Host "+host+" is not reachable with an MTU > 1500.")
                    raise RuntimeError("Host "+host+" is not reachable with an MTU > 1500.")
        for worker in self.worker:
            worker.run_script("load_tunneling.sh")
        self.logger.info("worker processes started")
        self.running = True
        return True

    def _stop(self):
        if(self.running):
            self.logger.info("removing tunnels...")
            self.remove_all_tunnels()
            #self.logger.info("shutting cluster down...")
            self.logger.info("removing nameserver entries...")
            for i in range(0,self.num_workers()):
                self.frontend.remove("worker"+str(i)+".mnCreator")
                self.frontend.remove("worker"+str(i)+".cmd")
            self.logger.info("shutting down frontend...")
            self.logger.info("Goodbye.")
            self.running=False
    
    def stop(self):
        """
        stop cluster and shut it down
        """
        self._stop()

    def num_workers(self):
        """
        return number of worker nodes in this cluster
        """
        return len(self.workers())

    def workers(self):
        """
        return list of worker instances for this cluster, ordered by worker id
        """
        if(self.is_running()):
            return self.worker
        else:
            return []

    def get_worker(self, wid):
        """
        return worker with id wid
        """
        return self.workers()[wid]

    def create_tunnel(self,w1,w2):
        """
        create gre tunnel connecting worker machine w1 and w2 and return name of
        created network interface
        """
        tid = self.tunhelper.get_tun_nr()
        tkey = self.tunhelper.get_key_nr()
        intf = "mn_tun"+str(tid)
        ip1=w1.ip()
        ip2=w2.ip()
        self.logger.debug("invoking tunnel create commands on "+ip1+" and "+ip2)
        w1.run_script("create_tunnel.sh "+ip1+" "+ip2+" "+intf+" "+str(tkey))
        w2.run_script("create_tunnel.sh "+ip2+" "+ip1+" "+intf+" "+str(tkey))
        self.logger.debug("done")
        return intf

    def remove_all_tunnels(self):
        """
        shut down all tunnels created in this cluster
        """
        for worker in self.workers():
            worker.run_script("delete_tunnels.sh")
        self.tunhelper = TunHelper()


class Experiment:
    """
    use this class to specify experiment. Experiments are created for
    one-time-usage and have to be stopped in the end. One cluster instance can
    run several experiments in sequence
    """
    def __init__(self,cluster, topology,controller=None, is_partitioned=False, switch=UserSwitch):
        self.cluster = cluster
        self.logger = logging.getLogger(__name__)
        self.topology=None
        self.starttime = time.localtime()
        self.printed_log_info = False
        self.isMonitoring = False
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
        self.switch=switch
        if controller:
            contr = controller
        else:
            contr = config.controller
        if contr.find(":")>=0:
            (host, port) = contr.split(":")
        else:
            host = contr
            port = "6633"
        self.controller = partial(RemoteController, ip=host, port=int(port))

    def configLinkStatus(self, src, dst, status):
        """Change status of src <-> dst links.
           src: node name
           dst: node name
           status: string {up, down}"""
        ws = self.get_worker(src)
        wd = self.get_worker(dst)
        if(ws==wd): # src and dst are on same worker. let mininet handle this
               ws.configLinkStatus(src,dst,status)
        else:
               src=self.get(src)
               dst=self.get(dst)
               intf = self.tunnellookup[(src.name,dst.name)]
               src.cmd("ifconfig "+intf+" "+status)
               dst.cmd("ifconfig "+intf+" "+status)



    @deprecated
    def find_worker(self,node):
        """
        return worker which emulates the specified node.
        Replaced by get_worker
        """
        return self.get_worker(node)

    def get_worker(self,node):
        """
        return worker which emulates the specified node.
        """
        if(isinstance(node,NodeWrapper)):
            return node.worker
        return self.cluster.get_worker(self.node_to_workerid[node])
        
    def get_log_folder(self):
        """
        returns folder to which log files will be saved
        """
        return "/tmp/maxinet_logs/"+Tools.time_to_string(self.starttime)+"/"

    def terminate_logging(self):
        for worker in self.cluster.workers():
            worker.run_cmd("killall getRxTx.sh getMemoryUsage.sh")
        self.isMonitoring = False

    def log_cpu(self):
        """
        log cpu useage of workers and place log files in /tmp/maxinet_logs/
        """
        for worker in self.cluster.workers():
            self.log_cpu_of_worker(worker)
            
    def log_cpu_of_worker(self,worker):
        """
        log cpu usage of worker and place log file in /tmp/maxinet_logs/
        """
        subprocess.call(["mkdir","-p","/tmp/maxinet_logs/"+Tools.time_to_string(self.starttime)+"/"])
        atexit.register(worker.get_file,"/tmp/maxinet_cpu_"+str(worker.wid)+"_("+worker.hn()+").log","/tmp/maxinet_logs/"+Tools.time_to_string(self.starttime)+"/")
        worker.daemonize("mpstat 1 | while read l; do echo -n \"`date +%s`    \" ; echo \"$l \" ; done > \"/tmp/maxinet_cpu_"+str(worker.wid)+"_("+worker.hn()+").log\"")
        atexit.register(self._print_log_info)
        
    def log_free_memory(self):
        """
        log memory usage of workers and place log files in /tmp/maxinet_logs
        Format is:
        timestamp,FreeMemory,Buffers,Cached
        """
        subprocess.call(["mkdir","-p","/tmp/maxinet_logs/"+Tools.time_to_string(self.starttime)+"/"])
        for worker in self.cluster.workers():
            atexit.register(worker.get_file,"/tmp/maxinet_mem_"+str(worker.wid)+"_("+worker.hn()+").log","/tmp/maxinet_logs/"+Tools.time_to_string(self.starttime)+"/")
            worker.daemonize("getMemoryUsage.sh > \"/tmp/maxinet_mem_"+str(worker.wid)+"_("+worker.hn()+").log\"")
            atexit.register(self._print_log_info)
            
    def log_interfaces_of_node(self,node):
        """
        logs statistics of interfaces of node and places them in /tmp/maxinet_logs
        Format is:
        timestamp,received bytes,sent bytes,received packets,sent packets
        """
        subprocess.call(["mkdir","-p","/tmp/maxinet_logs/"+Tools.time_to_string(self.starttime)+"/"])
        node = self.get(node)
        worker = self.get_worker(node)
        for intf in node.intfNames():
            self.log_interface(worker,intf)
            
    
    def log_interface(self,worker,intf):
        """
        logs statistics of interface of worker and places them in /tmp/maxinet_logs
        Format is:
        timestamp,received bytes,sent bytes,received packets,sent packets
        """
        atexit.register(worker.get_file,"/tmp/maxinet_intf_"+intf+"_"+str(worker.wid)+"_("+worker.hn()+").log","/tmp/maxinet_logs/"+Tools.time_to_string(self.starttime)+"/")
        worker.daemonize("getRxTx.sh "+intf+" > \"/tmp/maxinet_intf_"+intf+"_"+str(worker.wid)+"_("+worker.hn()+").log\"")
        atexit.register(self._print_log_info)
        
        
    def monitor(self):
        """
        logs statistics of worker interfaces and memory usage and places them in /tmp/maxinet_logs
        """
        self.isMonitoring = True
        atexit.register(self._print_monitor_info)
        self.log_free_memory()
        self.log_cpu()
        for worker in self.cluster.workers():
            intf = worker.run_cmd("ip addr show to "+worker.ip()+"/24 | head -n1 | cut -d' ' -f2 | tr -d :").strip()
            if(intf == ""):
                self.logger.warn("could not find main interface for "+worker.hn()+". no logging possible.")
            else:
                self.log_interface(worker,intf)
                
    def _print_log_info(self):
        if(not self.printed_log_info):
            self.printed_log_info=True
            self.logger.info("Log files will be placed in /tmp/maxinet_logs/"+Tools.time_to_string(self.starttime)+"/. You might want to save them somewhere else.")
            
    def _print_monitor_info(self):
        self.logger.info("You monitored this experiment. To generate a graph from your logs call \"maxinet_plot.py /tmp/maxinet_logs/"+Tools.time_to_string(self.starttime)+"/ plot.png\" ")
        
    
    def CLI(self,plocals,pglobals):
        """
        open interactive command line interface
        """
        CLI(self,plocals,pglobals)
            
        
                
    
    def addNode(self, name,**params):
        """
        add node at runtime.
        use parameter wid to specifiy worker id or pos to specify worker of
        existing node. otherwise random worker is chosen
        """
        wid = random.randint(0,self.cluster.num_workers()-1)
        if "pos" in params.keys():
            wid = self.node_to_workerid[params["pos"]]
            del params["pos"]
        if "wid" in params.keys():
            wid = int(params["wid"])-1
            del params["wid"]
        worker = self.cluster.get_worker(wid)
        self.node_to_workerid[name]=wid
        self.node_to_wrapper[name]=NodeWrapper(name,self.get_worker(name))
        self.nodes.append(self.node_to_wrapper[name])
    
          
    def addHost(self, name, cls = None, **params):
        """
        add host at runtime.
        use parameter wid to specifiy worker id or pos to specify worker of
        existing node. otherwise random worker is chosen
        """
        self.addNode(name,**params)
        self.get_worker(name).addHost(name,cls, **params)
        self.hosts.append(self.get(name))
        return self.get(name)
    
    def addSwitch(self, name, cls = None,  **params):
        """
        add switch at runtime
        use parameter wid to specifiy worker id or pos to specify worker of
        existing node. otherwise random worker is chosen
        """
        self.addNode(name, **params)
        self.get_worker(name).addSwitch(name,cls, **params)
        self.switches.append(self.get(name))
        return self.get(name)

    def addController(self, name="c0",controller = None, **params):
        """
        add controller at runtime
        use parameter wid to specifiy worker id or pos to specify worker of
        existing node. otherwise random worker is chosen
        """
        self.addNode(name, **params)
        self.get_worker(name).addController(name, controller, **params)
        return self.get(name)

    def name(self, node):
        """
        return name assigned to specified network node.
        """
        if(isinstance(node,NodeWrapper)):
            return node.nn
        return node

    def addLink(self, node1, node2, port1 = None, port2 = None, cls = None, autoconf=False, **params):
        """
        add links at runtime. will create tunnels between workers if necessary,
        but can not create tunnels between hosts and switches. (links will work fine)
        autoconf parameter handles attach() and config calls on switches and hosts
        """
        w1 = self.get_worker(node1)
        w2 = self.get_worker(node2)
        node1 = self.get(node1)
        node2 = self.get(node2)
        if(w1==w2):
            self.logger.debug("no tunneling needed")
            l=w1.addLink(self.name(node1),self.name(node2), port1, port2, cls, **params)

        else:
            self.logger.debug("tunneling needed")
            if(not ((node1 in self.switches) and (node2 in self.switches))):
                self.logger.error("We cannot create tunnels between switches and hosts. Sorry.")
                raise RuntimeError("Can't create tunnel between switch and host")
            intf = self.cluster.create_tunnel(w1,w2)
            w1.addTunnel(intf,self.name(node1), port1, cls, **params)
            w2.addTunnel(intf,self.name(node2), port2, cls, **params)
            l=((self.name(node1),intf),(self.name(node2),intf))
        if(autoconf):
                if(node1 in self.switches):
                    node1.attach(l[0][1])
                else:
                    node1.configDefault()
                if(node2 in self.switches):
                    node2.attach(l[1][1])
                else:
                    node2.configDefault()
        if(config.runWith1500MTU):
            self.setMTU(node1,1450)
            self.setMTU(node2,1450)
    
    def _find_topo_of_node(self,node, topos):
        for topo in topos:
            if node in topo.g.nodes():
                return topo


    def get_node(self, nodename):
        """
        return node that is specified by nodename
        :rtype : NodeWrapper
        """
        if(self.node_to_wrapper.has_key(nodename)):
            return self.node_to_wrapper[nodename]
        else:
            return None

    def get(self,nodename):
        """
        alias for get_node
        """
        return self.get_node(nodename)
        
    def setup(self):
        """
        start cluster if not yet started, assign topology parts to workers and
        start workers
        """
        if(not self.cluster.is_running()):
            self.cluster.start()
        if(not self.cluster.is_running()):
            raise RuntimeError("Cluster won't start")
        self.logger.info("Clustering topology...")
        if(not self.topology):
            parti = Partitioner()
            parti.loadtopo(self.origtopology)
            self.topology = parti.partition(self.cluster.num_workers(),self.cluster.get_worker_shares()) # assigning shares to workers requires that the workers are already startet. elsewise we don't have a way to determine the workerid of the worker. topologies are assigned to workers in ascending workerid order
            self.logger.debug("Tunnels: "+str(self.topology.getTunnels()))
        subtopos = self.topology.getTopos()
        if(len(subtopos) > self.cluster.num_workers()):
            raise RuntimeError("Cluster does not have enough workers for given topology")
        for subtopo in subtopos:
            for node in subtopo.nodes():
                self.node_to_workerid[node]=subtopos.index(subtopo)
                self.nodes.append(NodeWrapper(node, self.get_worker(node)))
                self.node_to_wrapper[node]=self.nodes[-1]
                if (not subtopo.isSwitch(node)):
                    self.hosts.append(self.nodes[-1])
                else:
                    self.switches.append(self.nodes[-1])
        self.logger.debug("Nodemapping: %s",self.node_to_workerid)
        tunnels = [[] for x in range(len(subtopos))]
        for tunnel in self.topology.getTunnels():
            w1 = self.get_worker(tunnel[0])
            w2 = self.get_worker(tunnel[1])
            intf = self.cluster.create_tunnel(w1,w2)
            self.tunnellookup[(tunnel[0],tunnel[1])]=intf
            self.tunnellookup[(tunnel[1],tunnel[0])]=intf
            for i in range(0,2):
                tunnels[self.node_to_workerid[tunnel[i]]].append([intf, tunnel[i], tunnel[2]]) # Assumes that workerid = subtopoid
        for topo in subtopos:
            self.cluster.workers()[subtopos.index(topo)].set_switch(self.switch)
            if(self.controller):
                self.cluster.workers()[subtopos.index(topo)].start(topo=topo, tunnels=tunnels[subtopos.index(topo)], controller=self.controller)
            else:
                self.cluster.workers()[subtopos.index(topo)].start(topo=topo, tunnels=tunnels[subtopos.index(topo)])
        if (config.runWith1500MTU):
            for topo in subtopos:
                for host in topo.nodes():
                    self.setMTU(host,1450)
    
    def setMTU(self,host,mtu):
        for intf in self.get(host).intfNames():
            self.get(host).cmd("ifconfig "+intf+" mtu "+str(mtu))
        
    
    @deprecated
    def run_cmd_on_host(self,host, cmd):
        """
        run cmd on emulated host specified by host name and return output
        This function is deprecated and will be removed in a future version of
        MaxiNet. Use experiment.get(node).cmd() instead
        """
        return self.get_worker(host).run_cmd_on_host(host,cmd)

    def stop(self):
        """
        stop experiment and shut down emulation on workers
        """

        if self.isMonitoring:
            self.terminate_logging()

        for worker in self.cluster.workers():
            worker.stop()
        self.cluster.remove_all_tunnels()

class NodeWrapper:
    """
    wrapper that allows most commands that can be used in mininet to be used
    in MaxiNet
    """

    # this feels like doing rpc via rpc...

    def __init__(self,nodename,worker):
        self.nn = nodename
        self.worker = worker

    def _call(self,cmd, *params1, **params2):
        return self.worker.rpc(self.nn, cmd, *params1, **params2)

    def _get(self,name):
        return self.worker.rattr(self.nn, name)

    def __getattr__(self,name):
        def method(*params1,**params2):
            return self._call(name,*params1,**params2)
        # the following commands SHOULD work. no guarantee given
        if name in [ "cleanup", "read", "readline", "write", "terminate", "stop",
                   "waitReadable", "sendCmd", "sendInt", "monitor", "waitOutput",
                   "cmd", "cmdPrint", "pexec", "newPort", "addIntf", "defaultIntf",
                   "intf", "connectionsTo", "deleteIntfs", "setARP", "setIP", "IP",
                   "MAC", "intfIsUp", "config", "configDefault",
                   "intfNames", "cgroupSet", "cgroupGet", "cgroupDel", "chrt",
                   "rtInfo", "cfsInfo", "setCPUFrac", "setCPUs", "defaultDpid",
                   "defaultIntf", "connected", "setup", "dpctl", "start", "stop",
                   "attach", "detach", "controllerUUIDs", "checkListening"]:
            return method
        elif name in [ "name","inNamespace","params","nameToIntf","waiting"]:
            return self._get(name)
        else:
            raise AttributeError(name)
    def __repr__(self):
        return "NodeWrapper ("+self.nn+" at "+str(self.worker)+")"

class Tools:
    
    @staticmethod
    def randByte():
        return hex(random.randint(0,255))[2:]

    @staticmethod
    def makeMAC(i):
        return Tools.randByte()+":"+Tools.randByte()+":"+Tools.randByte()+":00:00:" + hex(i)[2:]
    
    @staticmethod
    def makeDPID(i):
        a = Tools.makeMAC(i)
        dp = "".join(re.findall(r'[a-f0-9]+',a))
        return "0" * ( 12 - len(dp)) + dp

    @staticmethod
    def makeIP(i):
        return "10.0.0."+str(i)

    @staticmethod
    def time_to_string(t):
        if(t):
            return time.strftime("%Y-%m-%d_%H:%M:%S",t)
        else:
            return time.strftime("%Y-%m-%d_%H:%M:%S")



