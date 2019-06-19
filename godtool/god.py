#!/usr/bin/env python3

import os
import sys
import time
import json
import paramiko
import platform
import yaml
import socket
import subprocess
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
from .sampleFiles import sampleApp, sampleSys
from .godHelper import strExpand
from .coS3 import CoS3
from .myutil import NonBlockingStreamReader, str2arg, mergeDict

g_cwd = ""
g_scriptPath = ""

class MyUtil():
	def __init__(self):
		self.executableName = ""
		self.deployRoot = ""	# only for deployment
		self.deployOwner = ""	
		self.isRestart = True	# First start or modified source files

class Tasks():
	def __init__(self, server):
		self.proc = None
		self.outStream = None
		self.server = server	# None: local

		self.ssh = None
		if server is not None:
			self.ssh = CoSsh()
			port = server["port"] if "port" in server else 22
			print("deploy: connecting to the server[%s:%d] with ID:%s" % (server["host"], port, server["id"]))
			self.ssh.init(server["host"], port, server["id"])

	def __del__(self):
		if self.ssh is not None:
			self.ssh.close()
			self.ssh = None

	def onlyLocal(self):
		if self.server is not None:
			raise Exception("this method only can be used in local service.")

	def onlyRemote(self):
		if self.server is None:
			raise Exception("this method only can be used in remote service.")

	def buildTask(self, mygod):
		self.onlyLocal()

		print("run: building the app")
		if hasattr(mygod, "buildTask"):
			return mygod.buildTask(util=g_util, local=g_local, remote=g_remote)

		self.goBuild()

	def doServeStep(self, mygod):
		#if hasattr(g_mygod, "doServeStep"):
		#	return g_mygod.doServeStep()

		if g_util.isRestart:
			print("\n\n\n")

			buildExc = None
			try:
				self.buildTask(mygod)
			except Exception as e:
				buildExc = e

			if self.proc is not None:
				print("run: stop the daemon...")
				self.proc.kill()
				self.proc = None
				self.outStream = None

			if buildExc is None:
				print("run: run %s..." % g_util.executableName)
				cmd = ["./"+g_util.executableName]
				self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
				self.outStream = NonBlockingStreamReader(self.proc.stdout)

			g_util.isRestart = False	# it's used in NonBlockingStreamReader

		if self.outStream is not None:
			line = self.outStream.readline(0.1)
			if line is None:
				if not g_util.isRestart:
					raise Exception("non-block-stream: error")
			else:
				ss = line.decode("utf8")
				print(ss[:-1])

	def run(self, cmd):
		"""
		cmd: string or array
		"""
		if self.server is not None:
			return self.ssh.run(cmd)
		else:
			return subprocess.check_output(cmd, shell=True)

	def uploadFile(self, src, dest):
		self.onlyRemote()

		self.ssh.uploadFile(src, dest)

	def goBuild(self):
		print("task: goBuild...")

		self.onlyLocal()

		cmd = ["go", "build", "-o", g_util.executableName]
		ret = subprocess.run(cmd)
		if ret.returncode != 0:
			raise Exception("task.goBuild: build failed")

	def gqlGen(self):
		print("task: gql gen...")
		self.onlyLocal()

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
				raise Exception("task.gqlGen: failed to build graphql")

			os.utime("models_gen.go", (t1, t1))
		else:
			print("task: gql - skip because of no modification.")


	def dbXormReverse(self):
		print("task: xorm reverse...")
		self.onlyLocal()

		# load from config
		with open("./config/base.json") as f:
			cfg = json.load(f)

		with open("./config/my.json") as f:
			cfg2 = json.load(f)
			cfg = mergeDict(cfg, cfg2)

		print("run: ", cfg)

		db = cfg["db"]
		uri = "%s:%s@tcp(%s:%d)/%s?charset=utf8" % (db["id"], db["pw"], db["host"], db["port"], db["name"])
		cmd = ["xorm", "reverse", "mysql", uri,
				"/home/cjng96/go/src/github.com/go-xorm/cmd/xorm/templates/goxorm"]
		self.run(cmd)

	def pm2Register(self, useNvm=True):
		print("task: pm2 register...")
		self.onlyRemote()

		cmd = ""
		if useNvm:
			cmd += ". ~/.nvm/nvm.sh && "
		cmd += "cd %s/current && pm2 delete pm2.json && pm2 start pm2.json" % (g_util.deployRoot)
		self.ssh.run(cmd)

	def configBlock(self, path, marker, block, insertAfter=None):
		print("task: config block...")
		self.onlyRemote()

		dic = dict(name=g_config["config"]["name"])

		cfg = dict(cmd="configBlock", dic=dic,
			path=path, marker=marker, block=block, insertAfter=insertAfter)
		#pp = "/tmp/god_cfg.json"
		#json.dump(cfg, "/tmp/god_cfg.json")
		#g_ssh.uploadFile(pp, pp)

		pp2 = "/tmp/godHelper.py"
		self.uploadFile("./godHelper.py", pp2)
		self.run("python3 %s runStr \"%s\"" % (pp2, str2arg(json.dumps(cfg))))

	def configLine(self, path, regexp, line, items=None):
		print("task: config line...")
		self.onlyRemote()

		dic = dict(name=g_config["config"]["name"])

		cfg = dict(cmd="configLine", dic=dic,
			path=path, regexp=regexp, line=line, items=items)

		pp2 = "/tmp/godHelper.py"
		self.uploadFile("./godHelper.py", pp2)
		self.run("python3 %s runStr \"%s\"" % (pp2, str2arg(json.dumps(cfg))))

	def s3List(self, bucket, prefix):
		print("task: s3 list...")

		self.onlyLocal()

		s3 = CoS3()
		bb = s3.bucketGet(bucket)
		lst = bb.fileList(prefix)
		return lst

	def s3DownloadFiles(self, bucket, prefix, nameList, targetFolder):
		print("task: s3 download files...")

		self.onlyLocal()

		if not targetFolder.endswith("/"):
			targetFolder += "/"
		if not prefix.endswith("/"):
			prefix += "/"

		s3 = CoS3()
		bb = s3.bucketGet(bucket)
		for name in nameList:
			bb.downloadFile(prefix+name, targetFolder+name)


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

		if g_util.isRestart:
			return

		print("run: file - %s is %s" % (event.src_path, event.event_type))
		g_util.isRestart = True

	def on_modified(self, event):
		self.process(event)

	def on_created(self, event):
		self.process(event)

