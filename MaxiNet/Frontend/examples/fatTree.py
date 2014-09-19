import sys, random,re

#
# Fat-tree topology implemention for mininet
#

from mininet.topo import Topo

class FatTree(Topo):
    def randByte(self):
        return hex(random.randint(0,255))[2:]

    def makeMAC(self, i):
        return self.randByte()+":"+self.randByte()+":"+self.randByte()+":00:00:" + hex(i)[2:]
    
    def makeDPID(self, i):
        a = self.makeMAC(i)
        dp = "".join(re.findall(r'[a-f0-9]+',a))
        return "0" * ( 12 - len(dp)) + dp
    
    # args is a string defining the arguments of the topology! has be to format: "x,y,z" to have x hosts and a bw limit of y for those hosts each and a latency of z (in ms) per hop
    def __init__(self, hosts=2, bwlimit=10, lat=0.1, **opts):
        Topo.__init__(self, **opts)

        tor = []


        numLeafes = hosts
        bw = bwlimit

        s = 1
        #bw = 10

        for i in range(numLeafes):
            h = self.addHost('h' + str(i+1), mac=self.makeMAC(i), ip="10.0.0." + str(i+1))
            sw = self.addSwitch('s' + str(s), dpid=self.makeDPID(s),  **dict(listenPort=(13000+s-1)))
            s = s+1
            self.addLink(h, sw, bw=bw, delay=str(lat) + "ms")
            tor.append(sw)



        toDo = tor  # nodes that have to be integrated into the tree

        while len(toDo) > 1:
            newToDo = []
            for i in range(0, len(toDo), 2):
                sw = self.addSwitch('s' + str(s), dpid=self.makeDPID(s), **dict(listenPort=(13000+s-1)))
                s = s+1
                newToDo.append(sw)
                self.addLink(toDo[i], sw, bw=bw, delay=str(lat) + "ms")
                if len(toDo) > i+1:
                    self.addLink(toDo[i+1], sw, bw=bw, delay=str(lat) + "ms")
            toDo = newToDo
            bw = 2.0*bw
            
                
