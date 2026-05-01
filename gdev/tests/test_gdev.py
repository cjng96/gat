import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import gdev
import gdev.__main__ as gdev_main
from gdev import (
    AndroidDevice,
    AppVersion,
    BuildError,
    GatDev,
    ToolCmd,
    appendSelectedCommandNumber,
    bumpFlutterVersion,
    parseAdbDevices,
    parseFlutterVersion,
    parseLcovLineCoverage,
    replacePubspecVersion,
)


class FakeTty:
    def __init__(self, is_tty: bool):
        self.is_tty = is_tty

    def isatty(self):
        return self.is_tty

    def write(self, _text):
        pass

    def flush(self):
        pass


class DemoBuild(GatDev):
    pathCfg = GatDev.PathCfg(
        root=Path("/tmp/demo"),
        appDir="client",
        serDir="server",
        webDir="console",
        appPubspec="client/pubspec.yaml",
        appCoverageInfo="client/coverage/lcov.info",
        appApkPath="client/build/app/outputs/flutter-apk/app-release.apk",
        appApkRelPath="dist/android",
        apkPrefix="demo",
    )


class MissingCommandBuild(DemoBuild):
    cmdList = [GatDev.Cmds.andBuild, "custom"]


class GatDevTest(unittest.TestCase):
    def test_parse_and_bumpFlutterVersion(self):
        version = parseFlutterVersion("name: demo\nversion: 1.2.3+77\n")
        self.assertEqual(version.full, "1.2.3+77")
        self.assertEqual(bumpFlutterVersion(version).full, "1.2.4+10204")

    def test_replacePubspecVersion_line(self):
        self.assertEqual(
            replacePubspecVersion("name: demo\nversion: 1.0.0+1\n", AppVersion(1, 0, 1, 10001)),
            "name: demo\nversion: 1.0.1+10001\n",
        )

    def test_lcov_coverage_parser_calculates_line_coverage(self):
        covered, total, percent = parseLcovLineCoverage("LF:10\nLH:8\nLF:5\nLH:4\n")
        self.assertEqual((covered, total), (12, 15))
        self.assertAlmostEqual(percent, 80.0)

    def test_lcov_coverage_parser_rejects_empty_input(self):
        with self.assertRaises(BuildError):
            parseLcovLineCoverage("")

    def test_parseAdbDevices_keeps_installable_devices(self):
        devices = parseAdbDevices(
            "\n".join(
                [
                    "List of devices attached",
                    "emulator-5554 device product:sdk model:Pixel transport_id:1",
                    "10.0.0.2:5555 offline product:phone model:X transport_id:2",
                    "R3CN123 unauthorized usb:337641472X",
                ]
            )
        )
        self.assertEqual([device.serial for device in devices], ["emulator-5554"])

    def test_command_sequence_parser_maps_numbered_input_in_order(self):
        build = DemoBuild()
        self.assertEqual(
            build.parseCommandSequence("3 1 2,4"),
            ["serUp", "andBuild", "verUp", "andInstall"],
        )

    def test_command_sequence_parser_rejects_invalid_numbers(self):
        build = DemoBuild()
        for input_text in ("", "0", "13", "x", "1 x"):
            with self.subTest(input_text=input_text):
                with self.assertRaises(BuildError):
                    build.parseCommandSequence(input_text)

    def test_appendSelectedCommandNumber_keeps_ordered_input(self):
        self.assertEqual(appendSelectedCommandNumber("", 2), "3")
        self.assertEqual(appendSelectedCommandNumber("3", 0), "3 1")

    def test_path_config_resolves_configured_directories(self):
        build = DemoBuild()

        self.assertEqual(build.pathCfg.appDir, Path("/tmp/demo/client"))
        self.assertEqual(build.pathCfg.root, Path("/tmp/demo"))
        self.assertEqual(build.pathCfg.serDir, Path("/tmp/demo/server"))
        self.assertEqual(build.pathCfg.webDir, Path("/tmp/demo/console"))
        self.assertEqual(build.pathCfg.appPubspec, Path("/tmp/demo/client/pubspec.yaml"))
        self.assertEqual(build.pathCfg.appCoverageInfo, Path("/tmp/demo/client/coverage/lcov.info"))
        self.assertEqual(build.pathCfg.appApkPath, Path("/tmp/demo/client/build/app/outputs/flutter-apk/app-release.apk"))
        self.assertEqual(build.pathCfg.appApkRelPath, Path("/tmp/demo/dist/android"))
        self.assertEqual(build.pathCfg.apkPrefix, "demo")
        self.assertFalse(hasattr(build, "appPath"))
        self.assertFalse(hasattr(build, "appApkRelPath"))
        self.assertFalse(hasattr(build, "apkPrefix"))
        self.assertFalse(hasattr(build, "root"))

    def test_all_exports_only_core_api(self):
        self.assertEqual(
            gdev.__all__,
            [
                "AndroidDevice",
                "AppVersion",
                "BuildError",
                "GatDev",
                "ToolCmd",
            ],
        )

    def test_tool_cmd_builds_env_overridable_commands(self):
        with patch.dict("gdev.os.environ", {"FLUTTER_BIN": "/opt/flutter/bin/flutter --suppress-analytics"}):
            self.assertEqual(
                ToolCmd.flutter("test"),
                ["/opt/flutter/bin/flutter", "--suppress-analytics", "test"],
            )
        self.assertEqual(ToolCmd.cargo("test"), ["cargo", "test"])
        self.assertEqual(ToolCmd.npm("test"), ["npm", "test"])
        self.assertEqual(ToolCmd.adb("devices", "-l"), ["adb", "devices", "-l"])
        self.assertEqual(ToolCmd.gat("prod", "run"), ["gat", "prod", "run"])
        self.assertFalse(hasattr(gdev, "flutterCmd"))
        self.assertFalse(hasattr(gdev, "adbCmd"))

    def test_future_annotations_import_is_not_used(self):
        source = Path(gdev.__file__).read_text(encoding="utf-8")

        self.assertNotIn("from __future__ import annotations", source)

    def test_release_apk_filename_uses_project_prefix(self):
        self.assertEqual(DemoBuild().releaseApkName(AppVersion(1, 0, 1, 10001)), "demo-1.0.1+10001.apk")

    def test_andInstall_runs_adb_install_for_selected_device(self):
        build = DemoBuild()
        device = AndroidDevice("emulator-5554", "device", "model:Pixel")
        with tempfile.TemporaryDirectory() as tmp_dir:
            apk = Path(tmp_dir) / "app.apk"
            apk.write_text("apk", encoding="utf-8")
            with (
                patch.object(build, "listAndroidDevices", return_value=[device]),
                patch.object(build, "selectAndroidDevice", return_value=device),
                patch.object(build, "run") as run_mock,
            ):
                self.assertEqual(build.andInstall(apk), device)
        run_mock.assert_called_once()

    def test_main_without_command_requires_tty(self):
        build = DemoBuild()
        with (
            patch("gdev.sys.stdin", FakeTty(False)),
            patch("gdev.sys.stdout", FakeTty(False)),
            patch("gdev.sys.stderr", FakeTty(False)),
            patch.object(build, "selectCommandSequenceTui") as select_mock,
        ):
            self.assertEqual(build.main([]), 1)
        select_mock.assert_not_called()

    def test_checkedCommandMap_rejects_missing_custom_command(self):
        with self.assertRaises(BuildError):
            MissingCommandBuild().checkedCommandMap()

    def test_gdev_main_rejects_missing_gat_dev_py(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with (
                patch("gdev.__main__.Path.cwd", return_value=Path(tmp_dir)),
                patch("gdev.__main__.sys.stderr", FakeTty(False)),
            ):
                self.assertEqual(gdev_main.main(["--help"]), 1)

    def test_gdev_main_loads_project_build(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_file = Path(tmp_dir) / "gat_dev.py"
            project_file.write_text(
                "\n".join(
                    [
                        "class Build:",
                        "    def main(self, argv):",
                        "        return 7 if argv == ['ok'] else 1",
                        "BUILD = Build()",
                    ]
                ),
                encoding="utf-8",
            )
            with patch("gdev.__main__.Path.cwd", return_value=Path(tmp_dir)):
                self.assertEqual(gdev_main.main(["ok"]), 7)


if __name__ == "__main__":
    unittest.main()
