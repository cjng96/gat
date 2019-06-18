
import unittest
import sys
sys.path.append("..")

from godtool import godHelper

class HelperTest(unittest.TestCase):
	def test_skipEnter(self):
		"""
		Test that numbers between 0 and 5 are all even.
		"""
		self.assertEqual(godHelper.skipEnter("0123\n\n6", 4), 6)
		self.assertEqual(godHelper.skipEnter("0123\n\n6", 0), 0)
		self.assertEqual(godHelper.skipEnter("0123\n\n", 4), 6)

	def test_configAssureStr(self):
		ss = '''
test=1
'''
		s1 = godHelper.configAssureStr(ss, "### MARKER\n", "h1=99\nh2=1\n", None)
		self.assertEqual(s1, ss + "### MARKER\nh1=99\nh2=1\n")

		ss = '''
test=1
### MARKER
h1=1
'''
		s1 = godHelper.configAssureStr(ss, "### MARKER\n", "h1=99\nh2=1\n", None)
		self.assertEqual(s1, None)

		ss = '''
man=3
test=1
'''
		s1 = godHelper.configAssureStr(ss, "### MARKER\n", "h1=99\nh2=99\n", "man=3")
		self.assertEqual(s1, "\nman=3\n### MARKER\nh1=99\nh2=99\ntest=1\n")



