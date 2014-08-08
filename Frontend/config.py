import logging

logging.basicConfig(level=logging.INFO)
cfg = { "debian-vm1" :  { "ip" : "192.168.123.1"},
        "debian-vm2" : { "ip" : "192.168.123.2"},
        "debian-vm3" : { "ip" : "192.168.123.3"}
}
defaults = { "ip":None, "ls": "192.168.0.1", "share": 1 }
controller = "192.168.123.1:6633" # default controller
defaults = { "ip":None, "share": 1 }
runWith1500MTU = False




