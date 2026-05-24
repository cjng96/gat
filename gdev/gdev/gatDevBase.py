import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import ClassVar


@dataclass(frozen=True)
class AndroidCfg:
    driveTarget: str = "test_driver/and.dart"
    bundleTargetPlatforms: tuple[str, ...] = ("android-arm", "android-arm64", "android-x64")
    signingProperties: str | Path | None = None
    bundletoolJar: str | Path | None = None
    googlePlayPackageName: str | None = None


@dataclass(frozen=True)
class DesktopCfg:
    winDriveTarget: str = "test_driver/win.dart"
    macDriveTarget: str = "test_driver/mac.dart"
    ffiCommentFiles: tuple[str | Path, ...] = ()
    ffiLockfile: str | Path | None = None
    macPreBuildCommands: tuple[tuple[str | Path, tuple[str, ...]], ...] = ()
    macConfigOnly: bool = True
    winReleaseSource: str | Path = "app/build/windows/x64/runner/Release"
    winExeName: str | None = None
    winExtraFiles: tuple[str | Path, ...] = ()
    winNsiCommand: tuple[str, ...] = ()


@dataclass(frozen=True)
class SshCfg:
    host: str | None = None
    port: int = 22
    user: str | None = None


@dataclass(frozen=True)
class CoverageCfg:
    minLines: float = 80.0
    appIncludePrefix: str | None = None
    appExcludePrefixes: tuple[str, ...] = ()
    serverIgnoreRegex: str | None = None


