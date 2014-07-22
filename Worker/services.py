__author__ = 'm'
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel as mnSetLogLevel
from mininet.topo import Topo, SingleSwitchTopo
from mininet.node import UserSwitch, OVSSwitch
from mininet.link import Link, TCLink, Intf
import mininet.term
import logging
import subprocess, os, socket, atexit

class MininetCreator():
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        pass

    def create_mininet(self, topo=None, tunnels=[],  switch=UserSwitch, controller=None):
        "Create a Mininet and test it with pingall"
        self.setLogLevel('debug')
        self.logger.info("Creating mininet instance")
        if not topo:
            topo=SingleSwitchTopo(k=2)
        if controller:
            self.net = Mininet(topo=topo, link=TCLink, switch=switch, controller=controller)
        else:
            self.net = Mininet(topo=topo, link=TCLink, switch=switch)
        self.logger.info("Adding tunnels to mininet instance")
        for tunnel in tunnels:
            port=None
            cls=None
            if "port" in tunnel[2].keys():
                port = tunnel[2]["port"]
                del tunnel[2]["port"]
            if "cls" in tunnel[2].keys():
                cls = tunnel[2]["cls"]
                del tunnel[2]["cls"]
            self.addTunnel(tunnel[0], tunnel[1], port, cls, **tunnel[2])
        self.logger.info("Starting Mininet...")
        self.net.start()
        #print "Dumping host connections"
        dumpNodeConnections(self.net.hosts)
        self.logger.info("Startup complete.")
        # print "Testing network connectivity"
        # self.net.pingAll()
        # self.net.stop()
        # print "net created, pingAll finished!"
        #return net     # to do: it seems we get in trouble with serializing Mininet objects

    def getHosts(self):
        # todo just return the hosts names not the objects themselves they are not serializable
        hosts = self.net.hosts
        self.logger.debug('hosts type: ', type(hosts), ' ||| elem type:', type(hosts[0]))
        return hosts

    def setLogLevel(self, level='info'):
        '''
            set worker's mininet instance log level
        '''
        mnSetLogLevel(level)

    def configLinkStatus(self,src,dst,status):
        self.net.configLinkStatus(src,dst,status)

    def rpc(self, hostname, cmd, *params1, **params2):
        h = self.net.get(hostname)
        return getattr(h,cmd)(*params1, **params2)

    def attr(self, hostname, name):
        h = self.net.get(hostname)
        return getattr(h,name)

    def addHost(self,name, cls=None,**params):
        self.net.addHost(name,cls, **params)
        return name

    def addSwitch(self,name,cls=None, **params):
        self.net.addSwitch(name, cls, **params)
        self.net.get(name).start(self.net.controllers) #TODO: This should not be done here
        return name

    def addController(self,name="c0", controller=None,**params):
        self.net.addController(name, controller,**params)
        return name

    def addTunnel(self, name, switch, port, cls, **params):
        switch=self.net.get(switch)
        #self.net.addTunnel(name, switch, port, cls, **params)
        if not cls:
            cls=Intf
        cls(name, node=switch, port=port, link=None, **params)
    def tunnelX11(self, node,display):
        node = self.net.get(node)
        mininet.term.tunnelX11(node,display)
        
    def addLink(self, node1, node2, port1 = None, port2 = None, cls = None, **params):
        node1=self.net.get(node1)
        node2=self.net.get(node2)
        l=self.net.addLink(node1,node2,port1,port2,cls,**params)
        return ((node1.name,l.intf1.name),(node2.name,l.intf2.name))
    
    def runCmdOnHost(self, hostname, command, noWait=False):
        '''
            e.g. runCmdOnHost('h1', 'ifconfig')
        '''
        h1 = self.net.get(hostname)
        if noWait:
            return h1.sendCmd(command)
        else:
            return h1.cmd(command)

    def getNodePID(self, nodename):
        # todo : get pid of a specific switch or host in order to log its resource usage
        pass

    def stop(self):
        self.net.stop()
        self.logger.info('network stopped')
    
class CmdListener:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        pass

    def get_hostname(self):
        return socket.gethostname()

    def check_output(self, data):
        try:
            return subprocess.check_output(data,shell=True,stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError, e:
            return e.output

    def run_cmd(self, command):
        os.system(command)
        
    def daemonize(self, cmd):
        p = subprocess.Popen(cmd,shell=True)
        atexit.register(p.terminate)
