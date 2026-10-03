# Marea on Windows

Start with the [Windows desktop guide](DESKTOP.md) for requirements, native
pleamar builds, installation, updates, controls and the capability matrix.
The port is under development; the guide distinguishes implemented features
from limited integrations and hardware checks that remain unverified.

From the repository root, after preparing the native x64/MSVC pleamar build
with default Luau and its app-local runtime files:

```powershell
cargo build --release --locked --manifest-path deriva/Cargo.toml
.\install-windows.ps1 -PleamarBinary ..\pleamar\target\release\pleamar.exe
```

`install-windows.ps1` delegates to `install-desktop.ps1`; both install the same
desktop profile and preserve existing destinations. Use `update-desktop.ps1`
to update an existing desktop installation with a backup. The previous limited
window preview is no longer a source installation option. Existing preview
installations and their separate settings are not removed or migrated.

`build-desktop.py` generates `marea-desktop.plm` and `marea-desktop.luau` from the
upstream scenes and the adapters here. Those generated files are not tracked;
the installer and logic checks regenerate them. Linux uses the original files.

AI assistance: the Windows port and its validation tools were developed with
Codex. This branch is not an upstream Marea Windows release.
