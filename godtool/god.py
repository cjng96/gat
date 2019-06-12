#!/usr/bin/env python3

import collections
from copy import deepcopy
import os
import sys
import time
import json
import paramiko
import platform
import yaml
import socket
import subprocess
from threading import Thread
from queue import Queue, Empty
import datetime
import pathlib
import re

import zipfile
import tempfile

from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

from .__init__ import __version__

cwd = ""
scriptPath = ""
mymod = None


def path2folderList(pp):
	dirs = []
	while len(pp) >= 1:
		dirs.append(pp)
		pp, _  = os.path.split(pp)
		if pp == "/":
			break

	return dirs

def path2FolderListTest():
	print(path2folderList("/haha/a/test.txt"))
	print(path2folderList("haha/b/test.txt"))
	print(path2folderList("h/c/test.txt"))

# https://gist.github.com/angstwad/bf22d1822c38a92ec0a9
def mergeDict(dic, dic2):
	newDic = {}
	for k, v in dic.items():
		if k not in dic2:
			newDic[k] = deepcopy(v)

	for k, v in dic2.items():
		if (k in dic and isinstance(dic[k], dict) and isinstance(dic2[k], collections.Mapping)):
			newDic[k] = mergeDict(dic[k], dic2[k])
		else:
			newDic[k] = deepcopy(dic2[k])

	return newDic

class Args():
	def __init__(self):
		self.executableName = ""
		self.deployRoot = ""	# only for deployment
		self.deployOwner = ""	


class Tasks():
	def __init__(self):
		self.proc = None
		self.outStream = None
		self.isRestart = True	# First start or modified source files

	def doBuild(self, args, mygod):
		if hasattr(mygod, "doBuild"):
			return mygod.doBuild(args)

		print("run: building the app")
		ret = self.buildTask(args)
		if not ret:
			print("run: failed to build the program")

		return ret

	def buildTask(self, args):
		if hasattr(mygod, "buildTask"):
			return mygod.buildTask(args)

		return self.goBuild(args)

	def doServeStep(self, args, mygod):
		if hasattr(mygod, "doServeStep"):
			return mygod.doServeStep(args)

		if self.isRestart:
			print("\n\n\n")

			isSuccess = self.doBuild(args, mygod)

			if self.proc is not None:
				print("run: stop the daemon...")
				self.proc.kill()
				proc = None
				outStream = None

			if isSuccess:
				print("run: run %s..." % args.executableName)
				cmd = ["./"+args.executableName]
				self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
				self.outStream = NonBlockingStreamReader(self.proc.stdout)

			self.isRestart = False	# it's used in NonBlockingStreamReader

		if self.outStream is not None:
			line = self.outStream.readline(0.1)
			if line is not None:
				ss = line.decode("utf8")
				print(ss[:-1])

	def goBuild(self, args):
			cmd = ["go", "build", "-o", args.executableName]
			ret = subprocess.run(cmd)
			return ret.returncode == 0

	def dbGqlGen(self):
		print("task: gql gen...")

		# run only it's changed
		t1 = os.path.getmtime("schema.graphql")
		t2 = 0
		if os.path.exists("models_gen.go"):
			t2 = os.path.getmtime("models_gen.go")

		if t1 != t2:
			print("task: gql - graphql schema is updated... re-generate it.")
			cmd = ["go", "run", "github.com/99designs/gqlgen"]
			ret = subprocess.run(cmd)
			if ret.returncode != 0:
				print("run: failed to build graphql")

				return False

			os.utime("models_gen.go", (t1, t1))
		else:
			print("task: gql - skip because of no modification.")

		return True

	def dbXormReverse(self):
		print("task: xorm reverse...")

		# load from config
		with open("./config/base.json") as f:
			cfg = json.load(f)

		with open("./config/my.json") as f:
			cfg2 = json.load(f)
			cfg = mergeDict(cfg, cfg2)

		print("run: ", cfg)

		dbCfg = cfg["db"]
		host = dbCfg["host"]
		port = dbCfg["port"]
		id = dbCfg["id"]
		pw = dbCfg["pw"]
		db = dbCfg["name"]
		uri = "%s:%s@tcp(%s:%d)/%s?charset=utf8" % (id, pw, host, port, db)
		cmd = ["xorm", "reverse", "mysql", uri,
				"/home/cjng96/go/src/github.com/go-xorm/cmd/xorm/templates/goxorm"]
		subprocess.run(cmd)
		return True

	def pm2Register(self, useNvm=True):
		global ssh
		global args
		cmd = ""
		if useNvm:
			cmd += ". ~/.nvm/nvm.sh && "
		cmd += "cd %s/current && pm2 delete pm2.json && pm2 start pm2.json" % (args.deployRoot)
		ssh.run(cmd)
		return True


