#!/bin/bash

TARGET=~/.god
mkdir -p ~/bin
mkdir -p $TARGET
cd $TARGET
REPO=$TARGET/repo

if [[ ! -d $REPO ]]; then
    git clone -b stable https://github.com/cjng96/god.git repo
else
    echo "There is already god(ev) repo in $REPO"
fi

if [[ ! -f ~/bin/god ]]; then
    cd repo
    [ $? -ne 0 ] && echo "#### no repo folder" && exit
    virtualenv -p python3 env
    [ $? -ne 0 ] && echo "#### failed to run virtualenv" && exit
    ./env/bin/pip3 install -r requirements.txt
    [ $? -ne 0 ] && echo "#### failed to install python components" && exit

    cat > ~/bin/god << END
#!/bin/bash
P=~/.god/repo
\$P/env/bin/python3 \$P/god.py \$@
END
    chmod 755 ~/bin/god

    echo "Please type 'god' command to use it"
else
    echo "Setting is done already. Type 'god' for starting"
fi

