
import sys
import json
import traceback
import os.path as pypath


def configAssure(path, marker, block, insertAfter):
	with open(path, "r") as fp:
		ss = fp.read(path)

		# insertAfter

		# marker

		# update

		# save
		

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
		