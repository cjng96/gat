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
import importlib
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

class Error(Exception):
	pass

class ExcProgramExit(Exception):
	pass

class MyUtil():
	def __init__(self):
		#self.deployRoot = ""	# only for deployment -- 이거 그냥. g_remote.server.deployRoot쓰면 된다.
		#self.deployOwner = None	# 그냥 server.id를 기본값으로 한다.
		self.isRestart = True	# First start or modified source files
		self.cfg = None	# config object(g_config)

	def str2arg(self, ss):
		return str2arg(ss)

class Tasks():
  def __init__(self, server, dkTunnel=None, dkName=None, dkId=None):
    '''
    '''
    self.proc = None
    self._uploadHelper = False

    self.server = server
    self.ssh = None

    # accessbility
    self.data = g_data
    self.util = g_util		

    if server is not None:
      if dkTunnel is None:
        port = server.get("port", 22)
        self.initSsh(server.host, port, server.id)

      if "vars" not in server:
        server.vars = {}

      self.vars = server.vars

    # docker일 경우 dkTunnel, dkName가 필수며, 부모의 server도 있어야 함
    self.dkTunnel = dkTunnel
    self.dkName = dkName

    if dkId is not None:
      dkId = strExpand(dkId, g_dic)
    self.dkId = dkId

  def initSsh(self, host, port, id):
    self.ssh = CoSsh()
    print("ssh: connecting to the server[%s:%d] with ID:%s" % (host, port, id))
    self.ssh.init(host, port, id)

  def __del__(self):
    if self.ssh is not None:
      self.ssh.close()
      self.ssh = None

  def dockerConn(self, name, dkId=None):
    if self.dkTunnel is not None:
      raise Exception('dockerConn can be called only on remote connection.')

    dk = Tasks(self.server, self, name, dkId)
    return dk

  def parentConn(self):
    if self.dkTunnel is None:
      raise Exception('This connection is not docker connection.')
    return self.dkTunnel

  def otherDockerConn(self, name, dkId=None):
    if self.dkTunnel is None:
      raise Exception('otherDockerConn can be called on docker connection only.')

    return self.dkTunnel.dockerConn(name, dkId)

  def remoteConn(self, host, port, id, dkName=None, dkId=None):
    '''
    지정해서 커넥션을 만들어낸다.
    docker지정까지 가능하다. 이거 설정을 컨피그로 할수 있게 하자
    이건 util로 가는게 나을까
    '''
    dk = Tasks(Dict2(dict(name='remote', host=host, port=port, id=id)))	# no have owner
    dk.initSsh(host, port, id)

    if dkName is not None:
      dk = dk.dockerConn(dkName, dkId)

    return dk

  def onlyLocal(self):
    if self.ssh is not None:
      raise Exception("this method only can be used in local service.")

  def onlyRemote(self):
    if self.dkTunnel is None and self.ssh is None:
      raise Exception("this method only can be used in remote service.")

  def deployApp(self, path, profile, serverOvr=None, varsOvr=None):
    sys.path.insert(0, path)
    try:
      config = Config()
      helper = Helper(config)
      mymod = importlib.import_module('god_app')
      mygod = mymod.myGod(helper=helper)

      server = config.configServerGet(profile)
      if server is None:
        return

      # override configure
      server = deepcopy(server)
      if serverOvr is not None:
        server.fill(serverOvr)
      if varsOvr is not None:
        server.vars.fill(varsOvr)

      remote = Tasks(server)
      if 'dkName' in server.dic:
        remote = remote.dockerConn(server.dkName, dkId=server.get('dkId'))

      pp = os.path.abspath(os.curdir)
      os.chdir(path)
      try:
        g_main.taskDeploy(remote, server, mygod, config)
      finally:
        os.chdir(pp)

    finally:
      sys.path = sys.path[1:]

  def makeFile(self, content, path, sudo=False, mode=755):
    #self.onlyRemote()
    #ss = content.replace('"', '\\"').replace('%', '\%').replace('$', '\$')
    content = str2arg(content)

    sudoCmd = 'sudo' if sudo else ''
    self.run('echo "{1}" | {0} tee {2} > /dev/null && {0} chmod {3} {2}'.format(sudoCmd, content, path, mode))

  def runOutput(self, cmd, expandVars=True):
    '''
    cmd: string or array
    expandVars:
    return: stdout string
    exception: subprocess.CalledProcessError(returncode, output)
    '''
    print("executeOutput on %s[%s].." % (self._serverName(), cmd))

    if expandVars:
      cmd = strExpand(cmd, g_dic)

    if self.dkTunnel is not None:
      dkRunUser = '-u %s' % self.dkId if self.dkId is not None else ''
      cmd = str2arg(cmd)			
      cmd = 'docker exec -i %s %s bash -c "%s"' % (dkRunUser, self.dkName, cmd)
      return self.dkTunnel.ssh.runOutput(cmd)
    elif self.ssh is not None:
      return self.ssh.runOutput(cmd)
    else:
      return subprocess.check_output(cmd, shell=True, executable='/bin/bash')

  def runOutputAll(self, cmd, expandVars=True):
    '''
    cmd: string or array
    expandVars:
    return: stdout string
    exception: subprocess.CalledProcessError(returncode, output)
    '''
    print("executeOutputAll on %s[%s].." % (self._serverName(), cmd))

    if expandVars:
      cmd = strExpand(cmd, g_dic)

    if self.dkTunnel is not None:
      dkRunUser = '-u %s' % self.dkId if self.dkId is not None else ''
      cmd = str2arg(cmd)			
      cmd = 'docker exec -i %s %s bash -c "%s"' % (dkRunUser, self.dkName, cmd)
      return self.dkTunnel.ssh.runOutputAll(cmd)
    elif self.ssh is not None:
      return self.ssh.runOutputAll(cmd)
    else:
      return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, executable='/bin/bash')

  def _serverName(self):
    if self.server is None:
      return 'local'
    elif self.dkTunnel is None:
      return self.server.host
    else:
      return "%s[%s]" % (self.dkName, self.server.host)

  def run(self, cmd, expandVars=True):
    print("execute on %s[%s].." % (self._serverName(), cmd))

    if expandVars:
      cmd = strExpand(cmd, g_dic)

    if self.dkTunnel is not None:
      # it하면 오류 난다
      dkRunUser = '-u %s' % self.dkId if self.dkId is not None else ''
      cmd = str2arg(cmd)
      cmd = 'docker exec -i %s %s bash -c "%s"' % (dkRunUser, self.dkName, cmd)
      print('cmd - %s' % cmd)
      return self.dkTunnel.ssh.run(cmd)
    elif self.ssh is not None:
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

  def runSafe(self, cmd):
    '''
    return: success flag
    '''
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

  # TODO: mysql, goBuild, gqlGen, dbXorm, pm2Register등은 기본 task에서 빼야할듯
  def mysqlUserDel(self, id, host):
    hr = self.runOutput('''sudo mysql -e "SELECT 'exist' FROM mysql.user where user='%s';"''' % (id))
    if hr == "":
      return

    self.run('''sudo mysql -e "DROP USER '%s'@'%s';"''' % (id, host))

  def mysqlUserGen(self, id, pw, host, priv):
    #pw = str2arg(pw).replace(';', '\\;').replace('`', '``').replace("'", "\\'")
    pw = str2arg(pw).replace("'", "''")
    # 이게 좀 웃긴데, mysql 통해서 실행하는거기 때문에 \\는 \\\\로 바꿔야한다.
    pw = pw.replace("\\\\", "\\\\\\\\")
    host = str2arg(host)
    self.run('''sudo mysql -e "CREATE USER '%s'@'%s' IDENTIFIED BY '%s';"''' % (id, host, pw))

    privList = priv.split('/')
    for priv in privList:
      priv2, oper = priv.split(':')

      grantOper = ''
      lst = list(map(lambda x: x.strip().upper(), oper.split(',')))
      if 'GRANT' in lst:
        lst.remove('GRANT')
        oper = ','.join(lst)
        grantOper = 'WITH GRANT OPTION'
      self.run('''sudo mysql -e "GRANT %s ON %s TO '%s'@'%s' %s;"''' % (oper, priv2, id, host, grantOper))

  def goBuild(self):
    print("task: goBuild as [%s]..." % g_config.name)

    self.onlyLocal()

    cmd = ["go", "build", "-o", g_config.name]
    ret = subprocess.run(cmd)
    if ret.returncode != 0:
      raise Error("task.goBuild: build failed")

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
    cmd += "cd %s/current && pm2 delete pm2.json && pm2 start pm2.json" % (self.server.deployRoot)
    self.run(cmd)

  def _helperRun(self, args, sudo=False):
    pp2 = "/tmp/godHelper.py"

    if self.dkTunnel is None and self.ssh is None:
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

  """ use myutil.makeUser
  def userNew(self, name, existOk=False, sshKey=False):
    print("task: userNew...")
    self.onlyRemote()
    
    args = dict(cmd="userNew", dic=g_dic,
      name=name, existOk=existOk, sshKey=sshKey)
    self._helperRun(args, sudo=True)
  """

  def strLoad(self, path):
    print("task: strLoad...")
    self.onlyLocal()

    path = os.path.expanduser(path)
    with open(path, "rt") as fp:
      return fp.read()

  def strEnsure(self, path, str, sudo=False):
    print("task: strEnsure for %s..." % path)
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

  def configLine(self, path, regexp, line, items=None, sudo=False, append=False):
    print("task: config line...")
    #self.onlyRemote()

    args = dict(cmd="configLine", dic=g_dic,
      path=path, regexp=regexp, line=line, items=items, append=append)
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

  def s3DownloadFile(self, bucket, key, dest=None):
    print("task: s3 download file[%s -> %s]..." % (key, dest))
    self.onlyLocal()

    s3 = CoS3(g_config.get("s3.key", None), g_config.get("s3.secret", None))
    bb = s3.bucketGet(bucket)
    return bb.downloadFile(key, dest)

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

		print("observer: file - %s is %s" % (event.src_path, event.event_type))
		g_util.isRestart = True

	def on_modified(self, event):
		self.process(event)

	def on_created(self, event):
		self.process(event)

