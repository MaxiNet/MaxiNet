import atexit
import os
import subprocess


class SSH_Manager(object):

    def __init__(self, folder, ip, port):
        self.folder = folder
        self.popen = None
        if not self._folder_is_initialized():
            self.initialize_ssh_folder(ip, port)

    def _folder_is_initialized(self):
        if (os.path.exists(os.path.join(self.folder, "sshd_config")) and
           os.path.exists(os.path.join(self.folder, "authorized_keys")) and
           os.path.exists(os.path.join(self.folder, "ssh_host_rsa_key"))):
            return True
        return False

    def _write_sshd_config(self, ip, port, template="sshd_config.template"):
        with open(template, "r") as f_template:
            content = f_template.read()
        content = content.replace("<!IP!>", ip)
        content = content.replace("<!PORT!>", str(port))
        content = content.replace("<!FOLDER!>", self.folder)
        with open(os.path.join(self.folder, "sshd_config"), "w") as fn:
            fn.write(content)

    def add_key(self, key):
        with open(os.path.join(self.folder, "authorized_keys"), "a") as fn:
            fn.write("\n%s" % (key,))

    def has_key(self, key):
        with open(os.path.join(self.folder, "authorized_keys"), "r") as fn:
            content = fn.read()
        if content.count(key) > 0:
            return True
        return False

    def remove_key(self, key):
        with open(os.path.join(self.folder, "authorized_keys"), "r") as fn:
            content = fn.read()
        content = content.replace("key", "")
        with open(os.path.join(self.folder, "authorized_keys"), "w") as fn:
            fn.write(content)

    def remove_all_keys(self):
        with open(os.path.join(self.folder, "authorized_keys"), "w") as fn:
            fn.write("")

    def _generate_host_key(self):
        subprocess.call(["ssh-keygen", "-q", "-N", "\"\"", "-t", "rsa", "-f",
                         os.path.join(self.folder, "ssh_host_rsa_key")])

    def get_host_key_fingerprint(self):
        return subprocess.check_output(["ssh-keygen", "-l", "-f",
                                        os.path.join(self.folder, "ssh_host_rsa_key")]).strip()

    def initialize_ssh_folder(self, ip, port):
        self._write_sshd_config(ip, port)
        subprocess.call(["touch", os.path.join(self.folder, "authorized_keys")])
        self._generate_host_key()

    def start_sshd(self):
        self.popen = subprocess.Popen(["/usr/sbin/sshd", "-D",
                                       "-E",
                                       os.path.join(self.folder, "sshd.log"),
                                       "-f",
                                       os.path.join(self.folder, "sshd_config")
                                       ],
                                      stdin=subprocess.PIPE,
                                      stdout=open("/dev/null", "w"))
        atexit.register(self.terminate_sshd)

    def sshd_running(self):
        if(self.popen):
            if(self.popen.poll() is None):
                return True
        return False

    def terminate_sshd(self):
        if(self.sshd_running()):
            self.popen.terminate()
