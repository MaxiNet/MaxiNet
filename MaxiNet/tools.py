import atexit
from ConfigParser import RawConfigParser
from mininet.topo import Topo
import logging
import os
import random
import re
import subprocess
import tempfile
import threading
import time

import Pyro4

if hasattr(Pyro4.config, 'SERIALIZERS_ACCEPTED'):
    # From Pyro 4.25, pickle is not supported by default due to security.
    # However, it is required to serialise some objects used by maxinet.
    Pyro4.config.SERIALIZERS_ACCEPTED.add('pickle')
Pyro4.config.SERIALIZER = 'pickle'

class MaxiNetConfig(RawConfigParser):

    def __init__(self, file=None, register=False, **args):
        RawConfigParser.__init__(self, **args)
        self.logger = logging.getLogger(__name__)
        self.daemon = None
        if(file is None):
            self.read(["/etc/MaxiNet.cfg", os.path.expanduser("~/.MaxiNet.cfg"),
                       "MaxiNet.cfg"])
        self.set_loglevel()
        if(register):
            self.register()

    @Pyro4.expose
    def set_loglevel(self, level=None):
        if(level is None):
            level = self.get_loglevel()
        logging.basicConfig(level=level)

    @Pyro4.expose
    def get_nameserver_port(self):
        return self.getint("all", "port_ns")

    @Pyro4.expose
    def get_sshd_port(self):
        return self.getint("all", "port_sshd")

    @Pyro4.expose
    def get_frontend_ip(self):
        return self.get("FrontendServer", "ip")

    @Pyro4.expose
    def get_frontend_threads(self):
        if self.has_option("FrontendServer", "threadpool"):
            return self.getint("FrontendServer", "threadpool")
        return 256

    @Pyro4.expose
    def get_controller(self):
        return self.get("all", "controller")

    @Pyro4.expose
    def get_worker_ip(self, hostname, classifier=None):
        if(not self.has_section(hostname)):
            self.logger.warn("Unknown hostname: %s" % hostname)
            return None
        else:
            if(classifier is None):
                return self.get(hostname, "ip")
            else:
                if(not self.has_option(hostname, "ip_%s" % classifier)):
                    return self.get_worker_ip(hostname)
                else:
                    return self.get(hostname, "ip_%s" % classifier)

    @Pyro4.expose
    def run_with_1500_mtu(self):
        if(self.has_option("all","runWith1500MTU")):
            return self.getboolean("all","runWith1500MTU")
        return False

    @Pyro4.expose
    def use_stt_tunneling(self):
        if(self.has_option("all","useSTT")):
            return self.getboolean("all","useSTT")
        return False

    @Pyro4.expose
    def deactivateTSO(self):
        if(self.has_option("all","deactivateTSO")):
            return self.getboolean("all","deactivateTSO")
        return False

    @Pyro4.expose
    def get_nameserver_ip(self):
        return self.get_frontend_ip()

    @Pyro4.expose
    def get_nameserver_password(self):
        return self.get("all", "password")

    @Pyro4.expose
    def get_loglevel(self):
        lvl = self.get("all", "logLevel")
        lvls = {"CRITICAL": logging.CRITICAL,
                "ERROR": logging.ERROR,
                "WARNING": logging.WARNING,
                "INFO": logging.INFO,
                "DEBUG": logging.DEBUG}
        return lvls[lvl]

    def register(self):
        self.nameserver = Pyro4.locateNS(self.get_nameserver_ip(), self.get_nameserver_port(), hmac_key=self.get_nameserver_password())
        self.daemon = Pyro4.Daemon(host=self.get_nameserver_ip())
        self.daemon._pyroHmacKey = self.get_nameserver_password()
        uri = self.daemon.register(self)
        self.daemon_thread = threading.Thread(target=self.daemon.requestLoop)
        self.daemon_thread.daemon = True
        self.daemon_thread.start()
        self.nameserver.register("config", uri)
        atexit.register(self.unregister)

    def unregister(self):
        if(self.daemon):
            self.nameserver.remove("config")
            self.daemon.shutdown()
            self.daemon = None
            self.daemon_thread.join()
            self.daemon_thread = None

    @Pyro4.expose
    def get(self, section, option):
        return RawConfigParser.get(self, section, option)

    @Pyro4.expose
    def set(self, section, option, val):
        return RawConfigParser.set(self, section, option, val)

    @Pyro4.expose
    def has_section(self, section):
        return RawConfigParser.has_section(self, section)

    @Pyro4.expose
    def add_section(self, section):
        return RawConfigParser.add_section(self, section)

    @Pyro4.expose
    def has_option(self, section, option):
        return RawConfigParser.has_option(self, section, option)

    @Pyro4.expose
    def getint(self, section, option):
        return RawConfigParser.getint(self, section, option)

    @Pyro4.expose
    def getboolean(self, section, option):
        return RawConfigParser.getboolean(self, section, option)

