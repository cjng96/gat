
from queue import Queue, Empty
from threading import Thread
from copy import deepcopy
import collections


# https://gist.github.com/angstwad/bf22d1822c38a92ec0a9
def mergeDict(dic, dic2):
	newDic = {}
	for k, v in dic.items():
		if k not in dic2:
			newDic[k] = deepcopy(v)

	for k, v in dic2.items():
		if (k in dic and isinstance(dic[k], dict) and isinstance(dic2[k], collections.Mapping)):
			newDic[k] = mergeDict(dic[k], dic2[k])
		else:
			newDic[k] = deepcopy(dic2[k])

	return newDic

def str2arg(ss):
	return ss.replace("\\", "\\\\").replace("\"", "\\\"").replace("$", "\\$")

class NonBlockingStreamReader:
	def __init__(self, stream):
		'''
		stream: the stream to read from.
	    Usually a process' stdout or stderr.
		'''
		self.stream = stream
		self.queue = Queue()

		def _populateQueue(stream, queue):
			'''
			Collect lines from 'stream' and put them in 'quque'.
			'''
			while True:
				line = stream.readline()
				queue.put(line)	# line can be None for broken stream
				if line is None:
					return

		self.thread = Thread(target=_populateQueue, args=(self.stream, self.queue))
		self.thread.daemon = True
		self.thread.start()

	def readline(self, timeout=None):
		try:
			return self.queue.get(block=timeout is not None, timeout=timeout)
		except Empty:
			return None


class UnexpectedEndOfStream(Exception):
	pass