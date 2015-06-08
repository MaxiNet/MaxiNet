#!/bin/bash

echo "MaxiNet 1.0 installer"
echo ""
echo "This program installs MaxiNet 1.0 and all requirements to the home directory of your user"


read -n1 -r -p "Do you want to install Mininet 2.2.1rc1? ([y]/n)" mininet

if [ "$mininet" == "" ] || [ "$mininet" == "y" ] || [ "$mininet" == "Y" ]
then
	mininet="y"
	echo ""
	echo "You choose to install Mininet. Warning: This will automatically remove existing directories ~/mininet, ~/loxigen, and ~/openflow"
else
	mininet="n"
fi
echo ""

read -n1 -r -p "Do you want to install Metis 5.1? ([y]/n)" metis

if [ "$metis" == "" ] || [ "$metis" == "y" ] || [ "$metis" == "Y" ]
then
	metis="y"
else
	metis="n"
fi
echo ""

read -n1 -r -p "Do you want to install Pyro 4? ([y]/n)" pyro

if [ "$pyro" == "" ] || [ "$pyro" == "y" ] || [ "$pyro" == "Y" ]
then
	pyro="y"
else
	pyro="n"
fi
echo ""


echo "----------------"
echo ""
echo "MaxiNet installer will now install: "
if [ "$mininet" == "y" ]; then echo " -Mininet 2.2.1rc1"; fi
if [ "$metis" == "y" ]; then echo " -Metis 5.1"; fi
if [ "$pyro" == "y" ]; then echo " -Pyro 4"; fi
echo " -MaxiNet 1.0"
echo ""

read -n1 -r -p "Is this OK? Press ANY key to continue or CTRL+C to abort." abort


echo "installing required dependancies."

sudo apt-get install git autoconf screen cmake build-essential sysstat python-matplotlib uuid-runtime

if [ "$mininet" == "y" ]
then
	cd ~
	rm -rf openflow &> /dev/null
	rm -rf loxigen &> /dev/null
	rm -rf mininet &> /dev/null
	git clone git://github.com/mininet/mininet
	cd mininet
	git checkout -b 2.2.1rc1 2.2.1rc1
	cd .. && sudo mininet/util/install.sh -a
fi

if [ "$metis" == "y" ]
then
	cd ~
	wget http://glaros.dtc.umn.edu/gkhome/fetch/sw/metis/metis-5.1.0.tar.gz
	tar -xzf metis-5.1.0.tar.gz
	rm metis-5.1.0.tar.gz
	cd metis-5.1.0
	make config
	make
	sudo make install
	cd ~
	rm -rf metis-5.1.0
fi

if [ "$pyro" == "y" ]
then
	sudo apt-get install python-pip
	sudo pip install Pyro4
fi


cd ~ && git clone git://github.com/MaxiNet/MaxiNet.git
cd MaxiNet
git checkout v1.0
sudo make install


