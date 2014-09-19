#!/bin/bash

if [ -z "$1" ]
then
        echo "Usage: $0 <tunnel_device_name>"
        exit 1
fi
LOCALIF=$1

echo -n "Removing tunnel..."
sudo ip li se dev $LOCALIF down
sudo ip li del $LOCALIF
echo "done."


