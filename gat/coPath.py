
import os


def cutpath(parent, pp):
  if parent[-1] != "/":
    parent += "/"		 

  return pp[len(parent):]	

def path2folderList(pp):
  dirs = []
  while len(pp) >= 1:
    dirs.append(pp)
    pp, _  = os.path.split(pp)
    if pp == "/":
      break

  return dirs

def path2FolderListTest():
  print(path2folderList("/haha/a/test.txt"))
  print(path2folderList("haha/b/test.txt"))
  print(path2folderList("h/c/test.txt"))