'''
cmdAndDeploy같은 함수를 오버라이딩하면 기능이 동작한다.
기본적으로는 super.cmdAndDeploy()를 호출하면 기본형으로 동작한다.
혹시 커스터마이징이 필요하면, 해당 함수의 여기본문을 가져다가 수정해서 쓴다.
'''
class GatDevBase:
    @dataclass(frozen=True)
    class PathCfg:
        root: str | Path | None = None
        appDir: str | Path = "app"
        serDir: str | Path = "ser"
        webDir: str | Path = "web"
        appPubspec: str | Path = "app/pubspec.yaml"
        appBuildInfo: str | Path | None = None
        appCoverageInfo: str | Path = "app/coverage/lcov.info"
        appApkPath: str | Path = "app/build/app/outputs/flutter-apk/app-release.apk"
        appBundlePath: str | Path = "app/build/app/outputs/bundle/release/app-release.aab"
        appApksPath: str | Path = "app/app-rel.apks"
        appUniversalApkPath: str | Path = "app/universal.apk"
        appApkRelPath: str | Path = "release/android"
        releaseRoot: str | Path = "release"
        apkPrefix: str = "app"

        def resolve(self, inferred_root: str | Path | None = None) -> "GatDevBase.PathCfg":
            root = self.root if self.root is not None else inferred_root
            root_path = Path.cwd() if root is None else Path(root)
            if not root_path.is_absolute():
                root_path = Path.cwd() / root_path

            def path(value: str | Path) -> Path:
                p = Path(value)
                return p if p.is_absolute() else root_path / p

            values = {}
            for field in fields(self):
                value = getattr(self, field.name)
                if field.name == "root":
                    values[field.name] = root_path
                elif field.name == "apkPrefix" or value is None:
                    values[field.name] = value
                else:
                    values[field.name] = path(value)
            return type(self)(**values)

    pathCfg: ClassVar[PathCfg] = PathCfg()
    androidCfg: ClassVar[AndroidCfg] = AndroidCfg()
    desktopCfg: ClassVar[DesktopCfg] = DesktopCfg()
    sshCfg: ClassVar[SshCfg] = SshCfg()
    coverageCfg: ClassVar[CoverageCfg] = CoverageCfg()
    androidDriveTarget: ClassVar[str] = "test_driver/and.dart"
    winDriveTarget: ClassVar[str] = "test_driver/win.dart"
    macDriveTarget: ClassVar[str] = "test_driver/mac.dart"
    writeBuildInfoBeforeBuild: ClassVar[bool] = False
    buildInfoDateFormat: ClassVar[str] = "%y-%m-%dT%H"
    androidBundleTargetPlatforms: ClassVar[tuple[str, ...]] = ("android-arm", "android-arm64", "android-x64")
    androidSigningProperties: ClassVar[str | Path | None] = None
    bundletoolJar: ClassVar[str | Path | None] = None
    sshDeployHost: ClassVar[str | None] = None
    sshDeployPort: ClassVar[int] = 22
    sshDeployUser: ClassVar[str | None] = None
    ffiCommentFiles: ClassVar[tuple[str | Path, ...]] = ()
    ffiLockfile: ClassVar[str | Path | None] = None
    macPreBuildCommands: ClassVar[tuple[tuple[str | Path, tuple[str, ...]], ...]] = ()
    macConfigOnly: ClassVar[bool] = True
    winReleaseSource: ClassVar[str | Path] = "app/build/windows/x64/runner/Release"
    winExeName: ClassVar[str | None] = None
    winExtraFiles: ClassVar[tuple[str | Path, ...]] = ()
    winNsiCommand: ClassVar[tuple[str, ...]] = ()

    def cmdUnitTest(self) -> None:
        self.doUnitTest(unit_test_commands=getattr(self, "unitTestCommands", ()))

    def cmdAndBuild(self) -> None:
        self.doAndBuild(app_dir=self.pathCfg.appDir)

    def cmdVerUp(self) -> None:
        self.doVerUp(root_dir=self.pathCfg.root, app_pubspec=self.pathCfg.appPubspec)

    def cmdSerUp(self) -> None:
        self.doSerUp(ser_dir=self.pathCfg.serDir, ser_up_args=getattr(self, "serUpArgs", ("prod", "run")))

    def cmdAndInstall(self) -> None:
        self.doAndInstall()

    def cmdAndDeploy(self) -> None:
        self.cmdAndTest()
        self.cmdSerTest()
        self.cmdWebTest()
        self.cmdVerUp()
        self.doAndBundleBuild(
            app_dir=self.pathCfg.appDir,
            root_dir=self.pathCfg.root,
            target_platforms=self.androidCfg.bundleTargetPlatforms,
            signing_properties=self.androidCfg.signingProperties,
            bundletool_jar=self.androidCfg.bundletoolJar,
        )
        self.doAndDeploy(
            package_name=os.environ.get("GOOGLE_PLAY_PACKAGE_NAME", self.androidCfg.googlePlayPackageName or ""),
            track=os.environ.get("GOOGLE_PLAY_TRACK", "internal"),
            scope=os.environ.get("GOOGLE_PLAY_SCOPE", "https://www.googleapis.com/auth/androidpublisher"),
            auth_host=os.environ.get("GOOGLE_PLAY_AUTH_HOST", "localhost"),
            auth_port=int(os.environ.get("GOOGLE_PLAY_AUTH_PORT", "8080")),
            credential_file=os.environ.get("GOOGLE_PLAY_CREDENTIAL_FILE", "app/androidpublisher.dat"),
            client_secrets_file=os.environ.get("GOOGLE_PLAY_CLIENT_SECRETS_FILE", "app/client_secrets.json"),
            aab_path=self.pathCfg.appBundlePath,
        )
        # self.doCommandSequence(commands=("andTest", "serTest", "webTest", "verUp", "andBuild"))

    def cmdAndTest(self) -> None:
        self.doAndTest(app_dir=self.pathCfg.appDir)
        if self.hasAndroidIntegrationTest():
            self.doAndIntegrationTest(
                app_dir=self.pathCfg.appDir,
                root_dir=self.pathCfg.root,
                drive_target=self.androidCfg.driveTarget,
            )
        else:
            print("\nAndroid integration test skipped: no test_driver or integration_test directory")

    def hasAndroidIntegrationTest(self) -> bool:
        return (self.pathCfg.appDir / "test_driver").is_dir() or (
            self.pathCfg.appDir / "integration_test"
        ).is_dir()

    def cmdWinTest(self) -> None:
        self.doWinTest(app_dir=self.pathCfg.appDir, drive_target=self.desktopCfg.winDriveTarget)

    def cmdMacTest(self) -> None:
        self.doMacTest(app_dir=self.pathCfg.appDir, drive_target=self.desktopCfg.macDriveTarget)

    def cmdSerTest(self) -> None:
        self.doSerTest(ser_dir=self.pathCfg.serDir)

    def cmdWebTest(self) -> None:
        self.doWebTest(web_dir=self.pathCfg.webDir)

    def cmdWinBuild(self) -> None:
        self.doWinBuild(
            app_dir=self.pathCfg.appDir,
            release_root=self.pathCfg.releaseRoot,
            win_release_source=self.desktopCfg.winReleaseSource,
            win_exe_name=self.desktopCfg.winExeName,
            win_extra_files=self.desktopCfg.winExtraFiles,
            win_nsi_command=self.desktopCfg.winNsiCommand,
        )

    def cmdWinDeploy(self) -> None:
        self.doWinDeploy(
            release_root=self.pathCfg.releaseRoot,
            apk_prefix=self.pathCfg.apkPrefix,
            deploy_path=getattr(self, "sshWindowsDeployPath", None),
        )

    def cmdMacBuild(self) -> None:
        self.doMacBuild(
            app_dir=self.pathCfg.appDir,
            ffi_comment_files=self.desktopCfg.ffiCommentFiles,
            ffi_lockfile=self.desktopCfg.ffiLockfile,
            mac_pre_build_commands=self.desktopCfg.macPreBuildCommands,
            mac_config_only=self.desktopCfg.macConfigOnly,
        )

    def cmdMacXcodeBuild(self) -> None:
        self.doMacXcodeBuild(app_dir=self.pathCfg.appDir)

    def cmdMacFfiRestore(self) -> None:
        self.doMacFfiRestore(
            ffi_lockfile=self.desktopCfg.ffiLockfile,
            ffi_comment_files=self.desktopCfg.ffiCommentFiles,
        )

    def cmdMacDeploy(self) -> None:
        self.doMacDeploy(
            mac_app_path=self.requiredTaskSetting("macAppPath"),
            mac_unsigned_pkg=self.requiredTaskSetting("macUnsignedPkg"),
            mac_signed_pkg=self.requiredTaskSetting("macSignedPkg"),
            mac_app_sign_identity=getattr(self, "macAppSignIdentity", None),
            mac_product_sign_identity=getattr(self, "macProductSignIdentity", None),
            mac_upload_command=getattr(self, "macUploadCommand", ()),
        )

    def cmdLinuxBuild(self) -> None:
        self.doLinuxBuild(app_dir=self.pathCfg.appDir, release_root=self.pathCfg.releaseRoot)

    def cmdIosBuild(self) -> None:
        self.doIosBuild(app_dir=self.pathCfg.appDir)

    def cmdIosDeploy(self) -> None:
        self.doIosDeploy(app_dir=self.pathCfg.appDir, upload_command=self.requiredTaskSetting("iosUploadCommand"))

    def cmdWebBuild(self) -> None:
        self.doWebBuild(app_dir=self.pathCfg.appDir)

    def cmdAppCov(self) -> None:
        self.doAppCov(
            app_dir=self.pathCfg.appDir,
            coverage_info=self.pathCfg.appCoverageInfo,
            coverage_name="app",
            include_prefix=self.coverageCfg.appIncludePrefix,
            exclude_prefixes=self.coverageCfg.appExcludePrefixes,
        )

    def cmdSerCov(self) -> None:
        self.doSerCov(
            ser_dir=self.pathCfg.serDir,
            coverage_min_lines=self.coverageCfg.minLines,
            ignore_regex=self.coverageCfg.serverIgnoreRegex,
        )

    def cmdWebCov(self) -> None:
        self.doWebCov(web_dir=self.pathCfg.webDir, npm_args=getattr(self, "webCovArgs", ("run", "test:coverage")))

    def cmdAllCov(self) -> None:
        self.doAllCov(commands=getattr(self, "allCovCommands", ("appCov", "serCov", "webCov")))
