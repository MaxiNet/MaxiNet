import atexit
from ConfigParser import RawConfigParser
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
        if(file is None):
            self.read(["MaxiNet.cfg", os.path.expanduser("~/.MaxiNet.cfg"),
                       "/etc/MaxiNet.cfg"])
        self.set_loglevel()
        if(register):
            self.register()

    def set_loglevel(self, level=None):
        if(level is None):
            level = self.get_loglevel()
        logging.basicConfig(level=level)

    def get_nameserver_port(self):
        return self.getint("all", "port_ns")

    def get_sshd_port(self):
        return self.getint("all", "port_sshd")

    def get_frontend_ip(self):
        return self.get("FrontendServer", "ip")

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

    def run_with_1500_mtu(self):
        if(self.has_option("all","runWith1500MTU")):
            return self.getboolean("all","runWith1500MTU")
        return False

    def get_nameserver_ip(self):
        return self.get_frontend_ip()

    def get_nameserver_password(self):
        return self.get("all", "password")

    def get_loglevel(self):
        lvl = self.get("all", "logLevel")
        lvls = {"CRITICAL": logging.CRITICAL,
                "ERROR": logging.ERROR,
                "WARNING": logging.WARNING,
                "INFO": logging.INFO,
                "DEBUG": logging.DEBUG}
        return lvls[lvl]

    def register(self):
        self.nameserver = Pyro4.locateNS(self.get_nameserver_ip(), self.get_nameserver_port())
        self.daemon = Pyro4.Daemon(host=self.get_nameserver_ip())
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
            self.daemon.close()
            self.daemon = None
            self.daemon_thread.join()
            self.daemon_thread = None


class SSH_Tool(object):

    def __init__(self, config):
        self.config = config
        (self.key_priv, self.key_pub) = self._generate_ssh_key()

    def _generate_ssh_key(self):
        folder = tempfile.mkdtemp()
        subprocess.call(["ssh-keygen", "-t", "rsa", "-q", "-N", "\"\"",
                         os.path.join(folder, "sshkey")])
        return (os.path.join(folder, "sshkey"), os.path.join(folder, "sshkey.pub"))

    def get_pub_ssh_key(self):
        with open(self.key_pub) as fn:
            return fn.read().strip()

    def get_ssh_cmd(self, targethostname, cmd, opts=None):
        rip = self.config.get_worker_ip(targethostname)
        if(rip is None):
            return None
        cmd = ["ssh", "-o", "UserKnownHostsFile=/dev/null", "-o",
               "StrictHostKeyChecking=no", "-q", "-i", self.key_priv]
        if(opts):
            cmd.extend(opts)
        cmd.extend([rip, cmd])
        return cmd

    def get_scp_put_cmd(self, targethostname, local, remote, opts=None):
        rip = self.config.get_worker_ip(targethostname)
        if(rip is None):
            return None
        cmd = ["scp", "-o", "UserKnownHostsFile=/dev/null", "-o",
               "StrictHostKeyChecking=no", "-r", "-i", self.key_priv]
        if(opts):
            cmd.extend(opts)
        cmd.extend([local, "%s:%s" % (rip, remote)])
        return cmd

    def get_scp_get_cmd(self, targethostname, remote, local, opts=None):
        rip = self.config.get_worker_ip(targethostname)
        if(rip is None):
            return None
        cmd = ["scp", "-o", "UserKnownHostsFile=/dev/null", "-o",
               "StrictHostKeyChecking=no", "-r", "-i", self.key_priv]
        if(opts):
            cmd.extend(opts)
        cmd.extend(["%s:%s" % (rip, remote), local])
        return cmd


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
    def randByte():
        return hex(random.randint(0, 255))[2:]

    @staticmethod
    def makeMAC(i):
        return Tools.randByte() + ":" + Tools.randByte() + ":" +\
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
        return subprocess.check_output("ifconfig -a | awk '/(cast)/ { print $2 }' | cut -d':' -f2 | head -1", shell=True)
