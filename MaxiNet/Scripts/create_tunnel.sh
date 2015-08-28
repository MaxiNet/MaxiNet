#!/bin/bash

if [ -z "$4" ]
then
	echo "Usage: $0 <localip> <remoteip> <tunnel_device_name> <key>"
	exit 1
fi
LOCAL=$1
REMOTE=$2
LOCALIF=$3
KEY=$4

if [ -z "`lsmod | grep ip_gre`" ]
then
	load_tunneling.sh
fi

echo "Creating tunnel... $1 $2 $3 $4"
hostname -a
sudo ip li del $LOCALIF
sudo ip li ad $LOCALIF type gretap local $LOCAL remote $REMOTE ttl 64 key $KEY
sudo ip li se dev $LOCALIF up
sudo ethtool -K $LOCALIF gro off
sudo ethtool -K $LOCALIF tso off
sudo ethtool -K $LOCALIF gso off
echo "done."
	
