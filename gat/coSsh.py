import os
import sys
import time
import paramiko
from paramiko.agent import AgentRequestHandler
import socket
import subprocess
import signal
import getpass

from .coPath import cutpath, path2folderList


class SshAllowAllKeys(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self, client, hostname, key):
        return


class MyCalledProcessError(subprocess.CalledProcessError):
    def __init__(self, returncode, cmd, output=None, stderr=None):
        super(MyCalledProcessError, self).__init__(returncode, cmd, output, stderr)

    def __str__(self):
        if self.returncode and self.returncode < 0:
            try:
                return "Command '%s' died with %r." % (
                    self.cmd,
                    signal.Signals(-self.returncode),
                )
            except ValueError:
                return "Command '%s' died with unknown signal %d." % (
                    self.cmd,
                    -self.returncode,
                )
        else:
            return "Command '%s' returned non-zero exit status %d.%s" % (
                self.cmd,
                self.returncode,
                "\n out:[%s]" % self.output if self.output else "",
            )


def falseFunc(pp):
    return False


# sudo with ssh
# https://gist.github.com/vladwa/bc49621782736a825844ee4c2a7dacae

# TODO: use invoke_shell


# https://gist.github.com/kdheepak/c18f030494fea16ffd92d95c93a6d40d
# https://stackoverflow.com/questions/760978/long-running-ssh-commands-in-python-paramiko-module-and-how-to-end-them
class CoSsh:
    def __init__(self):
        pass

    def init(self, host, port, id, pw=None, keyFile=None):
        self.ssh = paramiko.SSHClient()
        # ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.set_missing_host_key_policy(SshAllowAllKeys())
        # self.ssh.connect(
        #     host, port=port, username=id, password=pw, key_filename=keyFile
        # )
        # , password='lol')

        # if "Darwin" in platform.system():
        #     import keyring

        #     pp = os.path.expanduser("~/.ssh/id_ed25519")
        #     ss = keyring.get_password("OpenSSH", pp)
        #     print(f"keyring: {ss} - {pp}")

        connected = False
        # keys = tuple(MacOSXAgent().get_keys())
        # print(f"key lenght: {len(keys)}")
        # for key in keys:
        #     try:
        #         self.ssh.connect(host, port=port, username=id, pkey=key)
        #         connected = True
        #     except paramiko.AuthenticationException:
        #         continue

        if not connected:
            try:
                self.ssh.load_system_host_keys()
                self.ssh.connect(
                    host,
                    port=port,
                    username=id,
                    key_filename=keyFile,
                )
                # , password='lol')
            except paramiko.PasswordRequiredException:
                pw = getpass.getpass("key password: ")
                self.ssh.connect(
                    host, port=port, username=id, key_filename=keyFile, passphrase=pw
                )

        # transport = self.ssh.get_transport()
        # s = transport.open_session()
        # paramiko.agent.AgentRequestHandler(s)
        # self.sftp = paramiko.SFTPClient.from_transport(transport)
        self.sftp = self.ssh.open_sftp()

        self.uploadFilterFunc = falseFunc

    def close(self):
        if hasattr(self, "ssh"):
            self.ssh.close()

    def log(self, lv, msg):
        print("%d) %s" % (lv, msg))

    def _run(self, cmd, doOutput, arg, logCmd=None, log=False):
        s = time.time()
        chan = self.ssh.get_transport().open_session()
        # chan.get_pty()
        chan.exec_command(cmd)
        chan.setblocking(0)
        isLoop = True
        while isLoop:
            try:
                line = chan.recv_stderr(99999)
                if len(line) > 0:
                    doOutput(False, line.decode("utf-8"), arg)

            except socket.timeout as e:
                pass

            try:
                line = chan.recv(99999)
                if len(line) == 0:
                    isLoop = False
                else:
                    doOutput(True, line.decode("utf-8"), arg)

            except socket.timeout as e:
                pass

        ret = chan.recv_exit_status()
        chan.close()

        if log:
            g = time.time() - s
            g = int(g * 1000)
            ss = f"{g}ms" if g < 10000 else f"{int(g/1000)}s"
            print(f"  -> ({ss}) ret:{ret} ")

        if ret != 0:
            sys.stdout.flush()
            # raise CalledProcessError("ssh command failed with ret:%d" % ret)
            ss = "" if arg is None else arg[0]
            if logCmd is None:
                logCmd = cmd
            raise MyCalledProcessError(ret, logCmd, ss)

    # return: nothing
    def run(self, cmd, logCmd=None, log=False):
        """
        exception: output이 빈채로 온다
        """

        buf = [""]

        def doOutput(isStdout, ss, arg):
            if log:
                print(ss, end="")
            else:
                buf[0] += ss

        try:
            self._run(cmd, doOutput, None, logCmd=logCmd, log=log)
        except MyCalledProcessError as e:
            # log가 아니라도 실패시에는 결과를 출력
            if not log:
                print(f"  -> output:{buf[0]}")
            raise e

    def runOutput(self, cmd, log=False):
        """
        return: stdout result
        exception: output에 stdout만 포함
        """
        out = [""]

        def doOutput(isStdout, ss, arg):
            if isStdout:
                arg[0] += ss
            else:
                if log:
                    print(" stderr: ", ss)

        self._run(cmd, doOutput, out, log=log)
        # print("  -> output:%s" % (out[0]))
        return out[0]

    def runOutputAll(self, cmd, log=False):
        """
        return: stdout + stderr result
        exception: output에 stderr, stdout 모두 포함
        """
        out = [""]

        def doOutput(isStdout, ss, arg):
            arg[0] += ss

        self._run(cmd, doOutput, out, log=log)
        # print("  -> output:%s" % (out[0]))
        return out[0]

    # sftp 상에 경로를 생성한다.
    # remote 경로가 directory이면, is_dir에 True를 전달한다.
    def mkdirs(self, remote, isFolder=False):
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
                self.log(1, f"sftp: making dir -> {pp}")
                self.sftp.mkdir(pp)

    def uploadFileTo(self, srcPath, destFolder):
        # print("sftp: uploadFilesTo - %s %s" % (srcPath, destFolder))
        name = os.path.split(srcPath)[1]
        self.uploadFile(srcPath, os.path.join(destFolder, name))

    def downloadFile(self, srcPath, destPath):
        destPath = os.path.expanduser(destPath)
        self.log(1, f"sftp: download file {srcPath} -> {destPath}")
        self.sftp.get(srcPath, destPath)

    # sftp 상에 파일을 업로드한다.
    # src_path에 dest_path로 업로드한다. 두개 모두 file full path여야 한다.
    def uploadFile(self, srcPath, destPath):
        self.log(1, f"sftp: upload file {srcPath} -> {destPath}")
        srcPath = os.path.expanduser(srcPath)

        if not os.path.isfile(srcPath):
            raise Exception("uploadFile: there is no file[%s]" % srcPath)

        if self.uploadFilterFunc(srcPath):
            self.log(1, f" ** exclude file - {srcPath}")
            return

        if destPath.startswith("~/"):
            destHome = self.runOutput("echo $HOME").strip()
            destPath = destPath.replace("~/", f"{destHome}/")

        self.mkdirs(destPath)
        try:
            self.sftp.put(srcPath, destPath)
        except Exception as e:
            # print("sftp: fail to upload " + srcPath + " ==> " + destPath)
            raise e
        # print("sftp: success to upload " + srcPath + " ==> " + destPath)

    # srcPath, destPath둘다 full path여야한다.
    def uploadFolder(self, srcPath, destPath):
        self.log(1, f"sftp: upload folder {srcPath} -> {destPath}")
        if not os.path.isdir(srcPath):
            raise Exception(f"uploadFolder: there is no folder[{srcPath}]")

        if self.uploadFilterFunc(srcPath):
            self.log(1, f" ** exclude folder - {srcPath}")
            return

        self.mkdirs(destPath, True)

        for folder, dirs, files in os.walk(srcPath):
            try:
                for pp in files:
                    src = os.path.join(folder, pp)
                    target = os.path.join(destPath, cutpath(srcPath, folder), pp)
                    self.uploadFile(src, target)
            except Exception as e:
                print(e)
                raise e
