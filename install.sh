#!/bin/bash

TARGET=~/.gat
mkdir -p ~/bin
mkdir -p $TARGET
cd $TARGET
REPO=$TARGET/repo

if [[ ! -d $REPO ]]; then
    git clone -b stable https://github.com/cjng96/gat.git repo
else
    echo "There is already gat(ev) repo in $REPO"
fi

if [[ ! -f ~/bin/gat ]]; then
    cd repo
    [ $? -ne 0 ] && echo "#### no repo folder" && exit
    virtualenv -p python3 env
    [ $? -ne 0 ] && echo "#### failed to run virtualenv" && exit
    ./env/bin/pip3 install -r requirements.txt
    [ $? -ne 0 ] && echo "#### failed to install python components" && exit

    cat > ~/bin/gat << END
#!/bin/bash
P=~/.gat/repo
\$P/env/bin/python3 \$P/gat/gat.py \$@
END
    chmod 755 ~/bin/gat

    echo "Please type 'gat' command to use it"
else
    echo "Setting is done already. Type 'gat' for starting"
fi

