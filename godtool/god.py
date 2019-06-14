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
from .coSsh import CoSsh
from .coPath import cutpath
from .sampleFiles import sampleApp, sampleEnv

g_cwd = ""
g_scriptPath = ""


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

	def doBuild(self, mygod, args):
		if hasattr(mygod, "doBuild"):
			return mygod.doBuild(args=args)

		print("run: building the app")
		ret = self.buildTask(mygod, args)
		if not ret:
			print("run: failed to build the program")

		return ret

	def buildTask(self, mygod, args):
		if hasattr(mygod, "buildTask"):
			return mygod.buildTask(args=args)

		return self.goBuild(args)

	def doServeStep(self, mygod, args):
		if hasattr(g_mygod, "doServeStep"):
			return g_mygod.doServeStep(args=args)

		if self.isRestart:
			print("\n\n\n")

			isSuccess = self.doBuild(mygod, args)

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

	def gqlGen(self):
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
		global g_ssh
		cmd = ""
		if useNvm:
			cmd += ". ~/.nvm/nvm.sh && "
		cmd += "cd %s/current && pm2 delete pm2.json && pm2 start pm2.json" % (g_args.deployRoot)
		g_ssh.run(cmd)
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
					if g_tasks.isRestart:
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

		if g_tasks.isRestart:
			return

		print("run: file - %s is %s" % (event.src_path, event.event_type))
		g_tasks.isRestart = True

	def on_modified(self, event):
		self.process(event)

	def on_created(self, event):
		self.process(event)

g_ssh = None
g_mygod = None
g_args = Args()
g_tasks = Tasks()

g_config = {}



def configServerGet(name):
	server = None
	for it in g_config["servers"]:
		if it["name"] == name:
			server = it
			print("deploy: selected server - ", it)
			break

	if server is None:
		print("Not found server[%s]" % name)
		return None

	return server


def deploy(serverName):
	global g_config
	server = configServerGet(serverName)
	if server is None:
		return

	g_tasks.doBuild(g_mygod, g_args)

	global g_ssh
	g_ssh = CoSsh()
	port = server["port"] if "port" in server else 22
	print("deploy: connecting to the server[%s:%d] with ID:%s" % (server["host"], port, server["id"]))
	g_ssh.init(server["host"], port, server["id"])

	name = g_config["config"]["name"]
	targetPath = server["targetPath"]
	realTarget = g_ssh.run("mkdir -p %s/shared && cd %s && mkdir -p releases && pwd" % (targetPath, targetPath))
	realTarget = realTarget.strip("\r\n")	# for sftp

	todayName = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")[2:]
	res = g_ssh.run("cd %s/releases && ls -d */" % targetPath)
	releases = list(filter(lambda x: re.match('\d{6}_\d{6}', x) is not None, res.split()))
	releases.sort()

	max = g_config["deploy"]["maxRelease"]-1
	cnt = len(releases)
	print("deploy: releases folders count is %d" % cnt)
	if cnt > max:
		print("deploy: remove old %d folders" % (cnt - max))
		removeList = releases[:cnt-max]
		for ff in removeList:
			if g_args.deployOwner != "":
				g_ssh.run("sudo rm -rf %s/releases/%s" % (targetPath, ff))
			else:
				g_ssh.run("rm -rf %s/releases/%s" % (targetPath, ff))

	# if deploy / owner is defined,
	# create release folder as ssh user, upload, extract then change release folder to deploy / owner
	if g_args.deployOwner != "":
		res = g_ssh.run("cd %s/releases && sudo mkdir %s && sudo chown %s: %s" % (targetPath, todayName, server["id"], todayName))
	else:
		res = g_ssh.run("cd %s/releases && mkdir %s" % (targetPath, todayName))

	# pre task
	g_args.deployRoot = targetPath
	if hasattr(g_mygod, "deployPreTask"):
		g_mygod.deployPreTask(ssh=g_ssh, args=g_args)

	# upload files
	realTargetFull = os.path.join(realTarget, "releases", todayName)
	include = []
	exclude = []
	sharedLinks = []
	include = g_config["deploy"]["include"]
	if "exclude" in g_config["deploy"]:
		exclude = g_config["deploy"]["exclude"]
	if "sharedLinks" in g_config["deploy"]:
		sharedLinks = g_config["deploy"]["sharedLinks"]

	def _filterFunc(pp):
		pp = os.path.normpath(pp)
		if pp in exclude:
			return True
		return False

	strategy = g_config["deploy"]["strategy"]
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

		g_ssh.uploadFile(zipPath, os.path.join(realTargetFull, "data.zip"))	# we don't include it by default
		g_ssh.run("cd %s/releases/%s && unzip data.zip && rm data.zip" % (targetPath, todayName))
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
		g_ssh.run("cd %s && mkdir -p shared/%s && ln -sf %s/shared/%s releases/%s/%s" % (targetPath, folder, targetPath, pp, todayName, pp))

	# update link
	if g_args.deployOwner != "":
		g_ssh.run("cd %s && sudo rm current && sudo ln -sf releases/%s current && sudo chown %s: current" % (targetPath, todayName, server["id"]))
	else:
		g_ssh.run("cd %s && rm current && ln -sf releases/%s current" % (targetPath, todayName))

	# post process
	if hasattr(g_mygod, "deployPostTask"):
		g_mygod.deployPostTask(ssh=g_ssh, args=g_args)

	if g_args.deployOwner != "":
		g_ssh.run("cd %s && sudo chown %s: releases/%s current" % (targetPath, g_args.deployOwner, todayName))

	g_ssh.close()