g_mygod = None

g_util = MyUtil()
g_local = Tasks(None)
g_remote = None

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


def taskDeploy(serverName):
	global g_config
	server = configServerGet(serverName)
	if server is None:
		return

	g_local.buildTask(g_mygod)

	global g_remote
	g_remote = Tasks(server)

	name = g_config["config"]["name"]
	targetPath = server["targetPath"]
	realTarget = g_remote.run("mkdir -p %s/shared && cd %s && mkdir -p releases && pwd" % (targetPath, targetPath))
	realTarget = realTarget.strip("\r\n")	# for sftp

	todayName = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")[2:]
	res = g_remote.run("cd %s/releases && ls -d */" % targetPath)
	releases = list(filter(lambda x: re.match('\d{6}_\d{6}', x) is not None, res.split()))
	releases.sort()

	max = g_config["deploy"]["maxRelease"]-1
	cnt = len(releases)
	print("deploy: releases folders count is %d" % cnt)
	if cnt > max:
		print("deploy: remove old %d folders" % (cnt - max))
		removeList = releases[:cnt-max]
		for ff in removeList:
			if g_util.deployOwner != "":
				g_remote.run("sudo rm -rf %s/releases/%s" % (targetPath, ff))
			else:
				g_remote.run("rm -rf %s/releases/%s" % (targetPath, ff))

	# if deploy / owner is defined,
	# create release folder as ssh user, upload, extract then change release folder to deploy / owner
	if g_util.deployOwner != "":
		res = g_remote.run("cd %s/releases && sudo mkdir %s && sudo chown %s: %s" % (targetPath, todayName, server["id"], todayName))
	else:
		res = g_remote.run("cd %s/releases && mkdir %s" % (targetPath, todayName))

	# pre task
	g_util.deployRoot = targetPath
	if hasattr(g_mygod, "deployPreTask"):
		g_mygod.deployPreTask(util=g_util, remote=g_remote, local=g_local)

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
					dic = dict(name=name)
					pp = strExpand(pp, dic)
						
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

		g_remote.uploadFile(zipPath, os.path.join(realTargetFull, "data.zip"))	# we don't include it by default
		g_remote.run("cd %s/releases/%s && unzip data.zip && rm data.zip" % (targetPath, todayName))
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
		g_remote.run("cd %s && mkdir -p shared/%s && ln -sf %s/shared/%s releases/%s/%s" % (targetPath, folder, targetPath, pp, todayName, pp))

	# update link
	if g_util.deployOwner != "":
		g_remote.run("cd %s && sudo rm current && sudo ln -sf releases/%s current && sudo chown %s: current" % (targetPath, todayName, server["id"]))
	else:
		g_remote.run("cd %s && rm current && ln -sf releases/%s current" % (targetPath, todayName))

	# post process
	if hasattr(g_mygod, "deployPostTask"):
		g_mygod.deployPostTask(util=g_util, local=g_local, remote=g_remote)

	if g_util.deployOwner != "":
		g_remote.run("cd %s && sudo chown %s: releases/%s current" % (targetPath, g_util.deployOwner, todayName))