class NonBlockingStreamReader:
	def __init__(self, stream):
		'''
		stream: the stream to read from.
	    Usually a process' stdout or stderr.
		'''
		self._s = stream
		self._q = Queue()

		def _populateQueue(stream, queue):
			'''
			Collect lines from 'stream' and put them in 'quque'.
			'''
			while True:
				line = stream.readline()
				if line:
					queue.put(line)
				else:
					if tasks.isRestart:
						return

					print("non-block-stream: error")
					raise UnexpectedEndOfStream

		self._t = Thread(target=_populateQueue, args=(self._s, self._q))
		self._t.daemon = True
		self._t.start()  # start collecting lines from the stream

	def readline(self, timeout=None):
		try:
			return self._q.get(block=timeout is not None, timeout=timeout)
		except Empty:
			return None


class UnexpectedEndOfStream(Exception):
	pass

# https://pythonhosted.org/watchdog/


class MyHandler(PatternMatchingEventHandler):
	def __init__(self, patterns=None, ignore_patterns=None,
			ignore_directories=False, case_sensitive=False):
		super(MyHandler, self).__init__(
			patterns, ignore_patterns, ignore_directories, case_sensitive)
		print("watching pattern - ", patterns)

	def process(self, event):
		"""
		event.event_type - 'modified' | 'created' | 'moved' | 'deleted'
		event.is_directory - True | False
		event.src_path - path/to/observed/file
		"""
		if event.is_directory:
			return

		if tasks.isRestart:
			return

		print("run: file - %s is %s" % (event.src_path, event.event_type))
		tasks.isRestart = True

	def on_modified(self, event):
		self.process(event)

	def on_created(self, event):
		self.process(event)

ssh = None
mygod = None
args = Args()
tasks = Tasks()

config = {}

def confLoad():
	global config
	with open("god.yml", 'r') as fp:
		try:
			config = yaml.safe_load(fp)
			print(config)

			global args
			args.executableName = config["config"]["name"]

		except yaml.YAMLError as e:
			print("config: error - %s" % e)
			raise e

class SshAllowAllKeys(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self, client, hostname, key):
   	    return

def cutpath(parent, pp):
	if parent[-1] != "/":
		parent += "/"		 

	return pp[len(parent):]

def falseFunc(pp):
	return False

