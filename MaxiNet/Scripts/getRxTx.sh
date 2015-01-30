#!/bin/bash

eth=$1


rx_old=0
tx_old=0

rx_pkt_old=0
tx_pkt_old=0

while [ 1 ]
do
	s=`cat /proc/net/dev | grep "[[:space:]]${eth}:"`
	rx=`echo ${s} | awk '{print $2}'`
	tx=`echo ${s} | awk '{print $10}'`
	rx_pkt=`echo ${s} | awk '{print $3}'`
	tx_pkt=`echo ${s} | awk '{print $11}'`

	if [ "$rx_old" -ge 1 ]
	then
		rec=$(($rx - $rx_old))
		sen=$(($tx - $tx_old))
		rec_pkt=$(($rx_pkt - $rx_pkt_old))
		sen_pkt=$(($tx_pkt - $tx_pkt_old))
		echo -e -n "`date +%s`,$rec,$sen,$rec_pkt,$sen_pkt\n"
	fi

	rx_old=$rx
	tx_old=$tx
	rx_pkt_old=$rx_pkt
	tx_pkt_old=$tx_pkt


	sleep 1
done
