from copy import deepcopy
import collections


# try:
#     collectionsAbc = collections.abc
# except AttributeError:
#     collectionsAbc = collections

collectionsAbc = getattr(collections, "abc", collections)


def dictGet(dic, pp, default):
    lst = pp.split(".")
    for item in lst:
        if item not in dic:
            return default

        dic = dic[item]

    return dic


def dictGetTest():
    dic = dict(a=1, b=dict(A=1, B=2))
    assert dictGet(dic, "", 99) == 99
    assert dictGet(dic, "a", 99) == 1
    assert dictGet(dic, "b.A", 99) == 1
    assert dictGet(dic, "b.C", 99) == 99


# dictGetTest()

# https://gist.github.com/angstwad/bf22d1822c38a92ec0a9
def dictMerge(dic, dic2):
    newDic = {}

    for k, v in dic.items():
        if k not in dic2:
            newDic[k] = deepcopy(v)

    for k, v in dic2.items():
        if k in dic and isinstance(dic[k], dict) and isinstance(dic2[k], collectionsAbc.Mapping):
            # newDic[k] = mergeDict(dic[k], dic2[k])
            newDic[k] = dictMerge(dic[k], dic2[k])
        else:
            newDic[k] = deepcopy(dic2[k])

    return newDic


def dictMerge2(dic, dic2):
    newDic = Dict2()

    if isinstance(dic, Dict2):
        dic = dic.dic

    if isinstance(dic2, Dict2):
        dic2 = dic2.dic

    for k, v in dic.items():
        if k not in dic2:
            newDic[k] = deepcopy(v)
    for k, v in dic2.items():
        if k in dic and isinstance(dic[k], (dict, Dict2)) and isinstance(dic2[k], (collectionsAbc.Mapping, Dict2)):
            newDic[k] = dictMerge2(dic[k], dic2[k])
        else:
            newDic[k] = deepcopy(dic2[k])

    return newDic


class Dict2:
    """
    dic["attr"] -> dic.attr
    dic.val = 1
    """

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
        return str(self.dic)  # __dict__)

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

    def fill(self, dic):
        if isinstance(dic, Dict2):
            # self.fill(dic.dic)
            # return
            dic = dic.dic

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


def dictMerge2Test():
    a = Dict2(dic={"a": 1, "d": {"a1": 1, "b1": 2}})
    b = Dict2(dic={"b": 1, "d": {"a1": 2, "c1": 3}})
    c = dictMerge2(a, b)
    assert c.a == 1
    assert c.b == 1
    assert c.d.a1 == 2
    assert c.d.b1 == 2
    assert c.d.c1 == 3


# dictMerge2Test()