#https://gist.github.com/kdheepak/c18f030494fea16ffd92d95c93a6d40d
#https://stackoverflow.com/questions/760978/long-running-ssh-commands-in-python-paramiko-module-and-how-to-end-them
class Ssh:
	def __init__(self):
		pass

	def init(self, host, port, id):
		self.ssh = paramiko.SSHClient()
		#ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		self.ssh.set_missing_host_key_policy(SshAllowAllKeys())
		self.ssh.connect(host, port=port, username=id)	#, password='lol')

		self.sftp = paramiko.SFTPClient.from_transport(self.ssh.get_transport())

		self.uploadFilterFunc = falseFunc

	def close(self):
		self.ssh.close()

	# return: result
	def run(self, cmd):
		chan = self.ssh.get_transport().open_session()
		chan.exec_command(cmd)
		chan.setblocking(0)
		out = ""
		while True:
			try:
				line = chan.recv(99999)
				if len(line) == 0:
					break
				out += line.decode("utf-8")
			except socket.timeout as e:
				pass

			try:
				line = chan.recv_stderr(99999)
				if len(line) == 0:
					break
				out += line.decode("utf-8")
			except socket.timeout as e:
				pass

		ret = chan.recv_exit_status()
		print("execute[%s] - ret:%d\n%s" % (cmd, ret, out))
		chan.close()
		if ret != 0:
			raise Exception("ssh command failed with ret:%d" % ret)
		return out


	# sftp 상에 경로를 생성한다.
	# remote 경로가 directory이면, is_dir에 True를 전달한다.
	def mkdir_p(self, remote, isFolder=False):
		dirs = []
		if isFolder:
			pp = remote
		else:
			pp, basename = os.path.split(remote)

		dirs = path2folderList(pp)

		# check last folder first
		if len(dirs) > 0:
			try:
				self.sftp.stat(dirs[0])
				return
			except:
				pass

		while len(dirs):
			pp = dirs.pop()
			try:
				self.sftp.stat(pp)
			except:
				print("sftp: making dir ->",  pp)
				self.sftp.mkdir(pp)

	def uploadFileTo(self, srcPath, destFolder):
		#print("sftp: uploadFilesTo - %s %s" % (srcPath, destFolder))
		name = os.path.split(srcPath)[1]
		self.uploadFile(srcPath, os.path.join(destFolder, name))


	# sftp 상에 파일을 업로드한다.
	# src_path에 dest_path로 업로드한다. 두개 모두 file full path여야 한다.
	def uploadFile(self, srcPath, destPath):
		print("sftp: upload file %s -> %s" % (srcPath, destPath))
		if self.uploadFilterFunc(srcPath):
			print(" ** exclude file - %s" % srcPath)
			return

		self.mkdir_p(destPath)
		try:
			self.sftp.put(srcPath, destPath)
		except Exception as e:
			#print("sftp: fail to upload " + srcPath + " ==> " + destPath)
			raise e
		#print("sftp: success to upload " + srcPath + " ==> " + destPath)

	# srcPath, destPath둘다 full path여야한다.
	def uploadFolder(self, srcPath, destPath):
		print("sftp: upload folder %s -> %s" % (srcPath, destPath))
		if self.uploadFilterFunc(srcPath):
			print(" ** exclude folder - %s" % srcPath)
			return

		self.mkdir_p(destPath, True)

		for folder, dirs, files in os.walk(srcPath):
			try:
				for pp in files:
					src = os.path.join(folder, pp)
					target = os.path.join(destPath, cutpath(srcPath, folder), pp)
					self.uploadFile(src, target)
			except Exception as e:
				print(e)
				raise e

