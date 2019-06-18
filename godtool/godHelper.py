
import sys
import json
import traceback
import re
import os.path as pypath


def skipEnter(ss, pt):
	sz = len(ss)
	while pt < sz:
		if ss[pt] not in "\r\n":
			return pt

		pt += 1

	return sz

def configAssureStr(ss, marker, block, insertAfter):
	# marker
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
	ss = ss[:pt] + marker + block + ss[pt:]
	return ss

def configAssure(path, marker, block, insertAfter):
	'''
	marker: ### TEST\n
	block: vv=1\n
	'''
	with open(path, "r") as fp:
		ss = fp.read(path)
		ss = configAssureStr(ss, marker, block, insertAfter)

	if ss is not None:
		with open(path, "w") as fp:
			fp.write(ss)

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

	if cfg.cmd == "configAssure":
		configAssure(**cfg)


if __name__ == "__main__":
	try:
		main()
	except Exception:
		traceback.print_exc()
		