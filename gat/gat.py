#!/usr/bin/env python3

import os
import sys
import time
import json
import requests

# import paramiko
# import platform
import yaml
import zlib
import shutil

# import select
# import socket
import subprocess
import datetime
import pathlib
import re
import base64

# import inspect
import fnmatch
import traceback
import importlib
import importlib.util

from copy import deepcopy

# from io import StringIO
from subprocess import Popen  # , PIPE

import zipfile
import tempfile

from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

from . import __version__
from .coSsh import CoSsh
from .coPath import cutpath
from .sampleFiles import sampleApp, sampleSys
from .gatHelper import strExpand
from .coS3 import CoS3
from .myutil import (
    cloneRepo,
    str2arg,
    envExpand,
    ObjectEncoder,
    pathRemove,
    pathIsChild,
)  # NonBlockingStreamReader,
from .coCollection import dictMerge, Dict2, dictMerge2

g_cwd = ""
g_scriptPath = ""


class Error(Exception):
    pass


class ExcProgramExit(Exception):
    pass


class MyUtil:
    def __init__(self):
        # self.deployRoot = ""	# only for deployment -- 이거 그냥. g_remote.server.deployRoot쓰면 된다.
        # self.deployOwner = None	# 그냥 server.id를 기본값으로 한다.
        self.isRestart = True  # First start or modified source files
        # self.config = None  # config object(g_config) -- 이건 전역 객체라 쓰면 안된다

    def str2arg(self, ss):
        return str2arg(ss)

    def deployFileListProd(self, env, func):
        include = env.config.deploy.include
        exclude = env.config.get("deploy.exclude", [])
        followLinks = env.config.deploy.followLinks

        g_main.targetFileListProd(include, exclude, func, followLinks=followLinks)


