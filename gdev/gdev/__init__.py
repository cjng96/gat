import argparse
import curses
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, ClassVar, Sequence


class BuildError(RuntimeError):
    pass


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


def appendSelectedCommandNumber(input_text: str, selected_index: int) -> str:
    prefix = input_text.rstrip()
    number = str(selected_index + 1)
    return number if not prefix else f"{prefix} {number}"


class GatDev:
    @dataclass(frozen=True)
    class PathCfg:
        root: str | Path = Path.cwd()
        appDir: str | Path = "app"
        serDir: str | Path = "ser"
        webDir: str | Path = "web"
        appPubspec: str | Path = "app/pubspec.yaml"
        appCoverageInfo: str | Path = "app/coverage/lcov.info"
        appApkPath: str | Path = "app/build/app/outputs/flutter-apk/app-release.apk"
        appApkRelPath: str | Path = "release/android"
        apkPrefix: str = "app"

        def resolve(self) -> "GatDev.PathCfg":
            root_path = Path(self.root)
            if not root_path.is_absolute():
                root_path = Path.cwd() / root_path

            def path(value: str | Path) -> Path:
                p = Path(value)
                return p if p.is_absolute() else root_path / p

            return type(self)(
                root=root_path,
                appDir=path(self.appDir),
                serDir=path(self.serDir),
                webDir=path(self.webDir),
                appPubspec=path(self.appPubspec),
                appCoverageInfo=path(self.appCoverageInfo),
                appApkPath=path(self.appApkPath),
                appApkRelPath=path(self.appApkRelPath),
                apkPrefix=self.apkPrefix,
            )

    class Cmds:
        andBuild = "andBuild"
        verUp = "verUp"
        serUp = "serUp"
        andInstall = "andInstall"
        andDeploy = "andDeploy"
        andTest = "andTest"
        serTest = "serTest"
        webTest = "webTest"
        appCov = "appCov"
        serCov = "serCov"
        webCov = "webCov"
        allCov = "allCov"

    pathCfg: ClassVar[PathCfg] = PathCfg()
    coverageMinLines: ClassVar[float] = 80.0
    serUpArgs: ClassVar[tuple[str, ...]] = ("prod", "run")
    cmdList: ClassVar[list[str]] = [
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

    def __init__(self) -> None:
        self.pathCfg = self.pathCfg.resolve()

    def run(self, cmd: Sequence[str], *, cwd: Path | None = None) -> None:
        run(cmd, cwd=cwd or self.pathCfg.root)

    def capture(self, cmd: Sequence[str], *, cwd: Path | None = None) -> str:
        return capture(cmd, cwd=cwd or self.pathCfg.root)

    def parseCommandSequence(self, input_text: str) -> list[str]:
        tokens = [token for token in re.split(r"[\s,]+", input_text.strip()) if token]
        if not tokens:
            raise BuildError("no command numbers were entered")

        commands: list[str] = []
        for token in tokens:
            if not token.isdecimal():
                raise BuildError(f"invalid command number: {token}")
            number = int(token)
            if number < 1 or number > len(self.cmdList):
                raise BuildError(f"command number is out of range: {number}")
            commands.append(self.cmdList[number - 1])
        return commands

    def commandSequenceFromInput(self, input_text: str, selected_index: int) -> list[str]:
        if not input_text.strip():
            return [self.cmdList[selected_index]]
        return self.parseCommandSequence(input_text)

    def selectCommandSequenceTui(self) -> list[str] | None:
        def menu(stdscr: curses.window) -> list[str] | None:
            try:
                curses.curs_set(1)
            except curses.error:
                pass
            stdscr.keypad(True)
            input_text = ""
            message = ""
            selected = 0

            while True:
                stdscr.erase()
                height, width = stdscr.getmaxyx()
                stdscr.addnstr(0, 0, "Select build commands", max(0, width - 1), curses.A_BOLD)
                if height > 1:
                    help_text = "Space: add selected  Enter: run  Up/Down: move  Esc: cancel"
                    stdscr.addnstr(1, 0, help_text, max(0, width - 1))

                for index, command in enumerate(self.cmdList):
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
                        return self.commandSequenceFromInput(input_text, selected)
                    except BuildError as exc:
                        message = str(exc)
                        continue
                if key in (curses.KEY_UP, ord("k")):
                    selected = (selected - 1) % len(self.cmdList)
                    continue
                if key in (curses.KEY_DOWN, ord("j")):
                    selected = (selected + 1) % len(self.cmdList)
                    continue
                if key in (curses.KEY_BACKSPACE, 8, 127):
                    input_text = input_text[:-1]
                    continue
                if key == ord(" "):
                    input_text = appendSelectedCommandNumber(input_text, selected)
                    continue
                if key == ord(",") or ord("0") <= key <= ord("9"):
                    input_text += chr(key)

        return curses.wrapper(menu)

    def readAppVersion(self) -> AppVersion:
        return parseFlutterVersion(self.pathCfg.appPubspec.read_text(encoding="utf-8"))

    def writeAppVersion(self, version: AppVersion) -> None:
        text = self.pathCfg.appPubspec.read_text(encoding="utf-8")
        self.pathCfg.appPubspec.write_text(replacePubspecVersion(text, version), encoding="utf-8")

    def releaseApkName(self, version: AppVersion) -> str:
        return f"{self.pathCfg.apkPrefix}-{version.full}.apk"

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

    def verUp(self) -> AppVersion:
        self.ensureGitClean()
        self.ensureUpstreamExists()
        old_version = self.readAppVersion()
        new_version = bumpFlutterVersion(old_version)
        print(f"\nVersion: {old_version.full} -> {new_version.full}")
        self.writeAppVersion(new_version)
        self.run(["git", "add", "--", str(self.pathCfg.appPubspec.relative_to(self.pathCfg.root))], cwd=self.pathCfg.root)
        self.run(["git", "commit", "-m", f"app: version - bump to {new_version.name}"], cwd=self.pathCfg.root)
        self.run(["git", "push"], cwd=self.pathCfg.root)
        return new_version

    def andTest(self) -> None:
        self.run(ToolCmd.flutter("pub", "get"), cwd=self.pathCfg.appDir)
        self.run(ToolCmd.flutter("analyze"), cwd=self.pathCfg.appDir)
        self.run(ToolCmd.flutter("test"), cwd=self.pathCfg.appDir)

    def serTest(self) -> None:
        self.run(ToolCmd.cargo("test"), cwd=self.pathCfg.serDir)

    def webTest(self) -> None:
        self.run(ToolCmd.npm("test"), cwd=self.pathCfg.webDir)

    def appCov(self) -> None:
        self.run(ToolCmd.flutter("pub", "get"), cwd=self.pathCfg.appDir)
        self.run(ToolCmd.flutter("test", "--coverage", "--concurrency=1"), cwd=self.pathCfg.appDir)
        if not self.pathCfg.appCoverageInfo.exists():
            raise BuildError(f"app coverage file was not found: {self.pathCfg.appCoverageInfo}")
        covered, total, _ = parseLcovLineCoverage(self.pathCfg.appCoverageInfo.read_text(encoding="utf-8"))
        self.requireLineCoverage("app", covered, total)

    def serCov(self) -> None:
        self.run(
            ToolCmd.cargo("llvm-cov", "--fail-under-lines", str(int(self.coverageMinLines)), "--summary-only"),
            cwd=self.pathCfg.serDir,
        )

    def webCov(self) -> None:
        self.run(ToolCmd.npm("run", "test:coverage"), cwd=self.pathCfg.webDir)

    def allCov(self) -> None:
        self.appCov()
        self.serCov()
        self.webCov()

    def copyAndroidApk(self, version: AppVersion) -> Path:
        if not self.pathCfg.appApkPath.exists():
            raise BuildError(f"release APK was not found: {self.pathCfg.appApkPath}")
        self.pathCfg.appApkRelPath.mkdir(parents=True, exist_ok=True)
        versioned = self.pathCfg.appApkRelPath / self.releaseApkName(version)
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
        devices = parseAdbDevices(self.capture(ToolCmd.adb("devices", "-l"), cwd=self.pathCfg.root))
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

    def andInstall(self, apk_path: Path | None = None) -> AndroidDevice | None:
        apk = apk_path or self.defaultInstallApk()
        if not apk.exists():
            raise BuildError(f"release APK was not found: {apk}")
        device = self.selectAndroidDevice(self.listAndroidDevices())
        if device is None:
            print("\nInstall cancelled.")
            return None
        self.run(ToolCmd.adb("-s", device.serial, "install", "-r", "-d", str(apk)), cwd=self.pathCfg.root)
        return device

    def andBuild(self) -> Path:
        version = self.readAppVersion()
        self.run(ToolCmd.flutter("pub", "get"), cwd=self.pathCfg.appDir)
        self.run(ToolCmd.flutter("build", "apk", "--release"), cwd=self.pathCfg.appDir)
        apk = self.copyAndroidApk(version)
        self.andInstall(apk)
        return apk

    def andDeploy(self) -> None:
        self.andTest()
        self.serTest()
        self.webTest()
        self.verUp()
        self.andBuild()

    def serUp(self) -> None:
        self.run(ToolCmd.gat(*self.serUpArgs), cwd=self.pathCfg.serDir)

    def commandMap(self) -> dict[str, Callable[[], object]]:
        return {
            self.Cmds.andBuild: self.andBuild,
            self.Cmds.andInstall: self.andInstall,
            self.Cmds.andDeploy: self.andDeploy,
            self.Cmds.serUp: self.serUp,
            self.Cmds.andTest: self.andTest,
            self.Cmds.serTest: self.serTest,
            self.Cmds.webTest: self.webTest,
            self.Cmds.appCov: self.appCov,
            self.Cmds.serCov: self.serCov,
            self.Cmds.webCov: self.webCov,
            self.Cmds.allCov: self.allCov,
            self.Cmds.verUp: self.verUp,
        }

    def checkedCommandMap(self) -> dict[str, Callable[[], object]]:
        commands_by_name = self.commandMap()
        missing = [command for command in self.cmdList if command not in commands_by_name]
        if missing:
            raise BuildError(f"commandMap is missing cmdList command(s): {', '.join(missing)}")
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
        parser.add_argument("command", choices=self.cmdList, nargs="?")
        return parser.parse_args(argv)

    def main(self, argv: Sequence[str] | None = None) -> int:
        args = self.parseArgs(sys.argv[1:] if argv is None else argv)
        try:
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
    "AndroidDevice",
    "AppVersion",
    "BuildError",
    "GatDev",
    "ToolCmd",
]
