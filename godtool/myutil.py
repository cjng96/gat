
import queue
from threading import Thread
from copy import deepcopy
import collections
import json, inspect

import re
import os


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

class Dict2():
	'''
	dic["attr"] -> dic.attr
	dic.val = 1
	'''
	def __init__(self, dic=None):
		self.dic = dict()
		if dic is not None:
			self.fill(dic)

	def toJson(self):
		return self.dic

	def __getattr__(self, name):
		if "dic" in self.__dict__ and name in self.dic:
			return self.dic[name]
		return super().__getattribute__(name)

	def __setattr__(self, name, value):
		if name != "dic":
			if name in self.dic:
				self.dic[name] = value
		return super().__setattr__(name, value)

	def __repr__(self):
		return str(self.dic)#__dict__)

	# dict compatiable
	def __getitem__(self, key):
		return self.dic[self.__keytransform__(key)]
	def __setitem__(self, key, value):
		self.dic[self.__keytransform__(key)] = value
	def __delitem__(self, key):
		del self.dic[self.__keytransform__(key)]
	def __iter__(self):
		return iter(self.dic)
	def __len__(self):
		return len(self.dic)
	def __keytransform__(self, key):
		return key
	def __contains__(self, key):
		return key in self.dic

	#@staticmethod
	#def make(dic):
	#	dic2 = Dict2()
	#	dic2.fill(dic)
	#	return dic2

	def fill(self, dic):
		if isinstance(dic, Dict2):
			self.dic = deepcopy(dic)
			return
			
		for key, value in dic.items():
			tt = type(value)
			if tt == dict:
				self.dic[key] = Dict2(value)
			elif tt == list:
				for idx, vv in enumerate(value):
					if type(vv) == dict:
						value[idx] = Dict2(vv)
				self.dic[key] = value
			else:
				self.dic[key] = value
		
	def get(self, name, default=None):
		lst = name.split(".")
		dic = self.dic
		for item in lst:
			if item not in dic:
				return default
			dic = dic[item]

		return dic

	def add(self, name, value):
		if name in self.dic:
			print("%s is already defined. it will be overwritten." % name)
		self.dic[name] = value