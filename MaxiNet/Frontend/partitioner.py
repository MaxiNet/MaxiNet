"""Partitioner code.

This file holds everything related to partitioning a single mininet topology
into multiple subtopologys interconnected by tunnels.
Most of the partitioning work is done by the metis graph partitioning tool.

Classes in this file:
    Clustering:
    Partitioner:
"""
import functools
import logging
import os
import subprocess
import warnings

from mininet.topo import Topo


logger = logging.getLogger(__name__)


# the following block is to support deprecation warnings. this is really not
# solved nicely and should probably be somewhere else
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


class Clustering(object):

    """Cluster of topologys.

    This class is used to hold a set of topologys interconnected by tunnels.

    Attributes:
        topos: Sequence of mininet.topo.Topo instances.
        tunnels: Sequence of tunnels in the form of
                 [[switchname1, switchname2, mininet linkInfo dict],...]
    """

    def __init__(self, topologies, tunnels):
        """Init Clustering."""
        self.topos = topologies
        self.tunnels = tunnels

    def getTunnels(self):
        """Get tunnel list."""
        return self.tunnels

    def getTopos(self):
        """Get topology list."""
        return self.topos


class Partitioner(object):

    """Partitions mininet topology into multiple interconnected by tunnels.

    The partitioner uses the graph partitioning tool metis to seperate a single
    mininet topology into several. It trys to do a mincut partitioning while
    keeping the partitions roughly equal (or equal accoring to a given set of
    weights).

    Attributes:
        metisCMD: Command line string to call metis.
        logger: Logging instance.
        paritions: Sequence of mininet.topo.Topo instances
        pos: Dict which maps line numbers in the metis in-/output file to
             switches.
        switches: Dict which maps switch names to line numbers in metis
                  in-/output file.
        topo: Original topology.
        tunnels: Sequence of tunnels in the form of
                 [[switchname1, switchname2, mininet linkInfo dict],...]
    """

    def __init__(self, metis="gpmetis -ptype=rb"):
        """Init partitioner.

        Args:
            metis: Command line string to call metis. Can be used to supply
                   additional parameters to metis. Default: "gpmetis -ptype=rb"
        """
        self.logger = logging.getLogger(__name__)
        self.metisCMD = metis

    def loadtopo(self, topo):
        """Load topology into partitioner and write metis input file.

        Args:
            topo: mininet.topo.Topo instance.
        """
        i = 1
        self.pos = {}
        self.switches = {}
        self.tunnels = []
        self.partitions = []
        self.topo = topo
        metis = [[]]  # <-- index 0 is header
        for switch in topo.switches():
            self.switches[switch] = i
            self.pos[i] = switch
            i += 1
            metis.append([1])
        links = 0
        for link in topo.links():
            if(topo.isSwitch(link[0]) and not topo.isSwitch(link[1])):
                metis[self.switches[link[0]]][0] = \
                                metis[self.switches[link[0]]][0] + 1
            elif(topo.isSwitch(link[1]) and not topo.isSwitch(link[0])):
                metis[self.switches[link[1]]][0] = \
                                metis[self.switches[link[1]]][0] + 1
            else:
                metis[self.switches[link[0]]].append(self.switches[link[1]])
                metis[self.switches[link[1]]].append(self.switches[link[0]])
                if("bw" in topo.linkInfo(link[0], link[1])):
                    metis[self.switches[link[0]]]\
                        .append(int(topo.linkInfo(link[0], link[1])["bw"]))
                    metis[self.switches[link[1]]]\
                        .append(int(topo.linkInfo(link[0], link[1])["bw"]))
                else:
                    metis[self.switches[link[0]]].append(100)
                    metis[self.switches[link[1]]].append(100)
                links += 1
        #write header
        metis[0] = [len(self.switches), links, "011 0"]
        ret = ""
        for line in metis:
            ret = ret + " ".join(map(str, line)) + "\n"
        self.graph = self._write_to_file(ret)

    def _convert_to_plain_topo(self, topo):
        """Convert topo to mininet.topo.Topo instance.

        This helper function allows the user to use topologys which are not
        direct instances of mininet.topo.Topo in MaxiNet. If the topology was
        not converted to a Topo instance the transfer via pyro most likely
        fails as the original class might not be available at the pyro remote.

        Args:
            topo: Instance which fullfills the interface of mininet.topo.Topo.

        Returns:
            Instance of mininet.topo.Topo,
        """
        r = Topo()
        for node in topo.nodes():
            r.addNode(node, **topo.nodeInfo(node))
        for edge in topo.links():
            r.addLink(**topo.linkInfo(edge[0], edge[1]))
        return r

    def partition(self, n, shares=None):
        self.tunnels = []
        self.partitions = []
        if(n > 1 and len(self.switches) > 1):
            if(shares):
                tpw = ""
                for i in range(0, n):
                    tpw += str(i) + " = " + str(shares[i]) + "\n"
                tpwf = self._write_to_file(tpw)
                outp = subprocess.check_output([self.metisCMD + " -tpwgts=" +
                        tpwf + " " + self.graph + " " + str(n)], shell=True)
                os.remove(tpwf)
            else:
                outp = subprocess.check_output([self.metisCMD + " " +
                        self.graph + " " + str(n)], shell=True)
            self.logger.debug(outp)
            self._parse_metis_result(self.graph + ".part." + str(n), n)
            os.remove(self.graph + ".part." + str(n))
            os.remove(self.graph)
        else:
            tpart = [self._convert_to_plain_topo(self.topo)]
            while(len(tpart) < n):
                tpart.append(Topo())
            self.partitions = tpart

        return Clustering(self.partitions, self.tunnels)

    def partition_using_map(self, mapping):
        """
        Partition loaded topology without metis but with mapping dictionary.
        Dictionary has to contain reference "nodename"->workerid for every
        node in topology.
        """
        self.tunnels = []
        self.partitions = []
        for i in range(0, max(mapping.values()) + 1):
            self.partitions.append(Topo())
        print mapping
        switch_to_part = {}
        for switch in self.switches:
            if(not switch in mapping):
                raise RuntimeError("no mapping for " + switch + " found")
            switch_to_part[switch] = mapping[switch]
            self.partitions[mapping[switch]].addNode(switch,
                    **self.topo.nodeInfo(switch))
        self._add_links(switch_to_part)
        return Clustering(self.partitions, self.tunnels)

    def _write_to_file(self, pstr):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            filename = os.tempnam()
        self.logger.debug("metis file: " + filename)
        self.logger.debug(pstr)
        f = open(filename, "w")
        f.write(pstr)
        f.close()
        return filename

    def _parse_metis_result(self, filepath, n):
        for i in range(0, n):
            self.partitions.append(Topo())
        f = open(filepath, "r")
        i = 1
        switch_to_part = {}
        for line in f:
            part = int(line)
            switch_to_part[self.pos[i]] = part
            self.partitions[part].addNode(self.pos[i],
                                          **self.topo.nodeInfo(self.pos[i]))
            i = i + 1
        f.close()
        self._add_links(switch_to_part)

    def _remove_nodeinfo(self, d):
        dr = d.copy()
        if("node1" in dr):
            del dr["node1"]
        if("node2" in dr):
            del dr["node2"]
        return dr

    def _add_links(self, switch_to_part):
        for node in self.topo.nodes():
            if not self.topo.isSwitch(node):
                for edge in self.topo.links():
                    if(edge[0] == node):
                        info = self._remove_nodeinfo(self.topo.linkInfo(node, edge[1]))
                        self.partitions[switch_to_part[edge[1]]].addNode(node,
                                                   **self.topo.nodeInfo(node))
                        self.partitions[switch_to_part[edge[1]]].addLink(node,
                                edge[1], **info)
                    if(edge[1] == node):
                        info = self._remove_nodeinfo(self.topo.linkInfo(edge[0], node))
                        self.partitions[switch_to_part[edge[0]]].addNode(node,
                                                   **self.topo.nodeInfo(node))
                        self.partitions[switch_to_part[edge[0]]]\
                                .addLink(edge[0], node, **info)
        for edge in self.topo.links():
            if (self.topo.isSwitch(edge[0]) and self.topo.isSwitch(edge[1])):
                info = self._remove_nodeinfo(self.topo.linkInfo(edge[0], edge[1]))
                if(switch_to_part[edge[0]] == switch_to_part[edge[1]]):
                    self.partitions[switch_to_part[edge[0]]].addLink(edge[0],
                               edge[1], **info)
                else:
                    self.tunnels.append([edge[0], edge[1],
                                        self.topo.linkInfo(edge[0], edge[1])])
        self.logger.debug("Topologies:")
        for t in self.partitions:
            self.logger.debug("Partition " + str(self.partitions.index(t)))
            self.logger.debug("Nodes: " + str(t.nodes()))
            self.logger.debug("Links: " + str(t.links()))
        self.logger.debug("Tunnels: " + str(self.tunnels))


class partitioner:

    @deprecated
    def __init__(self, string):
        self.partitioner = Partitioner()

    @deprecated
    def clusterTopology(self, topo, n):
        self.partitioner.loadtopo(topo)
        self.clustering = self.partitioner.partition(n)

    @deprecated
    def getTunnels(self):
        return self.partitioner.getTunnels()

    @deprecated
    def getTopos(self):
        return self.partitioner.getTopos()
