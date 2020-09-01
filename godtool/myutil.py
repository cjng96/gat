
import queue
from threading import Thread
from copy import deepcopy
import json, inspect

import re
import os

def str2arg(ss):
	'''
	기본적으로 ""로 감쌌다고 가정하고 랩핑한다.
	'''
	ss = ss.replace('\\', '\\\\')
	ss = ss.replace('"', '\\"')
	ss = ss.replace('$', '\\$')	#.replace('&', '\&')#.replace('%', '\%')
	#ss = ss.replace("!", "\!")	# echo 문자열 내에 있을때는 안해도 되네...
	ss = ss.replace('[^a-zA-Z]!', '\\!')	# a!는 변환하고 3!는 변환하지 말것
	ss = ss.replace('`', '\\`')	# bash -c "echo '`'" 이거 오류난다.
	return ss

def envExpand(ss):
	while True:
		m = re.search(r"\$\{\{([\w_]+)\}\}", ss)
		if m is None:
			return ss

		name = m.group(1)
		v = os.getenv(name, "")
		ss = ss[:m.start()] + str(v) + ss[m.end():]

def pathRemove(pp, parent):
  if parent[-1] != '/':
    parent += '/'
  
  if not pp.startswith(parent):
    return pp

  return pp[len(parent):]

def pathIsChild(pp, parent):
  if parent[-1] != '/':
    parent += '/'

  return pp.startswith(parent)

  
  

class NonBlockingStreamReader:
	def __init__(self, stream):
		'''
		stream: the stream to read from.
	    Usually a process' stdout or stderr.
		'''
		self.stream = stream
		self.queue = queue.Queue()

		def _populateQueue(stream, queue):
			'''
			Collect lines from 'stream' and put them in 'quque'.
			'''
			while True:
				line = stream.readline()
				queue.put(line)	# line can be "" for broken stream
				if line is b"":
					return

		self.thread = Thread(target=_populateQueue, args=(self.stream, self.queue))
		self.thread.daemon = True
		self.thread.start()

	def readline(self, timeout=None):
		'''
		return: None(empty), ""(exit the app)
		'''
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
