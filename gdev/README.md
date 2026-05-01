# gdev

`gdev` is a small local Python package for project build scripts that need:

- numbered command TUI
- Flutter version bumping
- Android APK build/copy/install
- app/server/web test and coverage commands
- `gat` server run command wrapping

Projects should keep their own thin `gat_dev.py` file and subclass `gdev.GatDev`.
The `gdev` launcher runs the current directory's `gat_dev.py`.

See [manual.md](manual.md) for the full usage notes.
