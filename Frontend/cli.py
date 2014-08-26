#!/usr/bin/python

from cmd import Cmd
import traceback
import subprocess
import sys


class CLI(Cmd):
    prompt = "MaxiNet> "
    
    helpStr = """You may also type '<hostname> <command>' to execute commands on maxinet hosts
\texample: h1 ifconfig h1-eth1"""

    def __init__(self,experiment,plocals,pglobals):
        self.experiment = experiment
        self.plocals = plocals
        self.pglobals = pglobals
        Cmd.__init__(self)
        while True: 
            try:
                self.cmdloop()
                break
            except KeyboardInterrupt:
                print "\nInterrupt"
                
    def emptyline(self):
        pass
        
    def do_help(self,s):
        "Print help"
        Cmd.do_help(self,s)
        if s is "":
            print self.helpStr
            
    def do_hosts(self,s):
        "Print all hostnames"
        h=""
        for host in self.experiment.hosts:
            h=h+" "+host.name
        print h
        
    def do_switches(self,s):
        "Print all switchnames"
        h=""
        for switch in self.experiment.switches:
            h=h+" "+switch.name
        print h
    
    def do_pingall(self,s):
        "Do ping between all hosts (or between one and all other hosts if host is given as parameter)"
        sent=0.0
        received=0.0
        if(len(s)==0):
            for host in self.experiment.hosts:
                for target in self.experiment.hosts:
                    if(target==host):
                        continue
                    sys.stdout.write(host.name +" -> "+ target.name)
                    sent+=1.0
                    if(host.pexec("ping -c1 "+target.IP())[2]!=0):
                        print " X"
                    else:
                        received +=1.0
                        print ""
        else:
            host = self.experiment.get(s)
            if(host==None):
                print "Error: Node "+s+" does not exist"
            else:
                for target in self.experiment.hosts:
                    if(target==host):
                        continue
                    sys.stdout.write(host.name +" -> "+ target.name)
                    sent+=1.0
                    if(host.pexec("ping -c1 "+target.IP())[2]!=0):
                        print " X"
                    else:
                        received+=1.0
                        print ""
        print "*** Results: %.2f%% dropped (%d/%d received)" % ((1.0-received/sent), int(received), int(sent))
        
    def do_ip(self,s):
        "Print ip of host"
        node = self.experiment.get(s)
        if(node==None):
            print "Error: Node "+s+" does not exist"
        else:
            print node.IP()
            
    def do_py(self,s):
        "Execute Python command"
        cmd = s
        main = __import__("__main__")
        try:
            exec(cmd, self.pglobals, self.plocals)
        except Exception, e:
            traceback.print_exc()
            
    def do_exit(self,s):
        "Exit"
        return "exited by user command"
        
    def do_quit(self,s):
        "Exit"
        return self.do_exit(s)
        
    def default(self,s):
        node = s[:s.find(" ")]
        cmd = s[s.find(" ")+1:]
        if(self.experiment.get(node)==None):
            print "Error: Node "+s+" does not exist"
        else:
            pid = self.experiment.get_worker(self.experiment.get(node)).run_cmd("ps ax | grep \"bash -ms mininet:"+node+"\" -m1 | awk '{print $1}'").strip()
            if self.experiment.get_worker(self.experiment.get(node)).tunnelX11(node):
                user = subprocess.check_output("ssh -q -t "+self.experiment.get_worker(self.experiment.get(node)).hn()+" echo $USER", shell=True).strip()
                rcmd = "ssh -q -Y -t "+self.experiment.get_worker(self.experiment.get(node)).hn()+" sudo  XAUTHORITY=/home/"+user+"/.Xauthority mnexec -a "+pid+" "+cmd
            else:
                rcmd = "ssh -q -t "+self.experiment.get_worker(self.experiment.get(node)).hn()+" sudo mnexec -a "+pid+" "+cmd
            subprocess.call(rcmd,shell=True)
