# Marea on Windows

Start with the [Windows desktop guide](DESKTOP.md) for requirements, native
pleamar builds, installation, updates, controls and the capability matrix.
The port is under development; the guide distinguishes implemented features
from limited integrations and hardware checks that remain unverified.

The current integration includes upstream Marea `0e23c6c`, pleamar 0.2.27
and pleamar-wm 0.2.28. The generated Windows profile preserves the new control
labels, roles, values and checked states. Two Spanish keys already supplied
by upstream were removed from the companion translation file to avoid a
duplicate-definition error. See [scheduled tasks and named credentials](TASKS.md)
for their native behavior and remaining unattended-input limits.

With the matching Windows WM, `pleamar-wm agent scenes` discovers Marea and
`agent tree PID json` describes her visible controls. Use names from that tree
with `agent press` or `agent say`; scene commands use the existing scene/Luau
handlers. They do not add an independent desktop keyboard or mouse. The local
native metadata check rendered the actual generated Spanish control center
and dragged a volume slider through isolated Luau logic on DISPLAY2. It denied
all device services and sent no physical input; this is not hardware or full
installed-product acceptance. Final integration CI is still pending.

The new upstream chat is being integrated separately; see its
[Windows agent status and validation](AGENT.md). Packaging now includes its
native host and locked SDK; full account and desktop interaction validation
remains pending.

The upstream chat/memory changes through `90e4f4b` are integrated: reading-paced
answers, the corrected input position, and Settings > What she remembers.
Memory uses the native files service under `%APPDATA%/pleamar/marea-desktop`.
The Windows settings grid scrolls so startup and keyboard shortcuts remain
reachable. Shared memory logic and a real isolated storage roundtrip passed;
the Spanish memory/settings/chat layouts were captured from owned D3D12 windows
on DISPLAY2. These checks use fixture data and do not establish signed-in model
or physical mouse/keyboard acceptance. Failed writes now preserve the current
conversation and saved memories; corrupt storage stays untouched and reports
an error. Archive names remain distinct within the same second, and partial
deletions retain the files that could not be removed. All 300 bounded memories
are reachable in pages of 24 rows, including after deleting the last page.
Seven native storage/error cases, shared logic tests, and six DISPLAY2 captures
passed; the captures used fixtures and sent no physical input.

The Windows profile workflow also runs `test-profile-ui-ci.py` on its disposable
GitHub-hosted desktop, using the optimized distribution build with default Luau.
It renders the generated control center, Windows-key
settings and six chat/settings states, checks translated control metadata,
drags the volume slider through named scene input and checks that a long chat
keeps its final row visible. All services are denied and the Luau logic uses
fixture data, so it cannot change a device, enable a keyboard hook or contact
a model. The artifact contains screenshots, scene trees, logs and a report;
its pixels still need visual review. The script refuses local desktops. This
is UI integration coverage, not physical input or full product acceptance.

The upstream third-copy change (`6e9dd41`) is integrated. On Windows the three
copies map to native monitors; brightness selection, window overview and the
wallpaper transition now include the third monitor. A transition prepares all
three sizes before it opens and rejects a display removed or renamed during
preparation. Isolated Luau tests cover those routes. Three-monitor hardware and
mixed-DPI acceptance remain separate; the Linux phone/virtual-output compositor
is not provided by this native Windows companion yet.

When the home monitor disappears, the Windows profile falls back to a live
copy without replacing the saved monitor name; it returns when that monitor
reappears. Following a window on an unrepresented output also falls back home.
Brightness selection follows these Lua-driven moves explicitly, avoids repeat
commands when the target is unchanged and ignores stale failures from a previous
selection. The isolated routing regression covers unplug/replug, a zero-output
interval and delayed completions; real hardware hotplug still needs validation.

Upstream `a355d17` also keeps the destination surface open before its arrival
animation starts. This lets its rules bring Marea back when the old surface
disappears with a disconnected monitor. The generated Windows profile retains
that condition; it does not depend on the Linux phone transport.

From the repository root, after preparing the native x64/MSVC pleamar build
with default Luau and its app-local runtime files:

```powershell
cargo build --release --locked --manifest-path deriva/Cargo.toml
# Prepare the native AI host, Node and SDK as shown in windows/DESKTOP.md.
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

An experimental native `pleamar-wm` session can now supply automatic per-monitor
layouts. When its Windows executable is available beside pleamar and its
session is running, Marea's context menu and finder expose the supported
layout/restore actions. Capability detection never enables Linux-only rain,
snow, ride or agent-seat actions. The adapter has passed isolated logic tests
and a real Luau/IPC test arranging owned windows on DISPLAY2. The package now bundles the CLI and a small background host, with recovery
tied to the exact Marea process. Full Marea UI acceptance and compositor-effect
parity remain pending. Updating these sources does not update an existing
installed preview.

Settings > Keyboard shortcuts offers an optional dedicated Windows-key layer,
off by default. It reserves Win and its combinations for Marea while she runs.
See the [shortcut behavior and validation](SHORTCUTS.md); physical shortcut and
foreground acceptance are still pending, separate from the tested native hook
lifetime and rendered settings page.

Upstream's `agent open --monitor` integration is retained for the Linux WM.
Windows currently keeps the native ordinary application launcher; an explicit
launch-monitor request fails before launching instead of claiming placement or
keyboard isolation. Its worker describes this limitation. Native monitor-aware
startup without stealing focus remains part of the unfinished WM port. Shared
chat launch results now preserve OS failures, cancellation and the WM's stop
decision, and do not launch a second copy after an unrecognized success reply.

AI assistance: the Windows port and its validation tools were developed with
Codex. This branch is not an upstream Marea Windows release.


The Windows launcher sets `PLEAMAR_MEDIA_NAME=Marea` unless it is already set.
This preserves `Pictures/Marea`, `Videos/Marea` and the `marea-` filename prefix
with the generic pleamar capture backend. Existing captures and recordings are
not moved; launching pleamar directly uses its own default unless you set the
variable in that PowerShell session.
