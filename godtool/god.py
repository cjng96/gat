#!/usr/bin/env python3

import os
import sys
import time
import json
import paramiko
import platform
import yaml
import zlib
import shutil
import select
import socket
import subprocess
import datetime
import pathlib
import re
import base64
import inspect
import traceback
from copy import deepcopy
from io import StringIO
from subprocess import Popen, PIPE

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
from .myutil import NonBlockingStreamReader, str2arg, mergeDict, envExpand, Dict2, ObjectEncoder

g_cwd = ""
g_scriptPath = ""


class MyUtil():
	def __init__(self):
		self.deployRoot = ""	# only for deployment
		#self.deployOwner = None	# 그냥 server.id를 기본값으로 한다.
		self.isRestart = True	# First start or modified source files
		self.config = None	# config object

class Tasks():
	def __init__(self, server, dkTunnel=None, dkName=None):
		self.proc = None
		#self.outStream = None
		self._uploadHelper = False

		#self.server = Dict2(server)	# None: local
		self.server = server

		if server is not None:
			if dkTunnel is None:
				self.ssh = CoSsh()
				port = server.get("port", 22)
				print("ssh: connecting to the server[%s:%d] with ID:%s" % (self.server.host, port, self.server.id))
				self.ssh.init(self.server.host, port, self.server.id)

			if "vars" not in server:
				server.vars = {}

			self.vars = server.vars

		#self.configInit(server)
		self.dkTunnel = dkTunnel
		self.dkName = dkName


	'''	
	def configInit(self, server):
		#self.dic = Dict2()
		self.config = deepcopy(g_config)
		# 이건 일단은 남겨두자. 나중에 없앨꺼다.
		self.config.add("name", g_config.name)

		if server is not None:		
			# server without vars
			server2 = deepcopy(server)
			if "vars" in server2:
				del server2["vars"]
			self.config.add("server", server2)

			# vars
			# 이게 고민이 쓰기 편하게 하려면 루트에 넣는게 좋은데...
			#self.config.fill(server["vars"])
			self.config.add("vars", server.vars if "vars" in server else dict())
	'''

	def __del__(self):
		if self.server is not None and self.dkTunnel is None:
			self.ssh.close()
			self.ssh = None

	def onlyLocal(self):
		if self.server is not None:
			raise Exception("this method only can be used in local service.")

	def onlyRemote(self):
		if self.server is None:
			raise Exception("this method only can be used in remote service.")

	def dockerConn(self, name):
		# TODO: 커넥션을 공유할까?
		dk = Tasks(self.server, self, name)
		return dk

	def buildTask(self, mygod):
		self.onlyLocal()

		print("run: building the app")
		if hasattr(mygod, "buildTask"):
			return mygod.buildTask(util=g_util, local=g_local, remote=g_remote)
		else:
			print("You should override buildTask method.")

	def makeFile(self, content, path, sudo=False):
		self.onlyRemote()
		ss = content.replace('"', '\\"').replace('%', '\%')

		self.run('echo "{1}" | sudo dd of={2}'.format('sudo' if sudo else '', ss, path))

	def runTask(self, mygod):
		self.onlyLocal()

		if hasattr(mygod, "runTask"):
			cmd = mygod.runTask(util=g_util, local=g_local, remote=g_remote)
			if type(cmd) != list:
				raise Exception("the return value of runTask function should be list type.")
		else:
			cmd = ["./"+g_config.name]

		print("run: running the app[%s]..." % cmd)
		if subprocess.call("type unbuffer", shell=True) == 0:
			#cmd = ["unbuffer", "./"+g_util.executableName]
			cmd = ["unbuffer"] + cmd

		return cmd

	def doServeStep(self, mygod):
		#if hasattr(g_mygod, "doServeStep"):
		#	return g_mygod.doServeStep()
		print("\n\n\n")

		buildExc = None
		try:
			self.buildTask(mygod)
		except Exception as e:
			buildExc = traceback.format_exc()

		if buildExc is not None:
			print("run: exception in buildTask...\n%s" % buildExc)
		else:
			cmd = self.runTask(mygod)

			with subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr) as p:
				while True:
					try:
						ret = p.wait(0.1)
						raise Exception("run: the application has been terminated[ret:%d]" % ret)

					except subprocess.TimeoutExpired as e:
						pass

					if g_util.isRestart:
						g_util.isRestart = False
						p.terminate()
						break

	def runOutput(self, cmd, expandVars=True):
		"""
		cmd: string or array
		expandVars:
		return: stdout string
		exception: subprocess.CalledProcessError(returncode, output)
		"""
		print("executeOutput[%s].." % (cmd))

		if expandVars:
			cmd = strExpand(cmd, g_dic)

		if self.server is not None:
			return self.ssh.runOutput(cmd)
		else:
			return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, executable='/bin/bash')

	def run(self, cmd, expandVars=True):
		print("execute[%s].." % (cmd))

		if expandVars:
			cmd = strExpand(cmd, g_dic)

		if self.server is not None:
			if self.dkTunnel is not None:
				# it하면 오류 난다
				#cmd = cmd.replace('"', '\\"')
				#cmd = str2arg(cmd)
				#cmd = cmd.replace(' ', '\\ ')
				return self.dkTunnel.ssh.run("docker exec -i %s bash -c '" % (self.dkName) + cmd + "'")
			else:
				return self.ssh.run(cmd)
		else:
			"""
			with Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE, bufsize=1, universal_newlines=True) as p:
				fdout = p.stdout.fileno()
				fcntl.fcntl(fdout, fcntl.F_SETFL, fcntl.fcntl(fdout, fcntl.F_GETFL) | os.O_NONBLOCK)

				fderr = p.stderr.fileno()
				fcntl.fcntl(fderr, fcntl.F_SETFL, fcntl.fcntl(fderr, fcntl.F_GETFL) | os.O_NONBLOCK)

				while True:
					reads = [fdout, fderr]
					ret = select.select(reads, [], [])
					for fd in ret[0]:
						if fd == fdout:
							print(p.stdout.read(), end='')
						if fd == fderr:
							print(p.stderr.read(), end='')
						
					if p.poll() != None:
						break
			rc = p.returncode
			if rc != 0:
				raise subprocess.CalledProcessError(rc, cmd)
			"""
			with Popen(cmd, shell=True, universal_newlines=True) as p:
				p.communicate()
				print("  -> ret:%d" % (p.returncode))
				if p.returncode != 0:
					raise subprocess.CalledProcessError(p.returncode, cmd)

	def runRet(self, cmd):
		try:
			self.run(cmd)
			return True
		except subprocess.CalledProcessError as e:
			print("run: failed %d\n -- %s\n" % (e.returncode, e.output))
			return False

	def uploadFile(self, src, dest):
		self.onlyRemote()
		src = os.path.expanduser(src)
		dest = os.path.expanduser(dest)
		if self.dkTunnel is not None:
			self.dkTunnel.ssh.uploadFile(src, "/tmp/upload.tmp")
			self.dkTunnel.ssh.run('docker cp /tmp/upload.tmp %s:%s' % (self.dkName, dest))
		else:
			self.ssh.uploadFile(src, dest)

	def uploadFileTo(self, src, dest):
		self.onlyRemote()
		src = os.path.expanduser(src)
		dest = os.path.expanduser(dest)
		pp = os.path.join(dest, os.path.basename(src))
		self.uploadFile(src, pp)

	def uploadFolder(self, src, dest):
		self.onlyRemote()
		self.ssh.uploadFolder(src, dest)

	def uploadFolderTo(self, src, dest):
		self.onlyRemote()
		self.ssh.uploadFolder(src, os.path.join(dest, os.path.basename(src)))

	def goBuild(self):
		print("task: goBuild as [%s]..." % g_config.name)

		self.onlyLocal()

		cmd = ["go", "build", "-o", g_config.name]
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

	def _helperRun(self, args, sudo=False):
		pp2 = "/tmp/godHelper.py"

		if self.server is None:
			shutil.copyfile(os.path.join(g_scriptPath, 'godHelper.py'), pp2)
		else:
			if not self._uploadHelper:
				if self.dkTunnel is not None:
					self.dkTunnel.uploadFile(os.path.join(g_scriptPath, "godHelper.py"), pp2)
					self.dkTunnel.ssh.run("docker cp /tmp/godHelper.py %s:/tmp/godHelper.py" % self.dkName)
				else:
					self.uploadFile(os.path.join(g_scriptPath, "godHelper.py"), pp2)

				self._uploadHelper = True

		#ss = str2arg(json.dumps(args, cls=ObjectEncoder))
		ss = json.dumps(args, cls=ObjectEncoder)
		ss2 = zlib.compress(ss.encode()) # 1/3이나 절반
		ss = base64.b64encode(ss2).decode()
		self.run("%spython3 %s runBin \"%s\"" % ('sudo ' if sudo else '', pp2, ss), expandVars=False)

	def userNew(self, name, existOk=False, sshKey=False):
		print("task: userNew...")
		self.onlyRemote()
		
		args = dict(cmd="userNew", dic=g_dic,
			name=name, existOk=existOk, sshKey=sshKey)
		self._helperRun(args, sudo=True)

	def strLoad(self, path):
		print("task: strLoad...")
		self.onlyLocal()

		path = os.path.expanduser(path)
		with open(path, "rt") as fp:
			return fp.read()

	def strEnsure(self, path, str, sudo=False):
		print("task: strEnsure...")
		self.onlyRemote()

		args = dict(cmd="strEnsure", dic=g_dic,
			path=path, str=str)
		self._helperRun(args, sudo)

	def configBlock(self, path, marker, block, insertAfter=None, sudo=False):
		'''
		marker: ### {mark} TEST
		block: vv=1
		'''
		print("task: config block...")
		#self.onlyRemote()

		args = dict(cmd="configBlock", dic=g_dic,
			path=path, marker=marker, block=block, insertAfter=insertAfter)
		self._helperRun(args, sudo)

	def configLine(self, path, regexp, line, items=None, sudo=False):
		print("task: config line...")
		#self.onlyRemote()

		args = dict(cmd="configLine", dic=g_dic,
			path=path, regexp=regexp, line=line, items=items)
		self._helperRun(args, sudo)

	def s3List(self, bucket, prefix):
		print("task: s3 list[%s/%s]..." % (bucket, prefix))
		self.onlyLocal()

		if not prefix.endswith("/"):
			prefix += "/"

		s3 = CoS3(g_config.get("s3.key", None), g_config.get("s3.secret", None))
		bb = s3.bucketGet(bucket)
		lst = bb.fileList(prefix)
		return lst

	def s3DownloadFiles(self, bucket, prefix, nameList, targetFolder):
		print("task: s3 download files[%s/%s]..." % (bucket, prefix))
		self.onlyLocal()

		if not targetFolder.endswith("/"):
			targetFolder += "/"
		if not prefix.endswith("/"):
			prefix += "/"

		s3 = CoS3(g_config.get("s3.key", None), g_config.get("s3.secret", None))
		bb = s3.bucketGet(bucket)
		for name in nameList:
			bb.downloadFile(prefix+name, targetFolder+name)

	def s3DownloadFile(self, bucket, key, dest):
		print("task: s3 download file[%s -> %s]..." % (key, dest))
		self.onlyLocal()

		s3 = CoS3(g_config.get("s3.key", None), g_config.get("s3.secret", None))
		bb = s3.bucketGet(bucket)
		bb.downloadFile(key, dest)


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

