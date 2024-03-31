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

from termcolor import colored, cprint

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
from .coCollection import dictMerge, Dict2, dict2Merge

g_cwd = ""
g_scriptPath = ""

# ##################### 나중에 사용될 여지가 있다. ###########################################

# 우분투 명령어와 centos 명령어를 매핑
# key(ubuntu) : value(centos)
# 우분투 패키지 명 기준으로 매핑
g_packages = {
    "rssh": {
        "centos": "rssh",
    },
    "sshfs": {
        "centos": "sshfs",
    },
    "knockd": {
        "centos": "epel-release knockd",
    },
    "openssh-client": {
        "centos": "openssh-clients",
    },
    "git": {
        "centos": "git",
    },
    "libmysqlclient-dev": {
        "centos": "mysql-devel",
    },
    "mongodb-org": {
        "centos": "mongodb-org",
    },
    "redis-server": {
        "centos": "redis",
    },
    "rabbitmq-server": {
        "centos": "rabbitmq-server",
    },
    "python3": {
        "centos": "epel-release python36",
    },
    "python3-pip": {
        "centos": "python36-pip",
    },
    "python3-setuptools": {
        "centos": "python36-setuptools",
    },
    "locales": {
        "centos": "glibc-locale-source glibc-langpack-en",
    },
    "openssh-server": {
        "centos": "openssh-server",
    },
    "tzdata": {
        "centos": "tzdata",
    },
    "cron": {
        "centos": "cronie",
    },
    "anacron": {
        "centos": "anacron",
    },
    "rsyslog": {
        "centos": "rsyslog",
    },
    "logrotate": {
        "centos": "logrotate",
    },
    "sudo": {
        "centos": "sudo",
    },
    "runit": {
        "centos": "epel-release runit",
    },
    "gnupg": {
        "centos": "gnupg2",
    },
    "fail2ban": {
        "centos": "fail2ban",
    },
    "transmission-daemon": {
        "centos": "transmission-daemon",
    },
    "bup": {"centos": "epel-release bup"},
}

# 우분투 명령어와 centos 명령어를 매핑
# key(ubuntu) : value(centos)
# 우분투 패키지 명 기준으로 매핑
g_options = {
    "-y": {
        "centos": "-y",
    },
    "--no-install-recommends": {
        "centos": "",
    },
}


# 패키지 등록 함수
# 우분투 패키지 이름을 기준으로 매핑
def pkgRegister(os, pkgUbuntu, pkg):
    global g_packages
    # 1. g_packages에 ubuntu 명령어 자체가 없는 경우, 새로운 매핑 생성
    if pkgUbuntu not in g_packages:
        g_packages[pkgUbuntu] = {os: pkg}
        print(f"{pkgUbuntu} for {os} has been successfully registered")
    else:
        # 2. 해당 Ubuntu 패키지에 대한 OS 매핑이 이미 존재하는 경우, 메시지 출력
        if os in g_packages[pkgUbuntu]:
            print(
                f"{pkgUbuntu} for {os} is already exist with package {g_packages[pkgUbuntu][os]}"
            )
        else:
            # 3. 존재하지 않는 경우, 새로운 OS 매핑 추가
            g_packages[pkgUbuntu][os] = pkg
            print(f"{pkgUbuntu} for {os} has been successfully registered")


# 옵션 등록 함수
# 우분투 옵션 이름을 기준으로 매핑
# 나중에 다시 수정이 필요, because 명령어마다 옵션이 다르기 때문에
def optRegister(os, optUbuntu, opt):
    global g_options
    if optUbuntu not in g_options:
        g_options[optUbuntu] = {os: opt}
        print(f"{optUbuntu} for {os} has been successfully registered")
    else:
        if os in g_options[optUbuntu]:
            print(
                f"{optUbuntu} for {os} is already exist with package {g_options[optUbuntu][os]}"
            )
        else:
            g_options[optUbuntu][os] = opt
            print(f"{optUbuntu} for {os} has been successfully registered")


# ######################################################################################3


g_logLv = 0
g_force = False

g_connList = []


def lld(ss):
    if g_logLv >= 1:
        print(ss)


def llw(ss):
    cprint(ss, "magenta", attrs=["bold"])


def lle(ss):
    cprint(ss, "red", attrs=["bold"])


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
        exclude = env.config.deploy.get("exclude", [])
        # basePath = env.config.deploy.get("basePath", ".")
        followLinks = env.config.deploy.followLinks
        srcPath = env.config.srcPath
        g_main.targetFileListProd(
            include, exclude, func, followLinks=followLinks, localSrcPath=srcPath
        )


