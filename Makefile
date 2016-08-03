install:
	python2 setup.py install
	mkdir -p /usr/local/share/MaxiNet
	cp -rv MaxiNet/Frontend/examples /usr/local/share/MaxiNet/
	chmod +x /usr/local/share/MaxiNet/examples/*
	cp share/MaxiNet-cfg-sample /usr/local/share/MaxiNet/config.example
	cp share/maxinet_plot.py changelog.txt INSTALL.txt LICENSE.txt /usr/local/share/MaxiNet/

clean:
	-rm -rf build
	-rm -rf dist

uninstall:
	rm -rf /usr/local/lib/python2.7/dist-packages/MaxiNet-*/
	rm -rf /usr/local/share/MaxiNet
	rm -f /usr/local/bin/MaxiNetServer /usr/local/bin/MaxiNetStatus /usr/local/bin/MaxiNetFrondendServer /usr/local/bin/MaxiNetWorker

reinstall: uninstall clean install

.PHONY: clean install uninstall reinstall
