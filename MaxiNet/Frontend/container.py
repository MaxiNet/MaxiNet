#!/usr/bin/env python2
"""Docker container support.

This file wraps the import of the Docker class from containernet.
"""

try:
    from mininet.node import Docker
except ImportError as e:
    Docker = None
    raise ImportError("Failed to import Docker. Make sure ContainerNet is installed properly.")
