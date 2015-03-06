import sys, os, subprocess,distutils
from setuptools import setup, find_packages

setup(name='MaxiNet',
      version='0.5',
      description='Distributed Software Defined Network Emulation',
      long_description="MaxiNet extends the famous Mininet emulation environment to span the emulation across several physical machines. This allows to emulate very large SDN networks.",
      classifiers=[
        'Programming Language :: Python :: 2.7',
      ],
      keywords='mininet MaxiNet SDN Network OpenFlow openvswitch',
      url='https://www.cs.uni-paderborn.de/?id=maxinet',
      author_email='maxinet@lists.upb.de',
      packages=find_packages(),
      install_requires=[
          'Pyro4',
      ],
      include_package_data=True,
      package_data={
        "MaxiNet":["Scripts/*"],
      },
      zip_safe=False)

if((__name__=="__main__") and (sys.argv[1] == "install")):
    # We need to make package_data files executable...
    # Ugly hack:
    fn = os.tempnam() # need file in different folder as local subfolder MaxiNet would be used otherwise
    f = open(fn,"w")
    f.write("""
import os,subprocess
print "Setting executable bits..."
from MaxiNet.tools import Tools
d = Tools.get_script_dir()
for f in filter(lambda x: x[-3:]==".sh",os.listdir(d)):
    print f
    subprocess.call(["sudo","chmod","a+x",d+f])
""")
    f.close()
    subprocess.call(["python",fn])
    os.remove(fn)