def dicInit(server):
	global g_dic	# helper run할때 전달되는 기능
	g_dic = deepcopy(g_config)
	g_dic.dic['server'] = server
	g_dic.dic['vars'] = deepcopy(server.vars)
	g_dic.dic['data'] = deepcopy(g_data)
	g_util.cfg = g_config
	g_util.data = g_data

class Main():

  # runTask와 doServerStep등은 Task말고 별도로 빼자 remote.runTask를 호출할일은 없으니까
  def runTask(self, mygod):
    #self.onlyLocal()

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
    except Error as e:
      buildExc = e.args
    except Exception as e:
      buildExc = traceback.format_exc()

    if buildExc is not None:
      print("\nrun: exception in buildTask...\n  %s" % buildExc)
      while True:	# wait for file modification
        if g_util.isRestart:
          return
          
        time.sleep(0.1)
    else:
      cmd = self.runTask(mygod)

      with subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr) as p:
        while True:
          try:
            ret = p.wait(0.1)
            raise ExcProgramExit("run: the application has been terminated[ret:%d]" % ret)

          except subprocess.TimeoutExpired as e:
            pass

          if g_util.isRestart:
            g_util.isRestart = False
            p.terminate()
            break

  def doTestStep(self, mygod):
    print("\n\n\n")

    cmd = g_config.test.cmd
    #if subprocess.call("type unbuffer", shell=True) == 0:
    #	cmd = ["unbuffer"] + cmd

    with subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr) as p:
      while True:
        try:
          ret = p.wait(0.1)
          raise ExcProgramExit("run: the application has been terminated[ret:%d]" % ret)

        except subprocess.TimeoutExpired as e:
          pass

        except ExcProgramExit:
          print('**** test job is finished')
          # 이 경우 재구동까지 기다린다.
          while not g_util.isRestart:
            time.sleep(0.1)

        if g_util.isRestart:
          g_util.isRestart = False
          p.terminate()
          break

  def buildTask(self, mygod):
    print("run: building the app")
    if hasattr(mygod, "buildTask"):
      return mygod.buildTask(util=g_util, local=g_local, remote=g_remote)
    else:
      print("You should override buildTask method.")

  def taskSetup(self, target, serverName):
    if not os.path.exists(target):
      print("There is no target file[%s]" % target)
      return
    
    server = g_config.configServerGet(serverName)
    if server is None:
      return

    global g_remote, g_data
    g_remote = Tasks(server)
    if 'dkName' in server.dic:
      g_remote = g_remote.dockerConn(server.dkName, dkId=server.get('dkId'))

    #g_remote.data = g_data
    #g_remote.util = g_util		
    dicInit(server)

    # expand env and variables
    expandVar(g_config)

    if not hasattr(g_mygod, "setupTask"):
      print("setup: You should override setupTask function in your myGod class")
      return

    g_mygod.setupTask(util=g_util, remote=g_remote, local=g_local)

  def taskTest(self):
    observer = None
    if len(g_config.test.patterns) > 0:
      observer = Observer()
      observer.schedule(MyHandler(g_config.test.patterns), path=".", recursive=True)
      observer.start()

    try:
      while True:
        time.sleep(0.01)
        g_util.isRestart = False
        self.doTestStep(g_mygod)

    except KeyboardInterrupt:
      if observer is not None:
        observer.stop()

    if observer is not None:
      observer.join()


  def taskServe(self):
    observer = None
    if len(g_config.serve.patterns) > 0:
      observer = Observer()
      observer.schedule(MyHandler(g_config.serve.patterns), path=".", recursive=True)
      observer.start()

    try:
      while True:
        time.sleep(0.01)
        g_util.isRestart = False
        self.doServeStep(g_mygod)

    except KeyboardInterrupt:
      if observer is not None:
        observer.stop()

    if observer is not None:
      observer.join()

  def taskDeploy(self, env, server, mygod, config):
    self.buildTask(mygod)

    dicInit(server)
    # expand env and variables
    expandVar(config)

    sudoCmd = ""
    if "owner" in server:
      sudoCmd = "sudo"

    name = config.name
    deployRoot = server.deployRoot
    realTarget = env.runOutput('realpath %s' %  deployRoot)
    realTarget = realTarget.strip("\r\n")	# for sftp
    todayName = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")[2:]

    # pre task
    deployPath = os.path.join(realTarget, "releases", todayName)
    g_dic.dic['deployRoot'] = deployRoot
    g_dic.dic['deployPath'] = deployPath
    if hasattr(mygod, "deployPreTask"):
      mygod.deployPreTask(util=g_util, remote=env, local=g_local)

    # prepare target folder
    env.runOutput('{0} mkdir -p {1}/shared && {0} mkdir -p {1}/releases'.format(sudoCmd, deployRoot))
    #('&& sudo chown %s: %s %s/shared %s/releases' % (server.owner, deployRoot, deployRoot, deployRoot) if server.owner else '') +

    res = env.runOutput("cd {0}/releases && ls -d *;echo".format(deployRoot))
    releases = list(filter(lambda x: re.match('\d{6}_\d{6}', x) is not None, res.split()))
    releases.sort()

    max = config.deploy.maxRelease-1
    cnt = len(releases)
    print("deploy: releases folders count is %d" % cnt)
    if cnt > max:
      print("deploy: remove old %d folders" % (cnt - max))
      removeList = releases[:cnt-max]
      for ff in removeList:
        env.runOutput("%s rm -rf %s/releases/%s" % (sudoCmd, deployRoot, ff))

    # if deploy / owner is defined,
    # create release folder as ssh user, upload, extract then change release folder to deploy / owner
    res = env.runOutput("cd %s/releases" % deployRoot +
      "&& %s mkdir %s" % (sudoCmd, todayName) +
      ("&& sudo chown %s: %s" % (server.owner, todayName) if "owner" in server else "")
      )

    # upload files
    include = []
    include = config.deploy.include
    exclude = config.get("deploy.exclude", [])
    sharedLinks = config.get("deploy.sharedLinks", [])

    def _filterFunc(pp):
      pp = os.path.normpath(pp)
      return pp in exclude

    strategy = config.deploy.strategy
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

              for folder, dirs, files in os.walk(pp, followlinks=config.deploy.followLinks):
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

      env.uploadFile(zipPath, "/tmp/godUploadPkg.zip")	# we don't include it by default
      env.run("cd %s/releases/%s " % (deployRoot, todayName) +
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
      if pp.endswith('/'):
        env.run("cd %s && %s mkdir -p shared/%s " % (deployRoot, sudoCmd, pp))
        pp = pp[:-1]

      env.run("cd %s && %s ln -sf ../../shared/%s releases/%s/%s" % (deployRoot, sudoCmd, pp, todayName, pp))

    # file owner
    if "owner" in server:
      env.run('cd %s && sudo chown %s: shared releases/%s -R' % (deployRoot, server.owner, todayName))
      env.run('cd %s && sudo chmod 775 shared releases/%s -R' % (deployRoot, todayName))

    # update current
    env.run("cd %s && %s rm -f current && %s ln -sf releases/%s current" % (deployRoot, sudoCmd, sudoCmd, todayName))
    if "owner" in server:
      env.run("cd %s && %s chown %s: current" % (deployRoot, sudoCmd, server.owner))

    # post process
    if hasattr(mygod, "deployPostTask"):
      mygod.deployPostTask(util=g_util, remote=env, local=g_local)
    
    # TODO: postTask에서 오류 발생시 다시 돌려놔야


def initSamples(type, fn):
  with open(fn, "w") as fp:
    if type == "app":
      fp.write(sampleApp)
    else:
      fp.write(sampleSys)
    
  print("init: %s file generated. You should modify that file for your environment before service or deployment." % (fn))

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

class Config(Dict2):
  def __init__(self):
    super().__init__()

  def configStr(self, cfgType, ss):
    '''
    type: yaml
    '''
    if cfgType == "yaml":
      try:
        #self.cfg = Dict2()
        self.fill(yaml.safe_load(ss))
        #g_util.config = g_config

        if 'defaultVars' in self:
          for server in self.servers:
            vars2 = Dict2()
            vars2.fill(self.defaultVars)
            vars2.fill(server.vars)
            server.vars = vars2

        if self.type == 'app':
          if 'followLinks' not in self.deploy:
            self.deploy['followLinks'] = False

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

  def configServerGet(self, name):
    server = None
    for it in self.servers:
      if it["name"] == name:
        server = it
        print("deploy: selected server - ", it)
        break

    if server is None:
      print("Not found server[%s]" % name)
      return None

    return server

class Helper:
	def __init__(self, config):
		self.config = config

	def configStr(self, cfgType, ss):
		self.config.configStr(cfgType, ss)

	def configFile(self, cfgType, pp):
		self.config.configFile(cfgType, pp)

	def configGet(self):
		return self.config.configGet()

	def loadData(self, pp):
		if not os.path.exists(pp):
			raise Exception('there is no data file[%s]' % pp)

		print('load data from %s...' % pp)
		# TODO: encrypt with input key when changed
		with open(pp, "r") as fp:
			dd = Dict2(yaml.safe_load(fp.read()))
			print('data - ', dd)
			return dd


#g_helper = Helper()
g_config = Config()
g_main = Main()
#g_config = Dict2()	# py코드에서는 util.cfg로 접근 가능
g_dic = None	# helper실행할때 씀, server, vars까지 설정
g_data = None	# .data.yml
# config, server, vars(of server)
# deployRoot, deployPath
g_mygod = None

g_util = MyUtil()
g_local = None
g_remote = None	# server, vars직접 접근 가능


def help(target):
	print("god-tool V%s" % (__version__))
	print("""\
Usage.
god init app - Generates god_app.py file for application.
god init sys SYSTEM_NAME - Generates the file for system.
  the SYSTEM_NAME.py file will be generated.

For application(There should be god_app.py file.),
god - Serves application.
god test - running automatic test.
god deploy SERVER_NAME - Deploy the application to the server.

For system,
god SYSTEM_NAME SERVER_NAME - Setup server defined in GOD_FILE.
""")
	if target is not None:
		print("\nThere is no %s script file." % target)

def main():
  global g_cwd, g_scriptPath, g_mygod
  g_cwd = os.getcwd()
  g_scriptPath = os.path.dirname(os.path.realpath(__file__))
  target = 'god_app.py'

  cnt = len(sys.argv)
  cmd = None
  if cnt > 1:
    cmd = sys.argv[1]

    if cmd == '--help':
      help(None)
      return

    elif cmd == "init":
      if cnt < 3:
        print("god init app OR god init sys NAME.")
        return

      type = sys.argv[2]
      if type != "app" and type != "sys":
        print("app or sys can be used for god init command.")
        return

      if type == 'app':
        initSamples(type, target)

      elif type == 'sys':
        if cnt < 4:
          print('Please specify SYSTEM_NAME to be generated.')
          return

        target = sys.argv[3]
        if not target.endswith(".py"):
          target += ".py"
        initSamples(type, target)
      
      else:
        print('unknown init type[%s]' % type)

      return

    elif cmd == "test":
      pass

    elif cmd == "deploy":
      pass

    else:
      # setup server system
      cmd = 'setup'
      if cnt < 2:
        print("god SYSTEM_FILE SERVER_NAME")
        return

      target = sys.argv[1]
      if not target.endswith(".py"):
        target += ".py"

  else:
    # app serve
    cmd = 'serve'

  # check first
  if not os.path.exists(target):	# or not os.path.exists("god.yml"):
    help(target)
    return

  global g_config
  helper = Helper(g_config)

  sys.path.append(g_cwd)
  mymod = __import__(target[:-3], fromlist=[''])
  g_mygod = mymod.myGod(helper=helper)

  print("god-tool V%s" % __version__)
  name = g_config.name
  type = g_config.get("type", "app")

  print("** config[type:%s, name:%s]" % (type, name))
  global g_local
  g_local = Tasks(None)
  #g_local.util = g_util

  # load secret
  global g_data
  secretPath = os.path.join(g_cwd, '.data.yml')
  if os.path.exists(secretPath):
    print('load data...')
    # TODO: encrypt with input key when changed
    with open(secretPath, "r") as fp:
      ss = fp.read()
      g_data = Dict2(yaml.safe_load(ss))
      print('data - ', g_data)

  if cmd == "deploy":
    #g_util.deployOwner = g_config.get("deploy.owner", None)	# replaced by server.owner
    target = sys.argv[2] if cnt > 2 else None
    if target is None:
      ss = ''
      for it in g_config.servers:
        ss += it['name'] + '|'
      print("Please specify server name.[%s]" % ss[:-1])
      return

    server = g_config.configServerGet(target)
    if server is None:
      return

    env = Tasks(server)
    if 'dkName' in server.dic:
      env = env.dockerConn(server.dkName, dkId=server.get('dkId'))

    g_main.taskDeploy(env, server, g_mygod, g_config)
    return

  elif cmd == "setup":
    if cnt < 3 and len(g_config.servers) == 1:
      serverName = g_config.servers[0].name
    else:
      if cnt < 3:
        ss = ''
        for it in g_config.servers:
          ss += it['name'] + '|'

        print('\nPlease specify SERVER_NAME...')
        print("eg> god SYSTEM_NAME.py SERVER_NAME")
        print(" ** you can use [%s] as SERVER_NAME" % ss[:-1])
        return

      # support empty server name?
      
      serverName = sys.argv[2]
    g_main.taskSetup(target, serverName)
    return

  elif cmd == 'test':
    # serve
    if type != "app":
      print("just god command can be used for application type only.")
      return

    g_main.taskTest()

  elif cmd == 'serve':
    # serve
    if type != "app":
      print("just god command can be used for application type only.")
      return

    g_main.taskServe()

  else:
    print('unknown command mode[%s]' % cmd)


if __name__ == "__main__":
	main()
