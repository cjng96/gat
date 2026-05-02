import argparse
import curses
import datetime
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from .errors import BuildError
from .gatDevBase import AndroidCfg, DesktopCfg, GatDevBase, SshCfg


@dataclass(frozen=True)
class AppVersion:
    major: int
    minor: int
    patch: int
    build: int

    @property
    def name(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def full(self) -> str:
        return f"{self.name}+{self.build}"


@dataclass(frozen=True)
class AndroidDevice:
    serial: str
    status: str
    description: str

    @property
    def label(self) -> str:
        return f"{self.serial}  {self.description}".rstrip()


class ToolCmd:
    @staticmethod
    def tool(env_name: str, default: str) -> list[str]:
        return shlex.split(os.environ.get(env_name, default))

    @staticmethod
    def flutter(*args: str) -> list[str]:
        return ToolCmd.tool("FLUTTER_BIN", "flutter") + list(args)

    @staticmethod
    def cargo(*args: str) -> list[str]:
        return ToolCmd.tool("CARGO_BIN", "cargo") + list(args)

    @staticmethod
    def npm(*args: str) -> list[str]:
        return ToolCmd.tool("NPM_BIN", "npm") + list(args)

    @staticmethod
    def adb(*args: str) -> list[str]:
        return ToolCmd.tool("ADB_BIN", "adb") + list(args)

    @staticmethod
    def gat(*args: str) -> list[str]:
        return ToolCmd.tool("GAT_BIN", "gat") + list(args)


def run(cmd: Sequence[str], *, cwd: Path) -> None:
    print(f"\n$ {' '.join(shlex.quote(part) for part in cmd)}")
    subprocess.run(list(cmd), cwd=cwd, check=True)


def capture(cmd: Sequence[str], *, cwd: Path) -> str:
    return subprocess.check_output(list(cmd), cwd=cwd, text=True).strip()


def parseFlutterVersion(pubspec_text: str) -> AppVersion:
    match = re.search(
        r"^version:[^\S\r\n]*(\d+)\.(\d+)\.(\d+)\+(\d+)[^\S\r\n]*$",
        pubspec_text,
        flags=re.MULTILINE,
    )
    if match is None:
        raise BuildError("pubspec version line was not found")
    return AppVersion(*(int(group) for group in match.groups()))


def androidVersionCode(version: AppVersion) -> int:
    return version.major * 10000 + version.minor * 100 + version.patch


def bumpFlutterVersion(version: AppVersion) -> AppVersion:
    next_version = AppVersion(
        major=version.major,
        minor=version.minor,
        patch=version.patch + 1,
        build=0,
    )
    return AppVersion(
        major=next_version.major,
        minor=next_version.minor,
        patch=next_version.patch,
        build=androidVersionCode(next_version),
    )


def replacePubspecVersion(pubspec_text: str, version: AppVersion) -> str:
    new_text, count = re.subn(
        r"^version:[^\S\r\n]*\d+\.\d+\.\d+\+\d+[^\S\r\n]*$",
        f"version: {version.full}",
        pubspec_text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise BuildError("failed to replace pubspec version line")
    return new_text


def parseAdbDevices(adb_devices_output: str) -> list[AndroidDevice]:
    devices: list[AndroidDevice] = []
    for raw_line in adb_devices_output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices"):
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        serial, status = parts[0], parts[1]
        if status != "device":
            continue

        devices.append(
            AndroidDevice(
                serial=serial,
                status=status,
                description=" ".join(parts[2:]),
            )
        )
    return devices


def selectTui(title: str, help_text: str, labels: Sequence[str]) -> int | None:
    if not labels:
        raise BuildError("no selectable items were provided")

    def menu(stdscr: curses.window) -> int | None:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        stdscr.keypad(True)
        selected = 0

        while True:
            stdscr.erase()
            height, width = stdscr.getmaxyx()
            stdscr.addnstr(0, 0, title, max(0, width - 1), curses.A_BOLD)
            if height > 1:
                stdscr.addnstr(1, 0, help_text, max(0, width - 1))

            for index, label in enumerate(labels):
                row = index + 3
                if row >= height:
                    break
                prefix = "> " if index == selected else "  "
                attr = curses.A_REVERSE if index == selected else curses.A_NORMAL
                stdscr.addnstr(row, 0, f"{prefix}{label}", max(0, width - 1), attr)

            key = stdscr.getch()
            if key == 27:
                return None
            if key in (curses.KEY_ENTER, 10, 13):
                return selected
            if key in (curses.KEY_UP, ord("k")):
                selected = (selected - 1) % len(labels)
            elif key in (curses.KEY_DOWN, ord("j")):
                selected = (selected + 1) % len(labels)

    return curses.wrapper(menu)


def parseLcovLineCoverage(lcov_text: str) -> tuple[int, int, float]:
    covered = 0
    total = 0
    for line in lcov_text.splitlines():
        if line.startswith("LH:"):
            covered += int(line[3:])
        elif line.startswith("LF:"):
            total += int(line[3:])
    if total == 0:
        raise BuildError("coverage line count is zero")
    return covered, total, covered / total * 100


def readPropertiesFile(path: Path) -> dict[str, str]:
    properties: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            key, separator, value = line.partition(":")
        if separator:
            properties[key.strip()] = value.strip()
    return properties


def fileSha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def appendSelectedCommandNumber(input_text: str, selected_index: int) -> str:
    prefix = input_text.rstrip()
    number = str(selected_index + 1)
    return number if not prefix else f"{prefix} {number}"


def commandInputAfterSpace(
    input_text: str,
    selected_index: int,
    *,
    selection_moved_after_input: bool = False,
) -> str:
    if input_text.strip() and not selection_moved_after_input:
        return f"{input_text} "
    return f"{appendSelectedCommandNumber(input_text, selected_index)} "


class GatDev(GatDevBase):
    def __init__(self) -> None:
        self.pathCfg = self.pathCfg.resolve(self.inferRoot())
        self.androidCfg = self.resolveAndroidCfg()
        self.desktopCfg = self.resolveDesktopCfg()
        self.sshCfg = self.resolveSshCfg()

    def inferRoot(self) -> Path:
        module = sys.modules.get(type(self).__module__)
        module_file = getattr(module, "__file__", None)
        if module_file:
            return Path(module_file).resolve().parent
        return Path.cwd().resolve()

    def resolveAndroidCfg(self) -> AndroidCfg:
        cfg = type(self).androidCfg
        return AndroidCfg(
            driveTarget=self.androidDriveTarget if self.androidDriveTarget != "test_driver/and.dart" else cfg.driveTarget,
            bundleTargetPlatforms=(
                self.androidBundleTargetPlatforms
                if self.androidBundleTargetPlatforms != ("android-arm", "android-arm64", "android-x64")
                else cfg.bundleTargetPlatforms
            ),
            signingProperties=self.androidSigningProperties if self.androidSigningProperties is not None else cfg.signingProperties,
            bundletoolJar=self.bundletoolJar if self.bundletoolJar is not None else cfg.bundletoolJar,
        )

    def resolveDesktopCfg(self) -> DesktopCfg:
        cfg = type(self).desktopCfg
        return DesktopCfg(
            winDriveTarget=self.winDriveTarget if self.winDriveTarget != "test_driver/win.dart" else cfg.winDriveTarget,
            macDriveTarget=self.macDriveTarget if self.macDriveTarget != "test_driver/mac.dart" else cfg.macDriveTarget,
            ffiCommentFiles=self.ffiCommentFiles or cfg.ffiCommentFiles,
            ffiLockfile=self.ffiLockfile if self.ffiLockfile is not None else cfg.ffiLockfile,
            macPreBuildCommands=self.macPreBuildCommands or cfg.macPreBuildCommands,
            macConfigOnly=self.macConfigOnly if self.macConfigOnly is not True else cfg.macConfigOnly,
            winReleaseSource=self.winReleaseSource if self.winReleaseSource != "app/build/windows/x64/runner/Release" else cfg.winReleaseSource,
            winExeName=self.winExeName if self.winExeName is not None else cfg.winExeName,
            winExtraFiles=self.winExtraFiles or cfg.winExtraFiles,
            winNsiCommand=self.winNsiCommand or cfg.winNsiCommand,
        )

    def resolveSshCfg(self) -> SshCfg:
        cfg = type(self).sshCfg
        return SshCfg(
            host=self.sshDeployHost if self.sshDeployHost is not None else cfg.host,
            port=self.sshDeployPort if self.sshDeployPort != 22 else cfg.port,
            user=self.sshDeployUser if self.sshDeployUser is not None else cfg.user,
        )

    def run(self, cmd: Sequence[str], *, cwd: Path | None = None) -> None:
        run(cmd, cwd=cwd or self.pathCfg.root)

    def runShell(self, cmd: str, *, cwd: Path | None = None) -> None:
        print(f"\n$ {cmd}")
        subprocess.check_call(cmd, cwd=cwd or self.pathCfg.root, shell=True)

    def capture(self, cmd: Sequence[str], *, cwd: Path | None = None) -> str:
        return capture(cmd, cwd=cwd or self.pathCfg.root)

    def resolveProjectPath(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.pathCfg.root / path

    def getToolCmd(self, cmd: str) -> str:
        return cmd

    def requiredTaskSetting(self, name: str) -> Any:
        value = getattr(self, name, None)
        if value is None or value == "" or value == ():
            raise BuildError(f"{name} is not configured")
        return value

    def toolCmd(self, cmd: str, *args: str) -> list[str]:
        return ToolCmd.tool(f"{cmd.upper()}_BIN", self.getToolCmd(cmd)) + list(args)

    def flutterCmd(self, *args: str) -> list[str]:
        return self.toolCmd("flutter", *args)

    def cargoCmd(self, *args: str) -> list[str]:
        return self.toolCmd("cargo", *args)

    def npmCmd(self, *args: str) -> list[str]:
        return self.toolCmd("npm", *args)

    def adbCmd(self, *args: str) -> list[str]:
        return self.toolCmd("adb", *args)

    def gatCmd(self, *args: str) -> list[str]:
        return self.toolCmd("gat", *args)

    def emulatorCmd(self, *args: str) -> list[str]:
        return self.toolCmd("emulator", *args)

    def javaCmd(self, *args: str) -> list[str]:
        return self.toolCmd("java", *args)

    def commandMethodName(self, command: str) -> str:
        return f"cmd{command[:1].upper()}{command[1:]}"

    def commandNameFromMethodName(self, method_name: str) -> str | None:
        if not method_name.startswith("cmd") or len(method_name) <= 3:
            return None
        command = method_name[3:]
        return f"{command[:1].lower()}{command[1:]}"

    def hasTask(self, command: str) -> bool:
        method_name = self.commandMethodName(command)
        method = type(self).__dict__.get(method_name)
        base_method = getattr(GatDevBase, method_name, None)
        return callable(method) and method is not base_method

    def declaredCmdList(self) -> list[str]:
        commands: list[str] = []
        for method_name, method in type(self).__dict__.items():
            if not callable(method):
                continue
            command = self.commandNameFromMethodName(method_name)
            if command and command not in commands and self.hasTask(command):
                commands.append(command)
        return commands

    def availableCmdList(self) -> list[str]:
        return self.declaredCmdList()

    def requireSupportedCommands(self) -> list[str]:
        commands = self.availableCmdList()
        if not commands:
            raise BuildError("no supported gdev commands are configured")
        return commands

    def unsupportedTask(self, command: str) -> None:
        raise BuildError(f"{command} task must be implemented by project gat_dev.py")

    def parseCommandSequence(self, input_text: str, commands: Sequence[str] | None = None) -> list[str]:
        command_list = list(commands or self.requireSupportedCommands())
        tokens = [token for token in re.split(r"[\s,]+", input_text.strip()) if token]
        if not tokens:
            raise BuildError("no command numbers were entered")

        commands: list[str] = []
        for token in tokens:
            if not token.isdecimal():
                raise BuildError(f"invalid command number: {token}")
            number = int(token)
            if number < 1 or number > len(command_list):
                raise BuildError(f"command number is out of range: {number}")
            commands.append(command_list[number - 1])
        return commands

    def commandSequenceFromInput(
        self,
        input_text: str,
        selected_index: int,
        commands: Sequence[str] | None = None,
    ) -> list[str]:
        command_list = list(commands or self.requireSupportedCommands())
        if not input_text.strip():
            return [command_list[selected_index]]
        return self.parseCommandSequence(input_text, command_list)

    def selectCommandSequenceTui(self) -> list[str] | None:
        commands = self.requireSupportedCommands()

        def menu(stdscr: curses.window) -> list[str] | None:
            try:
                curses.curs_set(1)
            except curses.error:
                pass
            stdscr.keypad(True)
            input_text = ""
            message = ""
            selected = 0
            selection_moved_after_input = False

            while True:
                stdscr.erase()
                height, width = stdscr.getmaxyx()
                stdscr.addnstr(0, 0, "Select build commands", max(0, width - 1), curses.A_BOLD)
                if height > 1:
                    help_text = "Space: add selected  Enter: run  Up/Down: move  Esc: cancel"
                    stdscr.addnstr(1, 0, help_text, max(0, width - 1))

                for index, command in enumerate(commands):
                    row = index + 3
                    if row >= height - 3:
                        break
                    prefix = "> " if index == selected else "  "
                    attr = curses.A_REVERSE if index == selected else curses.A_NORMAL
                    stdscr.addnstr(row, 0, f"{prefix}{index + 1:2}. {command}", max(0, width - 1), attr)

                input_row = max(0, height - 2)
                message_row = max(0, height - 1)
                stdscr.addnstr(input_row, 0, f"> {input_text}", max(0, width - 1))
                if message:
                    stdscr.addnstr(message_row, 0, message, max(0, width - 1))
                stdscr.move(input_row, min(width - 1, len(input_text) + 2))

                key = stdscr.getch()
                message = ""
                if key == 27:
                    return None
                if key in (curses.KEY_ENTER, 10, 13):
                    try:
                        return self.commandSequenceFromInput(input_text, selected, commands)
                    except BuildError as exc:
                        message = str(exc)
                        continue
                if key in (curses.KEY_UP, ord("k")):
                    selected = (selected - 1) % len(commands)
                    selection_moved_after_input = bool(input_text.strip())
                    continue
                if key in (curses.KEY_DOWN, ord("j")):
                    selected = (selected + 1) % len(commands)
                    selection_moved_after_input = bool(input_text.strip())
                    continue
                if key in (curses.KEY_BACKSPACE, 8, 127):
                    input_text = input_text[:-1]
                    selection_moved_after_input = False
                    continue
                if key == ord(" "):
                    input_text = commandInputAfterSpace(
                        input_text,
                        selected,
                        selection_moved_after_input=selection_moved_after_input,
                    )
                    selection_moved_after_input = False
                    continue
                if key == ord(",") or ord("0") <= key <= ord("9"):
                    input_text += chr(key)
                    selection_moved_after_input = False

        return curses.wrapper(menu)

    def readAppVersion(self) -> AppVersion:
        return parseFlutterVersion(self.pathCfg.appPubspec.read_text(encoding="utf-8"))

    def writeAppVersion(self, version: AppVersion) -> None:
        text = self.pathCfg.appPubspec.read_text(encoding="utf-8")
        self.pathCfg.appPubspec.write_text(replacePubspecVersion(text, version), encoding="utf-8")

    def apkFileName(self, version: AppVersion) -> str:
        return f"{self.pathCfg.apkPrefix}-{version.full}.apk"

    def updateBuildInfo(self) -> None:
        if self.pathCfg.appBuildInfo is None:
            raise BuildError("appBuildInfo path is not configured")
        version = self.readAppVersion()
        build_time = datetime.datetime.now().strftime(self.buildInfoDateFormat)
        self.pathCfg.appBuildInfo.parent.mkdir(parents=True, exist_ok=True)
        self.pathCfg.appBuildInfo.write_text(
            f"// 00 will be 0\nfinal g_version = '{version.name}';\nfinal g_buildDate = '{build_time}';",
            encoding="utf-8",
        )

    def maybeUpdateBuildInfo(self) -> None:
        if self.writeBuildInfoBeforeBuild and self.pathCfg.appBuildInfo is not None:
            self.updateBuildInfo()

    def readAndroidSigningProperties(self, *, signing_properties: str | Path | None) -> dict[str, str]:
        if signing_properties is None:
            raise BuildError("androidSigningProperties path is not configured")
        path = self.resolveProjectPath(signing_properties)
        if not path.exists():
            raise BuildError(f"android signing properties file was not found: {path}")
        return readPropertiesFile(path)

    def bundletoolBuildApksCommand(
        self,
        *,
        signing_properties: str | Path | None,
        bundletool_jar: str | Path | None,
        app_bundle_path: Path,
        app_apks_path: Path,
    ) -> list[str]:
        if bundletool_jar is None:
            raise BuildError("bundletoolJar path is not configured")
        props = self.readAndroidSigningProperties(signing_properties=signing_properties)
        required = ["storeFile", "storePassword", "keyAlias", "keyPassword"]
        missing = [key for key in required if not props.get(key)]
        if missing:
            raise BuildError(f"android signing properties missing key(s): {', '.join(missing)}")
        return self.javaCmd(
            "-jar",
            str(self.resolveProjectPath(bundletool_jar)),
            "build-apks",
            "--mode=universal",
            "--bundle",
            str(app_bundle_path),
            "--output",
            str(app_apks_path),
            "--overwrite",
            f"--ks={props['storeFile']}",
            f"--ks-pass=pass:{props['storePassword']}",
            f"--ks-key-alias={props['keyAlias']}",
            f"--key-pass=pass:{props['keyPassword']}",
        )

    def buildAndroidAppBundle(self, *, app_dir: Path, target_platforms: Sequence[str]) -> None:
        platforms = ",".join(target_platforms)
        self.run(
            self.flutterCmd("build", "appbundle", "--target-platform", platforms),
            cwd=app_dir,
        )

    def extractUniversalApk(self) -> Path:
        if not self.pathCfg.appApksPath.exists():
            raise BuildError(f"APKS file was not found: {self.pathCfg.appApksPath}")
        if self.pathCfg.appUniversalApkPath.exists():
            self.pathCfg.appUniversalApkPath.unlink()
        with zipfile.ZipFile(self.pathCfg.appApksPath) as apks:
            apks.extract("universal.apk", self.pathCfg.appUniversalApkPath.parent)
        extracted = self.pathCfg.appUniversalApkPath.parent / "universal.apk"
        if extracted != self.pathCfg.appUniversalApkPath:
            shutil.move(str(extracted), self.pathCfg.appUniversalApkPath)
        return self.pathCfg.appUniversalApkPath

    def copyAndroidUniversalApk(self, version: AppVersion, apk_path: Path) -> Path:
        if not apk_path.exists():
            raise BuildError(f"universal APK was not found: {apk_path}")
        self.pathCfg.appApkRelPath.mkdir(parents=True, exist_ok=True)
        versioned = self.pathCfg.appApkRelPath / self.apkFileName(version)
        latest = self.pathCfg.appApkRelPath / "latest.apk"
        shutil.copy2(apk_path, versioned)
        shutil.copy2(apk_path, latest)
        print(f"\nAPK: {versioned}")
        print(f"APK latest: {latest}")
        return versioned

    def doAndBundleBuild(
        self,
        *,
        app_dir: Path,
        root_dir: Path,
        target_platforms: Sequence[str],
        signing_properties: str | Path | None,
        bundletool_jar: str | Path | None,
    ) -> Path:
        self.maybeUpdateBuildInfo()
        version = self.readAppVersion()
        self.buildAndroidAppBundle(app_dir=app_dir, target_platforms=target_platforms)
        self.run(
            self.bundletoolBuildApksCommand(
                signing_properties=signing_properties,
                bundletool_jar=bundletool_jar,
                app_bundle_path=self.pathCfg.appBundlePath,
                app_apks_path=self.pathCfg.appApksPath,
            ),
            cwd=root_dir,
        )
        return self.copyAndroidUniversalApk(version, self.extractUniversalApk())

    def requireLineCoverage(self, name: str, covered: int, total: int) -> float:
        percent = covered / total * 100 if total else 0.0
        print(f"\n{name} line coverage: {percent:.2f}% ({covered}/{total})")
        if percent < self.coverageMinLines:
            raise BuildError(
                f"{name} line coverage {percent:.2f}% is below {self.coverageMinLines:.0f}%"
            )
        return percent

    def ensureGitClean(self) -> None:
        status = self.capture(["git", "status", "--porcelain"], cwd=self.pathCfg.root)
        if status:
            raise BuildError("git worktree is not clean; arrange changes before verUp")

    def ensureUpstreamExists(self) -> None:
        try:
            self.capture(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=self.pathCfg.root)
        except subprocess.CalledProcessError as exc:
            raise BuildError("current branch has no upstream; set upstream before verUp") from exc

    def doVerUp(self, *, root_dir: Path, app_pubspec: Path) -> AppVersion:
        status = self.capture(["git", "status", "--porcelain"], cwd=root_dir)
        if status:
            raise BuildError("git worktree is not clean; arrange changes before verUp")
        try:
            self.capture(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=root_dir)
        except subprocess.CalledProcessError as exc:
            raise BuildError("current branch has no upstream; set upstream before verUp") from exc
        old_version = parseFlutterVersion(app_pubspec.read_text(encoding="utf-8"))
        new_version = bumpFlutterVersion(old_version)
        print(f"\nVersion: {old_version.full} -> {new_version.full}")
        app_pubspec.write_text(
            replacePubspecVersion(app_pubspec.read_text(encoding="utf-8"), new_version),
            encoding="utf-8",
        )
        self.run(["git", "add", "--", str(app_pubspec.relative_to(root_dir))], cwd=root_dir)
        self.run(["git", "commit", "-m", f"app: version - bump to {new_version.name}"], cwd=root_dir)
        self.run(["git", "push"], cwd=root_dir)
        return new_version

    def runConfiguredCommands(self, commands: Sequence[tuple[str | Path, tuple[str, ...]]]) -> None:
        for cwd, cmd in commands:
            self.run(cmd, cwd=self.resolveProjectPath(cwd))

    def doUnitTest(self, *, unit_test_commands: Sequence[tuple[str | Path, tuple[str, ...]]]) -> None:
        if unit_test_commands:
            self.runConfiguredCommands(unit_test_commands)
            return
        self.cmdAndTest()

    def firstAndroidAvd(self) -> str:
        output = self.capture(self.emulatorCmd("-list-avds"), cwd=self.pathCfg.root)
        avds = [line.strip() for line in output.splitlines() if line.strip()]
        if not avds:
            raise BuildError("no Android AVDs were found")
        return avds[0]

    def startAndroidEmulator(self, avd_name: str) -> None:
        subprocess.Popen(self.emulatorCmd(f"@{avd_name}"), cwd=self.pathCfg.root)

    def findRunningAndroidEmulator(self) -> str:
        output = self.capture(self.adbCmd("devices"), cwd=self.pathCfg.root)
        for line in output.splitlines():
            if "emulator" in line and "\tdevice" in line:
                return line.split()[0]
        raise BuildError("running Android emulator was not found")

    def doAndIntegrationTest(self, *, app_dir: Path, root_dir: Path, drive_target: str) -> None:
        print("\nRunning android integration test...")
        avd = self.firstAndroidAvd()
        print(f"avd: {avd}")
        self.startAndroidEmulator(avd)
        import time
        time.sleep(6)
        emulator = self.findRunningAndroidEmulator()
        self.run(self.flutterCmd("drive", "-d", emulator, f"--target={drive_target}"), cwd=app_dir)
        self.run(self.adbCmd("-s", emulator, "emu", "kill"), cwd=root_dir)

    def doWinTest(self, *, app_dir: Path, drive_target: str) -> None:
        self.run(self.flutterCmd("drive", "-d", "windows", f"--target={drive_target}"), cwd=app_dir)

    def doMacTest(self, *, app_dir: Path, drive_target: str) -> None:
        self.run(self.flutterCmd("drive", "-d", "macos", f"--target={drive_target}"), cwd=app_dir)

    def doAndTest(self, *, app_dir: Path) -> None:
        self.run(self.flutterCmd("pub", "get"), cwd=app_dir)
        self.run(self.flutterCmd("analyze"), cwd=app_dir)
        self.run(self.flutterCmd("test"), cwd=app_dir)

    def doSerTest(self, *, ser_dir: Path) -> None:
        self.run(self.cargoCmd("test"), cwd=ser_dir)

    def doWebTest(self, *, web_dir: Path) -> None:
        self.run(self.npmCmd("test"), cwd=web_dir)

    def doAppCov(self, *, app_dir: Path, coverage_info: Path, coverage_name: str) -> None:
        self.run(self.flutterCmd("pub", "get"), cwd=app_dir)
        self.run(self.flutterCmd("test", "--coverage", "--concurrency=1"), cwd=app_dir)
        if not coverage_info.exists():
            raise BuildError(f"app coverage file was not found: {coverage_info}")
        covered, total, _ = parseLcovLineCoverage(coverage_info.read_text(encoding="utf-8"))
        self.requireLineCoverage(coverage_name, covered, total)

    def doSerCov(self, *, ser_dir: Path, coverage_min_lines: float) -> None:
        self.run(
            self.cargoCmd("llvm-cov", "--fail-under-lines", str(int(coverage_min_lines)), "--summary-only"),
            cwd=ser_dir,
        )

    def doWebCov(self, *, web_dir: Path, npm_args: Sequence[str]) -> None:
        self.run(self.npmCmd(*npm_args), cwd=web_dir)

    def doAllCov(self, *, commands: Sequence[str]) -> None:
        commands_by_name = self.checkedCommandMap()
        for command in commands:
            if command not in commands_by_name:
                raise BuildError(f"{command} task is not supported by this project")
            commands_by_name[command]()

    def copyAndroidApk(self, version: AppVersion) -> Path:
        if not self.pathCfg.appApkPath.exists():
            raise BuildError(f"release APK was not found: {self.pathCfg.appApkPath}")
        self.pathCfg.appApkRelPath.mkdir(parents=True, exist_ok=True)
        versioned = self.pathCfg.appApkRelPath / self.apkFileName(version)
        latest = self.pathCfg.appApkRelPath / "latest.apk"
        shutil.copy2(self.pathCfg.appApkPath, versioned)
        shutil.copy2(self.pathCfg.appApkPath, latest)
        print(f"\nAPK: {versioned}")
        print(f"APK latest: {latest}")
        return versioned

    def defaultInstallApk(self) -> Path:
        latest = self.pathCfg.appApkRelPath / "latest.apk"
        if latest.exists():
            return latest
        if self.pathCfg.appApkPath.exists():
            return self.pathCfg.appApkPath
        raise BuildError("release APK was not found; run andBuild first")

    def listAndroidDevices(self) -> list[AndroidDevice]:
        devices = parseAdbDevices(self.capture(self.adbCmd("devices", "-l"), cwd=self.pathCfg.root))
        if not devices:
            raise BuildError("no installable Android devices were found by adb")
        return devices

    def selectAndroidDevice(self, devices: Sequence[AndroidDevice]) -> AndroidDevice | None:
        if not devices:
            raise BuildError("no installable Android devices were found by adb")
        preferred_serial = os.environ.get("ANDROID_SERIAL", "").strip()
        if preferred_serial:
            for device in devices:
                if device.serial == preferred_serial:
                    print(f"\nAndroid device: {device.label}")
                    return device
            raise BuildError(f"ANDROID_SERIAL device was not found: {preferred_serial}")
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            if len(devices) == 1:
                print(f"\nAndroid device: {devices[0].label}")
                return devices[0]
            raise BuildError("andInstall requires an interactive terminal when multiple devices exist")
        return self.selectAndroidDeviceTui(devices)

    def selectAndroidDeviceTui(self, devices: Sequence[AndroidDevice]) -> AndroidDevice | None:
        selected = selectTui(
            "Select Android device to install APK",
            "Enter: install  Up/Down: move  Esc: cancel",
            [device.label for device in devices],
        )
        return None if selected is None else devices[selected]

    def doAndInstall(self, *, apk_path: Path | None = None) -> AndroidDevice | None:
        apk = apk_path or self.defaultInstallApk()
        if not apk.exists():
            raise BuildError(f"release APK was not found: {apk}")
        device = self.selectAndroidDevice(self.listAndroidDevices())
        if device is None:
            print("\nInstall cancelled.")
            return None
        self.run(self.adbCmd("-s", device.serial, "install", "-r", "-d", str(apk)), cwd=self.pathCfg.root)
        return device

    def doAndBuild(self, *, app_dir: Path) -> Path:
        self.maybeUpdateBuildInfo()
        version = self.readAppVersion()
        self.run(self.flutterCmd("pub", "get"), cwd=app_dir)
        self.run(self.flutterCmd("build", "apk", "--release"), cwd=app_dir)
        apk = self.copyAndroidApk(version)
        self.doAndInstall(apk_path=apk)
        return apk

    def doAndDeploy(self, *, commands: Sequence[str]) -> None:
        commands_by_name = self.checkedCommandMap()
        for command in commands:
            if command not in commands_by_name:
                raise BuildError(f"{command} task is not supported by this project")
            commands_by_name[command]()

    def doSerUp(self, *, ser_dir: Path, ser_up_args: Sequence[str]) -> None:
        self.run(self.gatCmd(*ser_up_args), cwd=ser_dir)

    def commentPrefixForPath(self, path: Path) -> str:
        return "#" if path.suffix in {".yaml", ".yml"} else "//"

    def setFfiComments(self, comment: bool, *, ffi_comment_files: Sequence[str | Path]) -> None:
        for raw_path in ffi_comment_files:
            path = self.resolveProjectPath(raw_path)
            if not path.exists():
                continue
            prefix = self.commentPrefixForPath(path)
            lines: list[str] = []
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.rstrip(" \r\n")
                stripped = line.lstrip(" ")
                indent = line[:len(line) - len(stripped)]
                if line.endswith("##ffiCmt"):
                    if comment and not stripped.startswith(prefix):
                        line = f"{indent}{prefix}{stripped}"
                    elif not comment and stripped.startswith(prefix):
                        line = f"{indent}{stripped[len(prefix):]}"
                lines.append(line)
            path.write_text("\n".join(lines), encoding="utf-8")

    def sqfliteFfiCommentOut(
        self,
        *,
        ffi_comment_files: Sequence[str | Path],
        ffi_lockfile: str | Path | None,
    ) -> None:
        self.setFfiComments(True, ffi_comment_files=ffi_comment_files)
        if ffi_lockfile is None:
            return
        lockfile = self.resolveProjectPath(ffi_lockfile)
        if lockfile.exists():
            shutil.move(str(lockfile), str(lockfile) + ".bak")

    def sqfliteFfiRestore(
        self,
        *,
        ffi_comment_files: Sequence[str | Path],
        ffi_lockfile: str | Path | None,
    ) -> None:
        if ffi_lockfile is not None:
            lockfile = self.resolveProjectPath(ffi_lockfile)
            backup = Path(str(lockfile) + ".bak")
            if backup.exists():
                shutil.move(str(backup), str(lockfile))
            else:
                print(f"backup file {backup} not found")
        self.setFfiComments(False, ffi_comment_files=ffi_comment_files)

    def doMacFfiRestore(
        self,
        *,
        ffi_lockfile: str | Path | None,
        ffi_comment_files: Sequence[str | Path],
    ) -> None:
        self.sqfliteFfiRestore(
            ffi_comment_files=ffi_comment_files,
            ffi_lockfile=ffi_lockfile,
        )

    def doLinuxBuild(self, *, app_dir: Path, release_root: Path) -> None:
        self.maybeUpdateBuildInfo()
        version = self.readAppVersion()
        self.run(self.flutterCmd("build", "linux", "--release"), cwd=app_dir)
        target = release_root / "linux" / f"V{version.name}"
        latest = release_root / "linux" / "latest"
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(app_dir / "build/linux/x86/release/bundle", target / "bundle")
        shutil.rmtree(latest, ignore_errors=True)
        latest.mkdir(parents=True, exist_ok=True)
        shutil.copytree(target / "bundle", latest / "bundle")

    def doWebBuild(self, *, app_dir: Path) -> None:
        self.maybeUpdateBuildInfo()
        self.run(self.flutterCmd("build", "web", "--no-tree-shake-icons"), cwd=app_dir)

    def doIosBuild(self, *, app_dir: Path) -> None:
        self.maybeUpdateBuildInfo()
        self.run(self.flutterCmd("build", "ipa"), cwd=app_dir)

    def doIosDeploy(self, *, app_dir: Path, upload_command: str) -> None:
        self.runShell(upload_command, cwd=app_dir)

    def doMacXcodeBuild(self, *, app_dir: Path) -> None:
        self.run(["xcodebuild", "archive", "-workspace", "Runner.xcworkspace", "-scheme", "Runner", "-configuration", "Release"], cwd=app_dir / "macos")
        self.run(["open", "Runner.xcworkspace"], cwd=app_dir / "macos")

    def doMacBuild(
        self,
        *,
        app_dir: Path,
        ffi_comment_files: Sequence[str | Path],
        ffi_lockfile: str | Path | None,
        mac_pre_build_commands: Sequence[tuple[str | Path, tuple[str, ...]]],
        mac_config_only: bool,
    ) -> None:
        if ffi_comment_files:
            self.sqfliteFfiCommentOut(
                ffi_comment_files=ffi_comment_files,
                ffi_lockfile=ffi_lockfile,
            )
        self.runConfiguredCommands(mac_pre_build_commands)
        self.maybeUpdateBuildInfo()
        cmd = self.flutterCmd("build", "macos")
        if mac_config_only:
            cmd.append("--config-only")
        else:
            cmd.append("--release")
        self.run(cmd, cwd=app_dir)

    def doMacDeploy(
        self,
        *,
        mac_app_path: str | Path,
        mac_unsigned_pkg: str | Path,
        mac_signed_pkg: str | Path,
        mac_app_sign_identity: str | None,
        mac_product_sign_identity: str | None,
        mac_upload_command: Sequence[str],
    ) -> None:
        app_path = self.resolveProjectPath(mac_app_path)
        unsigned_pkg = self.resolveProjectPath(mac_unsigned_pkg)
        signed_pkg = self.resolveProjectPath(mac_signed_pkg)
        if mac_app_sign_identity is None or mac_product_sign_identity is None:
            raise BuildError("mac signing identities are not configured")
        if unsigned_pkg.exists():
            unsigned_pkg.unlink()
        self.run(["codesign", "-vfs", mac_app_sign_identity, str(app_path)], cwd=self.pathCfg.root)
        self.run(["xcrun", "productbuild", "--component", str(app_path), "/Applications/", str(unsigned_pkg)], cwd=self.pathCfg.root)
        self.run(["xcrun", "productsign", "--sign", mac_product_sign_identity, str(unsigned_pkg), str(signed_pkg)], cwd=self.pathCfg.root)
        if mac_upload_command:
            self.run(mac_upload_command, cwd=self.pathCfg.root)

    def doWinBuild(
        self,
        *,
        app_dir: Path,
        release_root: Path,
        win_release_source: str | Path,
        win_exe_name: str | None,
        win_extra_files: Sequence[str | Path],
        win_nsi_command: Sequence[str],
    ) -> None:
        self.maybeUpdateBuildInfo()
        version = self.readAppVersion()
        self.run(self.flutterCmd("build", "windows"), cwd=app_dir)
        target = release_root / "win" / f"V{version.name}"
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(self.resolveProjectPath(win_release_source), target)
        if win_exe_name:
            default_exe = target / "app.exe"
            if default_exe.exists():
                default_exe.rename(target / win_exe_name)
        for raw_file in win_extra_files:
            source = self.resolveProjectPath(raw_file)
            if source.exists():
                shutil.copy2(source, target / source.name)
        self.writeWindowsUpdateInfo(target, version)
        latest = release_root / "win" / "latest"
        shutil.rmtree(latest, ignore_errors=True)
        shutil.copytree(target, latest)
        (app_dir / ".appVer.txt").write_text(f'!define APP_VERSION "{version.name}.0"', encoding="utf-8")
        if win_nsi_command:
            self.run(win_nsi_command, cwd=app_dir)

    def writeWindowsUpdateInfo(self, target: Path, version: AppVersion) -> None:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        files = []
        for root, _, names in os.walk(target):
            for name in names:
                if name == "updateInfo.json":
                    continue
                path = Path(root) / name
                files.append({
                    "name": str(path.relative_to(target)).replace("\\", "/"),
                    "size": path.stat().st_size,
                    "hash": fileSha1(path),
                })
        (target / "updateInfo.json").write_text(
            json.dumps({
                "version": version.name,
                "build-time": now,
                "buildTime": now,
                "files": files,
            }, indent=1),
            encoding="utf-8",
        )

    def doWinDeploy(self, *, release_root: Path, apk_prefix: str, deploy_path: str | None = None) -> None:
        version = self.readAppVersion()
        target = release_root / "win" / f"V{version.name}"
        zip_path = release_root / "win" / f"{apk_prefix}-win-{version.name}.zip"
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zip_work:
            for root, _, files in os.walk(target):
                for name in files:
                    path = Path(root) / name
                    zip_work.write(path, path.relative_to(target), compress_type=zipfile.ZIP_DEFLATED)
        self.uploadWindowsZip(zip_path, deploy_path=deploy_path)

    def openCoSsh(self) -> Any:
        from . import ssh_deploy
        try:
            return ssh_deploy.openCoSsh(
                host=self.sshCfg.host,
                port=self.sshCfg.port,
                user=self.sshCfg.user,
            )
        except ssh_deploy.SshDeployError as exc:
            raise BuildError(str(exc)) from exc

    def uploadAndroidLatest(self, *, deploy_path: str | None) -> None:
        if deploy_path is None:
            raise BuildError("android deploy path is not configured")
        version = self.readAppVersion()
        apk = self.pathCfg.appApkRelPath / self.apkFileName(version)
        version_code = androidVersionCode(version)
        ssh = self.openCoSsh()
        try:
            from . import ssh_deploy
            ssh.run(f"mkdir -p {deploy_path}")
            ssh_deploy.uploadFile(
                ssh=ssh,
                local_path=apk,
                remote_path=f"{deploy_path}/latest.apk",
            )
            ssh.run(f"echo {version_code} > {deploy_path}/latest.ver")
        finally:
            ssh.close()

    def uploadWindowsZip(self, zip_path: Path, *, deploy_path: str | None = None) -> None:
        if deploy_path is None:
            return
        ssh = self.openCoSsh()
        try:
            from . import ssh_deploy
            remote_zip = f"{deploy_path}/{zip_path.name}"
            ssh_deploy.runRemote(ssh=ssh, command=f"mkdir -p {deploy_path}")
            ssh_deploy.uploadFile(ssh=ssh, local_path=zip_path, remote_path=remote_zip)
        finally:
            ssh.close()

    def googlePlayCredentialPath(self, *, credential_file: str | Path) -> Path:
        return self.resolveProjectPath(credential_file)

    def googlePlayClientSecretsPath(self, *, client_secrets_file: str | Path) -> Path:
        return self.resolveProjectPath(client_secrets_file)

    def googlePlayService(
        self,
        *,
        credential_file: str | Path,
        client_secrets_file: str | Path,
        scope: str,
        auth_host: str,
        auth_port: int,
    ) -> Any:
        from . import google_play
        try:
            return google_play.buildService(
                client_secrets_path=self.googlePlayClientSecretsPath(client_secrets_file=client_secrets_file),
                credential_path=self.googlePlayCredentialPath(credential_file=credential_file),
                scope=scope,
                host=auth_host,
                port=auth_port,
            )
        except google_play.GooglePlayError as exc:
            raise BuildError(str(exc)) from exc

    def googlePlayPublish(
        self,
        *,
        package_name: str,
        track: str,
        scope: str,
        auth_host: str,
        auth_port: int,
        credential_file: str | Path,
        client_secrets_file: str | Path,
        aab_path: str | Path,
    ) -> None:
        if not package_name:
            raise BuildError("google play package name is not configured")
        from . import google_play
        google_play.publishBundle(
            service=self.googlePlayService(
                credential_file=credential_file,
                client_secrets_file=client_secrets_file,
                scope=scope,
                auth_host=auth_host,
                auth_port=auth_port,
            ),
            package_name=package_name,
            track=track,
            aab_path=self.resolveProjectPath(aab_path),
        )

    def commandNames(self) -> list[str]:
        return [
            command for method_name, method in vars(GatDevBase).items()
            if callable(method)
            for command in [self.commandNameFromMethodName(method_name)]
            if command is not None
        ]

    def commandMap(self) -> dict[str, Callable[[], object]]:
        commands: dict[str, Callable[[], object]] = {}
        for command in self.availableCmdList():
            method_name = self.commandMethodName(command)
            method = getattr(self, method_name, None)
            if callable(method):
                commands[command] = method
        return commands

    def checkedCommandMap(self) -> dict[str, Callable[[], object]]:
        commands_by_name = self.commandMap()
        return commands_by_name

    def resolveCommands(self, command: str | None) -> list[str] | None:
        if command is not None:
            return [command]
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise BuildError("command argument is required when no TTY is available")
        commands = self.selectCommandSequenceTui()
        if commands is None:
            print("\nCommand cancelled.")
        return commands

    def parseArgs(self, argv: Sequence[str]) -> argparse.Namespace:
        parser = argparse.ArgumentParser(description="gdev project build helper")
        parser.add_argument("command", choices=self.requireSupportedCommands(), nargs="?")
        return parser.parse_args(argv)

    def main(self, argv: Sequence[str] | None = None) -> int:
        try:
            args = self.parseArgs(sys.argv[1:] if argv is None else argv)
            commands = self.resolveCommands(args.command)
            if commands is None:
                return 0
            commands_by_name = self.checkedCommandMap()
            for command in commands:
                print(f"\n==> {command}")
                commands_by_name[command]()
        except BuildError as exc:
            print(f"\nERROR: {exc}", file=sys.stderr)
            return 1
        except subprocess.CalledProcessError as exc:
            print(f"\nERROR: command failed with exit code {exc.returncode}", file=sys.stderr)
            return exc.returncode
        return 0


__all__ = [
    "AndroidCfg",
    "AndroidDevice",
    "AppVersion",
    "BuildError",
    "DesktopCfg",
    "GatDev",
    "GatDevBase",
    "SshCfg",
    "ToolCmd",
]