class Tasks:
    def __init__(self, server, config, dkTunnel=None, dkName=None, dkId=None):
        """
        server: can be none
        config = {name, host, port, id, pw}
        """
        self.proc = None
        self._uploadHelper = False

        self.server = server
        self.ssh = None
        self.config = config

        # accessbility
        self.data = g_data
        self.util = g_util

        # for log
        self.name = "local" if server is None else server.host

        if server is not None:
            if dkTunnel is None:
                port = server.get("port", 22)
                self.initSsh(
                    server.host, port, server.id, keyFile=server.get("keyFile")
                )

            if "vars" not in server:
                server.vars = {}

            self.vars = server.vars

        # docker일 경우 dkTunnel, dkName가 필수며, 부모의 server도 있어야 함
        self.dkTunnel = dkTunnel
        self.dkName = dkName

        if dkId is not None:
            dkId = strExpand(dkId, g_dic)
        self.dkId = dkId

    def initSsh(self, host, port, id, keyFile=None):
        self.ssh = CoSsh()
        print(f"ssh: connecting to the server[{id}@{host}:{port}] with key:{keyFile}")
        if keyFile is not None:
            with open(keyFile) as fp:
                print("key - " + fp.read())
        self.ssh.init(host, port, id, keyFile=keyFile)

    def __del__(self):
        if self.ssh is not None:
            self.ssh.close()
            self.ssh = None

    def str2arg(self, ss):
        return str2arg(ss)

    def parentConn(self):
        if self.dkTunnel is None:
            raise Exception("This connection is not docker connection.")
        return self.dkTunnel

    def dockerConn(self, name, dkId=None):
        if self.dkTunnel is not None:
            # raise Exception("dockerConn can be called only on remote connection.")
            return self.dkTunnel.dockerConn(name, dkId)

        # dk = Tasks(self.server, g_config, self, name, dkId)
        dk = Tasks(self.server, self.config, self, name, dkId)
        return dk

    def otherDockerConn(self, name, dkId=None):
        # if self.dkTunnel is None:
        #     raise Exception("otherDockerConn can be called on docker connection only.")

        # return self.dkTunnel.dockerConn(name, dkId)
        return self.dockerConn(name, dkId)

    def remoteConn(self, host, port, id, pw=None, dkName=None, dkId=None, keyFile=None):
        """
        지정해서 커넥션을 만들어낸다.
        docker지정까지 가능하다. 이거 설정을 컨피그로 할수 있게 하자
        이건 util로 가는게 나을까
        """
        # dk = Tasks(Dict2(dict(name="remote", host=host, port=port, id=id)), g_config)  # no have owner
        serverCfg = Dict2(
            dict(name="remote", host=host, port=port, id=id, pw=pw, keyFile=keyFile)
        )

        dk = Tasks(serverCfg, self.config)
        # no have owner

        # Tasks 생성자에서 접속하는듯...
        # dk.initSsh(host, port, id, keyFile=keyFile)

        if dkName is not None:
            dk = dk.dockerConn(dkName, dkId)

        return dk

    def onlyLocal(self):
        if self.ssh is not None:
            raise Exception("this method only can be used in local service.")

    def onlyRemote(self):
        if self.dkTunnel is None and self.ssh is None:
            raise Exception("this method only can be used in remote service.")

    def setupApp(self, path, profile, serverOvr=None, varsOvr=None, subCmd=""):
        if path.endswith(".py"):
            path = path[:-3]

        path = os.path.expanduser(path)
        path = os.path.abspath(path)

        if not os.path.exists(path + ".py"):
            raise Exception(f"There is no target file[{path}] for deployApp")

        print(f"\nsetupApp - path:{path}...")
        dir = os.path.dirname(path)
        fn = os.path.basename(path)

        config = Config()
        helper = Helper(config)

        # sys.path.insert(0, dir)
        # sys.path = sys.path[1:]
        # importlib.invalidate_caches()
        # mymod = importlib.import_module(fn)

        # import module은 sys.path바꿔도 이미 로드한 모듈이름은 캐시해버린다
        spec = importlib.util.spec_from_file_location(fn, path + ".py")
        mymod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mymod)

        mygat = mymod.myGat(helper=helper)

        server = config.configServerGet(profile)
        if server is None:
            return

        # 위에서 이미 오버라이딩해놓은게 있을수 있으니 보존 - setupApp은 구조가 다르다
        # idx = config.servers.index(server)
        # server = deepcopy(env.server)
        # config.servers[idx] = server

        # override configure
        server = deepcopy(server)
        if serverOvr is not None:
            server.fill(serverOvr)
        if varsOvr is not None:
            server.vars.fill(varsOvr)

        # remote = Tasks(server)
        # if "dkName" in server.dic:
        #     remote = remote.dockerConn(server.dkName, dkId=server.get("dkId"))

        pp = os.path.abspath(os.curdir)
        os.chdir(dir)
        try:
            # g_main.taskDeploy(remote, server, mygat, config)
            # g_main.taskSetup(remote, server, mygat, config)
            g_main.taskSetup(server, subCmd, mygat, config)
        finally:
            os.chdir(pp)

    def deployApp(self, path, profile, serverOvr=None, varsOvr=None):
        if path.endswith(".py"):
            path = path[:-3]

        path = os.path.expanduser(path)
        path = os.path.abspath(path)

        if not os.path.exists(path + ".py"):
            raise Exception(f"There is no target file[{path}] for deployApp")

        print(f"\ndeployApp - path:{path}, profile:{profile}")
        dir = os.path.dirname(path)
        fn = os.path.basename(path)

        config = Config()
        helper = Helper(config)
        # mymod = importlib.import_module(fn)

        # import module은 sys.path바꿔도 이미 로드한 모듈이름은 캐시해버린다
        spec = importlib.util.spec_from_file_location(fn, path + ".py")
        mymod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mymod)

        mygat = mymod.myGat(helper=helper)

        server = config.configServerGet(profile)
        if server is None:
            return

        # 위에서 이미 오버라이딩해놓은게 있을수 있으니 보존
        # idx = config.servers.index(server)
        # server = deepcopy(env.server)
        # config.servers[idx] = server

        # override configure
        server = deepcopy(server)
        if serverOvr is not None:
            server.fill(serverOvr)
        if varsOvr is not None:
            server.vars.fill(varsOvr)

        # remote = Tasks(server)
        # if "dkName" in server.dic:
        #     remote = remote.dockerConn(server.dkName, dkId=server.get("dkId"))

        pp = os.path.abspath(os.curdir)
        os.chdir(dir)
        try:
            # g_main.taskDeploy(remote, server, mygat, config)
            g_main.taskDeploy(server, mygat, config)
        finally:
            os.chdir(pp)

    def copyFile(self, srcPath, targetPath, sudo=False, mode=755, makeFolder=False):
        srcPath = os.path.expanduser(srcPath)
        srcPath = os.path.abspath(srcPath)
        with open(srcPath, "r") as fp:
            content = fp.read()

        self.makeFile(
            content=content,
            path=targetPath,
            sudo=sudo,
            mode=mode,
            makeFolder=makeFolder,
        )

    def loadFile(self, path, sudo=False):
        sudoCmd = "sudo" if sudo else ""
        ss = self.runOutput(f"{sudoCmd} cat {path}")
        return ss

    def makeFile(self, content, path, sudo=False, mode=755, makeFolder=False):
        # self.onlyRemote()
        # ss = content.replace('"', '\\"').replace('%', '\%').replace('$', '\$')
        sudoCmd = "sudo" if sudo else ""

        if makeFolder:
            pp = os.path.dirname(path)
            self.run(f"{sudoCmd} mkdir -p {pp}")

        content = str2arg(content)

        self.run(
            f'echo "{content}" | {sudoCmd} tee {path} > /dev/null && {sudoCmd} chmod {mode} {path}'
        )

    def runOutput(self, cmd, expandVars=True):
        """
        cmd: string or array
        expandVars:
        return: stdout string
        exception: subprocess.CalledProcessError(returncode, output)
        """
        print("executeOutput on %s[%s].." % (self._serverName(), cmd))

        # if expandVars:
        #     cmd = strExpand(cmd, g_dic)

        if self.dkTunnel is not None:
            dkRunUser = "-u %s" % self.dkId if self.dkId is not None else ""
            cmd = str2arg(cmd)
            cmd = f'sudo docker exec -i {dkRunUser} {self.dkName} bash -c "{cmd}"'
            # alias defined in .bashrc is working but -l should be used for something in /etc/profile.d and .profile
            return self.dkTunnel.ssh.runOutput(cmd)
        elif self.ssh is not None:
            return self.ssh.runOutput(cmd)
        else:
            return subprocess.check_output(
                cmd, shell=True, executable="/bin/bash"
            ).decode()

    def runOutputAll(self, cmd, expandVars=True):
        """
        cmd: string or array
        expandVars:
        return: stdout and stderr string
        exception: subprocess.CalledProcessError(returncode, output)
        """
        print("executeOutputAll on %s[%s].." % (self._serverName(), cmd))

        # if expandVars:
        #     cmd = strExpand(cmd, g_dic)

        if self.dkTunnel is not None:
            dkRunUser = "-u %s" % self.dkId if self.dkId is not None else ""
            cmd = str2arg(cmd)
            cmd = f'sudo docker exec -i {dkRunUser} {self.dkName} bash -c "{cmd}"'
            return self.dkTunnel.ssh.runOutputAll(cmd)
        elif self.ssh is not None:
            return self.ssh.runOutputAll(cmd)
        else:
            return subprocess.check_output(
                cmd, shell=True, stderr=subprocess.STDOUT, executable="/bin/bash"
            )

    def _serverName(self):
        if self.server is None:
            return "local"
        elif self.dkTunnel is None:
            return f"{self.server.host}:{self.server.port}"
        else:
            return f"{self.dkName}[{self.server.host}:{self.server.port}]"

    def run(self, cmd, expandVars=True, printLog=True):
        if printLog:
            print(f"execute on {self._serverName()}[{cmd}]..")

        # if expandVars:
        #     cmd = strExpand(cmd, g_dic)

        if self.dkTunnel is not None:
            # it하면 오류 난다
            dkRunUser = "-u %s" % self.dkId if self.dkId is not None else ""
            cmd = str2arg(cmd)
            cmd = f'sudo docker exec -i {dkRunUser} {self.dkName} bash -c "{cmd}"'
            # print('run cmd(dk) - %s' % cmd)
            return self.dkTunnel.ssh.run(cmd)
        elif self.ssh is not None:
            # print('run cmd(ssh) - %s' % cmd)
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
        """
        return: success flag
        """
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
        pp = f"/tmp/upload-{g_main.uid}.tmp"
        if self.dkTunnel is not None:
            self.dkTunnel.ssh.uploadFile(src, pp)
            self.dkTunnel.ssh.run(f"sudo docker cp {pp} {self.dkName}:{dest}")
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
        if self.dkTunnel is not None:
            self.dkTunnel.ssh.run("rm -rf /tmp/gat_upload && mkdir /tmp/gat_upload")
            # allDir = []
            # allFile = []
            src = src.rstrip("/") + "/"
            for pp, dirs, files in os.walk(src):
                for dir in dirs:
                    self.dkTunnel.ssh.run(
                        "mkdir " + os.path.join("/tmp/gat_upload", pp, dir)
                    )
                for file in files:
                    self.dkTunnel.ssh.uploadFile(
                        os.path.join(src, pp, file),
                        os.path.join("/tmp/gat_upload", pp[len(src) :], file),
                    )

            self.run("rm -rf %s" % dest)
            self.dkTunnel.ssh.run(
                "sudo docker cp /tmp/gat_upload %s:%s && rm -rf /tmp/gat_upload"
                % (self.dkName, dest)
            )
        else:
            self.ssh.uploadFolder(src, dest)

    def uploadFolderTo(self, src, dest):
        self.onlyRemote()
        self.ssh.uploadFolder(src, os.path.join(dest, os.path.basename(src)))

    def _helperRun(self, args, sudo=False):
        pp2 = f"/tmp/gatHelper-{g_main.uid}.py"
        src = os.path.join(g_scriptPath, "gatHelper.py")

        if self.dkTunnel is None and self.ssh is None:
            shutil.copyfile(src, pp2)
        else:
            if not self._uploadHelper:
                if self.dkTunnel is not None:
                    self.dkTunnel.uploadFile(src, pp2)
                    self.dkTunnel.ssh.run(f"sudo docker cp {pp2} {self.dkName}:{pp2}")
                else:
                    self.uploadFile(src, pp2)

                self._uploadHelper = True

        # ss = str2arg(json.dumps(args, cls=ObjectEncoder))
        ss = json.dumps(args, cls=ObjectEncoder)
        ss2 = zlib.compress(ss.encode())  # 1/3이나 절반 - 사이즈가 문제가 아니라 escape때문에
        ss = base64.b64encode(ss2).decode()
        self.run(
            '%spython3 %s runBin "%s"' % ("sudo " if sudo else "", pp2, ss),
            expandVars=False,
            printLog=False,
        )

    """ use myutil.makeUser
  def userNew(self, name, existOk=False, sshKey=False):
    print("task: userNew...")
    self.onlyRemote()
    
    args = dict(cmd="userNew", dic=g_dic,
      name=name, existOk=existOk, sshKey=sshKey)
    self._helperRun(args, sudo=True)
  """

    def strLoad(self, path):
        print("task: strLoad from[%s]..." % path)
        self.onlyLocal()

        path = os.path.expanduser(path)
        with open(path, "rt") as fp:
            return fp.read()

    def strEnsure(self, path, str, sudo=False):
        """
        str이 없으면 추가한다
        """
        print("task[%s]: strEnsure[%s] for %s..." % (self._serverName(), str, path))
        self.onlyRemote()

        args = dict(cmd="strEnsure", dic=g_dic, path=path, str=str)
        self._helperRun(args, sudo)

    def configBlock(self, path, marker, block, insertAfter=None, sudo=False):
        """
        block이 보존한다(필요시 수정도)
        marker: ### {mark} TEST
        block: vv=1
        """
        print(f"task: config block[{marker}] for {path}...\n[{block}]\n")
        # self.onlyRemote()

        args = dict(
            cmd="configBlock",
            dic=g_dic,
            path=path,
            marker=marker,
            block=block,
            insertAfter=insertAfter,
        )
        self._helperRun(args, sudo)

    def configLine(self, path, regexp, line, items=None, sudo=False, append=False):
        """
        regexp에 부합되는 라인이 있을 경우 변경한다
        """
        print("task: config line[%s] for %s..." % (line, path))
        # self.onlyRemote()

        args = dict(
            cmd="configLine",
            dic=g_dic,
            path=path,
            regexp=regexp,
            line=line,
            items=items,
            append=append,
        )
        self._helperRun(args, sudo)

    def s3List(self, env, bucket, prefix):
        print("task: s3 list[%s/%s]..." % (bucket, prefix))
        self.onlyLocal()

        if not prefix.endswith("/"):
            prefix += "/"

        s3 = CoS3(env.config.get("s3.key", None), env.config.get("s3.secret", None))
        bb = s3.bucketGet(bucket)
        lst = bb.fileList(prefix)
        return lst

    def s3DownloadFiles(self, env, bucket, prefix, nameList, targetFolder):
        print("task: s3 download files[%s/%s]..." % (bucket, prefix))
        self.onlyLocal()

        if not targetFolder.endswith("/"):
            targetFolder += "/"
        if not prefix.endswith("/"):
            prefix += "/"

        s3 = CoS3(env.config.get("s3.key", None), env.config.get("s3.secret", None))
        bb = s3.bucketGet(bucket)
        for name in nameList:
            bb.downloadFile(prefix + name, targetFolder + name)

    def s3DownloadFile(self, env, bucket, key, dest=None):
        print("task: s3 download file[%s -> %s]..." % (key, dest))
        self.onlyLocal()

        s3 = CoS3(env.config.get("s3.key", None), env.config.get("s3.secret", None))
        bb = s3.bucketGet(bucket)
        return bb.downloadFile(key, dest)