class SSH_Tool(object):

    def __init__(self, config):
        self.config = config
        (self.key_priv, self.key_pub) = self._generate_ssh_key()
        self.known_hosts = tempfile.mkstemp()[1]
        self.add_known_host("localhost")

    def _generate_ssh_key(self):
        folder = tempfile.mkdtemp()
        subprocess.call(["ssh-keygen", "-t", "rsa", "-q", "-N", "", "-f",
                         os.path.join(folder, "sshkey")])
        atexit.register(self._cleanup)
        return (os.path.join(folder, "sshkey"), os.path.join(folder, "sshkey.pub"))

    def get_pub_ssh_key(self):
        with open(self.key_pub) as fn:
            return fn.read().strip()

    def get_ssh_cmd(self, targethostname, cmd, opts=None):
        rip = self.config.get_worker_ip(targethostname)

        #workaround: for some reason ssh-ing into localhost using localhosts external IP does not work.
        #hence, we replace the external ip with localhost if necessary.
        local = subprocess.check_output("ip route get %s" % rip, shell=True)
        if (local[0:5] == "local"):
            rip = "localhost"

        user = self.config.get("all", "sshuser")
        if(rip is None):
            return None
        cm = ["ssh", "-p", str(self.config.get_sshd_port()), "-o",
              "UserKnownHostsFile=%s" % self.known_hosts,
              "-q", "-i", self.key_priv]
        if(opts):
            cm.extend(opts)
        cm.append("%s@%s" % (user, rip))
        if(type(cmd) == str):
            if(self.config.getboolean("all", "usesudo")):
                cmd = "sudo "+cmd
            cm.append(cmd)
        else:
            if(self.config.getboolean("all", "usesudo")):
                cmd = ["sudo"] + cmd
            cm.extend(cmd)
        return cm

    def get_scp_put_cmd(self, targethostname, local, remote, opts=None):
        rip = self.config.get_worker_ip(targethostname)

        loc = subprocess.check_output("ip route get %s" % rip, shell=True)
        if (loc[0:5] == "local"):
            rip = "localhost"

        user = self.config.get("all", "sshuser")
        if(rip is None):
            return None
        cmd = ["scp", "-P", str(self.config.get_sshd_port()), "-o",
               "UserKnownHostsFile=%s" % self.known_hosts,
               "-r", "-i", self.key_priv]
        if(opts):
            cmd.extend(opts)
        cmd.extend([local, "%s@%s:\"%s\"" % (user, rip, remote)])
        return cmd

    def get_scp_get_cmd(self, targethostname, remote, local, opts=None):
        rip = self.config.get_worker_ip(targethostname)

        loc = subprocess.check_output("ip route get %s" % rip, shell=True)
        if (loc[0:5] == "local"):
            rip = "localhost"

        user = self.config.get("all", "sshuser")
        if(rip is None):
            return None
        cmd = ["scp", "-P", str(self.config.get_sshd_port()), "-o",
               "UserKnownHostsFile=%s" % self.known_hosts,
               "-r", "-i", self.key_priv]
        if(opts):
            cmd.extend(opts)
        cmd.extend(["%s@%s:\"%s\"" % (user, rip, remote), local])
        return cmd

    def add_known_host(self, ip):
        with open(self.known_hosts, "a") as kh:
            fp = subprocess.check_output(["ssh-keyscan", "-p",
                                          str(self.config.get_sshd_port()), ip])
            kh.write(fp)

    def _cleanup(self):
        subprocess.call(["rm", self.key_priv])
        subprocess.call(["rm", self.key_pub])
        subprocess.call(["rmdir", os.path.dirname(self.key_priv)])

