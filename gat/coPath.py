
import os


def cutpath(parent: str, pp: str) -> str:
  if parent[-1] != "/":
    parent += "/"

  return pp[len(parent):]

def path2folderList(pp: str) -> list[str]:
  dirs: list[str] = []
  while len(pp) >= 1:
    dirs.append(pp)
    pp, _  = os.path.split(pp)
    if pp == "/":
      break

  return dirs

def path2FolderListTest() -> None:
  print(path2folderList("/haha/a/test.txt"))
  print(path2folderList("haha/b/test.txt"))
  print(path2folderList("h/c/test.txt"))
