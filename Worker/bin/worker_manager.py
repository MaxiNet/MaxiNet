#!/usr/bin/python2

import argparse
import os,subprocess,threading
parser = argparse.ArgumentParser()


group=parser.add_mutually_exclusive_group(required=True)
group.add_argument("--start", help="start Worker daemons on remote hosts",
                    action="store_true")
group.add_argument("--stop", help="stop Worker daemons on remote hosts",
                    action="store_true")
parser.add_argument("--ns", help="nameserver to use", required=True,type=str, nargs=1, metavar="NAMESERVER")
parser.add_argument("--hmac", help="hmac key to use",type=str, nargs=1, metavar="KEY")
parser.add_argument("hosts",help="use these hosts",
                    nargs='+',metavar=("HOST1","HOST2"), type=str)
args = parser.parse_args()

def start(hn):
    wc = "fgcn-openflow/trunk/Worker/"
    if(args.hmac):
        cmd = "ssh "+ hn + " \"screen -d -m -S MNWorker sudo python "+wc+"server.py "+args.ns[0]+" "+args.hmac[0]+"\""
    else:
        cmd = "ssh "+ hn + " \"screen -d -m -S MNWorker sudo python "+wc+"server.py "+args.ns[0]+"\""
    print cmd
    subprocess.call(cmd,shell=True)

def stop(hn):
    wc = "fgcn-openflow/trunk/Worker/"
    dnull=open("/dev/null","w")
    cmd = "ssh "+ hn + " \"sudo pkill -f 'python "+wc+"server.py'\""
    subprocess.call(cmd,stdout=dnull,stderr=dnull,shell=True)
    cmd = "ssh "+ hn + " \"sudo mn --clean\""
    subprocess.call(cmd,stdout=dnull,stderr=dnull,shell=True)
    cmd = "ssh "+ hn + " \"sudo delete_tunnels.sh\""
    subprocess.call(cmd,stdout=dnull,stderr=dnull,shell=True)
    
    

hosts = args.hosts
threads=[]
for vm in hosts:
    print vm+"..."
    hn = vm
    chkcmd = "ssh "+hn+" screen -ls | grep MNWorker"
    dnull=open("/dev/null","w")
    if(args.start):
        if(subprocess.call(chkcmd,stdout=dnull,shell=True)==0):
            print "stopping running instance on " + vm
            stop(hn)
        threads.append(threading.Thread(None,start,None,(hn,)))
        threads[-1].start()
    if(args.stop):
        if(subprocess.call(chkcmd,shell=True,stdout=dnull)==1):
            print "ignoring " + vm + " as there seems to be no running instance"
            continue
        threads.append(threading.Thread(None,stop,None,(hn,)))
        threads[-1].start()
for t in threads:
    t.join()

