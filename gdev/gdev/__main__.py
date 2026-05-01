import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Sequence


def loadProjectModule(project_file: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("project_gat_dev", project_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load project file: {project_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(argv: Sequence[str] | None = None) -> int:
    project_file = Path.cwd() / "gat_dev.py"
    if not project_file.exists():
        print("ERROR: gat_dev.py not found in current directory", file=sys.stderr)
        return 1

    try:
        module = loadProjectModule(project_file)
        build = getattr(module, "BUILD", None)
        if build is None or not hasattr(build, "main"):
            print("ERROR: gat_dev.py must define BUILD with main()", file=sys.stderr)
            return 1
        old_argv0 = sys.argv[0]
        sys.argv[0] = "gdev"
        try:
            return int(build.main(sys.argv[1:] if argv is None else argv))
        finally:
            sys.argv[0] = old_argv0
    except Exception as exc:
        print(f"ERROR: failed to run gat_dev.py: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
