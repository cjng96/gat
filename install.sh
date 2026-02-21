#!/bin/bash

TARGET=~/.gat
mkdir -p $TARGET
cd $TARGET
REPO=$TARGET/repo

if [[ ! -d $REPO ]]; then
  git clone -b stable https://github.com/cjng96/gat.git repo
else
  echo "There is already gat(ev) repo in $REPO"
fi

if ! command -v uv &> /dev/null; then
  echo "'uv' command not found. Attempting to install with Homebrew..."
  if command -v brew &> /dev/null; then
    echo "Install uv with brew install uv"
  else
    echo "Homebrew is not installed. Please install Homebrew first."
  fi
  exit 1
else
  echo "uv is already installed."
fi

mkdir -p ~/bin
cat > ~/bin/gat << END
#!/bin/bash
P=~/.gat/repo
PYTHONPATH=\$P uv run --project \$P -m gat.gat \$@
END
chmod 755 ~/bin/gat


# Check if ~/bin is in PATH, and if not, add it to .zprofile
if [[ ":$PATH:" != *":$HOME/bin:"* ]]; then
  echo 'export PATH="$HOME/bin:$PATH"' >> ~/.zprofile
  echo "Added ~/bin to PATH in ~/.zprofile. Please restart your shell or run 'source ~/.zprofile'"
else
  echo "~/bin is already in PATH."
fi


echo "Please type 'gat' command to use it"