# https://pythonhosted.org/watchdog/
class MyHandler(PatternMatchingEventHandler):
    def __init__(
        self,
        patterns=None,
        ignore_patterns=None,
        ignore_directories=False,
        case_sensitive=False,
    ):
        super(MyHandler, self).__init__(
            patterns, ignore_patterns, ignore_directories, case_sensitive
        )
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
    global g_dic  # helper run할때 전달되는 기능
    g_dic = deepcopy(g_config)
    g_dic.dic["server"] = server
    g_dic.dic["vars"] = deepcopy(server.vars)
    g_dic.dic["data"] = deepcopy(g_data)
    # g_util.cfg = g_config
    # g_util.config = g_dic # 전역객체기 때문에 쓰면 안된다
    g_util.data = g_data


def _excludeFilter(_exclude, pp):
    pp = os.path.normpath(pp)
    if pp in _exclude:
        return True

    for item in _exclude:
        # exclude에 /a/dump라면 pp가 /a/dump/test라도 필터링 되야한다.
        if pathIsChild(pp, item):
            return True

        # /test/* 형태 지원
        if "*" in item:
            if fnmatch.fnmatch(pp, item):
                return True

    return False


def _pathExpand(pp2):
    # 원래 deploy에서 아래처럼 {{name}}으로 확장하는게 있었는데.. 일단 보류
    # dic = dict(name=config.name)
    pp2 = os.path.expanduser(pp2)
    # return strExpand(pp2, dic)
    return pp2


