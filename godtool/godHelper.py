
import sys
import json
import traceback
import os
import re
import platform
import os.path as pypath

g_dic = {}

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
	ss = ss[:pt] + "\n" + start + "\n" + block + "\n" + end + "\n" + ss[pt2:]
	return ss

def configBlock(path, marker, block, insertAfter):
	'''
	marker: ### {mark} TEST\n
	block: vv=1\n
	'''
	block = strExpand(block, g_dic)
	if insertAfter is not None:
		insertAfter = strExpand(insertAfter, g_dic)

	path = os.path.expanduser(path)
	with open(path, "r") as fp:
		ss = fp.read()
		start = marker.replace("{mark}", "BEGIN")
		end = marker.replace("{mark}", "END")

		start = strExpand(start, g_dic)
		end = strExpand(end, g_dic)

		ss = configBlockStr(ss, start, end, block, insertAfter)

	if ss is not None:
		with open(path, "w") as fp:
			fp.write(ss)

# 이건 marker가 없으면 block을 추가하는 역할
# configBlock이 완전 대체할수 있다.
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

def configLineStr(ss, regexp, line):
	m = re.search(regexp, ss, re.MULTILINE)
	if m is None:
		return None

	start = m.start()
	end = lineEndPos(ss, start)

	ss = ss[:start] + line + ss[end:]
	return ss

def configLine(path, regexp, line, items=None):
	path = os.path.expanduser(path)
	with open(path, "r") as fp:
		ss = fp.read()

		if items is not None:
			lst = items.splitlines()
			for item in lst:
				regexp2 = regexp.replace("{{item}}", item)
				line2 = line.replace("{{item}}", item)
				s2 = configLineStr(ss, regexp2, line2)
				if s2 is None:
					print("can't find regexp[%s]" % (regexp2))
				else:
					ss = s2
		else:
			ss = configLineStr(ss, regexp, line)

	if ss is not None:
		with open(path, "w") as fp:
			fp.write(ss)

def strExpand(ss, dic):
	while True:
		m = re.search(r"\{\{([\w.]+)\}\}", ss)
		if m is None:
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
	else:
		raise Exception("unknown command[%s]" % cmd)

	global g_dic
	g_dic = cfg["dic"]
	g_dic["hostname"] = platform.node()
	del cfg["dic"]

	func = cfg["cmd"]
	del cfg["cmd"]
	if func == "configBlock":
		configBlock(**cfg)
	elif func == "configLine":
		configLine(**cfg)


if __name__ == "__main__":
	try:
		main()
	except Exception:
		traceback.print_exc()
		sys.exit(1)
		