# gdev

`gdev` is a small local Python package for project build scripts that need:

- numbered command TUI
- Flutter version bumping
- Android APK build/copy/install
- Android appbundle + bundletool universal APK export
- Flutter desktop/web/iOS build wrappers
- app/server/web test and coverage commands
- `gat` server run command wrapping
- grouped project config via `AndroidCfg`, `DesktopCfg`, and `SshCfg`
- tool command customization via `getToolCmd(cmd)`

Projects should keep their own thin `gat_dev.py` file and subclass `gdev.GatDev`.
Project commands are exposed by overriding `cmdXxx()` methods; reusable build
logic lives in `doXxx(...)` helpers.
The `gdev` launcher runs the current directory's `gat_dev.py`.

See [manual.md](manual.md) for the full usage notes.
