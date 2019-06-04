
# Features
- Automatically re-run the application when modifying the soruce.
- Deploy the application like Capistrano. it's powerful but simple.

# How to install
\$ pip3 install god-tool

then you can use "god init" command under the foler which you want to use.

# How to use
## Initialization

\$ god init

It generates god.yml and god_my.py files.

### god.yml
You can define the configure of the application and the server definition for the application deployment in this file.

### god_my.py
You can define and expand the jobs for running and deployments.
