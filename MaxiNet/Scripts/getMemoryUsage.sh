#!/bin/bash


while [ 1 ]
do
    free=`grep MemFree /proc/meminfo | tr -s " " | cut -d " " -f 2`
    buffer=`grep Buffers /proc/meminfo | tr -s " " | cut -d " " -f 2`
    cache=`grep ^Cached /proc/meminfo | tr -s " " | cut -d " " -f 2`
    echo "`date +%s`,$free,$buffer,$cache"
    sleep 1
done