def deploy(serverName):
	global config
	server = None
	
	for it in config["servers"]:
		if it["name"] == serverName:
			server = it
			print("deploy: selected server - ", it)
			break

	if server is None:
		print("Not found server[%s]" % serverName)
		return

	tasks.doBuild(args, mygod)

	global ssh
	ssh = Ssh()
	port = 22
	if "port" in server:
		port = server["port"]
	print("deploy: connecting to the server[%s:%d] with ID:%s" % (server["host"], port, server["id"]))
	ssh.init(server["host"], port, server["id"])

	targetPath = server["targetPath"]
	name = config["config"]["name"]
	realTarget = ssh.run("mkdir -p %s/shared && cd %s && mkdir -p releases && pwd" % (targetPath, targetPath))
	realTarget = realTarget.strip("\r\n")	# for sftp


	todayName = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")[2:]
	res = ssh.run("cd %s/releases && ls -d */" % targetPath)
	releases = list(filter(lambda x: re.match('\d{6}_\d{6}', x) is not None, res.split()))
	releases.sort()

	max = config["deploy"]["maxRelease"]-1
	cnt = len(releases)
	print("deploy: releases folders count is %d" % cnt)
	if cnt > max:
		print("deploy: remove old %d folders" % (cnt - max))
		removeList = releases[:cnt-max]
		for ff in removeList:
			if args.deployOwner != "":
				ssh.run("sudo rm -rf %s/releases/%s" % (targetPath, ff))
			else:
				ssh.run("rm -rf %s/releases/%s" % (targetPath, ff))

	# if deploy / owner is defined,
	# create release folder as ssh user, upload, extract then change release folder to deploy / owner
	if args.deployOwner != "":
		res = ssh.run("cd %s/releases && sudo mkdir %s && sudo chown %s: %s" % (targetPath, todayName, server["id"], todayName))
	else:
		res = ssh.run("cd %s/releases && mkdir %s" % (targetPath, todayName))

	# pre task
	args.deployRoot = targetPath
	if hasattr(mygod, "deployPreTask"):
		mygod.deployPreTask(ssh, args)

	# upload files
	realTargetFull = os.path.join(realTarget, "releases", todayName)
	include = []
	exclude = []
	sharedLinks = []
	include = config["deploy"]["include"]
	if "exclude" in config["deploy"]:
		exclude = config["deploy"]["exclude"]
	if "sharedLinks" in config["deploy"]:
		sharedLinks = config["deploy"]["sharedLinks"]

	def _filterFunc(pp):
		pp = os.path.normpath(pp)
		if pp in exclude:
			return True
		return False

	strategy = config["deploy"]["strategy"]
	if strategy == "zip":
		zipPath = os.path.join(tempfile.gettempdir(), "data.zip")
		with zipfile.ZipFile(zipPath, "w") as zipWork:

			def _zipAdd(srcP, targetP):
				if _filterFunc(srcP):
					print("deploy: skip - %s" % srcP)
					return

				# make "./aaa" -> "aaa"
				targetP = os.path.normpath(targetP)

				print("zipping %s -> %s" % (srcP, targetP))
				zipWork.write(srcP, targetP, compress_type=zipfile.ZIP_DEFLATED)

			#zipWork.write(name, name, compress_type=zipfile.ZIP_DEFLATED)
			for pp in include:
				if type(pp) == str:
					if pp == "*":
						pp = "."
					
					# daemon
					pp = pp.replace("${name}", name)
						
					p = pathlib.Path(pp)
					if not p.exists():
						print("deploy: not exists - %s" % pp)
						continue
					
					if p.is_dir():
						if _filterFunc(pp):
							print("deploy: skip - %s" % pp)
							continue

						for folder, dirs, files in os.walk(pp):
							# filtering dirs too
							dirs2 = []
							for d in dirs:
								if _filterFunc(d):
									print("deploy: skip - %s" % d)
								else:
									dirs2.append(d)
							dirs[:] = dirs2

							for ff in files:
								_zipAdd(os.path.join(folder, ff), os.path.join(folder, ff))
					else:
						_zipAdd(pp, pp)

				else:
					src = pp["src"]
					target = pp["target"]

					for folder, dirs, files in os.walk(src):
						for ff in files:
							_zipAdd(os.path.join(folder, ff), os.path.join(target, cutpath(src, folder), ff))

		ssh.uploadFile(zipPath, os.path.join(realTargetFull, "data.zip"))	# we don't include it by default
		ssh.run("cd %s/releases/%s && unzip data.zip && rm data.zip" % (targetPath, todayName))
		os.remove(zipPath)
		"""	no use copy strategy anymore
		elif strategy == "copy":
			ssh.uploadFile(name, os.path.join(realTargetFull, name))	# we don't include it by default
			ssh.run("chmod 755 %s/%s" % (realTargetFull, name))

			ssh.uploadFilterFunc = _filterFunc

			for pp in include:
				if type(pp) == str:
					if pp == "*":
						pp = "."
					
					# daemon
					pp = pp.replace("${name}", name)
											
					p = pathlib.Path(pp)
					if not p.exists():
						print("deploy: not exists - %s" % pp)
						continue
					
					if p.is_dir():
						tt = os.path.join(realTargetFull, pp)
						ssh.uploadFolder(pp, tt)
					else: 
						ssh.uploadFileTo(pp, realTargetFull)
				else:
					src = pp["src"]
					target = pp["target"]
					tt = os.path.join(realTargetFull, target)
					ssh.uploadFolder(src, tt)
		"""
	else:
		raise Exception("unknown strategy[%s]" % strategy)

	# shared links
	for pp in sharedLinks:
		print("deploy: sharedLinks - %s" % pp)
		folder = os.path.dirname(pp)
		ssh.run("cd %s && mkdir -p shared/%s && ln -sf %s/shared/%s releases/%s/%s" % (targetPath, folder, targetPath, pp, todayName, pp))

	# update link
	if args.deployOwner != "":
		ssh.run("cd %s && sudo rm current && sudo ln -sf releases/%s current && sudo chown %s: current" % (targetPath, todayName, server["id"]))
	else:
		ssh.run("cd %s && rm current && ln -sf releases/%s current" % (targetPath, todayName))

	# post process
	if hasattr(mygod, "deployPostTask"):
		mygod.deployPostTask(ssh, args)

	if args.deployOwner != "":
		ssh.run("cd %s && sudo chown %s: releases/%s current" % (targetPath, args.deployOwner, todayName))

	ssh.close()

