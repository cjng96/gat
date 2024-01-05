import os
import unittest
import sys

sys.path.append("..")

from gat import gatHelper as h
from gat import myutil


class HelperTest(unittest.TestCase):
    def test_skipEnter(self):
        """ """
        self.assertEqual(h.skipEnter("0123\n\n6", 4), 6)
        self.assertEqual(h.skipEnter("0123\n\n6", 0), 0)
        self.assertEqual(h.skipEnter("0123\n\n", 4), 6)

    def test_envExpand(self):
        os.environ["TEST1"] = "1234"
        os.environ["TEST_2"] = "555"
        ss = "this is my ${TEST1}. ${TEST_2}."
        s1 = myutil.envExpand(ss)
        self.assertEqual(s1, "this is my 1234. 555.")

    def test_configAddStr(self):
        ss = """\ntest=1\n"""
        s1 = h.configAddStr(ss, "### MARKER\n", "h1=99\nh2=1\n", None)
        self.assertEqual(s1, ss + "### MARKER\nh1=99\nh2=1\n")

        ss = """\ntest=1\n### MARKER\nh1=1\n"""
        s1 = h.configAddStr(ss, "### MARKER\n", "h1=99\nh2=1\n", None)
        self.assertEqual(s1, None)

        ss = """\nman=3\ntest=1\n"""
        s1 = h.configAddStr(ss, "### MARKER\n", "h1=99\nh2=99\n", "man=3")
        self.assertEqual(s1, "\nman=3\n### MARKER\nh1=99\nh2=99\ntest=1\n")

    def test_configBlockStr(self):
        ss = """\ntest=1\n"""
        s1 = h.configBlockStr(ss, "### BEGIN", "### END", "h1=99\nh2=1", None)
        self.assertEqual(s1, "\ntest=1\n### BEGIN\nh1=99\nh2=1\n### END\n")

        ss = """\ntest=1\n### BEGIN\nh1=1\n### END\nend"""
        s1 = h.configBlockStr(ss, "### BEGIN", "### END", "h1=9\nh2=9", None)
        self.assertEqual(s1, "\ntest=1\n### BEGIN\nh1=9\nh2=9\n### END\nend")

        ss = """\nman=3\ntest=1\n"""
        s1 = h.configBlockStr(ss, "### BEGIN", "### END", "h1=1\nh2=2", "man=3")
        self.assertEqual(s1, "\nman=3\n### BEGIN\nh1=1\nh2=2\n### END\ntest=1\n")

    def test_strExpand(self):
        dic = dict(name="felix", server=dict(t=1, n="haha"))
        ss = "haha\n{{name}} {{tt}}is me\n"
        s1 = h.strExpand(ss, dic)
        self.assertEqual(s1, "haha\nfelix is me\n")

        ss = "test\n{{server.t}}-{{server.n}}end\n"
        self.assertEqual(h.strExpand(ss, dic), "test\n1-hahaend\n")

    def test_lineEndPos(self):
        self.assertEqual(h.lineEndPos("01234\n678", 2), 5)
        self.assertEqual(h.lineEndPos("01234\r\n789", 2), 5)
        self.assertEqual(h.lineEndPos("01234\r\n789", 8), 9)