def initSamples(type, fn):
	with open(fn, "w") as fp:
		if type == "app":
			fp.write(sampleApp)
		else:
			fp.write(sampleEnv)
		
	print("init: %s file generated. You should modify that file for your environment before service or deployment." % (fn))

def printTasks():
	print(
'''god-tool V%s
buildTask - 
  goBuild(args): "go build -o config.name"
servePreTask - 
  gqlGen(): running "go run github.com/99designs/gqlgen" job for gqlgen(https://github.com/99designs/gqlgen)
deployPostTask - 
  pm2Register(): "pm2 start pm2.json" - You should define pm2.json file first.
''' % __version__)

class Helper:
	def __init__(self):
		pass

	def configStr(self, type, ss):
		'''
		type: yaml

		'''
		global g_config, g_args
		if type == "yaml":
			try:
				g_config = yaml.safe_load(ss)
				g_args.executableName = g_config["config"]["name"]
			except yaml.YAMLError as e:
				raise e

		else:
			raise Exception("unknown config type[%s]" % type)

	def configFile(self, type, pp):
		'''
		type: yaml
		'''
		with open(pp, "r") as fp:
			self.configStr(type, fp.read())

g_helper = Helper()

def main():
	global g_cwd, g_scriptPath, g_mygod
	g_cwd = os.getcwd()
	g_scriptPath = os.path.dirname(os.path.realpath(__file__))

	cnt = len(sys.argv)
	cmd = None
	if cnt > 1:
		cmd = sys.argv[1]

		if cmd == "init":
			if cnt < 3:
				print("god init app OR god init env NAME.")
				return

			type = sys.argv[2]
			if type != "app" and type != "env":
				print("app or env can be used for god init command.")
				return

			target = sys.argv[2] if cnt > 3 else "god_my.py"
			initSamples(type, target)
			return
		elif cmd == "tasks":
			printTasks()
			return
		elif cmd == "deploy":
			target = "god_my.py"
			pass
		elif cmd == "setup":
			# server env
			if cnt < 3:
				print("god setup FILE.py")
				return
			target = sys.argv[2]
		else:
			print("unknown command - %s" % cmd)
			return

	else:
		# default operation for app
		target = "god_my.py"

	# check first
	if not os.path.exists(target):	# or not os.path.exists("god.yml"):
		print("god-tool V%s\nThere is no god relevent file. you can run god YOUR_GOD_FILE.py or initialize by 'god init'" % __version__)
		return

	sys.path.append(g_cwd)
	mymod = __import__(target[:-3], fromlist=[''])
	g_mygod = mymod.myGod(tasks=g_tasks, helper=g_helper)

	print("god-tool V%s" % __version__)
	global g_config
	name = g_config["config"]["name"]
	type = g_config["config"]["type"] if "type" in g_config["config"] else "app"

	print("** config[type:%s, name:%s]" % (type, name))

	global g_args

	if cmd == "deploy":
		if "owner" in g_config["deploy"]:
			g_args.deployOwner = g_config["deploy"]["owner"]

		target = sys.argv[2] if cnt > 2 else None
		if target is None:
			# todo: print server list
			print("Please specify server name.")
			return
		deploy(target)
		return
	elif cmd == "setup":
		serverName = "" if cnt <= 3 else sys.argv[3]
		setup(target, serverName)
		return

	# serve
	serve()

def setup(target, serverName):
	if not os.path.exists(target):
		print("There is no target file[%s]" % target)
		return
	
	server = configServerGet(serverName)
	if server is None:
		return

	global g_ssh
	g_ssh = Ssh()
	port = server["port"] if "port" in server else 22
	print("setup: connecting to the server[%s:%d] with ID:%s" % (server["host"], port, server["id"]))
	g_ssh.init(server["host"], port, server["id"])

	if hasattr(g_mygod, "setupTask"):
		g_mygod.setupTask(ssh=g_ssh, args=g_args)
	else:
		print("setup: You should override setupTask function in your myGod class")
		return


def serve():
	observer = Observer()
	observer.schedule(MyHandler(g_config["serve"]["patterns"]), path=".", recursive=True)
	observer.start()

	g_tasks.isRestart = True
	try:
		while True:
			time.sleep(0.01)
			g_tasks.doServeStep(g_mygod, g_args)

	except KeyboardInterrupt:
		observer.stop()

	observer.join()


if __name__ == "__main__":
	main()
