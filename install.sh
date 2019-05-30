#!/bin/bash

TARGET=~/.god
mkdir -p ~/bin
mkdir -p $TARGET
cd $TARGET
REPO=$TARGET/repo

if [[ ! -d $REPO ]]; then
    git clone -b stable https://github.com/cjng96/god.git
else
    echo "There is already god repo in $REPO"
fi

COMMENT="## god(ev) script ##"
cnt=$(sh -c "grep '$COMMENT' ~/.bashrc | wc -l")
if [[ $cnt -eq  0 ]]; then
    cd repo
    [ $? -ne 0 ] && echo "#### no repo folder" && exit
    virtualenv -p python3 env
    [ $? -ne 0 ] && echo "#### failed to run virtualenv" && exit
    ./env/bin/pip3 install -r requirements.txt
    [ $? -ne 0 ] && echo "#### failed to install python components" && exit

    cat << EOF > ~/bin/god
    cd ~/.god/repo
    ./env/bin/python3 god.py $@
    EOF

    echo "Please type 'god'"
else
    echo "Setting is done already. Type 'god' for starting"
fi