def initSamples(type, fn):
	with open(fn, "w") as fp:
		if type == "app":
			fp.write(sampleApp)
		else:
			fp.write(sampleSys)
		
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
		global g_config
		if type == "yaml":
			try:
				g_config = yaml.safe_load(ss)
				g_util.executableName = g_config["config"]["name"]
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
				print("god init app OR god init sys NAME.")
				return

			type = sys.argv[2]
			if type != "app" and type != "sys":
				print("app or sys can be used for god init command.")
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
			# server sys
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

	helper = Helper()

	sys.path.append(g_cwd)
	mymod = __import__(target[:-3], fromlist=[''])
	g_mygod = mymod.myGod(helper=helper)

	print("god-tool V%s" % __version__)
	global g_config
	name = g_config["config"]["name"]
	type = g_config["config"]["type"] if "type" in g_config["config"] else "app"

	print("** config[type:%s, name:%s]" % (type, name))

	if cmd == "deploy":
		if "owner" in g_config["deploy"]:
			g_util.deployOwner = g_config["deploy"]["owner"]

		target = sys.argv[2] if cnt > 2 else None
		if target is None:
			# todo: print server list
			print("Please specify server name.")
			return
		taskDeploy(target)
		return
	elif cmd == "setup":
		serverName = "" if cnt <= 3 else sys.argv[3]
		taskSetup(target, serverName)
		return

	# serve
	taskServe()

def taskSetup(target, serverName):
	if not os.path.exists(target):
		print("There is no target file[%s]" % target)
		return
	
	server = configServerGet(serverName)
	if server is None:
		return

	global g_remote
	g_remote = Tasks(server)		

	if not hasattr(g_mygod, "setupTask"):
		print("setup: You should override setupTask function in your myGod class")
		return

	g_mygod.setupTask(util=g_util, remote=g_remote, local=g_local)


def taskServe():
	observer = Observer()
	observer.schedule(MyHandler(g_config["serve"]["patterns"]), path=".", recursive=True)
	observer.start()

	g_util.isRestart = True
	try:
		while True:
			time.sleep(0.01)
			g_local.doServeStep(g_mygod)

	except KeyboardInterrupt:
		observer.stop()

	observer.join()


if __name__ == "__main__":
	main()
