from ConfigParser import RawConfigParser
import logging
import os


class MaxiNetConfig(RawConfigParser):

    def __init__(self, file=None, **args):
        super(MaxiNetConfig, self).__init__(**args)
        if(file is None):
            self.read(["MaxiNet.cfg", os.path.expanduser("~/.MaxiNet.cfg"),
                       "/etc/MaxiNet.cfg"])
        self.set_loglevel()

    def set_loglevel(self, level=None):
        if(level is None):
            level = self.get_loglevel()
        logging.basicConfig(level=level)

    def get_nameserver_port(self):
        return self.getint("all", "port_ns")

    def get_frontend_ip(self):
        return self.get("FrontendServer", "ip")

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


class Tools(object):

    @staticmethod
    def get_worker_dir():
        return os.path.join(Tools.get_base_dir(), "WorkerServer")

    @staticmethod
    def get_script_dir():
        return os.path.join(Tools.get_base_dir(), "Scripts")

    @staticmethod
    def get_base_dir():
        return os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
