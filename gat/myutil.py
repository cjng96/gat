import queue
import subprocess
from threading import Thread
from copy import deepcopy
import json, inspect

import re
import os

import requests


def str2arg(ss):
    """
    기본적으로 ""로 감쌌다고 가정하고 랩핑한다.
    """
    ss = ss.replace("\\", "\\\\")
    ss = ss.replace('"', '\\"')
    # ss = ss.replace("!", "\\!")
    ss = ss.replace("$", "\\$")  # .replace('&', '\&')#.replace('%', '\%')
    # ss = ss.replace("!", "\!")	# echo 문자열 내에 있을때는 안해도 되네...
    ss = ss.replace("[^a-zA-Z]!", "\\!")  # a!는 변환하고 3!는 변환하지 말것
    ss = ss.replace("`", "\\`")  # bash -c "echo '`'" 이거 오류난다.
    # baseimage내에서 echo내에서
    # ss = ss.replace("'", "\\'")
    return ss


def envExpand(ss):
    while True:
        m = re.search(r"\$\{\{([\w_]+)\}\}", ss)
        if m is None:
            return ss

        name = m.group(1)
        v = os.getenv(name, "")
        ss = ss[: m.start()] + str(v) + ss[m.end() :]


def pathRemove(pp, parent):
    if parent[-1] != "/":
        parent += "/"

    if not pp.startswith(parent):
        return pp

    return pp[len(parent) :]


def pathIsChild(pp, parent):
    if parent[-1] != "/":
        parent += "/"

    return pp.startswith(parent)


# input : gop_app.py에 설정한 config의 객체
# output : 원격 저장소의 최신 커밋의 해시값(str)
# def getRemoteRecentCommit(config):
# 	subprocess.run("pwd")

# 	url = f"https://api.bitbucket.org/2.0/repositories/{config.bitbucket[0].workspace}/{config.bitbucket[1].repoSlug}/commits/{config.bitbucket[4].branch}"
# 	headers = {
#         "Accept": "application/json",
#         "Authorization": f"Bearer {config.bitbucket[2].token}"
#     }

# 	print(f"url : {url}. headers : {headers} 로 요청을 보내는 중입니다.")

# 	try:
# 		response = requests.request(
# 			"GET",
# 			url,
# 			headers=headers
# 		)
# 		response.raise_for_status()
# 		return response.json()["values"][0]["hash"]
# 	except requests.HTTPError as err:
# 		print(f"HTTP 오류 발생 - 상태 코드 : {err.response.status_code}")
# 		raise
# 	except requests.RequestException as err:
# 		print(f"요청 시도 중 오류 발생")
# 		raise


# input
# - directory : 이전 버전의 clone 폴더 이름
# - cloneUrl : clone url
def cloneRepo(cloneUrl, branch, clonePath):
    # subprocess.run("pwd")
    print(f"gitClone: start proceeding with git clone")
    subprocess.run(["rm", "-rf", clonePath])
    subprocess.run(["git", "clone", "-b", branch, cloneUrl, clonePath])
    old = os.curdir
    os.chdir(clonePath)
    subprocess.run(["git", "submodule", "update", "--init"])
    os.chdir(old)

    print(f"gitClone: success git clone with submodules")


# input
# - directory : clone한 프로젝트의 .git폴더의 위치
# - recentlyCommit : 원격 저장소의 최신 커밋
# output
# - 원격 저장소의 최신 커밋과 동일하면 true, 아니면 false
# def isRecentlyCommit(directory, recentlyCommit):
# 	try:
# 		commitHash = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=directory)
# 		if commitHash != recentlyCommit:
# 			return True
# 		else:
# 			return False
# 	# clone 파일이 없는 경우 만들어주기 위해서
# 	except:
# 		return True


class NonBlockingStreamReader:
    def __init__(self, stream):
        """
            stream: the stream to read from.
        Usually a process' stdout or stderr.
        """
        self.stream = stream
        self.queue = queue.Queue()

        def _populateQueue(stream, queue):
            """
            Collect lines from 'stream' and put them in 'quque'.
            """
            while True:
                line = stream.readline()
                queue.put(line)  # line can be "" for broken stream
                if line == b"":
                    return

        self.thread = Thread(target=_populateQueue, args=(self.stream, self.queue))
        self.thread.daemon = True
        self.thread.start()

    def readline(self, timeout=None):
        """
        return: None(empty), ""(exit the app)
        """
        try:
            return self.queue.get(block=timeout is not None, timeout=timeout)
        except queue.Empty:
            return None


class UnexpectedEndOfStream(Exception):
    pass


class ObjectEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, "toJson"):
            return self.default(obj.toJson())
        elif hasattr(obj, "__dict__"):
            d = dict(
                (key, value)
                for key, value in inspect.getmembers(obj)
                if not key.startswith("__")
                and not inspect.isabstract(value)
                and not inspect.isbuiltin(value)
                and not inspect.isfunction(value)
                and not inspect.isgenerator(value)
                and not inspect.isgeneratorfunction(value)
                and not inspect.ismethod(value)
                and not inspect.ismethoddescriptor(value)
                and not inspect.isroutine(value)
            )
            return self.default(d)
        return obj


class HttpError(Exception):
    def __init__(self, status_code, message):
        super().__init__(*args)