def dicInit(server):
	global g_dic
	g_dic = deepcopy(g_config)
	g_dic.dic['server'] = server
	g_dic.dic['vars'] = deepcopy(server.vars)
	g_util.dic = g_dic


def configServerGet(name):
	server = None
	for it in g_config.servers:
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
	dicInit(server)

	# expand env and variables
	expandVar(g_config)

	sudoCmd = ""
	if server.owner:
		sudoCmd = "sudo"

	name = g_config.name
	deployRoot = server.targetPath
	realTarget = g_remote.runOutput('realpath %s' % deployRoot)
	realTarget = realTarget.strip("\r\n")	# for sftp
	todayName = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")[2:]

	# pre task
	deployPath = os.path.join(realTarget, "releases", todayName)
	g_dic.dic['deployRoot'] = deployRoot
	g_dic.dic['deployPath'] = deployPath
	if hasattr(g_mygod, "deployPreTask"):
		g_mygod.deployPreTask(util=g_util, remote=g_remote, local=g_local)

	# prepare target folder
	g_remote.runOutput('{0} mkdir -p {1}/shared && {0} mkdir -p {1}/releases'.format(sudoCmd, deployRoot))
	#('&& sudo chown %s: %s %s/shared %s/releases' % (server.owner, deployRoot, deployRoot, deployRoot) if server.owner else '') +

	res = g_remote.runOutput("cd {0}/releases && ls -d *".format(deployRoot))
	releases = list(filter(lambda x: re.match('\d{6}_\d{6}', x) is not None, res.split()))
	releases.sort()

	max = g_config.deploy.maxRelease-1
	cnt = len(releases)
	print("deploy: releases folders count is %d" % cnt)
	if cnt > max:
		print("deploy: remove old %d folders" % (cnt - max))
		removeList = releases[:cnt-max]
		for ff in removeList:
			g_remote.runOutput("%s rm -rf %s/releases/%s" % (sudoCmd, deployRoot, ff))

	# if deploy / owner is defined,
	# create release folder as ssh user, upload, extract then change release folder to deploy / owner
	res = g_remote.runOutput("cd %s/releases" % deployRoot +
		"&& %s mkdir %s" % (sudoCmd, todayName) +
		"&& sudo chown %s: %s" % (server.owner, todayName) if server.owner else ""
		)

	# upload files
	include = []
	include = g_config.deploy.include
	exclude = g_config.get("deploy.exclude", [])
	sharedLinks = g_config.get("deploy.sharedLinks", [])

	def _filterFunc(pp):
		pp = os.path.normpath(pp)
		return pp in exclude

	strategy = g_config.deploy.strategy
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

						for folder, dirs, files in os.walk(pp, followlinks=g_dic.deploy.followLinks):
							# filtering dirs too
							dirs2 = []
							for d in dirs:
								dd = os.path.join(folder, d)
								if _filterFunc(dd):
									print("deploy: skip - %s" % dd)
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

		g_remote.uploadFile(zipPath, "/tmp/godUploadPkg.zip")	# we don't include it by default
		g_remote.run("cd %s/releases/%s" % (deployRoot, todayName) +
			"&& %s unzip /tmp/godUploadPkg.zip && rm /tmp/godUploadPkg.zip" % sudoCmd
			)
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
		g_remote.run("cd %s && mkdir -p shared/%s" % (deployRoot, folder) +
		"&& %s ln -sf %s/shared/%s releases/%s/%s" % (sudoCmd, deployRoot, pp, todayName, pp))

	# update link
	g_remote.run("cd %s && %s rm -f current " % (deployRoot, sudoCmd) +
		"&& %s ln -sf releases/%s current " % (sudoCmd, todayName) +
		"&& sudo chown %s: current %s/releases/%s -R" % (server.owner, deployRoot, todayName) if server.owner else ""
	)

	# file owner
	if server.owner:
		g_remote.run('cd %s && sudo chown %s: shared releases/%s current -R' % (deployRoot, server.owner, todayName))
		g_remote.run('cd %s && sudo chmod 775 shared releases/%s current -R' % (deployRoot, todayName))

	# post process
	if hasattr(g_mygod, "deployPostTask"):
		g_mygod.deployPostTask(util=g_util, remote=g_remote, local=g_local)


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
  goBuild(args): "go build -o name"
