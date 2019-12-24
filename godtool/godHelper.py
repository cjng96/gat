
import sys
import json
import traceback
import os
import re
import zlib
import base64
import platform
import subprocess
import os.path as pypath

g_dic = {}


def run(cmd):
  return subprocess.check_output(cmd, shell=True)


def runRet(cmd):
  try:
    run(cmd)
    return 0
  except subprocess.CalledProcessError as e:
    return e.returncode


def skipEnter(ss, pt):
  sz = len(ss)
  while pt < sz:
    if ss[pt] not in "\r\n":
      return pt

    pt += 1
  return sz


def configBlockStr(ss, start, end, block, insertAfter):
  # marker
  pt = ss.find(start)
  if pt >= 0:
    pt2 = ss.find(end, pt)
    if pt2 == -1:
      # 문제가 있는 경우인데.. 그냥 start marker만 대체한다.
      pt2 = pt + len(start)
    else:
      pt2 += len(end)
      pt2 = skipEnter(ss, pt2)
  else:
    # insertAfter
    pt = len(ss)
    if insertAfter is not None:
      m = re.search(insertAfter, ss)
      if m is not None:
        pt = m.end()
        pt = skipEnter(ss, pt)

    pt2 = pt

  # insert
  ss = ss[:pt] + "\n" + start + "\n" + block + "\n" + end + "\n\n" + ss[pt2:]
  return ss


def configBlock(path, marker, block, insertAfter):
  '''
  marker: ### {mark} TEST
  block: vv=1
  '''
  block = strExpand(block, g_dic)
  if insertAfter is not None:
    insertAfter = strExpand(insertAfter, g_dic)

  path = os.path.expanduser(path)
  path = strExpand(path, g_dic)
  with open(path, "r") as fp:
    orig = fp.read()
    start = marker.replace("{mark}", "BEGIN")
    end = marker.replace("{mark}", "END")

    start = strExpand(start, g_dic)
    end = strExpand(end, g_dic)

    ss = configBlockStr(orig, start, end, block, insertAfter)

  if ss is not None and ss != orig:
    with open(path, "w") as fp:
      fp.write(ss)
      print('configBlock - update file', path)


def configAddStr(ss, marker, str, insertAfter):
  # regexp
  m = re.search(marker, ss)
  if m is not None:
    return None

  # insertAfter
  pt = len(ss)
  if insertAfter is not None:
    m = re.search(insertAfter, ss)
    if m is not None:
      pt = m.end()
      pt = skipEnter(ss, pt)

  # insert
  ss = ss[:pt] + marker + str + ss[pt:]
  return ss

# 이건 marker가 없으면 block을 추가하는 역할
# configBlock이 완전 대체할수 있다. 이건 추가된 내용을 수정 할수가 없다


def configAdd(path, marker, str, insertAfter):
  '''
  marker: ### TEST\n
  block: vv=1\n
  '''
  marker = strExpand(marker, g_dic)
  str = strExpand(str, g_dic)
  if insertAfter is not None:
    insertAfter = strExpand(insertAfter, g_dic)

  with open(path, "r") as fp:
    ss = fp.read(path)
    ss = configAddStr(ss, marker, str, insertAfter)

  if ss is not None:
    with open(path, "w") as fp:
      fp.write(ss)


def strEnsure(path, str):
  path = os.path.expanduser(path)
  path = strExpand(path, g_dic)
  with open(path, "rt") as fp:
    ss = fp.read()
    hr = ss.find(str)
    if hr != -1:
      return

  with open(path, "at") as fp:
    fp.write("\n"+str)


"""
def userNew(name, existOk, sshKey):
	'''
	needed sudo right
	'''
	if not existOk or runRet("id -u %s" % name) != 0:
		run("useradd %s -m -s /bin/bash" % (name))

	if sshKey:
		if not os.access("/home/%s/.ssh/id_rsa" % name, os.F_OK):
			run("sudo -u %s ssh-keygen -b 2048 -t rsa -f /home/%s/.ssh/id_rsa -N '' -q" % (name, name))
"""


def lineEndPos(ss, pt):
  '''
  return: 01234\n 이면 5위치를 돌려준다.
          만약없으면 마지막 문자 위치
  '''
  sz = len(ss)
  while pt < sz:
    if ss[pt] in "\r\n":
      return pt
    pt += 1

  return sz-1


def configLineStr(ss, regexp, line, append=False):
  m = re.search(regexp, ss, re.MULTILINE)
  if m is None:
    if append:
      if ss[-1] != '\n':
	      ss += '\n' + line
      else:
	      ss += line
      return ss

    return None

  start = m.start()
  end = lineEndPos(ss, start)

  ss = ss[:start] + line + ss[end:]
  return ss


def configLine(path, regexp, line, items=None, append=False):
  '''
  replace it to the [line] after finding [regexp]
  no action if there is no regexp
  '''
  path = os.path.expanduser(path)
  path = strExpand(path, g_dic)

  with open(path, "r") as fp:
    ss = fp.read()

  if items is not None:
    lst = items.splitlines()
    for item in lst:
      regexp2 = regexp.replace("{{item}}", item)
      line2 = line.replace("{{item}}", item)
      line2 = strExpand(line2, g_dic)
      s2 = configLineStr(ss, regexp2, line2, append)
      if s2 is None:
        print("can't find regexp[%s]" % (regexp2))
      else:
        ss = s2
  else:
    line2 = strExpand(line, g_dic)
    ss = configLineStr(ss, regexp, line2, append)
    if ss is None:
      print("can't find regexp[%s]" % (regexp2))

  if ss is not None:
    with open(path, "w") as fp:
      fp.write(ss)


def strExpand(ss, dic):
  '''
  convert {{target}} to the item in the dic
  '''
  while True:
    m = re.search(r"\{\{([\w_.]+)\}\}", ss)
    if m is None:
      ss = ss.replace('\{{', '{{')
      return ss

    name = m.group(1)
    lst = name.split(".")

    dic2 = dic
    for item in lst:
      if item in dic2:
        dic2 = dic2[item]
      else:
        print("strExpand: no variable[%s]" % name)
        dic2 = ""
        break

    # dic can be int
    ss = ss[:m.start()] + str(dic2) + ss[m.end():]


def main():
  if len(sys.argv) <= 2:
    raise Exception("godHelper.py runFile configPath")
  cmd = sys.argv[1]
  pp = sys.argv[2]

  if cmd == "runFile":
    with open(pp, "r") as fp:
      cfg = json.load(fp)
  elif cmd == "runStr":
    cfg = json.loads(pp)
  elif cmd == "runBin":
    # zip+base64
    pp = base64.b64decode(pp)
    ss = zlib.decompress(pp).decode()
    cfg = json.loads(ss)
  else:
    raise Exception("unknown command[%s]" % cmd)

  global g_dic
  g_dic = cfg["dic"]
  g_dic["hostname"] = platform.node()
  del cfg["dic"]

  func = cfg["cmd"]
  #print('godHelper - %s - %s' % (func, g_dic))
  del cfg["cmd"]
  if func == "configBlock":
    configBlock(**cfg)
  elif func == "configLine":
    configLine(**cfg)
  elif func == "strEnsure":
    strEnsure(**cfg)
  # elif func == "userNew":
  #	userNew(**cfg)
  else:
      raise Exception('unknow commad2[%s]' % func)


if __name__ == "__main__":
  try:
    main()
  except Exception:
    traceback.print_exc()
    sys.exit(1)
