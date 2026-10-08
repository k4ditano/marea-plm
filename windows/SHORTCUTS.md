# Windows-key shortcuts

Open Settings > Keyboard shortcuts and enable **Use the Windows key for Marea**.
The switch is off by default. While enabled, Win is dedicated to Marea:

| Key | Action |
| --- | --- |
| Win, or Win+Space | Search |
| Win+Shift+A | Chat |
| Win+A | Control center |
| Win+I | Settings |
| Win+Tab | Window overview (requires the native WM session) |
| Win+D | Show/hide the application dock on Marea's home monitor |
| Win+N | Notifications |
| Win+W | Toggle tiled/free windows on the monitor under the pointer (requires the native WM session) |
| Win+M | Minimize the active application on a managed monitor in free-window mode |
| Win+Shift+M | Restore the last minimized application still inside the native WM session |
| Win+Left or Win+Up | Previous eligible window on the active application's monitor |
| Win+Right or Win+Down | Next eligible window on that monitor |
| Win+Q | Ask the active application or dialog to close |

Unassigned Win combinations are consumed too; Start and Windows' corresponding
shortcuts are replaced while Marea owns the layer. Disable the switch to restore
them. Closing Marea releases the hook; no registry keyboard remapping is made.
Ctrl+Alt+Space remains the normal search shortcut. Set `MAREA_SEARCH_HOTKEY`
before launch to change that fallback, or set it empty to disable it.

The choice is saved in `%APPDATA%\pleamar\marea-desktop\shortcuts.json` after
native readback. Saving failures are visible and keep the current session's
choice; a failed save does not undo a successful opt-out. Restart uses only a
recognized version-1 preference. A conflicting owner, registration error or
timeout is shown instead of reporting success. This requires the corresponding
pleamar Windows-key API; older engines report the option unavailable.

The minimize/restore shortcuts require the native WM session. Its bounded
history follows actual Windows minimize events, including the application's
own minimize button; closed or already restored windows are removed. It tracks
only windows in that session's monitor/process scope, and starts empty after
a session restart. Restoration uses the native restore state, including a
window minimized from maximized. Windows still controls foreground permission.

Navigation requires the native WM session too. It preserves a stable cycle in
free mode and follows the layout order in tiled mode; minimized, hidden and
disabled windows are skipped. It does not leave an active modal dialog or cross
the session's monitor/process scope. Rapid navigation requests are serialized
in a bounded queue; a failure cancels the remaining requests. Closing uses the
application's normal close request, so unsaved-work prompts remain available.
These source changes do not establish physical Win-key dispatch acceptance.

## Verification

```powershell
python windows/test-logic.py --binary ..\pleamar\target\release\pleamar.exe --luau-runner ..\pleamar\target\release\examples\luau-test.exe
```

The isolated suites include the shortcut profile, saved opt-in/default-off,
native readback, failed storage/native calls, duplicate/stale callbacks, timeout
recovery, action routing and custom/disabled fallback. Win+W sends the native
pointer-monitor command even when cached availability is stale, and reports
native failures instead of silently acting on Marea's home monitor. The generated scene keeps
the upstream settings enum order; a regression assertion guards page titles.

Four actual D3D12/WGC views on non-primary DISPLAY2 were inspected: the scrolled
settings grid, disabled/enabled switch and storage error. The native foreground
window stayed unchanged. These used fixture states, not live key remapping.
The engine separately tests hook registration and cleanup on a private desktop.
Physical key dispatch, foreground focus, elevated applications, games and secure
desktop transitions remain unverified. These checks do not establish complete
Windows/Linux parity. The installed preview is not updated by source edits.

AI assistance: implemented and reviewed with Codex.