def initSamples():
	with open("god_my.py", "w") as fp:
		fp.write("""
class myGod:
	def __init__(self, tasks):
		self.tasks = tasks

	def buildTask(self, args):
		#if not self.tasks.dbGqlGen():
		#	return False
		return self.tasks.goBuild(args)

	def deployPreTask(self, ssh, args):
		#subprocess.check_output("npm run build", shell=True)
		return True

	def deployPostTask(self, ssh, args):
		#if not self.tasks.pm2Register():
		#	return False
		#ssh.run("cd %s/current && echo 'finish'" % args.deployRoot)
		return True
""")
		
	with open("god.yml", "w") as fp:
		fp.write("""
config:
  name: test

serve:
  patterns:
    - "*.go"
    - "*.json"
    - "*.graphql"

deploy:
  strategy: zip
  #owner: test	# all generated files's owner is set it. if owner is specified, servers/id should be the user who can use sudo command due to sudo cmd
  maxRelease: 3
  include:
	#- "*"
	- ${name}
    - config
    - pm2.json
		- src: ../build
		  target: build
  exclude:
    - config/my.json
  sharedLinks:
    - config/my.json
  

servers:
  - name: test
    host: test.com
	port: 22
    id: test
    targetPath: ~/test
""")
	print("init: god_my.py and god.yml files generated. You should modify those files for your environment before service or deployment.")

def printTasks():
	print(
'''god-tool V%s
buildTask - 
  goBuild(args): "go build -o config.name"
servePreTask - 
  dbGqlGen(): running "go run github.com/99designs/gqlgen" job for gqlgen(https://github.com/99designs/gqlgen)
deployPostTask - 
  pm2Register(): "pm2 start pm2.json" - You should define pm2.json file first.
''' % __version__)

def main():
	global cwd, scriptPath, mymod, mygod
	cwd = os.getcwd()
	scriptPath = os.path.dirname(os.path.realpath(__file__))

	cnt = len(sys.argv)
	if cnt > 1:
		cmd = sys.argv[1]
		if cmd == "init":
			initSamples()
			return
		elif cmd == "tasks":
			printTasks()
			return

	# check first
	sys.path.append(cwd)
	if not os.path.exists("god_my.py") or not os.path.exists("god.yml"):
		print("god-tool V%s\nThere is no god relevent files. you can initialize by 'god init' command" % __version__)
		return

	mymod = __import__("god_my", fromlist=[''])
	mygod = mymod.myGod(tasks)

	print("god-tool V%s" % __version__)
	confLoad()
	global config
	name = config["config"]["name"]

	print("** daemon is %s" % name)

	global args
	if "owner" in config["deploy"]:
		args.deployOwner = config["deploy"]["owner"]

	if cnt > 1:
		cmd = sys.argv[1]
		if cmd == "deploy":
			if cnt < 3:
				# todo: print server list
				print("Please specify server name.")
				return
			deploy(sys.argv[2])
			return
		else:
			print("unknown command - %s" % cmd)
			return

	observer = Observer()
	observer.schedule(MyHandler(config["serve"]["patterns"]), path=".", recursive=True)
	observer.start()

	tasks.isRestart = True

	try:
		while True:
			time.sleep(0.01)
			tasks.doServeStep(args, mygod)

	except KeyboardInterrupt:
		observer.stop()

	observer.join()


if __name__ == "__main__":
	main()