import socket


class Main:
    def __init__(self):
        self.uid = socket.gethostname() + "-" + str(os.getpid())

    # runTask와 doServerStep등은 Task말고 별도로 빼자 remote.runTask를 호출할일은 없으니까
    def runTask(self, mygat):
        # self.onlyLocal()

        if hasattr(mygat, "getRunCmd"):
            cmd = mygat.getRunCmd(util=g_util, local=g_local, remote=g_remote)
            if type(cmd) != list:
                raise Exception(
                    "the return value of runTask function should be list type."
                )
        else:
            if not hasattr(g_config, "cmd"):
                g_config.cmd = "./" + g_config.name

            if isinstance(g_config.cmd, str):
                g_config.cmd = [g_config.cmd]

            cmd = g_config.cmd

        print("run: running the app[%s]..." % cmd)
        if subprocess.call("type unbuffer", shell=True) == 0:
            # cmd = ["unbuffer", "./"+g_util.executableName]
            cmd = ["unbuffer"] + cmd

        return cmd

    def doServeStep(self, mygat):
        # if hasattr(g_mygat, "doServeStep"):
        # 	return g_mygat.doServeStep()
        print("\n\n\n")

        buildExc = None
        try:
            self.buildTask(mygat)
        except Error as e:
            buildExc = e.args
        except Exception:
            buildExc = traceback.format_exc()

        if buildExc is not None:
            print("\nrun: exception in buildTask...\n  %s" % buildExc)
            while True:  # wait for file modification
                if g_util.isRestart:
                    return

                time.sleep(0.1)
        else:
            cmd = self.runTask(mygat)

            with subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr) as p:
                while True:
                    try:
                        ret = p.wait(0.1)
                        raise ExcProgramExit(
                            "run: the application has been terminated[ret:%d]" % ret
                        )

                    except subprocess.TimeoutExpired:
                        pass

                    if g_util.isRestart:
                        g_util.isRestart = False
                        p.terminate()
                        break

    def doTestStep(self, mygat):
        print("\n\n\n")

        cmd = g_config.test.cmd
        # if subprocess.call("type unbuffer", shell=True) == 0:
        # 	cmd = ["unbuffer"] + cmd

        with subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr) as p:
            while True:
                try:
                    ret = p.wait(0.1)
                    raise ExcProgramExit(
                        "run: the application has been terminated[ret:%d]" % ret
                    )

                except subprocess.TimeoutExpired:
                    pass

                except ExcProgramExit:
                    print("**** test job is finished")
                    # 이 경우 재구동까지 기다린다.
                    while not g_util.isRestart:
                        time.sleep(0.1)

                if g_util.isRestart:
                    g_util.isRestart = False
                    p.terminate()
                    break

    def buildTask(self, mygat):
        print("run: building the app")
        if hasattr(mygat, "buildTask"):
            return mygat.buildTask(util=g_util, local=g_local, remote=g_remote)
        else:
            print("You should override buildTask method.")

    # def taskSetup(self, target, serverName, subCmd):
    def taskSetup(self, server, subCmd, mygat, config):
        # if not os.path.exists(target):
        #     print("There is no target file[%s]" % target)
        #     return

        # server = g_config.configServerGet(serverName)
        # if server is None:
        #     return

        # deprecated
        # server["runImage"] = runImageFlag
        if subCmd not in ["run", "dev", "prod", "full", "init", ""]:
            raise Exception(f"Invalid sub command[{subCmd}] for setup task")

        # global g_remote, g_data
        # g_remote = Tasks(server)
        # g_remote.runFlag = subCmd == "run"
        # g_remote.runImageFlag = g_remote.runFlag  # deprecated
        # g_remote.fullFlag = subCmd == "full"
        # if "dkName" in server.dic:
        #     g_remote = g_remote.dockerConn(server.dkName, dkId=server.get("dkId"))

        env = Tasks(server, config)
        if "dkName" in server.dic:
            env = env.dockerConn(server.dkName, dkId=server.get("dkId"))

        # print("\n\n\n\nhahahaha")
        # print(env.config)
        # print("\n\n\n\n")

        env.runFlag = False
        env.runProfile = None
        if subCmd in ["dev", "prod", "run"]:
            env.runFlag = True
            if subCmd != "run":
                env.runProfile = subCmd

        # env.runImageFlag = env.runFlag  # deprecated

        env.fullFlag = subCmd == "full"
        env.initFlag = subCmd == "init"

        # g_remote.data = g_data
        # g_remote.util = g_util
        dicInit(server)

        # expand env and variables
        expandVar(config)

        if not hasattr(mygat, "setupTask"):
            print("setup: You should override setupTask function in your myGat class")
            return

        # 1. 원격 repo에서 특정 브렌치의 최신 커밋 받기
        # 2. 기존 clone 이 최신인지 판단하고 최신이 아니면 삭제후 다시 클론
        # recentCommit = getRemoteRecentCommit(config=config)
        # directory = os.getcwd() + "/clone"
        # print(directory)
        # if(isRecentlyCommit(directory=directory, recentlyCommit=recentCommit)):
        #     cloneRepo(config.bitbucket[3].cloneUrl, config.bitbucket[4].branch)

        # global g_config
        # oldConfig = g_config
        # try:
        # 내부적으로 g_config에 액서스할때가 있어서 일단은..
        # config접근을 env를 통해서 하게 할까...
        # g_config = config
        mygat.setupTask(util=g_util, remote=env, local=g_local)
        # finally:
        # g_config = oldConfig

    def taskTest(self):
        observer = None
        if len(g_config.test.patterns) > 0:
            observer = Observer()
            observer.schedule(
                MyHandler(g_config.test.patterns), path=".", recursive=True
            )
            observer.start()

        try:
            while True:
                time.sleep(0.01)
                g_util.isRestart = False
                self.doTestStep(g_mygat)

        except KeyboardInterrupt:
            if observer is not None:
                observer.stop()

        if observer is not None:
            observer.join()

    def taskServe(self):
        observer = None
        if len(g_config.serve.patterns) > 0:
            observer = Observer()
            observer.schedule(
                MyHandler(g_config.serve.patterns), path=".", recursive=True
            )
            observer.start()

        try:
            while True:
                time.sleep(0.01)
                g_util.isRestart = False
                self.doServeStep(g_mygat)

        except KeyboardInterrupt:
            if observer is not None:
                observer.stop()

        if observer is not None:
            observer.join()

    # localSrcPath 를 뒤에 둔 이유는 기본 값이 필요해서 + 이 함수를 사용하는 다른 곳에서 인자 위치로 인한 에러
    def targetFileListProd(
        self, include, exclude, func, localSrcPath="", followLinks=True
    ):
        for pp in include:
            if type(pp) == str:
                if pp == "*":
                    pp = "."

                # daemon
                pp = _pathExpand(pp)

                p = pathlib.Path(os.path.join(localSrcPath, pp))
                if not p.exists():
                    print(f"target: not exists - {pp}")
                    continue

                if p.is_dir():
                    if _excludeFilter(exclude, pp):
                        print(f"target: skip - {pp}")
                        continue

                    for folder, dirs, files in os.walk(pp, followlinks=followLinks):
                        # filtering dirs too
                        dirs2 = []
                        for d in dirs:
                            dd = os.path.join(folder, d)
                            if _excludeFilter(exclude, dd):
                                print(f"target: skip - {dd}")
                                continue

                            dirs2.append(d)

                        dirs[:] = dirs2  # 이걸 변경하면 다음 files가 바뀌나?

                        for ff in files:
                            # _zipAdd(os.path.join(folder, ff), os.path.join(folder, ff))
                            full = os.path.join(folder, ff)
                            if _excludeFilter(exclude, full):
                                print(f"target: skip - {full}")
                                continue

                            func(full, None)
                else:
                    # _zipAdd(pp, pp)
                    if _excludeFilter(exclude, pp):
                        print(f"target: skip - {pp}")
                        continue

                    func(pp, None)

            else:
                src = pp["src"]
                src = _pathExpand(src)
                dest = pp["dest"]

                exclude2 = []
                if "exclude" in pp:
                    exclude2 = pp["exclude"]

                for folder, dirs, files in os.walk(src):
                    for ff in files:
                        localPath = os.path.join(folder, ff)
                        localPath = pathRemove(localPath, src)
                        if _excludeFilter(exclude2, localPath):
                            print(f"target: skip - {os.path.join(folder, ff)}")
                            continue

                        # _zipAdd(os.path.join(folder, ff), os.path.join(dest, cutpath(src, folder), ff))
                        func(
                            os.path.join(folder, ff),
                            os.path.join(dest, cutpath(src, folder), ff),
                        )

    # def taskDeploy(self, env, server, mygat, config):
    def taskDeploy(self, server, mygat, config):
        env = Tasks(server, config)
        if "dkName" in server.dic:
            env = env.dockerConn(server.dkName, dkId=server.get("dkId"))

        self.buildTask(mygat)

        dicInit(server)
        # expand env and variables
        expandVar(config)

        sudoCmd = ""
        if "owner" in server:
            sudoCmd = "sudo"

        # name = config.name
        deployRoot = server.deployRoot
        realTarget = env.runOutput("realpath %s" % deployRoot)
        realTarget = realTarget.strip("\r\n")  # for sftp
        todayName = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")[2:]

        # pre task
        deployPath = os.path.join(realTarget, "releases", todayName)
        g_dic.dic["deployRoot"] = deployRoot
        g_dic.dic["deployPath"] = deployPath

        env.server.deployPath = deployPath
        if hasattr(mygat, "deployPreTask"):
            mygat.deployPreTask(util=g_util, remote=env, local=g_local)

        # prepare target folder
        env.runOutput(
            f"{sudoCmd} mkdir -p {deployRoot}/shared && {sudoCmd} mkdir -p {deployRoot}/releases"
        )
        # ('&& sudo chown %s: %s %s/shared %s/releases' % (server.owner, deployRoot, deployRoot, deployRoot) if server.owner else '') +

        res = env.runOutput(f"cd {deployRoot}/releases && ls -d *;echo")
        releases = list(
            filter(lambda x: re.match("\d{6}_\d{6}", x) is not None, res.split())
        )
        releases.sort()

        max = config.deploy.maxRelease - 1
        cnt = len(releases)
        print(f"deploy: releases folders count is {cnt}")
        if cnt > max:
            print(f"deploy: remove old {cnt - max} folders")
            removeList = releases[: cnt - max]
            for ff in removeList:
                env.runOutput(f"{sudoCmd} rm -rf {deployRoot}/releases/{ff}")

        # if deploy / owner is defined,
        # create release folder as ssh user, upload, extract then change release folder to deploy / owner
        res = env.runOutput(
            f"cd {deployRoot}/releases"
            + f"&& {sudoCmd} mkdir {todayName}"
            + (
                f"&& sudo chown {server.owner}: {todayName}"
                if "owner" in server
                else ""
            )
        )

        # upload files
        include = config.deploy.include
        exclude = config.get("deploy.exclude", [])
        sharedLinks = config.get("deploy.sharedLinks", [])

        def zipProcess(env, include, exclude, localSrcPath=None):
            zipPath = os.path.join(tempfile.gettempdir(), "data.zip")
            with zipfile.ZipFile(zipPath, "w") as zipWork:

                def _zipAdd(srcP, targetP):
                    # if _filterFunc(srcP, exclude):
                    #     print(f"deploy: skip - {srcP}")
                    #     return

                    # make "./aaa" -> "aaa"
                    targetP = os.path.normpath(targetP)

                    print(f"zipping {srcP} -> {targetP}")
                    zipWork.write(srcP, targetP, compress_type=zipfile.ZIP_DEFLATED)

                # dic = dict(name=config.name)
                # def _pathExpand(pp):
                #     pp = os.path.expanduser(pp)
                #     return strExpand(pp, dic)

                # zipWork.write(config.name, config.name, compress_type=zipfile.ZIP_DEFLATED)
                def fileProc(src, dest):
                    if dest is None:
                        dest = src
                    _zipAdd(src, dest)

                self.targetFileListProd(
                    include,
                    exclude,
                    fileProc,
                    localSrcPath=localSrcPath,
                    followLinks=config.deploy.followLinks,
                )

            env.uploadFile(
                zipPath, "/tmp/gatUploadPkg.zip"
            )  # we don't include it by default
            env.run(
                f"cd {deployRoot}/releases/{todayName} "
                + f"&& {sudoCmd} unzip /tmp/gatUploadPkg.zip && {sudoCmd} rm /tmp/gatUploadPkg.zip"
            )
            os.remove(zipPath)

        strategy = g_config.deploy.strategy
        if strategy == "zip":
            zipProcess(env, include, exclude, strategy)

        elif strategy == "git":
            # 여기 path는 git clone을 받을 주소
            # 나중에 따로 god_app.py에서 설정하도록 하면 코드가 더욱 좋아질거라 예상
            path = "./clone"
            cloneRepo(g_config.deploy.gitRepo, server.gitBranch, path)

            zipProcess(env, include, exclude, path)

            """	no use copy strategy anymore
      elif strategy == "copy":
        ssh.uploadFile(config.name, os.path.join(realTargetFull, config.name))	# we don't include it by default
        ssh.run("chmod 755 %s/%s" % (realTargetFull, config.name))

        ssh.uploadFilterFunc = _filterFunc

        for pp in include:
          if type(pp) == str:
            if pp == "*":
              pp = "."
            
            # daemon
            pp = pp.replace("${name}", config.name)
                        
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
            raise Exception(f"unknown strategy[{strategy}]")

        # shared links
        for pp in sharedLinks:
            print(f"deploy: sharedLinks - {pp}")
            if pp.endswith("/"):
                env.run(f"cd {deployRoot} && {sudoCmd} mkdir -p shared/{pp} ")
                pp = pp[:-1]

            env.run(
                "%s ln -rsf %s/shared/%s %s/releases/%s/%s"
                % (sudoCmd, deployRoot, pp, deployRoot, todayName, pp)
            )

            # ssh user용으로 변경해놔야 post process에서 쉽게 접근 가능
            if "owner" in server:
                env.run(
                    f"cd {deployRoot} && sudo chown {server.get('dkId', server.id)}: releases/{todayName} shared -R"
                )

        # update current - post전에 갱신되어 있어야 current에 있는거 실행한다
        env.run(
            f"cd {deployRoot} && {sudoCmd} rm -f current && {sudoCmd} ln -sf releases/{todayName} current"
        )
        # if "owner" in server:
        #  env.run("cd %s && %s chown %s: current" % (deployRoot, sudoCmd, server.owner))

        # post process
        if hasattr(mygat, "deployPostTask"):
            mygat.deployPostTask(util=g_util, remote=env, local=g_local)

        # file owner - 이걸 post후에 해야 ssh user가 파일 접근이 가능하다
        if "owner" in server:
            env.run(
                f"cd {deployRoot} && sudo chown {server.owner}: shared releases/{todayName} -R"
            )
            env.run(f"cd {deployRoot} && sudo chmod 775 shared releases/{todayName} -R")

        # TODO: postTask에서 오류 발생시 다시 돌려놔야


def initSamples(type, fn):
    with open(fn, "w") as fp:
        if type == "app":
            fp.write(sampleApp)
        else:
            fp.write(sampleSys)

    print(
        "init: %s file generated. You should modify that file for your environment before service or deployment."
        % (fn)
    )


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
        """
        type: yaml
        """
        if cfgType == "yaml":
            try:
                # self.cfg = Dict2()
                self.fill(yaml.safe_load(ss))
                # g_util.config = g_config

                if "defaultVars" in self:
                    for server in self.servers:
                        # vars2 = Dict2()
                        # vars2.fill(self.defaultVars)
                        # vars2.fill(server.vars)
                        # server.vars = vars2
                        server.vars = dictMerge2(self.defaultVars, server.vars)

                if self.type == "app":
                    if "followLinks" not in self.deploy:
                        self.deploy["followLinks"] = False

            except yaml.YAMLError as e:
                raise e
        else:
            raise Exception("unknown config type[%s]" % cfgType)

    def configFile(self, cfgType, pp):
        """
        type: yaml
        """
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
            print(self)
            raise Exception(f"Not found server[{name}]")

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
            raise Exception(f"there is no data file[{pp}]")

        print(f"load data from {pp}...")
        # TODO: encrypt with input key when changed
        with open(pp, "r") as fp:
            dd = Dict2(yaml.safe_load(fp.read()))
            print("data -", dd)
            return dd


# g_helper = Helper()
g_config = Config()
g_main = Main()
# g_config = Dict2()	# py코드에서는 util.cfg로 접근 가능
g_dic = None  # helper실행할때 씀, server, vars까지 설정
g_data = None  # .data.yml
# config, server, vars(of server)
# deployRoot, deployPath
g_mygat = None

g_util = MyUtil()
g_local = None
g_remote = None  # server, vars직접 접근 가능


def help(target):
    print(f"gat V{__version__}")
    print(
        """\
