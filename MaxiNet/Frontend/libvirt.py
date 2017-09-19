#!/usr/bin/env python2
"""LibvirtHost support.

This file wraps the import of the LibvirtHost class from containernet.
"""

try:
    from mininet.node import LibvirtHost
except ImportError as e:
    Libvirt = None
    raise ImportError("Failed to import LibvirtHost. Make sure ContainerNet2.0 is installed properly.")
