PWD=`pwd`

if [ `basename $PWD` = Worker ] 
    then
    echo installing scripts...
    chmod +x bin/*
    sudo cp -vp bin/* /usr/local/bin/
else
    echo please call $0 from Worker directory
    exit 1
fi
