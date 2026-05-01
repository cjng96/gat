# gdev Manual

## Purpose

`gdev` extracts reusable build-script behavior from project-local command files.
The package owns generic mechanics; each project owns only paths, command order, and naming rules.

## Minimal Project File

```python
from pathlib import Path
from gdev import GatDev


Cmds = GatDev.Cmds


class gatDev(GatDev):
    pathCfg = GatDev.PathCfg(
        root=Path(__file__).resolve().parent,
        appPubspec="app/pubspec.yaml",
        appCoverageInfo="app/coverage/lcov.info",
        appApkPath="app/build/app/outputs/flutter-apk/app-release.apk",
        appApkRelPath="release/android",
        apkPrefix="easycoll",
    )
    serUpArgs = ("prod", "run")
    cmdList = [
        Cmds.andBuild,
        Cmds.verUp,
        Cmds.serUp,
        Cmds.andInstall,
        Cmds.andDeploy,
        Cmds.andTest,
        Cmds.serTest,
        Cmds.webTest,
        Cmds.appCov,
        Cmds.serCov,
        Cmds.webCov,
        Cmds.allCov,
    ]


BUILD = gatDev()
```

## Command Order

The default command order is:

1. `andBuild`
2. `verUp`
3. `serUp`
4. `andInstall`
5. `andDeploy`
6. `andTest`
7. `serTest`
8. `webTest`
9. `appCov`
10. `serCov`
11. `webCov`
12. `allCov`

Projects can override `cmdList` with `GatDev.Cmds` constants. If a project adds a new command name, it must
also override `commandMap()` and return a callable for that command. `gdev`
validates this before execution and fails with `BuildError` when a listed command
has no implementation.

## Launcher

`~/bin/gdev` runs the current working directory's `gat_dev.py`:

```bash
#!/bin/bash
P=~/.gat/repo
PYTHONPATH=$P/gdev uv run --project $P -m gdev "$@"
```

## Environment Overrides

Tool commands can be overridden with environment variables:

- `FLUTTER_BIN`
- `CARGO_BIN`
- `NPM_BIN`
- `ADB_BIN`
- `GAT_BIN`

Internally these commands are built through `ToolCmd` static methods such as
`ToolCmd.flutter("test")` and `ToolCmd.adb("devices", "-l")`.

The values are shell-split, so wrappers such as `uv run flutter` are supported.

## Version Rule

`bumpFlutterVersion()` increments patch version by one and computes Android build number as:

```text
major * 10000 + minor * 100 + patch
```

Example: `1.2.3+77` becomes `1.2.4+10204`.

## Testing

Run package tests:

```bash
cd /Users/cjng96/iner/gat
PYTHONPATH=/Users/cjng96/iner/gat/gdev python3 -m unittest discover -s /Users/cjng96/iner/gat/gdev/tests
```

Project command files should also test their subclass configuration.