class Conn:
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

        self._os = None

        # for log
        if server is None:
            self.logName = "local"
        else:
            if dkTunnel is None:
                self.logName = f"{server.host}:{server.port}"
            else:
                self.logName = f"{dkTunnel.logName}/{dkName}"

        if server is not None:
            if dkTunnel is None:
                port = server.get("port", 22)
                # port 0 is local conn
                if port != 0:
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

        self.tempPath = None

        g_connList.append(self)

    def clearConn(self):
        self.run("rm -f /tmp/gatHelper.py", printLog=False)
        self.tempPathClear()

    def tempPathGet(self):
        if self.tempPath is None:
            pp = f"/tmp/gat-{self.config.name}"
            ss = self.runOutput(f"test -d ${pp}; echo $?")
            if ss == "0":
                if not g_force:
                    raise Exception(
                        f"remote work path[{pp}] already exists. you can proceed with -f option."
                    )

                self.run(f"rm -rf {pp}")

            self.tempPath = pp

        return self.tempPath

    def tempPathClear(self):
        if self.tempPath is not None:
            self.run(f"rm -rf {self.tempPath}")
            self.tempPath = None

    def log(self, msg):
        print(f"[{self.logName}]: {msg}")

    def initSsh(self, host, port, id, keyFile=None):
        self.ssh = CoSsh()
        self.log(
            f"ssh - connecting to the server[{id}@{host}:{port}] with key:{keyFile}"
        )
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

        dk = Conn(self.server, self.config, self, name, dkId)
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

        dk = Conn(serverCfg, self.config)
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

        self.log(f"setupApp - path:{path}...")
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
            g_main.taskSetup(server, subCmd, mygat, config)
        finally:
            os.chdir(pp)

    # 이제 이거 쓰는곳이 없다
    def deployApp(self, path, profile, serverOvr=None, varsOvr=None):
        if path.endswith(".py"):
            path = path[:-3]

        path = os.path.expanduser(path)
        path = os.path.abspath(path)

        if not os.path.exists(path + ".py"):
            raise Exception(f"There is no target file[{path}] for deployApp")

        self.log(f"deployApp - path:{path}, profile:{profile}")
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
            g_main.taskDeploy(server, mygat, config)
        finally:
            os.chdir(pp)

    # 이거 좀 애매한데 uploadFile인데 사실상...
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
        # self.run(f'echo "{content}" > {path}')

    def runOutput(self, cmd, expandVars=True):
        """
        cmd: string or array
        expandVars:
        return: stdout string
        exception: subprocess.CalledProcessError(returncode, output)
        """
        ss = cmd[:100] + "..." if g_logLv == 0 and len(cmd) > 100 else cmd
        self.log(f"runOutput [{ss}]")

        # if expandVars:
        #     cmd = strExpand(cmd, g_dic)

        log = g_logLv > 0

        out = ""
        if self.dkTunnel is not None:
            dkRunUser = "-u %s" % self.dkId if self.dkId is not None else ""
            cmd = str2arg(cmd)
            cmd = f'sudo docker exec -i {dkRunUser} {self.dkName} bash -c "{cmd}"'
            # alias defined in .bashrc is working but -l should be used for something in /etc/profile.d and .profile
            out = self.dkTunnel.ssh.runOutput(cmd, log=log)
        elif self.ssh is not None:
            out = self.ssh.runOutput(cmd, log=log)
        else:
            out = subprocess.check_output(
                cmd, shell=True, executable="/bin/bash"
            ).decode()

        if g_logLv > 0:
            print("  -> output:%s" % (out))
        return out

    # return os name of remote server
    def getOS(self):
        if self._os is None:
            try:
                osInfo = self.runOutput("cat /etc/os-release").lower()
                if "ubuntu" in osInfo:
                    self._os = "ubuntu"
                elif "centos" in osInfo:
                    self._os = "centos"
                else:
                    raise Exception("Unknown OS")

            except Exception as e:
                osInfo = self.runOutput("sw_vers")
                osInfo = osInfo.lower()
                if "mac os" in osInfo or "macos" in osInfo:
                    self._os = "macos"
                else:
                    raise Exception("Unknown OS")

            # print(f"========== remote os : {self._os} ==========")

        return self._os

    # runOutput 래퍼 함수
    # os 별 ~/.profile 명령이 다르기 때문에 대응하기 위해
    def runOutputProf(self, cmd, expandVars=True):
        os = self.getOS()

        if os == "ubuntu":
            profile = "profile"
        elif os == "centos":
            profile = "bash_profile"
        elif os == "macos":
            profile = "bash_profile"
        else:
            raise Exception(f"Unknown OS - {os}")

        cmd = f". ~/.{profile} && " + cmd
        return self.runOutput(cmd, expandVars=expandVars)

    def runOutputAll(self, cmd, expandVars=True):
        """
        cmd: string or array
        expandVars:
        return: stdout and stderr string
        exception: subprocess.CalledProcessError(returncode, output)
        """
        ss = cmd[:100] + "..." if g_logLv == 0 and len(cmd) > 100 else cmd
        self.log(f"runOutputAll [{ss}]")

        # if expandVars:
        #     cmd = strExpand(cmd, g_dic)

        if self.dkTunnel is not None:
            dkRunUser = "-u %s" % self.dkId if self.dkId is not None else ""
            cmd = str2arg(cmd)
            cmd = f'docker exec -i {dkRunUser} {self.dkName} bash -c "{cmd}"'
            return self.dkTunnel.ssh.runOutputAll(cmd)
        elif self.ssh is not None:
            return self.ssh.runOutputAll(cmd)
        else:
            return subprocess.check_output(
                cmd, shell=True, stderr=subprocess.STDOUT, executable="/bin/bash"
            )

    # def _serverName(self):
    #     if self.server is None:
    #         return "local"
    #     elif self.dkTunnel is None:
    #         return f"{self.server.host}:{self.server.port}"
    #     else:
    #         return f"{self.dkName}[{self.server.host}:{self.server.port}]"

    def run(self, cmd, expandVars=True, printLog=True):
        if printLog:
            ss = cmd[:100] + "..." if g_logLv == 0 and len(cmd) > 100 else cmd
            self.log(f"run [{ss}]")

        # if expandVars:
        #     cmd = strExpand(cmd, g_dic)

        if self.dkTunnel is not None:
            # it하면 오류 난다
            dkRunUser = "-u %s" % self.dkId if self.dkId is not None else ""
            cmd = str2arg(cmd)
            # sudo docker로 하면 cmd에 '가 있으면 centos에서 실행이 안된다
            cmd = f'docker exec -i {dkRunUser} {self.dkName} bash -c "{cmd}"'
            # print("run cmd(dk) - %s" % cmd)
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

    # runOutput 래퍼 함수
    # os 별 ~/.profile 명령이 다르기 때문에 대응하기 위해
    def runProf(self, cmd, expandVars=True):
        os = self.getOS()

        tmpCmd = ". ~/."

        if os == "ubuntu":
            tmpCmd = tmpCmd + "profile"
        elif os == "centos":
            tmpCmd = tmpCmd + "bash_profile"
        tmpCmd = tmpCmd + " && "

        cmd = tmpCmd + cmd
        self.run(cmd, expandVars=expandVars)

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
        """
        support both local and remote
        """
        # self.onlyRemote()
        src = os.path.expanduser(src)
        dest = os.path.expanduser(dest)
        if self.dkTunnel is not None:
            # pp = f'/tmp/upload-{g_main.uid}.tmp'
            pp = f"{self.tempPathGet()}/upload.tmp"
            self.dkTunnel.ssh.uploadFile(src, pp)
            self.dkTunnel.ssh.run(
                f"sudo docker cp {pp} {self.dkName}:{dest} && rm {pp}"
            )
        elif self.ssh is None:
            self.run(f"cp {src} {dest}")
        else:
            self.ssh.uploadFile(src, dest)

    def uploadFileTo(self, src, dest):
        # self.onlyRemote()
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
        # pp2 = f"{self.tempPathGet()}/gatHelper.py"
        pp2 = f"/tmp/gatHelper.py"
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
        ss2 = zlib.compress(
            ss.encode()
        )  # 1/3이나 절반 - 사이즈가 문제가 아니라 escape때문에
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
        self.log("task - strLoad from[%s]..." % path)
        self.onlyLocal()

        path = os.path.expanduser(path)
        with open(path, "rt") as fp:
            return fp.read()

    def strEnsure(self, path, str, sudo=False):
        """
        str이 없으면 추가한다
        """
        self.log(f"task - strEnsure[{str}] for {path}...")
        self.onlyRemote()

        args = dict(cmd="strEnsure", dic=g_dic, path=path, str=str)
        self._helperRun(args, sudo)

    def configBlock(self, path, marker, block, insertAfter=None, sudo=False):
        """
        block이 보존한다(필요시 수정도)
        marker: ### {mark} TEST
        block: vv=1
        """

        ss = f"task - config block[{marker}] for {path}...\n"
        if g_logLv > 0:
            ss += f"[{block}]\n"
        self.log(ss)
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
        self.log("task - config line[%s] for %s..." % (line, path))
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
        self.log("task - s3 list[%s/%s]..." % (bucket, prefix))
        self.onlyLocal()

        if not prefix.endswith("/"):
            prefix += "/"

        s3 = CoS3(env.config.get("s3.key", None), env.config.get("s3.secret", None))
        bb = s3.bucketGet(bucket)
        lst = bb.fileList(prefix)
        return lst

    def s3DownloadFiles(self, env, bucket, prefix, nameList, targetFolder):
        self.log("task - s3 download files[%s/%s]..." % (bucket, prefix))
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
        self.log("task - s3 download file[%s -> %s]..." % (key, dest))
        self.onlyLocal()

        s3 = CoS3(env.config.get("s3.key", None), env.config.get("s3.secret", None))
        bb = s3.bucketGet(bucket)
        return bb.downloadFile(key, dest)

    # ####################### 나중에 사용될 여지가 있다. ####################################

    # 패키지 install 함수 -> ubuntu, centos 지원
    def pkgInstall(self, sudo=False, options=[], packages=[]):
        # sudo 권한 여부 확인 후 sudo 추가
        cmdSudo = "sudo " if sudo else ""
        # OS에 따라 패키지 매니저 추가
        os = self.getOS()
        cmdPkgManager = None
        if os == "ubuntu":
            cmdPkgManager = "apt-get"
        elif os == "centos":
            cmdPkgManager = "yum"
        else:
            raise Exception(f"Unknown OS - {os}")

        # 해당 옵션을 운영체제에 알맞게 매핑
        optionList = self._mapOptionToOs(os=os, options=options)
        cmdOption = " ".join(optionList)
        # 해당 OS에 알맞게 패키지명 매핑
        packageList = self._mapPackageToOs(os=os, packages=packages)
        cmdPackage = " ".join(packageList)
        # 명령어 실행
        cmd = f"{cmdSudo}{cmdPkgManager} install {cmdOption} {cmdPackage}"
        self.run(cmd)

    # update 함수 -> ubuntu, centos 지원
    def pkgUpdate(self, sudo=False):
        os = self.getOS()
        # sudo 권한 여부 확인 후 sudo 추가
        cmdSudo = "sudo " if sudo else ""
        # OS에 따라 패키지 매니저 추가
        cmdPkgManager = None
        if os == "ubuntu":
            cmdPkgManager = "apt-get"
        elif os == "centos":
            cmdPkgManager = "yum"
        # 명령어 실행
        cmd = f"{cmdSudo}{cmdPkgManager} update"
        self.run(cmd)

    # 프로그램 실행 함수
    def pkgStart(self, sudo=False, package=""):
        # sudo 권한 여부 확인 후 sudo 추가
        cmdSudo = "sudo " if sudo else ""
        # 프로그램 시작 명령어
        cmdPkgStart = None
        pkg = self._mapPackageToOs(os=os, packages=package)
        cmdPkgStart = f"systemctl start {pkg}"
        # 명령어 실행
        cmd = f"{cmdSudo}{cmdPkgStart}"
        self.run(cmd)

    # 프로그램 재실행 함수
    def pkgRestart(self, sudo=False, package=""):
        # sudo 권한 여부 확인 후 sudo 추가
        cmdSudo = "sudo " if sudo else ""
        # 프로그램 시작 명령어
        cmdPkgRestart = None
        pkg = self._mapPackageToOs(os=os, packages=package)
        cmdPkgRestart = f"systemctl restart {pkg}"
        # 명령어 실행
        cmd = f"{cmdSudo}{cmdPkgRestart}"
        self.run(cmd)

    # 프로그램 정지 함수
    def pkgStop(self, sudo=False, package=""):
        # sudo 권한 여부 확인 후 sudo 추가
        cmdSudo = "sudo " if sudo else ""
        # 프로그램 정지 명령어
        cmdPkgStop = None
        pkg = self._mapPackageToOs(os=os, packages=package)
        cmdPkgStop = f"systemctl restart {pkg}"
        cmd = f"{cmdSudo}{cmdPkgStop}"
        self.run(cmd)

    # 옵션 인자를 OS에 맞춰서 매핑
    def _mapOptionToOs(self, os="", options=[]):
        global g_options
        optionList = []
        for option in options:
            if g_options.__contains__(option):
                if os == "ubuntu":
                    optionList.append(option)
                elif os == "centos":
                    optionCentOs = g_options.get(option)
                    optionList.append(optionCentOs)
            else:
                raise Exception("Unknown option")
        return optionList

    # 패키지를 OS에 맞춰서 매핑
    def _mapPackageToOs(self, os="", packages=[]):
        global g_packages
        packageList = []
        for package in packages:
            if g_packages.__contains__(package):
                if os == "ubuntu":
                    packageList.append(package)
                elif os == "centos":
                    packageCentOs = g_packages.get(package)
                    packageList.append(packageCentOs)
            else:
                raise Exception("Unknown package")
        return packageList

    # #####################################################################3


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
        # self.uid = socket.gethostname() + "-" + str(os.getpid())
        # self.workPath = f"/tmp/"
        pass

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
        llw("buildTask: building the app")
        if hasattr(mygat, "buildTask"):
            return mygat.buildTask(util=g_util, local=g_local, remote=g_remote)
        else:
            lle("You should override buildTask method.")

    def taskSetup(self, server, subCmd, mygat, config):
        llw("taskSetup: setting up the app...")

        # deprecated
        if subCmd not in ["run", "dev", "prod", "full", "init", ""]:
            raise Exception(f"Invalid sub command[{subCmd}] for setup task")

        env = Conn(server, config)
        if "dkName" in server.dic:
            env = env.dockerConn(server.dkName, dkId=server.get("dkId"))

        # print(env.config)

        env.runFlag = False
        env.runProfile = None
        if subCmd in ["dev", "prod", "run"]:
            env.runFlag = True
            if subCmd != "run":
                env.runProfile = subCmd

        env.fullFlag = subCmd == "full"
        env.initFlag = subCmd == "init"

        dicInit(server)
        expandVar(config)

        if not hasattr(mygat, "setupTask"):
            lle("setup: You should override setupTask function in your myGat class")
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
                pp = os.path.join(localSrcPath, pp)

                p = pathlib.Path(pp)
                if not p.exists():
                    llw(f"targetList: not exists - {pp}")
                    continue

                if p.is_dir():
                    if _excludeFilter(exclude, pp):
                        lld(f"targetList: skip - {pp}")
                        continue

                    for folder, dirs, files in os.walk(pp, followlinks=followLinks):
                        # filtering dirs too
                        dirs2 = []
                        for d in dirs:
                            dd = os.path.join(folder, d)
                            if _excludeFilter(exclude, dd):
                                lld(f"targetList: skip - {dd}")
                                continue

                            dirs2.append(d)

                        dirs[:] = dirs2  # 이걸 변경하면 다음 files가 바뀌나?

                        for ff in files:
                            # _zipAdd(os.path.join(folder, ff), os.path.join(folder, ff))
                            full = os.path.join(folder, ff)
                            if _excludeFilter(exclude, full):
                                lld(f"targetList: skip - {full}")
                                continue

                            func(full, None)
                else:
                    # _zipAdd(pp, pp)
                    if _excludeFilter(exclude, pp):
                        lld(f"targetList: skip - {pp}")
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
                            lld(f"targetList: skip - {os.path.join(folder, ff)}")
                            continue

                        # _zipAdd(os.path.join(folder, ff), os.path.join(dest, cutpath(src, folder), ff))
                        func(
                            os.path.join(folder, ff),
                            os.path.join(dest, cutpath(src, folder), ff),
                        )

    def taskDeploy(self, server, mygat, config):
        llw("taskDeploy: deploy the app...")

        env = Conn(server, config)
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
        env.run(f"mkdir -p {deployRoot}")
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
        llw(f"taskDeploy: releases folders count is {cnt}")
        if cnt > max:
            llw(f"taskDeploy: remove old {cnt - max} folders")
            removeList = releases[: cnt - max]
            for ff in removeList:
                env.runOutput(f"{sudoCmd} rm -rf {deployRoot}/releases/{ff}")

        # if deploy / owner is defined,
        # create release folder as ssh user, upload, extract then change release folder to deploy / owner
        cmd = f"cd {deployRoot}/releases && {sudoCmd} mkdir {todayName}"
        if "owner" in server:
            cmd += f" && {sudoCmd} chown {server.owner}: {todayName}"
        res = env.runOutput(cmd)

        # upload files
        include = config.deploy.include
        exclude = config.get("deploy.exclude", [])
        sharedLinks = config.get("deploy.sharedLinks", [])

        def zipProcess(env, include, exclude, localSrcPath):
            zipPath = os.path.join(tempfile.gettempdir(), "data.zip")
            with zipfile.ZipFile(zipPath, "w") as zipWork:

                def _zipAdd(srcP, targetP):
                    # if _filterFunc(srcP, exclude):
                    #     print(f"deploy: skip - {srcP}")
                    #     return

                    # make "./aaa" -> "aaa"
                    targetP = os.path.normpath(targetP)

                    lld(f"zipping {srcP} -> {targetP}")
                    zipWork.write(srcP, targetP, compress_type=zipfile.ZIP_DEFLATED)

                # dic = dict(name=config.name)
                # def _pathExpand(pp):
                #     pp = os.path.expanduser(pp)
                #     return strExpand(pp, dic)

                # zipWork.write(config.name, config.name, compress_type=zipfile.ZIP_DEFLATED)
                def _fileProc(src, dest):
                    if dest is None:
                        dest = src
                    _zipAdd(src, dest)

                self.targetFileListProd(
                    include,
                    exclude,
                    _fileProc,
                    localSrcPath=localSrcPath,
                    followLinks=config.deploy.followLinks,
                )

            # we don't include it by default
            env.uploadFile(zipPath, "/tmp/gatUploadPkg.zip")
            os.remove(zipPath)
            env.run(
                f"cd {deployRoot}/releases/{todayName} "
                + f"&& {sudoCmd} unzip /tmp/gatUploadPkg.zip && {sudoCmd} rm /tmp/gatUploadPkg.zip"
            )

        strategy = g_config.deploy.strategy
        # workPath = env.config.srcPath
        workPath = g_config.srcPath

        old = os.path.abspath(os.curdir)
        try:
            # 아예 해당 폴더로 가서 생성한다
            os.chdir(workPath)
            workPath = ""

            # deployApp으로 온 경우 env.config가 새로 만들어진다
            if strategy == "zip":
                zipProcess(env, include, exclude, workPath)

            elif strategy == "git":
                # 여기 path는 git clone을 받을 주소
                # 나중에 따로 god_app.py에서 설정하도록 하면 코드가 더욱 좋아질거라 예상
                cloneRepo(g_config.deploy.gitRepo, server.gitBranch, workPath)
                zipProcess(env, include, exclude, workPath)

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
        finally:
            os.chdir(old)

        # shared links
        for pp in sharedLinks:
            lld(f"taskDeploy: sharedLinks - {pp}")
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

    llw(
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
        self.dic["srcPath"] = "."

    def configStr(self, cfgType, ss):
        """
        type: yaml
        """
        if cfgType == "yaml":
            try:
                self.fill(yaml.safe_load(ss))

                if "defaultVars" in self:
                    for server in self.servers:
                        server.vars = dict2Merge(self.defaultVars, server.vars)

                if self.type == "app":
                    if "followLinks" not in self.deploy:
                        self.deploy["followLinks"] = False

            except yaml.YAMLError as e:
                raise e
        else:
            raise Exception(f"unknown config type[{cfgType}]")

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

        print(f"init: load data from {pp}...")
        # TODO: encrypt with input key when changed
        with open(pp, "r") as fp:
            dd = Dict2(yaml.safe_load(fp.read()))
            # print("data -", dd)
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

For application(a gat_app.py file should be exist),
gat - Serves application.
gat test - Runs automatic test.

For deployment(a gat_app.py file should be exist),
gat SERVER_NAME deploy - Deploy the application to the server.

For setup task(a gat_app.py file should be exist),
gat SERVER_NAME setup - Setups environment.
gat SERVER_NAME run - Setup and Run the system.

For system(GAT_FILE_NAME.py file should be exist),
gat GAT_FILE_NAME SERVER_NAME - Setup server defined in GAT_FILE.
"""
    )
    if target is not None:
        print(f"\nThere is no {target} script file.")


class MyArgv:
    def __init__(self, argv, fileExists=None):
        self.gatName = "gat_app.py"
        self.serverName = ""
        self.opts = []  # -v, --git, --zip
        self.cmd = ""  # help, init | deploy, setup, run
        self.args = []  # arguments

        if fileExists is None:
            fileExists = os.path.exists

        removeIdxs = []
        for i in range(len(argv)):
            arg = argv[i]
            if arg.startswith("-"):
                self.opts.append(arg)
                removeIdxs.append(i)
        for i in reversed(removeIdxs):
            argv.pop(i)

        if "--help" in self.opts:
            self.opts.remove("--help")
            self.cmd = "help"
            return

        if len(argv) == 0:
            raise Exception("missing gat command")

        self.cmd = argv[0]
        if self.cmd == "help":
            return
        elif self.cmd == "init":
            if len(argv) < 2:
                raise Exception("gat init app OR gat init sys FILE_NAME.")
            self.args.append(argv[1])
            if self.args[-1] == "sys":
                if len(argv) < 3:
                    raise Exception(
                        "Please specify target file name to be generated.\n$ gat init sys FILE_NAME"
                    )

                self.args.append(argv[2])
            return
        # elif self.cmd == "test":
        #     return
        # elif self.cmd == "serve":
        #     return

        # 이제 용법은
        # gat SERVER_NAME CMD - gat파일은 gat_app.py로 고정

        # gat파일 명시
        # gat GAT_FILE SERVER_NAME CMD
        # gat GAT_FILE SERVER_NAME - cmd는 setup
        # gat GAT_FILE CMD - server 하나
        # gat GAT_FILE - server하나, CMD는 setup -- 시스템용

        # xxx gat CMD - gat_app.py, server 하나

        # SERVER_NAME에는 아래 예약된 명령어는 못쓴다
        cmds = ["deploy", "setup", "run"]

        pt = 0
        name = argv[pt]
        if not name.endswith(".py"):
            name += ".py"
        if fileExists(name):
            self.gatName = name
            pt += 1

        # if pt >= len(argv):
        #     raise Exception("Please specify SERVER_NAME")
        if pt == len(argv):
            self.cmd = "setup"
            return

        arg1 = argv[pt]
        if arg1 in cmds:
            self.cmd = arg1
            pt += 1
            # if pt >= len(argv):
            #     raise Exception("No more arguments")
            return

        self.serverName = arg1
        pt += 1

        if pt >= len(argv):
            self.cmd = "setup"
            # raise Exception("Please specify CMD")
        else:
            self.cmd = argv[pt]

        return


def testMyArgv():
    argv = ["help"]
    aa = MyArgv(argv)
    assert aa.cmd == "help"

    argv = ["init", "app"]
    aa = MyArgv(argv)
    assert aa.cmd == "init"
    assert aa.args == ["app"]

    argv = ["init", "sys", "test"]
    aa = MyArgv(argv)
    assert aa.cmd == "init"
    assert aa.args == ["sys", "test"]

    try:
        argv = ["init", "sys"]
        aa = MyArgv(argv)
        assert False
    except Exception as e:
        pass

    # gat GAT_FILE [SERVER_NAME] [CMD]
    argv = ["gat2", "ser1", "run"]
    aa = MyArgv(argv, fileExists=lambda x: x == "gat2.py")
    assert aa.gatName == "gat2.py"
    assert aa.serverName == "ser1"
    assert aa.cmd == "run"

    argv = ["gat2", "ser1"]
    aa = MyArgv(argv, fileExists=lambda x: x == "gat2.py")
    assert aa.gatName == "gat2.py"
    assert aa.serverName == "ser1"
    assert aa.cmd == "setup"

    argv = ["gat2", "run"]
    aa = MyArgv(argv, fileExists=lambda x: x == "gat2.py")
    assert aa.gatName == "gat2.py"
    assert aa.serverName == ""
    assert aa.cmd == "run"

    argv = ["gat2.py", "deploy"]
    aa = MyArgv(argv, fileExists=lambda x: x == "gat2.py")
    assert aa.gatName == "gat2.py"
    assert aa.serverName == ""
    assert aa.cmd == "deploy"

    argv = ["gat2"]
    aa = MyArgv(argv, fileExists=lambda x: x == "gat2.py")
    assert aa.gatName == "gat2.py"
    assert aa.serverName == ""
    assert aa.cmd == "setup"

    # gat SERVER_NAME CMD
    argv = ["prod", "run"]
    aa = MyArgv(argv)
    assert aa.gatName == "gat_app.py"
    assert aa.serverName == "prod"
    assert aa.cmd == "run"

    print("test ok")


def main():
    mainDo()

    for conn in reversed(g_connList):
        conn.clearConn()


def mainDo():
    # testMyArgv()
    # return

    ma = MyArgv(sys.argv[1:])
    if ma.cmd == "help":
        help(None)
        return
    elif ma.cmd == "init":
        if len(ma.args) == 0:
            lle("gat init app OR gat init sys FILE_NAME.")
            return

        type = ma.args[0]
        if type != "app" and type != "sys":
            lle("app or sys can be used for gat init command.")
            return

        if type == "app":
            initSamples(type, "gat_app.py")
        else:
            if len(ma.args) < 2:
                lle("Please specify target file name to be generated.")
                return

            target = ma.args[1]
            if not target.endswith(".py"):
                target += ".py"
            initSamples(type, target)

        return

    global g_cwd, g_scriptPath, g_mygat
    g_cwd = os.getcwd()
    g_scriptPath = os.path.dirname(os.path.realpath(__file__))
    deployStrategy = None

    global g_config
    helper = Helper(g_config)
    sys.path.append(g_cwd)
    pyFileName = ma.gatName[:-3]
    mymod = __import__(pyFileName, fromlist=[""])
    g_mygat = mymod.myGat(helper=helper)
    # g_config 객체 생성 지점 -> 여기부터 설정 객체 사용 가능

    cprint(f"gat-tool V{__version__}", "green")
    name = g_config.name
    type = g_config.get("type", "app")
    srcPath = g_config.srcPath

    # load secret - 이걸 mygat init하는데서 수동으로 하게해놨는데..
    # 무조건 로드하게하고 추가 로드를 할수 있게할까? - 좀 애매하다
    global g_data
    if hasattr(g_mygat, "data"):
        g_data = g_mygat.data

    global g_local
    g_local = Conn(None, g_config)
    if not os.path.exists(ma.gatName):  # or not os.path.exists("gat.yml"):
        help(ma.gatName)
        return

    print(f"** config[type:{type} name:{name} srcPath:{srcPath} cmd:{ma.cmd}]")

    if ma.cmd == "test":
        # serve
        if type != "app":
            lle("just gat command can be used for application type only.")
            return
        g_main.taskTest()

    elif ma.cmd == "serve":
        # serve
        if type != "app":
            lle("just gat command can be used for application type only.")
            return
        g_main.taskServe()

    else:
        if ma.cmd not in ["run", "setup", "deploy"]:
            raise Exception(f"Invalid command[{ma.cmd}]")

        for opt in ma.opts:
            if opt == "-v":
                global g_logLv
                g_logLv = 1
            elif opt == "-f":
                global g_force
                g_force = True
            elif opt == "--git":
                deployStrategy = "git"
            elif opt == "--zip":
                deployStrategy = "zip"
            else:
                raise Exception(f"unknown option[{opt}]")

        def checkServerName(serverName):
            """
            return: none(error), str(new serverName)
            """
            if serverName == "":
                if len(g_config.servers) == 0:
                    lle("\nThere is no server definition.")
                    return

                if len(g_config.servers) == 1:
                    serverName = g_config.servers[0].name

                else:
                    ss = ""
                    for it in g_config.servers:
                        ss += it["name"] + "|"
                    s2 = ss[:-1]
                    lle(
                        f"\nPlease specify the sever name is no server definition.[{s2}]"
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

                    lle(f"There is no server[{serverName}] in {ss[:-1]}")
                    return
            return serverName

        if deployStrategy is not None:
            g_config.deploy.strategy = deployStrategy

        # g_config.srcPath = "."
        # if cmd != "system":
        #     strategy = g_config.deploy.strategy
        #     if strategy == "git":
        #         g_config.srcPath = "./clone"
        if "deploy" in g_config and g_config.deploy.strategy == "git":
            g_config.srcPath = "./clone"

        if ma.cmd == "deploy":
            serverName = checkServerName(ma.serverName)
            if serverName is None:
                return

            server = g_config.configServerGet(serverName)
            g_main.taskDeploy(server, g_mygat, g_config)
            return

        subCmd = "run" if ma.cmd == "run" else ""

        serverName = checkServerName(ma.serverName)
        if serverName is None:
            return

        llw(f"systemSetup - target:{ma.gatName}, server:{serverName}, subCmd:{subCmd}")
        server = g_config.configServerGet(serverName)

        g_main.taskSetup(server, subCmd, g_mygat, g_config)


if __name__ == "__main__":
    main()
