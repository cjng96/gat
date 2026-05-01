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
from typing import Any

g_dic: dict[str, Any] = {}


def run(cmd: str) -> bytes:
    return subprocess.check_output(cmd, shell=True)


def runRet(cmd: str) -> int:
    try:
        run(cmd)
        return 0
    except subprocess.CalledProcessError as e:
        return e.returncode


def skipEnter(ss: str, pt: int) -> int:
    sz = len(ss)
    while pt < sz:
        if ss[pt] not in "\r\n":
            return pt

        pt += 1
    return sz


def skipEnterBackward(ss: str, pt: int) -> int:
    while pt >= 0:
        if pt == 0 or ss[pt - 1] not in "\r\n":
            return pt
        pt -= 1

    return 0


def configBlockStr(ss: str, start: str, end: str, block: str, insertAfter: str | None) -> str:
    # marker
    start = f"\n{start}"
    end = f"{end}\n"
    ctx = f"{start}\n{block}\n{end}"
    if ctx in ss:
        return ss

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
        pt2 = None
        if insertAfter is not None:
            m = re.search(insertAfter, ss)
            if m is not None:
                pt = m.end()
                pt2 = skipEnter(ss, pt)
        else:
            # 마지막 \n은 무시
            pt = skipEnterBackward(ss, pt)
            ss = ss[:pt]

        if pt2 is None:
            pt2 = pt

    # insert
    ss = ss[:pt] + ctx + ss[pt2:]
    return ss


def configBlock(path: str, marker: str, block: str, insertAfter: str | None) -> None:
    """
    marker: ### {mark} TEST
    block: vv=1
    """
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
            print("configBlock - update file", path)


def configAddStr(ss: str, marker: str, str: str, insertAfter: str | None) -> str | None:
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


def configAdd(path: str, marker: str, str: str, insertAfter: str | None) -> None:
    """
    marker: ### TEST\n
    block: vv=1\n
    """
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


def strEnsure(path: str, str: str) -> None:
    path = os.path.expanduser(path)
    path = strExpand(path, g_dic)
    with open(path, "rt") as fp:
        ss = fp.read()
        hr = ss.find(str)
        if hr != -1:
            return

    with open(path, "at") as fp:
        fp.write("\n" + str)


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


def lineEndPos(ss: str, pt: int) -> int:
    """
    return: 01234\n 이면 5위치를 돌려준다.
            만약없으면 라인 길이
    """
    sz = len(ss)
    while pt < sz:
        if ss[pt] in "\r\n":
            return pt
        pt += 1

    return sz


# append: True면 추가 - deprecated use appendAfterRe="" instead
# appendAfterRe: ""이면 마지막에 덧붙이기
# ignore: appendAfterRe를 안쓰는데 패턴을 못찾으면 원본을 반환
def configLineStr(
    ss: str,
    regexp: str,
    line: str,
    append: bool = False,
    appendAfterRe: str | None = None,
    ignore: bool = False,
) -> str | None:
    m = re.search(regexp, ss, re.MULTILINE)
    if m is None:
        if append or appendAfterRe is not None:
            if appendAfterRe != "":
                m = re.search(appendAfterRe, ss, re.MULTILINE)
                if m is None:
                    raise Exception(f"can't find appendAfterRe[{appendAfterRe}]")

                start = lineEndPos(ss, m.start())
                ss = ss[:start] + "\n" + line + ss[start:]
                return ss

            else:
                if ss[-1] != "\n":
                    ss += "\n" + line
                else:
                    ss += line
            return ss

        if ignore:
            return ss

        return None

    start = m.start()
    end = lineEndPos(ss, start + 1)
    # print(f"\n\nconfigLine -- {start}-{end}, [\n{ss[start:]}\n]")

    ss = ss[:start] + line + ss[end:]
    return ss


def configLine(
    path: str,
    regexp: str,
    line: str,
    items: str | None = None,
    append: bool = False,
    appendAfterRe: str | None = None,
    ignore: bool = False,
) -> None:
    """
    replace it to the [line] after finding [regexp]
    ignore: no action if there is no regexp
    """
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
            s2 = configLineStr(
                ss,
                regexp=regexp2,
                line=line2,
                append=append,
                appendAfterRe=appendAfterRe,
                ignore=ignore,
            )
            if s2 is None:
                # print("can't find regexp[%s]" % (regexp2))
                raise Exception("can't find regexp[%s]" % (regexp2))

    else:
        line2 = strExpand(line, g_dic)
        s2 = configLineStr(
            ss,
            regexp=regexp,
            line=line2,
            append=append,
            appendAfterRe=appendAfterRe,
            ignore=ignore,
        )
        if s2 is None:
            # print("can't find regexp[%s]" % (regexp))
            raise Exception("can't find regexp[%s]" % (regexp))

    if s2 is not None and s2 != ss:
        with open(path, "w") as fp:
            fp.write(s2)


def strExpand(ss: str, dic: dict[str, Any]) -> str:
    """
    convert {{target}} to the item in the dic
    """
    while True:
        m = re.search(r"\{\{([\w_.]+)\}\}", ss)
        if m is None:
            ss = ss.replace("\\{{", "{{")
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
        ss = ss[: m.start()] + str(dic2) + ss[m.end() :]


def main() -> None:
    if len(sys.argv) <= 2:
        raise Exception("gatHelper.py runFile configPath")
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
    # print('gatHelper - %s - %s' % (func, g_dic))
    del cfg["cmd"]
    if func == "configBlock":
        configBlock(**cfg)
    elif func == "configLine":
        configLine(**cfg)
    elif func == "strEnsure":
        strEnsure(**cfg)
    # elif func == "userNew":
    # 	userNew(**cfg)
    else:
        raise Exception("unknow commad2[%s]" % func)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
