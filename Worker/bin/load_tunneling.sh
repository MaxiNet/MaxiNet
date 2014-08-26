#!/bin/bash
if [ -z "`lsmod |  grep ip_gre`" ]
then
        echo "Loading kernel modules..."
        sudo rmmod openvswitch
        sudo rmmod openvswitch_mod
        sudo modprobe ip_gre
        sudo modprobe tun
        sudo modprobe openvswitch
        sudo modprobe openvswitch_mod
        echo "done"
fi
