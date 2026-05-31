import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

import gdev
import gdev.__main__ as gdev_main
from gdev import (
    AndroidCfg,
    AndroidDevice,
    AppVersion,
    BuildError,
    CoverageCfg,
    DesktopCfg,
    GatDev,
    GatDevBase,
    SshCfg,
    ToolCmd,
    appendSelectedCommandNumber,
    bumpFlutterVersion,
    commandInputAfterSpace,
    filterLcovRecords,
    parseAdbDevices,
    parseFlutterVersion,
    parseLcovLineCoverage,
    readPropertiesFile,
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


class InferredRootBuild(GatDev):
    pathCfg = GatDev.PathCfg(appDir="client")


class DispatchBuild(DemoBuild):
    def cmdAndBuild(self) -> None:
        pass

    def cmdVerUp(self) -> None:
        pass

    def cmdSerUp(self) -> None:
        pass

    def cmdWebCov(self) -> None:
        self.doWebCov(web_dir=self.pathCfg.webDir, npm_args=("run", "test:coverage"))


class OrderedOnlyBuild(DemoBuild):
    def cmdAndBuild(self) -> None:
        pass

    def cmdWebCov(self) -> None:
        pass

    def cmdMacBuild(self) -> None:
        pass

    def cmdCustomTask(self) -> None:
        pass


class SingleCommandBuild(DemoBuild):
    def cmdAndBuild(self) -> None:
        pass


class SuperCommandBuild(DemoBuild):
    def cmdAndTest(self) -> None:
        super().cmdAndTest()


class SuperCommandBuildWithIntegration(DemoBuild):
    def cmdAndTest(self) -> None:
        super().cmdAndTest()


class BundleBuild(DemoBuild):
    androidCfg = AndroidCfg(
        bundletoolJar="/opt/bundletool.jar",
        signingProperties="client/key.properties",
    )

    def apkFileName(self, version: AppVersion) -> str:
        return f"{self.pathCfg.apkPrefix}-{version.name}.apk"


class MacDeployBuild(DemoBuild):
    def cmdMacDeploy(self) -> None:
        self.doMacDeploy(
            mac_app_path="app/build/macos/Build/Products/Release/Demo.app",
            mac_unsigned_pkg="app/Demo.unsigned.pkg",
            mac_signed_pkg="app/Demo.pkg",
            mac_app_sign_identity="Developer ID Application: Demo",
            mac_product_sign_identity="3rd Party Mac Developer Installer: Demo",
            mac_upload_command=("upload", "app/Demo.pkg"),
        )


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

    def test_lcov_filter_keeps_included_records_and_excludes_prefixes(self):
        filtered = filterLcovRecords(
            "\n".join(
                [
                    "SF:lib/core/a.dart",
                    "LF:10",
                    "LH:8",
                    "end_of_record",
                    "SF:lib/core/frb/generated.dart",
                    "LF:10",
                    "LH:0",
                    "end_of_record",
                    "SF:lib/ui.dart",
                    "LF:10",
                    "LH:0",
                    "end_of_record",
                ]
            ),
            include_prefix="lib/core/",
            exclude_prefixes=("lib/core/frb/",),
        )

        self.assertIn("SF:lib/core/a.dart", filtered)
        self.assertNotIn("SF:lib/core/frb/generated.dart", filtered)
        self.assertNotIn("SF:lib/ui.dart", filtered)

    def test_parseAdbDevices_keeps_installable_devices(self):
        devices = parseAdbDevices(
            "\n".join(
                [
                    "List of devices attached",
                    "emulator-5554 device product:sdk model:Pixel transport_id:1",
                    "adb-R5CN123._adb-tls-connect._tcp device product:phone model:Galaxy transport_id:2",
                    "10.0.0.2:5555 offline product:phone model:X transport_id:2",
                    "R3CN123 unauthorized usb:337641472X",
                ]
            )
        )
        self.assertEqual(
            [device.serial for device in devices],
            ["emulator-5554", "adb-R5CN123._adb-tls-connect._tcp"],
        )

    def test_command_sequence_parser_maps_numbered_input_in_order(self):
        build = DispatchBuild()
        self.assertEqual(
            build.parseCommandSequence("3 1 2,4"),
            ["serUp", "andBuild", "verUp", "webCov"],
        )

    def test_command_sequence_parser_rejects_invalid_numbers(self):
        build = DispatchBuild()
        for input_text in ("", "0", "5", "x", "1 x"):
            with self.subTest(input_text=input_text):
                with self.assertRaises(BuildError):
                    build.parseCommandSequence(input_text)

    def test_appendSelectedCommandNumber_keeps_ordered_input(self):
        self.assertEqual(appendSelectedCommandNumber("", 2), "3")
        self.assertEqual(appendSelectedCommandNumber("3", 0), "3 1")

    def test_commandInputAfterSpace_only_adds_selected_command_when_input_is_empty(self):
        self.assertEqual(commandInputAfterSpace("", 2), "3 ")
        self.assertEqual(commandInputAfterSpace("3", 0), "3 ")
        self.assertEqual(commandInputAfterSpace("3 ", 0), "3  ")

    def test_commandInputAfterSpace_adds_selected_command_after_selection_move(self):
        self.assertEqual(commandInputAfterSpace("3", 0, selection_moved_after_input=True), "3 1 ")
        self.assertEqual(commandInputAfterSpace("3 ", 1, selection_moved_after_input=True), "3 2 ")

    def test_space_selected_command_then_manual_number_parses_in_entered_order(self):
        build = DispatchBuild()
        input_text = commandInputAfterSpace("", 2) + "1"

        self.assertEqual(input_text, "3 1")
        self.assertEqual(build.parseCommandSequence(input_text), ["serUp", "andBuild"])

    def test_manual_number_then_selection_move_space_parses_in_entered_order(self):
        build = DispatchBuild()
        input_text = commandInputAfterSpace("3", 0, selection_moved_after_input=True) + "4"

        self.assertEqual(input_text, "3 1 4")
        self.assertEqual(build.parseCommandSequence(input_text), ["serUp", "andBuild", "webCov"])

    def test_path_config_resolves_configured_directories(self):
        build = DemoBuild()

        self.assertEqual(build.pathCfg.appDir, Path("/tmp/demo/client"))
        self.assertEqual(build.pathCfg.root, Path("/tmp/demo"))
        self.assertEqual(build.pathCfg.serDir, Path("/tmp/demo/server"))
        self.assertEqual(build.pathCfg.webDir, Path("/tmp/demo/console"))
        self.assertEqual(build.pathCfg.appPubspec, Path("/tmp/demo/client/pubspec.yaml"))
        self.assertIsNone(build.pathCfg.appBuildInfo)
        self.assertEqual(build.pathCfg.appCoverageInfo, Path("/tmp/demo/client/coverage/lcov.info"))
        self.assertEqual(build.pathCfg.appApkPath, Path("/tmp/demo/client/build/app/outputs/flutter-apk/app-release.apk"))
        self.assertEqual(build.pathCfg.appBundlePath, Path("/tmp/demo/app/build/app/outputs/bundle/release/app-release.aab"))
        self.assertEqual(build.pathCfg.appApksPath, Path("/tmp/demo/app/app-rel.apks"))
        self.assertEqual(build.pathCfg.appUniversalApkPath, Path("/tmp/demo/app/universal.apk"))
        self.assertEqual(build.pathCfg.appApkRelPath, Path("/tmp/demo/dist/android"))
        self.assertEqual(build.pathCfg.releaseRoot, Path("/tmp/demo/release"))
        self.assertEqual(build.pathCfg.apkPrefix, "demo")
        self.assertFalse(hasattr(build, "appPath"))
        self.assertFalse(hasattr(build, "appApkRelPath"))
        self.assertFalse(hasattr(build, "apkPrefix"))
        self.assertFalse(hasattr(build, "root"))

    def test_path_config_infers_root_from_build_class_module(self):
        build = InferredRootBuild()
        expected_root = Path(__file__).resolve().parent

        self.assertEqual(build.pathCfg.root, expected_root)
        self.assertEqual(build.pathCfg.appDir, expected_root / "client")

    def test_all_exports_only_core_api(self):
        self.assertEqual(
            gdev.__all__,
            [
                "AndroidCfg",
                "AndroidDevice",
                "AppVersion",
                "BuildError",
                "CoverageCfg",
                "DesktopCfg",
                "filterLcovRecords",
                "GatDev",
                "GatDevBase",
                "SshCfg",
                "ToolCmd",
            ],
        )

    def test_gatdev_inherits_command_declarations_from_base(self):
        self.assertTrue(issubclass(GatDev, GatDevBase))
        self.assertFalse(hasattr(GatDev, "Cmds"))
        self.assertFalse(hasattr(GatDevBase, "Cmds"))
        self.assertIs(GatDev.cmdAndBuild, GatDevBase.cmdAndBuild)

    def test_gatdev_inherits_shared_config_from_base(self):
        self.assertIs(GatDev.PathCfg, GatDevBase.PathCfg)

        for field_name in (
            "pathCfg",
            "androidCfg",
            "desktopCfg",
            "sshCfg",
            "coverageCfg",
            "writeBuildInfoBeforeBuild",
        ):
            with self.subTest(field_name=field_name):
                self.assertIn(field_name, GatDevBase.__dict__)
                self.assertNotIn(field_name, GatDev.__dict__)

    def test_grouped_config_dataclasses_and_tool_hook_are_resolved(self):
        class ConfigBuild(DemoBuild):
            androidCfg = AndroidCfg(
                driveTarget="test_driver/custom.dart",
                bundleTargetPlatforms=("android-arm64",),
                signingProperties="client/key.properties",
                bundletoolJar="/opt/bundletool.jar",
                googlePlayPackageName="demo.pkg",
            )
            desktopCfg = DesktopCfg(
                winDriveTarget="test_driver/custom_win.dart",
                macDriveTarget="test_driver/custom_mac.dart",
                winExeName="Demo.exe",
            )
            sshCfg = SshCfg(host="example.com", user="deploy")
            coverageCfg = CoverageCfg(
                minLines=90.0,
                appIncludePrefix="lib/core/",
                appExcludePrefixes=("lib/core/frb/",),
                serverIgnoreRegex=r"(/db\.rs)$",
            )

            def getToolCmd(self, cmd: str) -> str:
                match cmd:
                    case "flutter":
                        return "fvm flutter"
                    case "java":
                        return "/opt/java"
                    case _:
                        return super().getToolCmd(cmd)

        build = ConfigBuild()

        self.assertEqual(build.flutterCmd("test"), ["fvm", "flutter", "test"])
        self.assertEqual(build.javaCmd("-version"), ["/opt/java", "-version"])
        self.assertEqual(build.androidCfg.driveTarget, "test_driver/custom.dart")
        self.assertEqual(build.androidCfg.bundleTargetPlatforms, ("android-arm64",))
        self.assertEqual(build.androidCfg.googlePlayPackageName, "demo.pkg")
        self.assertEqual(build.desktopCfg.winDriveTarget, "test_driver/custom_win.dart")
        self.assertEqual(build.desktopCfg.macDriveTarget, "test_driver/custom_mac.dart")
        self.assertEqual(build.desktopCfg.winExeName, "Demo.exe")
        self.assertEqual(build.sshCfg.host, "example.com")
        self.assertEqual(build.sshCfg.user, "deploy")
        self.assertEqual(build.coverageCfg.minLines, 90.0)
        self.assertEqual(build.coverageCfg.appIncludePrefix, "lib/core/")
        self.assertEqual(build.coverageCfg.appExcludePrefixes, ("lib/core/frb/",))
        self.assertEqual(build.coverageCfg.serverIgnoreRegex, r"(/db\.rs)$")

    def test_desktop_config_excludes_task_only_mac_deploy_fields(self):
        config = DesktopCfg()

        for field_name in (
            "macAppPath",
            "macUnsignedPkg",
            "macSignedPkg",
            "macAppSignIdentity",
            "macProductSignIdentity",
            "macUploadCommand",
        ):
            with self.subTest(field_name=field_name):
                self.assertFalse(hasattr(config, field_name))
                self.assertFalse(hasattr(GatDev, field_name))

    def test_core_excludes_task_only_command_settings(self):
        for field_name in (
            "unitTestCommands",
            "webCovArgs",
            "sshAndroidDeployPath",
            "sshWindowsDeployPath",
            "toolCfg",
            "flutterBin",
            "cargoBin",
            "npmBin",
            "adbBin",
            "gatBin",
            "emulatorBin",
            "javaBin",
        ):
            with self.subTest(field_name=field_name):
                self.assertFalse(hasattr(GatDev, field_name))
                self.assertFalse(hasattr(SshCfg(), field_name))

    def test_google_play_settings_are_task_only(self):
        for field_name in (
            "googlePlayCfg",
            "googlePlayTrack",
            "googlePlayScope",
            "googlePlayAuthHost",
            "googlePlayAuthPort",
            "googlePlayCredentialFile",
            "googlePlayClientSecretsFile",
        ):
            with self.subTest(field_name=field_name):
                self.assertFalse(hasattr(GatDev, field_name))

        build = DemoBuild()
        self.assertTrue(hasattr(AndroidCfg(), "googlePlayPackageName"))
        self.assertFalse(hasattr(gdev, "GooglePlayCfg"))
        self.assertFalse(hasattr(GatDev, "cmdGooglePlayTrackList"))
        self.assertNotIn("test", build.commandNames())

    def test_legacy_flat_config_fields_still_work(self):
        class LegacyBuild(DemoBuild):
            androidDriveTarget = "test_driver/legacy.dart"
            sshDeployHost = "legacy.example.com"
            sshDeployUser = "legacy"
            coverageMinLines = 91.0

        build = LegacyBuild()

        self.assertEqual(build.androidCfg.driveTarget, "test_driver/legacy.dart")
        self.assertEqual(build.sshCfg.host, "legacy.example.com")
        self.assertEqual(build.sshCfg.user, "legacy")
        self.assertEqual(build.coverageCfg.minLines, 91.0)

    def test_tool_commands_use_overridable_hook(self):
        class ToolBuild(DemoBuild):
            def getToolCmd(self, cmd: str) -> str:
                match cmd:
                    case "flutter":
                        return "fvm flutter"
                    case _:
                        return super().getToolCmd(cmd)

        build = ToolBuild()

        self.assertFalse(hasattr(GatDev, "toolCfg"))
        self.assertEqual(build.getToolCmd("adb"), "adb")
        self.assertEqual(build.flutterCmd("test"), ["fvm", "flutter", "test"])
        self.assertEqual(build.adbCmd("devices"), ["adb", "devices"])

    def test_emulator_command_uses_android_sdk_root_when_not_on_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            emulator = Path(tmp_dir) / "emulator" / "emulator"
            emulator.parent.mkdir()
            emulator.write_text("#!/bin/sh\n", encoding="utf-8")

            with patch.dict("gdev.gatDev.os.environ", {"ANDROID_SDK_ROOT": tmp_dir}, clear=True):
                self.assertEqual(DemoBuild().emulatorCmd("-list-avds"), [str(emulator), "-list-avds"])

    def test_tool_cmd_builds_env_overridable_commands(self):
        with patch.dict("gdev.gatDev.os.environ", {"FLUTTER_BIN": "/opt/flutter/bin/flutter --suppress-analytics"}):
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

    def test_task_support_requires_cmd_override(self):
        self.assertFalse(DemoBuild().hasTask("webCov"))
        self.assertTrue(DispatchBuild().hasTask("webCov"))
        self.assertNotIn("webCov", DemoBuild().commandMap())
        self.assertIn("webCov", DispatchBuild().commandMap())

    def test_cmd_list_uses_project_method_definition_order(self):
        build = OrderedOnlyBuild()

        self.assertEqual(
            build.availableCmdList(),
            [
                "andBuild",
                "webCov",
                "macBuild",
                "customTask",
            ],
        )
        self.assertIn("macBuild", build.commandMap())
        self.assertIn("customTask", build.commandMap())

    def test_inherited_project_commands_are_not_exposed_by_child_class(self):
        build = SingleCommandBuild()

        self.assertEqual(build.availableCmdList(), ["andBuild"])

    def test_overridden_command_can_delegate_to_default_parent_implementation(self):
        build = SuperCommandBuild()
        calls: list[str] = []

        def mark(name: str):
            def run_command(*_args, **_kwargs):
                calls.append(name)

            return run_command

        self.assertTrue(build.hasTask("andTest"))
        with (
            patch.object(build, "doAndTest", side_effect=mark("unit")) as unit_mock,
            patch.object(build, "doAndIntegrationTest", side_effect=mark("integration")) as integration_mock,
        ):
            build.commandMap()["andTest"]()

        self.assertEqual(calls, ["unit"])
        unit_mock.assert_called_once_with(app_dir=build.pathCfg.appDir)
        integration_mock.assert_not_called()

    def test_default_and_test_runs_integration_when_project_has_integration_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "client/test_driver").mkdir(parents=True)

            class TmpBuild(SuperCommandBuildWithIntegration):
                pathCfg = GatDev.PathCfg(root=root, appDir="client")

                def cmdAndTest(self) -> None:
                    super().cmdAndTest()

            build = TmpBuild()
            calls: list[str] = []

            def mark(name: str):
                def run_command(*_args, **_kwargs):
                    calls.append(name)

                return run_command

            with (
                patch.object(build, "doAndTest", side_effect=mark("unit")) as unit_mock,
                patch.object(build, "doAndIntegrationTest", side_effect=mark("integration")) as integration_mock,
            ):
                build.commandMap()["andTest"]()

        self.assertEqual(calls, ["unit", "integration"])
        unit_mock.assert_called_once_with(app_dir=build.pathCfg.appDir)
        integration_mock.assert_called_once_with(
            app_dir=build.pathCfg.appDir,
            root_dir=build.pathCfg.root,
            drive_target=build.androidCfg.driveTarget,
        )

    def test_frb_generate_skips_when_bridge_api_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)

            class TmpBuild(DemoBuild):
                pathCfg = GatDev.PathCfg(root=root, appDir="client")

            build = TmpBuild()
            with patch.object(build, "run") as run_mock:
                build.doFrbGen()

        run_mock.assert_not_called()

    def test_frb_generate_uses_standard_project_paths_once(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)

            class TmpBuild(DemoBuild):
                pathCfg = GatDev.PathCfg(root=root, appDir="client")

            (root / "client/native/src").mkdir(parents=True)
            (root / "client/native/src/api.rs").write_text("pub fn api() {}\n", encoding="utf-8")
            (root / "client/ios/Runner").mkdir(parents=True)
            build = TmpBuild()
            with (
                patch.dict("gdev.gatDev.os.environ", {}, clear=True),
                patch.object(build, "run") as run_mock,
            ):
                build.doFrbGen()
                build.doFrbGen()

        run_mock.assert_called_once_with(
            [
                "flutter_rust_bridge_codegen",
                "generate",
                "--rust-root",
                str(root / "client/native"),
                "--rust-input",
                "crate::api",
                "--dart-output",
                str(root / "client/lib/core/frb"),
                "--rust-output",
                str(root / "client/native/src/frb_generated.rs"),
                "--dart-root",
                str(root / "client"),
                "--c-output",
                str(root / "client/ios/Runner/frb_generated.h"),
            ],
            cwd=root,
        )

    def test_default_android_commands_run_frb_generate(self):
        build = DemoBuild()

        with (
            patch.object(build, "doFrbGen") as frb_mock,
            patch.object(build, "doAndBuild") as build_mock,
        ):
            build.cmdAndBuild()

        frb_mock.assert_called_once_with()
        build_mock.assert_called_once_with(app_dir=build.pathCfg.appDir)

        build = DemoBuild()
        with (
            patch.object(build, "doFrbGen") as frb_mock,
            patch.object(build, "doAndTest") as test_mock,
            patch.object(build, "doAndIntegrationTest") as integration_mock,
        ):
            build.cmdAndTest()

        frb_mock.assert_called_once_with()
        test_mock.assert_called_once_with(app_dir=build.pathCfg.appDir)
        integration_mock.assert_not_called()

        build = DemoBuild()
        with (
            patch.object(build, "doFrbGen") as frb_mock,
            patch.object(build, "cmdAndTest") as and_test_mock,
            patch.object(build, "cmdSerTest") as ser_test_mock,
            patch.object(build, "cmdWebTest") as web_test_mock,
            patch.object(build, "cmdVerUp") as ver_up_mock,
            patch.object(build, "doAndBundleBuild") as bundle_mock,
            patch.object(build, "doAndDeploy") as deploy_mock,
        ):
            build.cmdAndDeploy()

        frb_mock.assert_called_once_with()
        and_test_mock.assert_called_once_with()
        ser_test_mock.assert_called_once_with()
        web_test_mock.assert_called_once_with()
        ver_up_mock.assert_called_once_with()
        bundle_mock.assert_called_once()
        deploy_mock.assert_called_once()

    def test_all_builtin_commands_have_cmd_placeholders(self):
        build = DemoBuild()

        for command in build.commandNames():
            with self.subTest(command=command):
                self.assertTrue(hasattr(GatDev, build.commandMethodName(command)))

    def test_cmd_wrapper_passes_named_args_to_do_method(self):
        build = DispatchBuild()

        with patch.object(build, "doWebCov") as do_mock:
            build.commandMap()["webCov"]()

        do_mock.assert_called_once_with(web_dir=build.pathCfg.webDir, npm_args=("run", "test:coverage"))

    def test_default_and_deploy_uses_android_config_package_name(self):
        class DeployBuild(DemoBuild):
            androidCfg = AndroidCfg(
                signingProperties="client/key.properties",
                bundletoolJar="/opt/bundletool.jar",
                googlePlayPackageName="demo.pkg",
            )

        build = DeployBuild()
        calls: list[str] = []

        def mark(name: str):
            def run_command(*_args, **_kwargs):
                calls.append(name)

            return run_command

        with (
            patch.object(build, "cmdAndTest", side_effect=mark("andTest")) as and_test_mock,
            patch.object(build, "cmdSerTest", side_effect=mark("serTest")) as ser_test_mock,
            patch.object(build, "cmdWebTest", side_effect=mark("webTest")) as web_test_mock,
            patch.object(build, "cmdVerUp", side_effect=mark("verUp")) as ver_up_mock,
            patch.object(build, "doAndBundleBuild", side_effect=mark("bundle")) as bundle_mock,
            patch.object(build, "doAndDeploy", side_effect=mark("publish")) as deploy_mock,
            patch.dict(
                "os.environ",
                {
                    "GOOGLE_PLAY_TRACK": "production",
                    "GOOGLE_PLAY_CREDENTIAL_FILE": "/tmp/demo/androidpublisher.dat",
                    "GOOGLE_PLAY_CLIENT_SECRETS_FILE": "/tmp/demo/client_secrets.json",
                    "GOOGLE_PLAY_SERVICE_ACCOUNT_FILE": "/tmp/demo/play-store-credentials.json",
                },
                clear=False,
            ),
        ):
            build.cmdAndDeploy()

        self.assertEqual(calls, ["andTest", "serTest", "webTest", "verUp", "bundle", "publish"])
        and_test_mock.assert_called_once_with()
        ser_test_mock.assert_called_once_with()
        web_test_mock.assert_called_once_with()
        ver_up_mock.assert_called_once_with()
        bundle_mock.assert_called_once_with(
            app_dir=build.pathCfg.appDir,
            root_dir=build.pathCfg.root,
            target_platforms=build.androidCfg.bundleTargetPlatforms,
            signing_properties=build.androidCfg.signingProperties,
            bundletool_jar=build.androidCfg.bundletoolJar,
        )
        deploy_mock.assert_called_once_with(
            package_name="demo.pkg",
            track="production",
            scope="https://www.googleapis.com/auth/androidpublisher",
            auth_host="localhost",
            auth_port=8080,
            credential_file="/tmp/demo/androidpublisher.dat",
            client_secrets_file="/tmp/demo/client_secrets.json",
            service_account_file="/tmp/demo/play-store-credentials.json",
            aab_path=build.pathCfg.appBundlePath,
        )

    def test_android_appbundle_build_clears_local_application_id_suffix(self):
        build = DemoBuild()

        with patch.object(build, "run") as run_mock:
            build.buildAndroidAppBundle(
                app_dir=build.pathCfg.appDir,
                target_platforms=("android-arm64", "android-x64"),
            )

        run_mock.assert_called_once_with(
            ToolCmd.flutter(
                "build",
                "appbundle",
                "--target-platform",
                "android-arm64,android-x64",
                "--android-project-arg",
                "gdevApplicationIdSuffix=",
            ),
            cwd=build.pathCfg.appDir,
        )

    def test_android_appbundle_universal_apk_uses_prod_release_names(self):
        build = DemoBuild()
        version = AppVersion(1, 2, 3, 10203)

        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "universal.apk"
            src.write_text("apk", encoding="utf-8")
            build.pathCfg.appApkRelPath.mkdir(parents=True, exist_ok=True)

            copied = build.copyAndroidUniversalApk(version, src)

        self.assertEqual(copied, build.pathCfg.appApkRelPath / "demo-prod-1.2.3+10203.apk")
        self.assertEqual((build.pathCfg.appApkRelPath / "demo-prod-1.2.3+10203.apk").read_text(), "apk")
        self.assertEqual((build.pathCfg.appApkRelPath / "latest-prod.apk").read_text(), "apk")

    def test_mac_deploy_wrapper_passes_task_only_named_args_to_do_method(self):
        build = MacDeployBuild()

        with patch.object(build, "doMacDeploy") as do_mock:
            build.commandMap()["macDeploy"]()

        do_mock.assert_called_once_with(
            mac_app_path="app/build/macos/Build/Products/Release/Demo.app",
            mac_unsigned_pkg="app/Demo.unsigned.pkg",
            mac_signed_pkg="app/Demo.pkg",
            mac_app_sign_identity="Developer ID Application: Demo",
            mac_product_sign_identity="3rd Party Mac Developer Installer: Demo",
            mac_upload_command=("upload", "app/Demo.pkg"),
        )

    def test_do_and_deploy_uses_named_google_play_task_settings(self):
        build = DemoBuild()
        service = object()

        with (
            patch.object(build, "googlePlayService", return_value=service) as service_mock,
            patch("gdev.google_play.publishBundle") as publish_mock,
        ):
            build.doAndDeploy(
                package_name="demo.pkg",
                track="internal",
                scope="https://scope.example",
                auth_host="localhost",
                auth_port=8080,
                credential_file="client/androidpublisher.dat",
                client_secrets_file="client/client_secrets.json",
                aab_path="client/build/app.aab",
            )

        service_mock.assert_called_once_with(
            credential_file="client/androidpublisher.dat",
            client_secrets_file="client/client_secrets.json",
            scope="https://scope.example",
            auth_host="localhost",
            auth_port=8080,
            service_account_file=None,
        )
        publish_mock.assert_called_once_with(
            service=service,
            package_name="demo.pkg",
            track="internal",
            aab_path=Path("/tmp/demo/client/build/app.aab"),
        )

    def test_do_and_deploy_requires_google_play_package_name(self):
        with self.assertRaisesRegex(BuildError, "package name"):
            DemoBuild().doAndDeploy(
                package_name="",
                track="internal",
                scope="https://scope.example",
                auth_host="localhost",
                auth_port=8080,
                credential_file="client/androidpublisher.dat",
                client_secrets_file="client/client_secrets.json",
                aab_path="client/build/app.aab",
            )

    def test_google_play_service_uses_explicit_service_account_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            service_account_path = root / "service-account.json"
            service_account_path.write_text("{}", encoding="utf-8")

            class TmpBuild(DemoBuild):
                pathCfg = GatDev.PathCfg(root=root, appDir="client")

            service = object()
            build = TmpBuild()
            with (
                patch("gdev.google_play.buildServiceFromServiceAccount", return_value=service) as service_account_mock,
                patch("gdev.google_play.buildService") as oauth_mock,
            ):
                result = build.googlePlayService(
                    credential_file="client/androidpublisher.dat",
                    client_secrets_file="client/client_secrets.json",
                    service_account_file="service-account.json",
                    scope="https://scope.example",
                    auth_host="localhost",
                    auth_port=8080,
                )

        self.assertIs(result, service)
        service_account_mock.assert_called_once_with(
            service_account_path=service_account_path,
            scope="https://scope.example",
        )
        oauth_mock.assert_not_called()

    def test_google_play_service_uses_default_service_account_file_when_present(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            default_path = root / "client/play-store-credentials.json"
            default_path.parent.mkdir(parents=True)
            default_path.write_text("{}", encoding="utf-8")

            class TmpBuild(DemoBuild):
                pathCfg = GatDev.PathCfg(root=root, appDir="client")

            service = object()
            build = TmpBuild()
            with (
                patch("gdev.google_play.buildServiceFromServiceAccount", return_value=service) as service_account_mock,
                patch("gdev.google_play.buildService") as oauth_mock,
            ):
                result = build.googlePlayService(
                    credential_file="client/androidpublisher.dat",
                    client_secrets_file="client/client_secrets.json",
                    scope="https://scope.example",
                    auth_host="localhost",
                    auth_port=8080,
                )

        self.assertIs(result, service)
        service_account_mock.assert_called_once_with(
            service_account_path=default_path,
            scope="https://scope.example",
        )
        oauth_mock.assert_not_called()

    def test_google_play_service_falls_back_to_oauth_when_service_account_is_absent(self):
        build = DemoBuild()
        service = object()

        with (
            patch("gdev.google_play.buildServiceFromServiceAccount") as service_account_mock,
            patch("gdev.google_play.buildService", return_value=service) as oauth_mock,
        ):
            result = build.googlePlayService(
                credential_file="client/androidpublisher.dat",
                client_secrets_file="client/client_secrets.json",
                scope="https://scope.example",
                auth_host="localhost",
                auth_port=8080,
            )

        self.assertIs(result, service)
        service_account_mock.assert_not_called()
        oauth_mock.assert_called_once_with(
            client_secrets_path=Path("/tmp/demo/client/client_secrets.json"),
            credential_path=Path("/tmp/demo/client/androidpublisher.dat"),
            scope="https://scope.example",
            host="localhost",
            port=8080,
        )

    def test_google_play_service_rejects_missing_explicit_service_account_file(self):
        with self.assertRaisesRegex(BuildError, "service account file"):
            DemoBuild().googlePlayService(
                credential_file="client/androidpublisher.dat",
                client_secrets_file="client/client_secrets.json",
                service_account_file="missing-service-account.json",
                scope="https://scope.example",
                auth_host="localhost",
                auth_port=8080,
            )

    def test_ser_cov_passes_ignore_regex_to_cargo_llvm_cov(self):
        class CovBuild(DemoBuild):
            coverageCfg = CoverageCfg(minLines=90.0, serverIgnoreRegex=r"(/db\.rs)$")

            def cmdSerCov(self) -> None:
                super().cmdSerCov()

        build = CovBuild()

        with patch.object(build, "run") as run_mock:
            build.cmdSerCov()

        run_mock.assert_called_once_with(
            [
                "cargo",
                "llvm-cov",
                "--ignore-filename-regex",
                r"(/db\.rs)$",
                "--fail-under-lines",
                "90",
                "--summary-only",
            ],
            cwd=build.pathCfg.serDir,
        )

    def test_do_web_cov_runs_configured_npm_coverage_command(self):
        build = DispatchBuild()

        with patch.object(build, "run") as run_mock:
            build.doWebCov(web_dir=build.pathCfg.webDir, npm_args=("run", "coverage"))

        run_mock.assert_called_once_with(["npm", "run", "coverage"], cwd=build.pathCfg.webDir)

    def test_future_annotations_import_is_not_used(self):
        source = Path(gdev.gatDev.__file__).read_text(encoding="utf-8")

        self.assertNotIn("from __future__ import annotations", source)

    def test_optional_google_play_and_ssh_helpers_are_split_from_core(self):
        source = Path(gdev.gatDev.__file__).read_text(encoding="utf-8")

        self.assertNotIn("from http.server import", source)
        self.assertNotIn("import webbrowser", source)
        self.assertNotIn("import mimetypes", source)
        self.assertNotIn("from coPy.coSsh import CoSsh", source)

    def test_release_apk_filename_uses_project_prefix(self):
        self.assertFalse(hasattr(GatDev, "apkNameFormat"))
        self.assertEqual(DemoBuild().apkFileName(AppVersion(1, 0, 1, 10001)), "demo-1.0.1+10001.apk")

    def test_release_apk_filename_uses_overridable_method(self):
        self.assertFalse(hasattr(BundleBuild, "apkNameFormat"))
        self.assertEqual(BundleBuild().apkFileName(AppVersion(1, 0, 1, 10001)), "demo-1.0.1.apk")

    def test_properties_file_parser_reads_gradle_signing_values(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "key.properties"
            path.write_text(
                "\n".join([
                    "# comment",
                    "storeFile=/tmp/key.jks",
                    "storePassword : secret",
                    "keyAlias=upload",
                    "keyPassword=secret2",
                ]),
                encoding="utf-8",
            )
            self.assertEqual(
                readPropertiesFile(path),
                {
                    "storeFile": "/tmp/key.jks",
                    "storePassword": "secret",
                    "keyAlias": "upload",
                    "keyPassword": "secret2",
                },
            )

    def test_bundletool_command_uses_project_paths_and_signing_properties(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)

            class TmpBundleBuild(BundleBuild):
                pathCfg = GatDev.PathCfg(root=root, appDir="client", appPubspec="client/pubspec.yaml")

            (root / "client").mkdir()
            (root / "client/key.properties").write_text(
                "\n".join([
                    "storeFile=/tmp/key.jks",
                    "storePassword=store-pass",
                    "keyAlias=upload",
                    "keyPassword=key-pass",
                ]),
                encoding="utf-8",
            )

            build = TmpBundleBuild()
            cmd = build.bundletoolBuildApksCommand(
                signing_properties="client/key.properties",
                bundletool_jar="/opt/bundletool.jar",
                app_bundle_path=build.pathCfg.appBundlePath,
                app_apks_path=build.pathCfg.appApksPath,
            )
            self.assertEqual(cmd[:4], ["java", "-jar", "/opt/bundletool.jar", "build-apks"])
            self.assertIn(f"--bundle", cmd)
            self.assertIn(str(root / "app/build/app/outputs/bundle/release/app-release.aab"), cmd)
            self.assertIn("--ks-pass=pass:store-pass", cmd)
            self.assertIn("--key-pass=pass:key-pass", cmd)

    def test_update_build_info_writes_flutter_constants(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)

            class TmpBuild(DemoBuild):
                pathCfg = GatDev.PathCfg(root=root, appDir="client", appPubspec="client/pubspec.yaml", appBuildInfo="client/lib/buildInfo.dart")

            (root / "client/lib").mkdir(parents=True)
            (root / "client/pubspec.yaml").write_text("name: demo\nversion: 1.2.3+10203\n", encoding="utf-8")
            with patch("gdev.gatDev.datetime.datetime") as datetime_mock:
                datetime_mock.now.return_value.strftime.return_value = "26-05-01T12"
                TmpBuild().updateBuildInfo()
            self.assertEqual(
                (root / "client/lib/buildInfo.dart").read_text(encoding="utf-8"),
                "// 00 will be 0\nfinal g_version = '1.2.3';\nfinal g_buildDate = '26-05-01T12';",
            )

    def test_ffi_comment_toggle_comments_yaml_and_dart_markers(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)

            class TmpBuild(DemoBuild):
                pathCfg = GatDev.PathCfg(root=root)

            (root / "lib").mkdir()
            (root / "lib/db.dart").write_text("final x = 1; ##ffiCmt\n", encoding="utf-8")
            (root / "pubspec.yaml").write_text("  sqflite: any ##ffiCmt\n", encoding="utf-8")
            (root / "pubspec.lock").write_text("lock", encoding="utf-8")

            build = TmpBuild()
            build.sqfliteFfiCommentOut(
                ffi_comment_files=("lib/db.dart", "pubspec.yaml"),
                ffi_lockfile="pubspec.lock",
            )
            self.assertEqual((root / "lib/db.dart").read_text(encoding="utf-8"), "//final x = 1; ##ffiCmt")
            self.assertEqual((root / "pubspec.yaml").read_text(encoding="utf-8"), "  #sqflite: any ##ffiCmt")
            self.assertFalse((root / "pubspec.lock").exists())
            self.assertTrue((root / "pubspec.lock.bak").exists())

            build.sqfliteFfiRestore(
                ffi_comment_files=("lib/db.dart", "pubspec.yaml"),
                ffi_lockfile="pubspec.lock",
            )
            self.assertEqual((root / "lib/db.dart").read_text(encoding="utf-8"), "final x = 1; ##ffiCmt")
            self.assertEqual((root / "pubspec.yaml").read_text(encoding="utf-8"), "  sqflite: any ##ffiCmt")
            self.assertTrue((root / "pubspec.lock").exists())

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
                self.assertEqual(build.doAndInstall(apk_path=apk), device)
        run_mock.assert_called_once()

    def test_andInstall_auto_installs_adb_tcp_devices_before_selection(self):
        build = DemoBuild()
        auto_device = AndroidDevice(
            "adb-R5CN123._adb-tls-connect._tcp",
            "device",
            "model:Galaxy",
        )
        selected_device = AndroidDevice("emulator-5554", "device", "model:Pixel")
        devices = [auto_device, selected_device]
        with tempfile.TemporaryDirectory() as tmp_dir:
            apk = Path(tmp_dir) / "app.apk"
            apk.write_text("apk", encoding="utf-8")

            with (
                patch.object(build, "listAndroidDevices", return_value=devices),
                patch.object(build, "run") as run_mock,
            ):
                def select_device(input_devices):
                    self.assertEqual(input_devices, devices)
                    self.assertEqual(run_mock.call_count, 1)
                    return selected_device

                with patch.object(build, "selectAndroidDevice", side_effect=select_device):
                    self.assertEqual(build.doAndInstall(apk_path=apk), selected_device)

        self.assertEqual(
            run_mock.call_args_list,
            [
                call(
                    ToolCmd.adb("-s", auto_device.serial, "install", "-r", "-d", str(apk)),
                    cwd=build.pathCfg.root,
                ),
                call(
                    ToolCmd.adb("-s", selected_device.serial, "install", "-r", "-d", str(apk)),
                    cwd=build.pathCfg.root,
                ),
            ],
        )

    def test_andInstall_does_not_reinstall_auto_device_when_selected(self):
        build = DemoBuild()
        auto_device = AndroidDevice(
            "adb-R5CN123._adb-tls-connect._tcp",
            "device",
            "model:Galaxy",
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            apk = Path(tmp_dir) / "app.apk"
            apk.write_text("apk", encoding="utf-8")
            with (
                patch.object(build, "listAndroidDevices", return_value=[auto_device]),
                patch.object(build, "selectAndroidDevice", return_value=auto_device),
                patch.object(build, "run") as run_mock,
            ):
                self.assertEqual(build.doAndInstall(apk_path=apk), auto_device)

        run_mock.assert_called_once_with(
            ToolCmd.adb("-s", auto_device.serial, "install", "-r", "-d", str(apk)),
            cwd=build.pathCfg.root,
        )

    def test_main_without_command_requires_tty(self):
        build = DemoBuild()
        with (
            patch("gdev.gatDev.sys.stdin", FakeTty(False)),
            patch("gdev.gatDev.sys.stdout", FakeTty(False)),
            patch("gdev.gatDev.sys.stderr", FakeTty(False)),
            patch.object(build, "selectCommandSequenceTui") as select_mock,
        ):
            self.assertEqual(build.main([]), 1)
        select_mock.assert_not_called()

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