servePreTask - 
  gqlGen(): running "go run github.com/99designs/gqlgen" job for gqlgen(https://github.com/99designs/gqlgen)
deployPostTask - 
  pm2Register(): "pm2 start pm2.json" - You should define pm2.json file first.
''' % __version__)

def expandVar(dic):
	dicType = type(dic)
	if dicType == list:
		for idx, value in enumerate(dic):
			tt = type(value)
			if tt == Dict2 or tt == dict:
				expandVar(value)
			elif tt == str:
				value = envExpand(value)
				value = strExpand(value, g_dic)
				dic[idx] = value
			elif tt == list:
				expandVar(value)
	else:
		for key in dic:
			value = dic[key]

			tt = type(value)
			if tt == Dict2:
				expandVar(value)
			elif tt == str:
				value = envExpand(value)
				value = strExpand(value, g_dic)
				dic[key] = value
			elif tt == list:
				expandVar(value)


class Helper:
	def __init__(self):
		pass

	def configStr(self, cfgType, ss):
		'''
		type: yaml
		'''
		global g_config
		if cfgType == "yaml":
			try:
				g_config = Dict2(yaml.safe_load(ss))
				#g_util.config = g_config

				if g_config.type == 'app':
					if 'followLinks' not in g_config.deploy:
						g_config.deploy['followLinks'] = False

			except yaml.YAMLError as e:
				raise e
		else:
			raise Exception("unknown config type[%s]" % cfgType)

	def configFile(self, cfgType, pp):
		'''
		type: yaml
		'''
		with open(pp, "r") as fp:
			self.configStr(cfgType, fp.read())

	def configGet(self):
		return g_config


g_config = Dict2()
g_dic = None
# config, server, vars(of server)
# deployRoot, deployPath
g_mygod = None

g_util = MyUtil()
g_local = None
g_remote = None


def help(target):
	print("god-tool V%s" % (__version__))
	if target is not None:
		print("There is no %s script file." % target)
	print("""god init (sys|app) [GOD_FILE] - Generates god file.
god [GOD_FILE] - Serves application service. use god_my.py file if GOD_FILE is skipped.
god deploy SERVER_NAME - Deploy the application to the server.
god setup [GOD_FILE] SERVER_NAME - Setup server defined in GOD_FILE."""
 	)

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

			target = sys.argv[3] if cnt > 3 else "god_my.py"
			if not target.endswith(".py"):
				target += ".py"
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
				print("god setup FILE.py SERVER_NAME")
				return
			target = sys.argv[2]
			if not target.endswith(".py"):
				target += ".py"

		elif cmd == '--help':
			help(None)
			return
		else:
			print("unknown command - %s" % cmd)
			return

	else:
		# default operation for app
		target = "god_my.py"

	# check first
	if not os.path.exists(target):	# or not os.path.exists("god.yml"):
		help(target)
		return

	helper = Helper()

	sys.path.append(g_cwd)
	mymod = __import__(target[:-3], fromlist=[''])
	g_mygod = mymod.myGod(helper=helper)

	print("god-tool V%s" % __version__)
	global g_config
	name = g_config.name
	type = g_config.get("type", "app")

	print("** config[type:%s, name:%s]" % (type, name))
	global g_local
	g_local = Tasks(None)

	if cmd == "deploy":
		#g_util.deployOwner = g_config.get("deploy.owner", None)	# replaced by server.owner

		target = sys.argv[2] if cnt > 2 else None
		if target is None:
			# todo: print server list
			print("Please specify server name.")
			return
		taskDeploy(target)
		return
	elif cmd == "setup":
		if cnt < 4:
			ss = ''
			for it in g_config.servers:
				ss += it['name'] + '|'

			print("god setup FILE.py [%s]" % ss[:-1])
			return

		# support empty server name?
		serverName = "" if cnt <= 3 else sys.argv[3]
		taskSetup(target, serverName)
		return

	# serve
	if type != "app":
		print("god [GOD_FILE] can be used for application type only.")
		return
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
	dicInit(server)

	# expand env and variables
	expandVar(g_config)

	if not hasattr(g_mygod, "setupTask"):
		print("setup: You should override setupTask function in your myGod class")
		return

	g_mygod.setupTask(cfg=g_config, util=g_util, remote=g_remote, local=g_local)


def taskServe():
	observer = None
	if len(g_config.serve.patterns) > 0:
		observer = Observer()
		observer.schedule(MyHandler(g_config.serve.patterns), path=".", recursive=True)
		observer.start()

	try:
		while True:
			time.sleep(0.01)
			g_util.isRestart = False
			g_local.doServeStep(g_mygod)

	except KeyboardInterrupt:
		if observer is not None:
			observer.stop()

	if observer is not None:
		observer.join()


if __name__ == "__main__":
	main()