#
# Fat-tree topology implemention for mininet
#
class FatTree(Topo):
    def randByte(self, max=255):
        return hex(random.randint(0, max))[2:]

    def makeMAC(self, i):
        return "00:" + self.randByte() + ":" + \
               self.randByte() + ":00:00:" + hex(i)[2:]

    def makeDPID(self, i):
        return self.makeMAC(i)

    # args is a string defining the arguments of the topology!
    # has be to format: "x,y,z" to have x hosts and a bw limit of y for
    # those hosts each and a latency of z (in ms) per hop
    def __init__(self, hosts=2, bwlimit=10, lat=0.1, **opts):
        Topo.__init__(self, **opts)
        tor = []
        numLeafes = hosts
        bw = bwlimit
        s = 1
        #bw = 10
        for i in range(numLeafes):
            h = self.addHost('h' + str(i + 1), mac=self.makeMAC(i),
                            ip="10.0.0." + str(i + 1))
            sw = self.addSwitch('s' + str(s), dpid=self.makeDPID(s),
                                **dict(listenPort=(13000 + s - 1)))
            s = s + 1
            self.addLink(h, sw, bw=bw, delay=str(lat) + "ms")
            tor.append(sw)
        toDo = tor  # nodes that have to be integrated into the tree
        while len(toDo) > 1:
            newToDo = []
            for i in range(0, len(toDo), 2):
                sw = self.addSwitch('s' + str(s), dpid=self.makeDPID(s),
                                    **dict(listenPort=(13000 + s - 1)))
                s = s + 1
                newToDo.append(sw)
                self.addLink(toDo[i], sw, bw=bw, delay=str(lat) + "ms")
                if len(toDo) > (i + 1):
                    self.addLink(toDo[i + 1], sw, bw=bw, delay=str(lat) + "ms")
            toDo = newToDo
            bw = 2.0 * bw


class Tools(object):

    @staticmethod
    def get_worker_dir():
        return os.path.join(Tools.get_base_dir(), "WorkerServer") + os.sep

    @staticmethod
    def get_script_dir():
        return os.path.join(Tools.get_base_dir(), "Scripts") + os.sep

    @staticmethod
    def get_base_dir():
        return os.path.abspath(os.path.dirname(os.path.abspath(__file__))) + os.sep

    @staticmethod
    def randByte(max=255):
        return hex(random.randint(0, max))[2:]

    @staticmethod
    def makeMAC(i):
        return Tools.randByte(127) + ":" + Tools.randByte() + ":" +\
               Tools.randByte() + ":00:00:" + hex(i)[2:]

    @staticmethod
    def makeDPID(i):
        a = Tools.makeMAC(i)
        dp = "".join(re.findall(r'[a-f0-9]+', a))
        return "0" * (12 - len(dp)) + dp

    @staticmethod
    def makeIP(i):
        return "10.0.0." + str(i)

    @staticmethod
    def time_to_string(t):
        if(t):
            return time.strftime("%Y-%m-%d_%H:%M:%S", t)
        else:
            return time.strftime("%Y-%m-%d_%H:%M:%S")

    @staticmethod
    def guess_ip():
        ip = subprocess.check_output("ifconfig -a | awk '/(cast)/ { print $2 }' | cut -d':' -f2 | head -1", shell=True)
        return ip.strip()