Usage.
gat init app - Generates gat_app.py file for application.
gat init sys SYSTEM_NAME - Generates the file for system.
  the SYSTEM_NAME.py file will be generated.

For application(There should be gat_app.py file.),
gat - Serves application.
gat test - running automatic test.
gat PROFILE_NAME deploy - Deploy the application to the server.

gat PROFILE_NAME setup - Setup task.
gat PROFILE_NAME run - Run system.

For system,
gat SYSTEM_NAME PROFILE_NAME - Setup server defined in GAT_FILE.
"""
    )
    if target is not None:
        print(f"\nThere is no {target} script file.")


def main():
    global g_cwd, g_scriptPath, g_mygat
    g_cwd = os.getcwd()
    g_scriptPath = os.path.dirname(os.path.realpath(__file__))
    target = "gat_app.py"

    cnt = len(sys.argv)
    cmd = None
    # setup or run의 argv를 받기 위한 변수
    manualStrategyValue = None
    if cnt > 1:
        cmd = sys.argv[1]

        if cmd == "help" or cmd == "--help":
            help(None)
            return

        elif cmd == "init":
            if cnt < 3:
                print("gat init app OR gat init sys NAME.")
                return

            type = sys.argv[2]
            if type != "app" and type != "sys":
                print("app or sys can be used for gat init command.")
                return

            if type == "app":
                initSamples(type, "gat_app.py")

            elif type == "sys":
                if cnt < 4:
                    print("Please specify Target file name to be generated.")
                    return

                target = sys.argv[3]
                if not target.endswith(".py"):
                    target += ".py"
                initSamples(type, target)

            else:
                print("unknown init type[%s]" % type)

            return

        elif cmd == "test":
            pass

        elif cmd == "serve":
            pass

        # deploy도 아래 system 문법으로
        # elif cmd == "deploy":
        #     pass

        else:
            # 로칼에 gat_app.py가 있으면 configName생략 모드
            if not os.path.exists(target):
                target = None

            # setup server system or deploy
            cmd = "system"
            if cnt < 2:
                # can skip SERVER_NAME(if there is only one target), cmd(default setup)
                print("gat [CONFIG_NAME] [SERVER_NAME] [run|deploy|init|SETUP]")
                return

            p = 1
            if target is None:
                target = sys.argv[p]
                if not target.endswith(".py"):
                    target += ".py"
                p += 1

            runCmd = None
            serverName = None
            if cnt > p:
                second = sys.argv[p]
                # print(f"second:{second}")
                if second in ["run", "deploy", "init", "setup"]:
                    runCmd = second
                else:
                    # 아니면 Server이름
                    serverName = second
                p += 1

                # print(f"cnt:{cnt}, p:{p}")
                if cnt > p:
                    if runCmd is not None:
                        serverName = runCmd
                    runCmd = sys.argv[p]
                else:
                    runCmd = "setup"

                print(f"target2 -- {runCmd}, {serverName}")

            else:
                runCmd = "setup"

            # strategy 분기
            p += 1
            if (runCmd == "setup" or runCmd == "run") and cnt - 1 == p:
                print(f"========== 명령어 확인 : {sys.argv[p]} ==========")
                if sys.argv[p] == "--git":
                    manualStrategyValue = "git"
                    # g_config.deploy.strategy = argv
                elif sys.argv[p] == "--zip":
                    manualStrategyValue = "zip"
                    # g_config.deploy.strategy = argv
                else:
                    raise Exception(f"{manualStrategyValue}는 올바르지 않은 명령어입니다.")

    else:
        print("missing gat command")
        return

    # check first
    if not os.path.exists(target):  # or not os.path.exists("gat.yml"):
        help(target)
        return

    global g_config
    helper = Helper(g_config)
    sys.path.append(g_cwd)
    mymod = __import__(target[:-3], fromlist=[""])
    g_mygod = mymod.myGod(helper=helper)
    # g_config 객체 생성 지점 -> 여기부터 설정 객체 사용 가능
    if manualStrategyValue is not None:
        g_config.deploy.strategy = manualStrategyValue

    print("gat-tool V%s" % __version__)
    name = g_config.name
    type = g_config.get("type", "app")

    print("** config[type:%s, name:%s]" % (type, name))

    # load secret - 이걸 mygat init하는데서 수동으로 하게해놨는데..
    # 무조건 로드하게하고 추가 로드를 할수 있게할까? - 좀 애매하다
    global g_data
    # secretPath = os.path.join(g_cwd, ".data.yml")
    # if os.path.exists(secretPath):
    #     print("load data...")
    #     # TODO: encrypt with input key when changed
    #     with open(secretPath, "r") as fp:
    #         ss = fp.read()
    #         g_data = Dict2(yaml.safe_load(ss))
    #         print("data - ", g_data)
    # if g_mygat.data is not None:
    if hasattr(g_mygat, "data"):
        g_data = g_mygat.data

    global g_local
    g_local = Tasks(None, g_config)
    # g_local.util = g_util

    def checkServerName(serverName):
        """
        return: none(error), str(new serverName)
        """
        if serverName is None:
            if len(g_config.servers) == 0:
                print("\nThere is no server definition.")
                return

            if len(g_config.servers) == 1:
                serverName = g_config.servers[0].name

            else:
                ss = ""
                for it in g_config.servers:
                    ss += it["name"] + "|"
                print(
                    f"\nPlease specify the sever name is no server definition.[{ss[:-1]}]"
                )
                return

        else:
            serverFound = False
            for it in g_config.servers:
                if it.name == serverName:
                    serverFound = True
            if not serverFound:
                ss = ""
                for it in g_config.servers:
                    ss += it.name + "|"

                print(f"There is no server[{serverName}] in {ss[:-1]}")
                return
        return serverName

    if cmd == "system":
        if runCmd == "deploy":
            # g_util.deployOwner = g_config.get("deploy.owner", None)	# replaced by server.owner
            # serverName = sys.argv[2] if cnt > 2 else None
            # if serverName is None:
            #     if len(g_config.servers) == 1:
            #         serverName = g_config.servers[0]["name"]
            #     else:
            #         ss = ""
            #         for it in g_config.servers:
            #             ss += it["name"] + "|"
            #         print(f"\nPlease specify server name.[{ss[:-1]}]")
            #         return
            serverName = checkServerName(serverName)
            if serverName is None:
                return

            server = g_config.configServerGet(serverName)

            # env = Tasks(server)
            # if "dkName" in server.dic:
            #     env = env.dockerConn(server.dkName, dkId=server.get("dkId"))

            # g_main.taskDeploy(env, server, g_mygat, g_config)
            g_main.taskDeploy(server, g_mygat, g_config)
            return

        subCmd = ""
        if runCmd in ["run", "full", "init"]:
            subCmd = runCmd

        serverName = checkServerName(serverName)
        if serverName is None:
            return

        print(f"systemSetup - target:{target}, server:{serverName}, subCmd:{subCmd}")
        server = g_config.configServerGet(serverName)

        g_main.taskSetup(server, subCmd, g_mygat, g_config)
        return

    elif cmd == "test":
        # serve
        if type != "app":
            print("just gat command can be used for application type only.")
            return

        g_main.taskTest()

    elif cmd == "serve":
        # serve
        if type != "app":
            print("just gat command can be used for application type only.")
            return

        g_main.taskServe()

    else:
        print("unknown command mode[%s]" % cmd)


if __name__ == "__main__":
    main()
