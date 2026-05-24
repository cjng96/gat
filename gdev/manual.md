# gdev Manual

## Purpose

`gdev` extracts reusable build-script behavior from project-local command files.
The package owns generic mechanics; each project owns only paths, command order, and naming rules.

## Minimal Project File

```python
from pathlib import Path
from gdev import CoverageCfg, GatDev


class gatDev(GatDev):
    pathCfg = GatDev.PathCfg(
        appPubspec="app/pubspec.yaml",
        appCoverageInfo="app/coverage/lcov.info",
        appApkPath="app/build/app/outputs/flutter-apk/app-release.apk",
        appApkRelPath="release/android",
        apkPrefix="easycoll",
    )
    coverageCfg = CoverageCfg(
        minLines=90.0,
        appIncludePrefix="lib/core/",
        appExcludePrefixes=("lib/core/frb/",),
    )

    def getToolCmd(self, cmd):
        match cmd:
            case "flutter":
                return "fvm flutter"
            case _:
                return super().getToolCmd(cmd)

    def cmdAndBuild(self):
        return self.doAndBundleBuild(
            app_dir=self.pathCfg.appDir,
            root_dir=self.pathCfg.root,
            target_platforms=("android-arm", "android-arm64", "android-x64"),
            signing_properties=Path.home() / ".gradle/upload.properties",
            bundletool_jar=Path.home() / "bin/bundletool.jar",
        )

    def cmdVerUp(self):
        return self.doVerUp(root_dir=self.pathCfg.root, app_pubspec=self.pathCfg.appPubspec)

    def cmdAndInstall(self):
        return self.doAndInstall()

    def cmdAndTest(self):
        return self.doAndTest(app_dir=self.pathCfg.appDir)


BUILD = gatDev()
```

## Command Order

The command order is the `cmdXxx()` method definition order in the project
subclass. A command is supported only when the project subclass directly
overrides its `cmdXxx()` method. Inherited base commands provide reusable
default behavior, but they are not exposed until the project class declares the
command.

The `cmdXxx()` method should only bind project configuration and call reusable
`doXxx(...)` logic with named parameters. For example:

```python
def cmdWebCov(self):
    self.doWebCov(web_dir=self.pathCfg.webDir, npm_args=("run", "test:coverage"))
```

For example, `cmdMacFfiRestore()` is exposed as `macFfiRestore`.

## Interactive Command Selection

When `gdev` runs in a TTY without a command argument, it opens a numbered command
selector.

- `Up`/`Down` or `k`/`j` moves the selected command.
- Number keys enter command numbers manually.
- `Space` on an empty input adds the currently selected command number followed
  by a space.
- `Space` immediately after manual number input adds only a separator space.
- If manual numbers are already entered and the selection is moved with
  `Up`/`Down` or `k`/`j`, `Space` adds the newly selected command number followed
  by a space.
- `Enter` runs the entered command sequence, preserving the entered order.

## Project Configuration

Prefer grouped config objects for settings shared by multiple tasks:

- `AndroidCfg`: Android defaults that are intentionally shared by multiple project tasks
- `DesktopCfg`: desktop defaults that are intentionally shared by multiple project tasks
- `SshCfg`: deploy host/user connection settings
- `CoverageCfg`: coverage threshold plus app/server coverage filters

`PathCfg.root` is inferred from the project `gat_dev.py` file by default. Set it
only when a build file intentionally uses a different project root.

Tool command names should be customized by overriding `getToolCmd(cmd)`, not by
storing tool names in class fields. The default implementation returns `cmd`
unchanged, and environment variables such as `FLUTTER_BIN` still take precedence
when present.

Legacy flat class fields such as `sshDeployHost` are still accepted for older
project files, but new project files should use grouped dataclasses only for
settings shared across tasks.

Task-only settings should stay in the project `cmdXxx()` method and be passed to
`doXxx(...)` as named parameters. For example, `macDeploy` signing identities,
package paths, and upload command should be passed from `cmdMacDeploy()` instead
of being stored in `DesktopCfg`.
Google Play package, track, OAuth redirect, credential file, and client secrets
package name is read from `AndroidCfg.googlePlayPackageName` by the default
`cmdAndDeploy()` implementation. Track, OAuth redirect, credential file, and
client secrets file values use the default deploy task values with environment
overrides. Custom deploy flows can still call `doAndDeploy(...)` directly from a
project-owned `cmdXxx()` method.

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

Projects that still have legacy `build.py` behavior can declare matching
`cmdXxx()` methods and map them to `GatDev` helpers such as `doAndBundleBuild()`,
`updateBuildInfo()`, `sqfliteFfiCommentOut()`, `doWinBuild()`, `doMacBuild()`,
`doIosBuild()`, and `doAndDeploy()` from project-owned `cmdXxx()` methods.

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
