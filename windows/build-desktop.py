"""Generate a native desktop profile; keep the upstream Linux files untouched."""
from pathlib import Path
import re
import json
import runpy

root = Path(__file__).resolve().parents[1]
sources = runpy.run_path(str(root / 'windows/profile-source.py'))
scene = sources['scene_source'](root / 'marea.plm')
logic = sources['logic_source'](root)
scene, logic = runpy.run_path(str(root / 'windows/sound-profile.py'))['apply'](scene, logic, root)
scene, logic = runpy.run_path(str(root / 'windows/radio-profile.py'))['apply'](scene, logic)

def replace_once(source, old, new):
    assert source.count(old) == 1, f'Upstream changed: {old[:80]}'
    return source.replace(old, new, 1)

def remove_between(source, begin, end, replacement=''):
    start = source.index(begin)
    stop = source.index(end, start)
    return source[:start] + replacement + source[stop:]

# A transparent time-dependent shader still forces full-panel repainting.
# Match its own early return while preserving the fade and working animation.
scene = replace_once(scene, 'shader chat_tide { at:',
    'shader chat_tide { show: chat.stir > 0.001; at:')

scene = remove_between(scene, '    surface lockscreen {', '    // ── the adventure\'s stage')
# Native output removal changes screens.count even when an old name remains in
# the scene. Rebuild the live set without overwriting the user's saved home.
logic = remove_between(logic, 'local function decide()', '--  Her wardrobe\'s pieces', '''local function decide()
    local count = math.min(tonumber(fact["screens.count"]) or 0, 3)
    local wanted = pointed or focused
    local chosen = nil
    for k = 0, count - 1 do
        if monitors[k + 1] ~= nil then
            if chosen == nil or k == fact.home then chosen = k end
        end
    end
    if fact.following == true then
        for k = 0, count - 1 do
            if monitors[k + 1] == wanted then chosen = k end
        end
    end
    for k = 0, 2 do fact["hosts." .. k] = k == chosen end
    -- Lua writes do not echo fact events to their own subscribers.
    if chosen ~= nil then select_brightness_monitor(chosen) end
    tell_island()
end

''')
logic = remove_between(logic, 'local function place()', '-- ── the stones:', '''local function place()
    local count = math.min(tonumber(fact["screens.count"]) or 0, 3)
    fact.home = 0
    for k = 0, 2 do
        local name = text["screen." .. k .. ".name"]
        monitors[k + 1] = if k < count and name ~= nil and name ~= "" then name else nil
        if monitors[k + 1] ~= nil and name == settings.home then fact.home = k end
    end
    fact.following = settings.follow == true
    fact.taking_room = settings.room == true
    decide()
end
for k = 0, 2 do on("text:screen." .. k .. ".name", place) end
on("fact:screens.count", place)
place()

''')
scene = re.sub(r'^        run: .*$', '        run: "node", "deriva-worker", "marea-agent", "pleamar-wm", "curl.exe", "powershell.exe"', scene, flags=re.M)
logic = replace_once(logic, '''    local base = sys.ask("env", "XDG_STATE_HOME")
    if base == nil or base == "" then base = home_dir .. "/.local/state" end
    local STATE = base .. "/marea-plm/agent"''', '''    local base = sys.ask("env", "LOCALAPPDATA")
    if base == nil or base == "" then error("Marea's agent needs LOCALAPPDATA") end
    local STATE = base .. "/Marea/Agent"''')
logic = replace_once(logic, 'image = { path = "/state/" .. name }', 'image = { path = STATE .. "/" .. name }')
scene = replace_once(scene, '    fact language:', (root / 'windows/startup.plm').read_text(encoding='utf-8') + '\n    fact language:')
scene = replace_once(scene, '    fact language:', (root / 'windows/shortcuts.plm').read_text(encoding='utf-8') + '\n    fact language:')
scene = replace_once(scene, '    fact language:', '    event windows_toggle_autohide ->\n    fact language:')
settings_start = scene.index('                    page menu "Settings" {')
settings_end = scene.index('                    // ── where she lives ──', settings_start)
settings_menu = scene[settings_start:settings_end]
assert settings_menu.count(', cell.w, h: 90) {') == 8, 'The settings tile list changed'
assert 'width: 456; row: 90' in settings_menu
# Keep every Windows setting reachable
# inside the card instead of letting the startup control fall below its edge.
settings_menu = replace_once(settings_menu, '''                        grid {
                            at: card.x - 228, card.top + 98; columns: 2; gap: 10; width: 456; row: 90''', '''                        column windows_settings_list {
                            at: card.x - 228, card.top + 98
                            view: 456, 390
                            grid {
                            at: 0, 0; columns: 2; gap: 10; width: 456; row: 90''')
settings_menu = replace_once(settings_menu, '''                        }
                    }
''', (root / 'windows/startup-row.plm').read_text(encoding='utf-8') + (root / 'windows/shortcuts-row.plm').read_text(encoding='utf-8') + '''                        }
                        }
                        text "↓" { at: card.x + 239, card.top + 476; anchor: center; size: 15; color: mint; show: windows_settings_list.content - windows_settings_list.scroll > 391 }
                    }
''')
settings_menu = replace_once(settings_menu, '                            Tile("Her look",',
    (root / 'windows/auto-hide-row.plm').read_text(encoding='utf-8') + '                            Tile("Her look",')
scene = scene[:settings_start] + settings_menu + scene[settings_end:]
# Append the page without renumbering the upstream section enum or its titles.
scene = replace_once(scene, '''                    }
                }
            }

            // ── the agents' reservoirs''', '''                    }
''' + (root / 'windows/shortcuts-page.plm').read_text(encoding='utf-8') + '''                }
            }

            // ── the agents' reservoirs''')
scene = replace_once(scene, '"What she remembers") { at: px0',
    '"What she remembers", "Keyboard shortcuts") { at: px0')
scene = replace_once(scene, 'text "Reading your windows…" {', 'text windows_agents_status {')
scene = replace_once(scene, 'She talks with you, and can use your desktop with hands of her own.',
    'She talks with you. Desktop actions share your mouse and keyboard.')
logic = replace_once(logic, 'if g.observed then\n                local ago = now - g.observed', '''if #g.limits == 0 then table.insert(parts, "Sin datos de cuota") end
            if g.observed and g.observed <= now then
                local ago = now - g.observed''')
logic = replace_once(logic, 'local fresh = g and g.observed and now - g.observed < 900', 'local fresh = g and g.observed and now >= g.observed and now - g.observed < 900')
scene = scene.replace('"network",', '"network", "network.*", "bluetooth", "bluetooth.*",')
scene = scene.replace('"apps.launch",', '"apps.*", "desktop.*",')
logic = replace_once(logic, 'local chat_desktop = nil', 'local chat_desktop = install_desktop_agent(native_sys)')
logic = replace_once(logic, '    local function perform(id, tool, args, row)\n', '''    local function perform(id, tool, args, row)
        if running_task and (tool == "open_app" or (tool:sub(1, 8) == "desktop_" and tool ~= "desktop_windows" and tool ~= "desktop_look")) then
            finish_row(row, false)
            answer(id, false, "Unattended desktop input is not available on Windows. The shared keyboard and pointer must remain with the user. Ask them to continue in a normal chat.")
            return
        end
''')
task_start = logic.index('    -- ── her tasks:')
task_end = logic.index('    -- ── what the panel asks', task_start)
tasks = logic[task_start:task_end]
tasks = remove_between(tasks, '    local function notice(title, body, actions, then_)', '\n    local run_task',
    (root / 'windows/task-notices.luau').read_text(encoding='utf-8') + '\n')
logic = logic[:task_start] + tasks + logic[task_end:]
scene = replace_once(scene, 'She does these on her own at their time. Ask her in the chat: «every day at 8:00, …».',
    'Scheduled chat and reading; unattended desktop control is pending.')
logic = remove_between(logic, '    --  The passwords you saved for her tasks', '    --  What goes to her in every conversation',
    (root / 'windows/chat-credentials.luau').read_text(encoding='utf-8') + '\n')
# Native typing consumes the credential inside pleamar. Neither Luau nor the
# worker receives the saved value or launches a secret-tool subprocess.
logic = remove_between(logic, '        if tool == "desktop_type_secret" then', '        local argv = agent_args(', '')
scene = replace_once(scene, '"files", "files.write"', '"files", "credentials.*", "files.write"')
scene = replace_once(scene, 'model keys.rows max 12 { name: text }', '''model keys.rows max 12 { name: text; token: number }
    fact keys.page = 1
    fact keys.pages = 1
    fact keys.count = 0
    fact keys.readable = false
    text keys.page_label = ""
    event keys_page ->
    event keys_page_changed''')
scene = replace_once(scene, 'text "{keys.rows.count}"', 'text "{keys.count}"')
keys_start = scene.index('                    page keys "')
keys_end = scene.index('                    // ── what she remembers', keys_start)
keys = scene[keys_start:keys_end]
keys = replace_once(keys, 'emit drop(r.index)', 'emit drop(r.token)')
keys = replace_once(keys, 'show: keys.rows.count < 1', 'show: keys.rows.count < 1 and keys.readable')
keys = replace_once(keys, 'width: 456; lines: 1 }', 'width: 456; lines: 2 }')
keys = replace_once(keys, '                        //  A new one:', '''                        on keys_page_changed { keys_list.scroll: 0 ~0ms }
                        group {
                            show: keys.pages > 1
                            text keys.page_label { at: card.x, card.top + 382; anchor: center; size: 10; color: st.faint }
                            text "Previous" { at: card.x - 180, card.top + 382; anchor: center; size: 10; color: mint; show: keys.page > 1 }
                            text "Next" { at: card.x + 180, card.top + 382; anchor: center; size: 10; color: mint; show: keys.page < keys.pages }
                            zone box keys_prev { at: card.x - 180, card.top + 382; size: 90, 18; cursor: pointer; active: keys.page > 1 }
                            zone box keys_next { at: card.x + 180, card.top + 382; size: 90, 18; cursor: pointer; active: keys.page < keys.pages }
                            on press keys_prev { emit keys_page(-1) }
                            on press keys_next { emit keys_page(1) }
                        }
                        //  A new one:''')
scene = scene[:keys_start] + keys + scene[keys_end:]
for first, windows in [('"dolphin"', '"explorer", "file explorer"'), ('"kitty"', '"windows terminal", "powershell", "command prompt"'), ('"zen"', '"microsoft edge"'), ('"gnome-text-editor"', '"notepad", "bloc de notas"')]:
    logic = replace_once(logic, 'apps = { ' + first, 'apps = { ' + windows + ', ' + first)
scene = scene.replace('"apps.*",', '"apps.*", "search.*", "shell.open", "hotkeys", "hotkeys.*", "wallpaper.*", "screenshot.*", "recording.*", "clipboard.set",')
scene = replace_once(scene, 'model icons max 8 { icon: image 22, 22; title: text }', 'model icons max 8 { icon: image 22, 22; title: text; more: bool }')
scene = replace_once(scene, 'image i.icon { at: 3, 3 - rise * 1.5; size: 22, 22 }', '''image i.icon { at: 3, 3 - rise * 1.5; size: 22, 22; show: not i.more }
            group {
                show: i.more
                repeat dot in 0..3 {
                    ellipse { at: 6 + dot * 8, 14; radius: 1.8; color: ink }
                }
            }''')
assert 'fact skin: lens | liquid | classic = classic' in scene
assert 'fact hidden = true' in scene
scene = replace_once(scene, '    service media as playback', '''    model windows_media_cover max 1 { pic: image 112, 112 }
    fact windows_media_has_art = false
    service media as playback''')
scene = replace_once(scene, '''                //  The cover, which here is a gradient: there is no artwork yet.
                body {
                    gradient: radial x0 + 28, by - 6 radius 44, #e8c9a8, #6f8f7d
                    box { at: x0 + 28, by; size: 56, 56; corner: 12 }
                }''', '''                box { at: x0 + 28, by; size: 56, 56; corner: 12; color: #242628 }
                text "♪" { at: x0 + 28, by; anchor: center; size: 28; color: mint; show: not windows_media_has_art }
                for cover in windows_media_cover {
                    image cover.pic { at: x0 + 4, by - 24; size: 48, 48 }
                }''')
scene = replace_once(scene, 'fact demo = true', 'fact demo = false')
# The main Marea panels are only 820x680; their screen facts are not the
# full wallpaper area. Publish each tide surface's actual measured geometry.
scene = replace_once(scene, 'model tidepics max 1 { pic: image 1280, 720 }', '''model tidepics max 3 { pic: image 1280, 720 }
    repeat k in 0..3 {
        fact windows_tide_width.$k = 0
        fact windows_tide_height.$k = 0
    }''')
scene = replace_once(scene, '        let tw = tide.width\n        let th = tide.height', '''        let tw = tide.width
        let th = tide.height
        on change tw { windows_tide_width.$screen = tw }
        on change th { windows_tide_height.$screen = th }''')
scene = replace_once(scene, '            for t in tidepics {\n                group {', '''            for t in tidepics {
                group {
                    show: t.index == screen.index''')
# A flattened water ellipse still casts a wide SDF shadow. Once detached,
# the edge geometry must leave the body as well as becoming visually thin.
scene = replace_once(scene, 'ellipse tether { at: cx, 0; radius: 30;', 'ellipse tether { at: cx, 0; radius: if(wet > 0.01, 30, 0);')
scene = scene.replace('radius: 9; scale: 1, ripple.h / 9;', 'radius: if(ripple.h > 0.1, 9, 0); scale: 1, ripple.h / 9;')
# Pointer feedback belongs to the render thread, independent of device polling.
scene = replace_once(scene, '    prop bright_level = 0 ~quick', '''    repeat k in 0..3 {
        fact windows_level_available.$k = false
        fact windows_level_pending.$k = false
        fact windows_level_drag.$k = false
        prop windows_level_target.$k = 0 ~16ms
    }
    prop bright_level = 0 ~quick''')
# The fourth upstream level controls pleamar-wm's rain shader. There is no
# Windows compositor equivalent yet; only the three native device levels bind.
scene = replace_once(scene, 'repeat k in 0..4 {\n                let step = 66 - 14 * four', 'repeat k in 0..3 {\n                let step = 66 - 14 * four')
scene = replace_once(scene, 'let val = pick(k, bright_level, vol_level, mic_level, rain_level)', 'let val = if(windows_level_available.$k, if(windows_level_pending.$k, windows_level_target.$k, pick(k, display.level, sound.volume, sound.input)), 0)')
scene = replace_once(scene, 'let avail = if(k == 0, if(display.present, 1, 0), 1)', 'let avail = if(windows_level_available.$k, 1, 0)')
scene = replace_once(scene, 'text "{val * 100, 0}%" { at: sx, iy + 42; anchor: center; size: 11.5; weight: 500; color: mint }', '''text "{val * 100, 0}%" { at: sx, iy + 42; anchor: center; size: 11.5; weight: 500; color: mint; show: windows_level_available.$k }
                text "—" { at: sx, iy + 42; anchor: center; size: 11.5; color: ink; opacity: 0.4; show: not windows_level_available.$k }''')
scene = replace_once(scene, 'zone box track.$k { at: sx, track_top + track_h / 2; size: 34 - 6 * four, track_h + 18; corner: 17; cursor: pointer; active: content > 0.9 and (k < 3 or rain_on)', 'zone box track.$k { at: sx, track_top + track_h / 2; size: 34, track_h + 18; corner: 17; cursor: pointer; active: content > 0.9 and windows_level_available.$k')
scene = replace_once(scene, 'zone box icon.$k { at: sx, iy; size: 30, 30; corner: 15; cursor: pointer; active: content > 0.9 and (k < 3 or rain_on)', 'zone box icon.$k { at: sx, iy; size: 30, 30; corner: 15; cursor: pointer; active: content > 0.9 and (k == 0 or windows_level_available.$k)')
for gesture in ('press', 'drag'):
    scene = replace_once(scene, f'            on {gesture} track.3 {{ emit set_rain(finger.0) }}\n', '')
logic = replace_once(logic, '''do
    local ok, where = pcall(sys.ask, "env", "PLEAMAR_SOCKETS")
    in_wm = ok and type(where) == "string" and where:find("pleamar%-pleamar") ~= nil
end''', '-- An inherited Linux socket hint cannot provide a Windows compositor.')
logic = remove_between(logic, 'on("set_rain", function(v)', '--  From her finder:',
    'on("set_rain", function() notice("El efecto de lluvia de pleamar-wm no está disponible en Windows.") end)\n')
for k, event in enumerate(('set_brightness', 'set_volume', 'set_mic')):
    for gesture in ('press', 'drag'):
        scene = replace_once(scene, f'on {gesture} track.{k} {{ emit {event}(finger.0) }}',
            f'on {gesture} track.{k} {{ windows_level_pending.{k} = true; windows_level_drag.{k} = true; windows_level_target.{k}: finger.0 ~16ms; emit {event}(finger.0) }}')
    scene = scene.replace(f'            on drag track.{k}', f'            on release track.{k} {{ windows_level_drag.{k} = false; windows_level_pending.{k} = true; windows_level_target.{k}: finger.0 ~16ms; emit {event}(finger.0) }}\n            on drag track.{k}', 1)
scene = replace_once(scene, 'on lock { locked = true }', 'on lock { emit windows_lock }')
scene = replace_once(scene, 'on record { purpose = nook; asleep = false; play retire }', 'on record while not windows_recording_busy { purpose = nook; asleep = false; play retire }')
scene = replace_once(scene, 'on snap { purpose = shot;', 'on snap while not windows_capture_busy { windows_capture_busy = true; windows_notice = false; purpose = shot;')
# Windows owns authentication; never present a custom password prompt as a lock.
scene = replace_once(scene, 'on to_lock { section = lock }', 'on to_lock { emit windows_lock_info }')
scene = scene.replace('pick(with_exit, "Password only", "Safety net on")', '"Windows"')
# Windows frosts the captured background in the existing lens pipeline. Flat
# glass uses the same capture with refraction disabled; no compositor blur API.
scene = replace_once(scene, 'let bends = skin == lens', 'let bends = skin != classic')
scene = replace_once(scene, '        lens: bends', '        lens: bends\n        refraction: if(skin == lens, 1, 0)\n        dispersion: if(skin == lens, 1, 0)')
# Native radio state is independent of an Ethernet Internet connection.
scene = scene.replace('follow lit.1 = if(net.online, 1, 0)', '')
scene = scene.replace('active: content > 0.9 and k < 3', 'active: content > 0.9 and k < 3 and ((k == 1 and windows_wifi_present) or (k == 2 and windows_bluetooth_present))')
# A missing adapter opens its explanation; it is not a radio switched off.
radio = '((k == 1 and windows_wifi_present) or (k == 2 and windows_bluetooth_present))'
scene = replace_once(scene, 'size: if(k < 3, 40, 12), 23', f'size: if({radio}, 40, 12), 23')
scene = replace_once(scene, 'color: mix(#2a2b2c, mint, lit.$k); show: k < 3', f'color: mix(#2a2b2c, mint, lit.$k); show: {radio}')
scene = replace_once(scene, 'color: #ffffff; show: k < 3', f'color: #ffffff; show: {radio}')
scene = replace_once(scene, 'stroke: 1.6; opacity: 70%; show: k > 2', f'stroke: 1.6; opacity: 70%; show: not {radio}')
scene = replace_once(scene, 'text bt.sub {', 'text windows_bluetooth_summary {')
scene = scene.replace('text title.1 = "Wi-Fi"', 'text title.1 = "Red"')
# A paused session still needs a play button, otherwise it cannot be resumed.
scene = replace_once(scene, '                show: playback.playing', '                show: windows_media_available')
scene = scene.replace('show: not playback.playing', 'show: not windows_media_available')
for x in (162, 170):
    scene = replace_once(scene, f'box {{ at: card.x + {x}, by; size: 3.4, 14; corner: 1.7; color: ink }}', f'box {{ show: playback.playing; at: card.x + {x}, by; size: 3.4, 14; corner: 1.7; color: ink }}')
scene = replace_once(scene, '                path { at: bx3 - 6, by - 7;', '                path { show: not playback.playing; at: card.x + 161, by - 7; color: ink; move 0, 0; line 12, 7; line 0, 14; close }\n                path { at: bx3 - 6, by - 7;')
for button, capability in [('prev_btn', 'previous'), ('play_btn', 'toggle'), ('next_btn', 'next')]:
    pattern = rf'(zone box {button} \{{[^\n]*active: content > 0\.9)'
    scene, count = re.subn(pattern, rf'\1 and windows_media_can_{capability}', scene)
    if count != 1: raise RuntimeError(f'Expected one media button: {button}')
for prefix, capability in [
    ('path { at: bx1 - 6, by - 7;', 'previous'), ('box { at: bx1 - 8, by;', 'previous'),
    ('ellipse { at: card.x + 166, by;', 'toggle'),
    ('box { show: playback.playing; at: card.x + 162, by;', 'toggle'),
    ('box { show: playback.playing; at: card.x + 170, by;', 'toggle'),
    ('path { show: not playback.playing; at: card.x + 161, by - 7;', 'toggle'),
    ('path { at: bx3 - 6, by - 7;', 'next'), ('box { at: bx3 + 10, by;', 'next'),
]:
    scene = replace_once(scene, prefix, prefix + f' opacity: if(windows_media_can_{capability}, 1, 0.3);')
scene = replace_once(scene, 'text "Nothing playing" { at: card.x, by;', 'text windows_media_status { at: card.x, by;')
scene = replace_once(scene, 'on press icon.1 { emit mute_output }', 'on press icon.0 { emit windows_display_info }\n            on press icon.1 { emit mute_output }')
# A row slot can hold another notice after a native update. Its gesture state
# belongs to that identity, and pressing must not resolve a row before release.
scene = replace_once(scene, '        fact alive.$k = true', '        fact alive.$k = true\n        fact windows_row_revision.$k = 0')
scene = replace_once(scene, '            on press row_zone.$k { emit resolve(k) }', '')
scene = replace_once(scene, 'opacity: rise.$k * (1 - flung.$k)', 'opacity: rise.$k * (1 - abs(flung.$k))')
scene = replace_once(scene, 'active: tray > 0.9 and visible.$k > 0.5', 'active: tray > 0.9 and visible.$k > 0.5 and alive.$k and abs(flung.$k) < 0.05')
scene = replace_once(scene, '        on drag row_zone.$k while alive.$k', '''        on change windows_row_revision.$k {
            pull.$k: 0 ~0ms; flung.$k: 0 ~0ms; freed.$k: 0 ~0ms; touch.$k: 0 ~0ms
        }
        on drag row_zone.$k while alive.$k''')

scene = replace_once(scene, 'scene Marea {', 'scene Marea {\n    text windows_search_status = ""\n' + (root / 'windows/media-volume.plm').read_text(encoding='utf-8'))
scene = replace_once(scene, '        //  The selection is ONE single one', '        text windows_search_status { at: bx0 + 594, by0 + 126; anchor: right center; width: 480; lines: 1; size: 10; color: #8b8f95 }\n        //  The selection is ONE single one')
scene = replace_once(scene, 'let by = card.top + 466', 'let by = card.top + 455')
scene = replace_once(scene, '                on press next_btn { emit next }', '                on press next_btn { emit next }\n' + (root / 'windows/media-volume-row.plm').read_text(encoding='utf-8'))
scene = scene.replace('by - 9; anchor: left center; size: 12.5; width: 130;', 'by - 9; anchor: left center; size: 12.5; width: 250;')
scene = scene.replace('by + 10; anchor: left center; size: 11; width: 130;', 'by + 10; anchor: left center; size: 11; width: 250;')
scene = replace_once(scene, 'Each piece chases in its own way: the hat rests, the glasses stay stuck on, the mug keeps her company and the headphones go on air when the screen is shared.', 'Choose a hat or headphones. Glasses and the cup can be combined with either.')
# Minimized applications can fold into Marea while retaining a reachable count.
scene = replace_once(scene, '    model stones max 6', (root / 'windows/window-shelf.plm').read_text(encoding='utf-8') + '\n    model stones max 6')
scene = replace_once(scene, 'landed.$k and not open and not searching and not tray_open', 'landed.$k and not windows_shelf_folded and not open and not searching and not tray_open')
scene = replace_once(scene, 'let sx.$k = cx - r - 24 - place.stone.$k * 34', 'let sx.$k = cx - (r + 24 + place.stone.$k * 34) * windows_shelf_unfold')
scene = replace_once(scene, 'active: stone.$k > 0.6', 'active: stone.$k > 0.6 and not windows_shelf_folded')
# A visible status explains unsupported actions instead of logging invisible errors.
notice = '''    text windows_status = ""
    text windows_agents_status = "Leyendo las cuotas de agentes…"
    fact windows_initialized = false
    fact windows_deriva_loaded = false
    fact windows_deriva_busy = false
    text windows_deriva_status = "Deriva: esperando al servicio de biblioteca."
    fact windows_capture_busy = false
    fact windows_recording_busy = false
    fact windows_notifications_allowed = false
    fact windows_notifications_requesting = false
    fact windows_notifications_requestable = false
    fact windows_notifications_sync = false
    text windows_notifications_status = "Leyendo el permiso de notificaciones…"
    event windows_notifications_enable ->
    text windows_capture_path = ""
    fact windows_notice = false
    fact windows_media_available = false
    fact windows_media_busy = false
    fact windows_media_can_toggle = false
    fact windows_media_can_previous = false
    fact windows_media_can_next = false
    text windows_media_status = ""
    fact windows_wifi_present = false
    fact windows_wifi_strength = 0
    fact windows_bluetooth_present = false
    fact windows_bluetooth_pages = false
    fact windows_bluetooth_previous = false
    fact windows_bluetooth_next = false
    text windows_bluetooth_page = ""
    text windows_bluetooth_warning = ""
    event windows_bluetooth_page ->
    text windows_wifi_status = "Leyendo Wi-Fi…"
    text windows_bluetooth_status = "Leyendo Bluetooth…"
    text windows_bluetooth_summary = "Leyendo dispositivos…"
    event windows_display_info ->
    event windows_lock ->
    event windows_lock_info ->
'''
scene = replace_once(scene, '    clip inset 2 box { at: card.x, card.y; size: card.w, card.h; corner: card.corner }', notice + '\n    clip inset 2 box { at: card.x, card.y; size: card.w, card.h; corner: card.corner }')
# Draw notices after the card contents. Earlier placement put media artwork
# and transport controls over the message and let clicks reach them beneath it.
notice_overlay = '''    group {
        show: open and content > 0.9 and windows_notice
        box { at: card.x, card.top + card.h - 48; size: card.w - 32, 80; corner: 8; color: #20282a }
        text windows_status { at: card.x - 222, card.top + card.h - 48; anchor: left center; width: 416; lines: 4; size: 11; color: #e8c07a }
        text "×" { at: card.x + 218, card.top + card.h - 48; anchor: center; size: 18; color: ink }
        zone box windows_notice_dismiss { at: card.x, card.top + card.h - 48; size: card.w - 32, 80; corner: 8; cursor: pointer }
        on press windows_notice_dismiss { windows_notice = false }
    }

'''
scene = replace_once(scene, "    // ── the adventure's stage", notice_overlay + "    // ── the adventure's stage")
scene = replace_once(scene,
    'text "Quiet ones still arrive: they go to their drop, without a card." { at: card.x - 228, card.top + 116; anchor: left center; size: 12; color: st.faint }',
    '''text windows_notifications_status { at: card.x - 228, card.top + 116; anchor: left center; width: if(windows_notifications_requestable, 332, 456); lines: 2; size: 11; color: st.faint }
                        group {
                            show: windows_notifications_requestable
                            box notification_enable { at: card.x + 173, card.top + 115; size: 110, 30; corner: 12; color: mint; cursor: pointer }
                            text "Permitir" { at: card.x + 173, card.top + 115; anchor: center; size: 12; color: coal }
                            on press notification_enable { emit windows_notifications_enable }
                        }''')
scene = scene.replace('"Only the urgent ones get through"', '"Silencia los avisos dentro de Marea"')
scene = scene.replace('"None of them ends up in your video or your call. Locked, always quiet"',
    '"Marea se silencia. Los banners de Windows se gestionan en Windows"')
scene = replace_once(scene, 'text "Open" { at: cx.i, f.top + 58;', 'text "Abrir app" { at: cx.i, f.top + 58;')

# Scroll listeners receive the wheel for every enclosing zone, but a press
# goes to the last declared zone. Keep the gallery's scroll area behind cards.
wall_areas = re.findall(r'(?m)^[ \t]*zone box walls_area \{[^\n]*\}', scene)
assert len(wall_areas) == 1, 'Upstream wallpaper scroll area changed'
wall_area = wall_areas[0]
scene = replace_once(scene, wall_area + '\n', '')
scene = replace_once(scene, '                show: page == walls\n                grid {',
                     '                show: page == walls\n' + wall_area + '\n                grid {')

scene, logic = runpy.run_path(str(root / 'windows/deriva-profile.py'))['apply'](scene, logic, root)
logic = remove_between(logic, '-- ── the system tray', '-- ── the photograph',
    (root / 'windows/tray.luau').read_text(encoding='utf-8') + '\n\n')
logic = remove_between(logic, '--  In the pictures folder', '-- ── the recording',
    (root / 'windows/screenshots.luau').read_text(encoding='utf-8') + '\n\n')
logic = remove_between(logic, '-- ── the recording', '-- ── the desktop wallpaper',
    (root / 'windows/recording.luau').read_text(encoding='utf-8') + '\n\n')
logic = remove_between(logic, '-- ── the stones:', 'if not sys.watch("window",',
    (root / 'windows/window-shelf.luau').read_text(encoding='utf-8') + '\n\n')
logic = replace_once(logic, 'function() if hooks.wm_restore then hooks.wm_restore() end end, "wm"',
    'function() if hooks.wm_restore then hooks.wm_restore() end end')
logic = replace_once(logic, 'local apps = {}', 'local search_match = (function()\n' + (root / 'windows/search-match.luau').read_text(encoding='utf-8') + '\nend)()\nlocal apps = {}')
logic = remove_between(logic, 'local function own_matches(q)', 'if not sys.watch("apps"',
    (root / 'windows/search.luau').read_text(encoding='utf-8') + '\n')
logic = replace_once(logic, 'after(600, playBatch)', 'fact.demo = false -- Never substitute demo notices for unavailable native data')
logic = replace_once(logic, 'local CATEGORY_OF = { TELEGRAM = 1, MAIL = 2, CALENDAR = 3, SYSTEM = 4 }',
    'local CATEGORY_OF = { TELEGRAM = 1, MAIL = 2, CALENDAR = 3, SYSTEM = 4, ["MAREA WINDOWS"] = 3 }')
logic = remove_between(logic, '--  When its time comes: once, and marked', '\ndo\n    local y, m, d = today()',
    'install_calendar_reminders(native_sys, notice, cal, save_calendar, tr)\n')
# Do not revive dismissed rows when their ages or translations refresh.
logic = replace_once(logic, 'local function render()\n    for k = 1, 5 do', '''local windows_row_keys, windows_row_serial = {}, 0
local function render()
    for k = 1, 5 do''')
logic = replace_once(logic, '        fact["alive." .. k] = f ~= nil and (not f.done or f.flying == true)', '''        local key = f and (f.id or f) or nil
        if windows_row_keys[k] ~= key then
            if fact.undoable and fact.resolved_row == k then fact.undoable = false end
            windows_row_keys[k] = key
            windows_row_serial += 1
            fact["windows_row_revision." .. k] = windows_row_serial
        end
        fact["alive." .. k] = f ~= nil and not f.done''')
logic = replace_once(logic, 'local function refill()\n    if live == nil or fact.tray_open then return end',
    'local function refill(force)\n    if live == nil or (fact.tray_open and not force) then return end')
logic = replace_once(logic, '        if not gone[n.id] then', '        if not gone[n.id] and not finished[n.id] then')
logic = replace_once(logic, 'local function from_service(list)',
    (root / 'windows/notification-dismiss.luau').read_text(encoding='utf-8') + '\nlocal function from_service(list)')
logic = re.sub(r'sys\.call\("notifications\.dismiss", ([nfr]\.id)\)', r'dismiss_native(\1)', logic)
logic = remove_between(logic, 'on("clear_all", function()', '-- ── the calendar',
    (root / 'windows/notification-clear-all.luau').read_text(encoding='utf-8') + '\n')
logic = replace_once(logic, 'on("resolve", function(k)\n    local f = rows[k]\n    if f == nil then return end',
    'on("resolve", function(k)\n    local f = rows[k]\n    if f == nil or f.done then return end')
logic = replace_once(logic, 'on("dismiss", function(k)\n    local f = rows[k]\n    if f == nil then return end',
    'on("dismiss", function(k)\n    local f = rows[k]\n    if f == nil or f.done then return end')

logic = replace_once(logic, '    sys.call("notifications.keep", true)', '    -- Windows remains responsible for toast expiration.')
logic = replace_once(logic, 'local function quiet_for(n)\n', 'local function quiet_for(n)\n    if fact.windows_notifications_sync then return true end\n')
logic = replace_once(logic, 'text["row." .. k .. ".age"] = age_of(f, k)', 'text["row." .. k .. ".age"] = notification_age(f.time, os.time(), tr("now"))')
logic = replace_once(logic, '''elseif n.title ~= f.title or n.body ~= f.detail then
                f.title, f.detail = n.title, n.body
                changed = true''', '''elseif refresh_notification_row(f, n, tr("notice")) then
                local category = CATEGORY_OF[f.app] or classify(f.app)
                if category ~= f.cat then
                    fact["n." .. f.cat] = math.max(0, (fact["n." .. f.cat] or 0) - 1)
                    fact["n." .. category] = (fact["n." .. category] or 0) + 1
                    f.cat = category
                end
                if k == 1 then show_front(f) end
                changed = true''')
logic = logic.replace('log("notifications · the real ones: this is who receives them now")', 'log("notifications · mirroring the Windows notification center")')
logic = replace_once(logic, 'a.key == "default" end', 'a.key == "open-app" end')
logic = replace_once(logic, 'if a.key ~= "default" and #arriving_actions < 2', 'if a.key ~= "open-app" and #arriving_actions < 2')
logic = replace_once(logic, 'if can_open then sys.call("notifications.invoke", f.id, "default") else dismiss_native(f.id) end',
    'if can_open then sys.call("notifications.invoke", f.id, "open-app") else notice("Windows no proporciona una aplicación que abrir para este aviso.") end')
logic = logic.replace('log("demo · the notices are made up: pleamar gives up the place to whoever already has it")', 'log("Windows: notification collection is unavailable")')
logic = '\n'.join(line for line in logic.splitlines() if 'log("demo · another batch:' not in line)
logic = logic.replace('on("set_brightness", function(v) sys.call("brightness.level", v) end)', '')
logic = logic.replace('on("set_volume", function(v) sys.call("audio.volume", v) end)', '')
logic = logic.replace('on("set_mic", function(v) sys.call("audio.input", v) end)', '')
for event, command in [('play_pause', 'toggle'), ('previous', 'previous'), ('next', 'next')]:
    logic = replace_once(logic, f'on("{event}", function() sys.call("media.{command}") end)', '')
logic = remove_between(logic, '--  And what she had on,', '-- ── the language',
    (root / 'windows/wardrobe.luau').read_text(encoding='utf-8') + '\n')
logic = replace_once(logic, '    settings.skin = fact.skin', '    settings.skin = fact.skin\n    settings.shelf_folded = fact.windows_shelf_folded == true')
logic = replace_once(logic, 'on("fact:taking_room", function() save_settings() end)',
    'on("fact:taking_room", function() save_settings() end)\ndo\n(function()\n' +
    (root / 'windows/auto-hide.luau').read_text(encoding='utf-8') + '\nend)()(settings, sys, notice)\nend')
# Lua writes do not echo a fact event back to their own handlers. Rebuild the
# dynamic labels explicitly after choosing the language, including at startup.
logic = replace_once(logic, '    fact.locale = LOCALES[fact.language] or system_locale()', '''    fact.locale = LOCALES[fact.language] or system_locale()
    emit("windows_language_updated")
    render()
    set_menu()
    if fact.searching == true then search() end''')
logic = replace_once(logic, 'local plugin_entries = {', '''local plugin_entries = {
    { id = "windows.shelf", group = "Desktop", title = "Tuck applications away" },''')
logic = replace_once(logic, 'title = tr(e.title), first = e.first', 'title = tr(e.id == "windows.shelf" and (fact.windows_shelf_folded and "Show applications" or "Tuck applications away") or e.title), first = e.first')
logic = replace_once(logic, 'set_menu()\n\non("menu_entry"', '''set_menu()
on("fact:windows_shelf_folded", set_menu)
on("fact:menu_open", function(value) if value then set_menu() end end)

on("menu_entry"''')
logic = replace_once(logic, '    local e = plugin_entries[i + 1]', '''    local e = plugin_entries[i + 1]
    if e ~= nil and e.id == "windows.wm.overview" then hooks.windows_overview(); return end
    if e ~= nil and e.id == "windows.wm.dock" then hooks.windows_dock(); return end
    if e ~= nil and e.id == "windows.wm.layout" then hooks.wm_free(); return end
    if e ~= nil and e.id == "windows.wm.restore" then hooks.wm_restore(); return end
    if e ~= nil and e.id == "windows.shelf" then emit("windows_toggle_shelf"); return end''')
logic += '\ndo\n(function()\n' + (root / 'windows/window-manager.luau').read_text(encoding='utf-8') + '''
end)()(native_run, hooks, plugin_entries, set_menu, function()
    for k = 0, 2 do if fact["hosts." .. k] == true then return monitors[k + 1] end end
    return nil
end, notice, native_spawn)
end
install_shortcuts(native_sys, notice, hooks)
'''
logic = replace_once(logic, 'local OWN = {', '''local OWN = {
    { "Application dock", "dock applications apps barra aplicaciones anclar", 1,
      function() if hooks.windows_dock then hooks.windows_dock() end end, "wm" },
    { "Window overview", "windows overview ventanas vista abiertas overview resumen", 1,
      function() if hooks.windows_overview then hooks.windows_overview() end end, "wm" },''')
# Development shells often inject C.UTF-8; it is not a user language choice.
logic = replace_once(logic, 'value ~= "C" and value ~= "POSIX"', 'value ~= "C" and not value:match("^C%.") and value ~= "POSIX"')
# Keep the original portable animation/calendar/settings logic. Linux command
# integrations fail explicitly in the adapter, and are never executed.
logic = replace_once(logic, 'local WALLPAPER = settings.wallpaper or "/usr/share/wallpapers/cachyos-wallpapers/GreenFeathers.png"', 'local WALLPAPER = ""')
logic = remove_between(logic, '--  Only the `swaybg`', '-- ── her home:')
logic = remove_between(logic, '-- ── the wallpapers, and the tide', '--  Which monitor each copy is,',
    (root / 'windows/wallpapers.luau').read_text(encoding='utf-8') + '\n\n')
adapter = (root / 'windows/desktop-adapter.luau').read_text(encoding='utf-8')
adapter = 'local install_desktop_agent = (function()\n' + (root / 'windows/desktop-agent.luau').read_text(encoding='utf-8') + '\nend)()\n' + adapter
logic = remove_between(logic, '-- ── software: updates, and programs to install', '-- ── the chat: talking to her', '''-- Native WinGet software page.
install_software(native_run, native_spawn, hooks, notice)
\n''')
adapter = 'local install_software = (function()\n' + (root / 'windows/software.luau').read_text(encoding='utf-8') + '\nend)()\n' + adapter
scene = replace_once(scene, '    text sw.pw = ""', '''    text sw.pw = ""
    text windows_sw_search_error = ""
    fact windows_sw_indeterminate = false''')
scene = replace_once(scene, '    on change sw.state while sw.state == unlocking { focus sw.pw }', '')
scene = replace_once(scene, '            on submit sw.pw { emit sw_auth }', '')
scene = replace_once(scene, '''                    input sw.pw { at: sw.x0 + 26, ay + 48; width: 300; size: 13; color: ink; placeholder: "Your password"; secret: true; selection: #2f5f52 }''', '''                    text "Windows will request administrator permission if needed" { at: sw.x0 + 26, ay + 48; anchor: left center; width: 290; lines: 2; size: 10.5; color: ink }''')
scene = replace_once(scene, 'text pick(sw.verifying, "Go", "…")', 'text pick(sw.verifying, "Confirm", "…")')
scene = scene.replace('and not sw.busy }', 'and not sw.busy and sw.state != unlocking }')
scene = replace_once(scene, 'text "{sw.bar * 100, 0}%" {', 'text pick(windows_sw_indeterminate, "{sw.bar * 100, 0}%", "…") {')
scene = replace_once(scene, 'text "Open a terminal" {', 'text "Check again" {')
scene = replace_once(scene, '"It may want an answer of yours: in a terminal you can give it"', '"WinGet errors are shown above; check again before retrying"')
scene = replace_once(scene, '"Leave it be until it ends: it is changing the system"', '"Stopping requests cancellation; an installer may still finish"')
scene = replace_once(scene, '                    input sw.query {', '''                    text windows_sw_search_error { at: sw.x0 + 4, card.top + 456; anchor: left center; width: 446; lines: 2; size: 10.5; color: #ef7a66 }
                    input sw.query {''')
adapter = 'local install_startup = (function()\n' + (root / 'windows/startup.luau').read_text(encoding='utf-8') + '\nend)()\n' + adapter
adapter = 'local install_shortcuts = (function()\n' + (root / 'windows/shortcuts.luau').read_text(encoding='utf-8') + '\nend)()\n' + adapter
adapter = 'local install_weather = (function()\n' + (root / 'windows/weather.luau').read_text(encoding='utf-8') + '\nend)()\n' + adapter
adapter = 'local install_media_controls = (function()\n' + (root / 'windows/media-controls.luau').read_text(encoding='utf-8') + '\nend)()\n' + adapter
adapter = 'local install_media_volume = (function()\n' + (root / 'windows/media-volume.luau').read_text(encoding='utf-8') + '\nend)()\n' + adapter
adapter = 'local install_calendar_reminders = (function()\n' + (root / 'windows/calendar-reminders.luau').read_text(encoding='utf-8') + '\nend)()\n' + adapter
adapter = 'local install_agent_reader = (function()\n' + (root / 'windows/agent-reader.luau').read_text(encoding='utf-8') + '\nend)()\n' + adapter
levels = (root / 'windows/level-controls.luau').read_text(encoding='utf-8')
devices = (root / 'windows/device-controls.luau').read_text(encoding='utf-8')
adapter = 'local install_notification_controls = (function()\n' + (root / 'windows/notifications.luau').read_text(encoding='utf-8') + '\nend)()\n' + adapter
adapter = 'local install_device_controls = (function()\n' + devices + '\nend)()\n' + adapter
adapter = 'local install_level_controls = (function()\n' + levels + '\nend)()\n' + adapter
logic = 'fact.windows_initialized = false\n' + adapter + '\n' + logic + '\nfact.demo = false\nfact.windows_initialized = true\n'
# Windows UI uses the same language table as the portable scene.
windows_translations = json.loads((root / 'windows/translations.json').read_text(encoding='utf-8'))
old_labels = {"Abrir app": "Open app", "Actualizar": "Refresh", "Anterior": "Previous", "Buscar redes": "Find networks",
    "Cancelar": "Cancel", "Conectar": "Connect", "Contrasena": "Password", "Contrasena de la red": "Network password",
    "Marea se silencia. Los banners de Windows se gestionan en Windows": "Marea is silenced. Manage Windows banners in Windows",
    "Permitir": "Allow", "Siguiente": "Next", "Silencia los avisos dentro de Marea": "Silence notices inside Marea", "Red": "Network"}
old_labels.update({"Deriva: esperando al servicio de biblioteca.": "Waiting for the library service…", "Leyendo Bluetooth…": "Reading Bluetooth…", "Leyendo Wi-Fi…": "Reading Wi-Fi…", "Leyendo dispositivos…": "Reading devices…", "Leyendo el permiso de notificaciones…": "Reading notification access…", "Leyendo las cuotas de agentes…": "Reading agent quotas…"})
for old, new in old_labels.items():
    scene = scene.replace(json.dumps(old, ensure_ascii=False), json.dumps(new, ensure_ascii=False))
existing = set()
for language in (root / 'lang').glob('es*.plm'):
    existing.update(re.findall(r'"((?:[^"\\]|\\.)*)"\s*=', language.read_text(encoding='utf-8')))
entries = '\n'.join('        ' + json.dumps(key, ensure_ascii=False) + ' = ' + json.dumps(value, ensure_ascii=False)
    for key, value in windows_translations.items() if key not in existing)
scene = replace_once(scene, 'scene Marea {', 'scene Marea {\n    translations es {\n' + entries + '\n    }')
(root / 'marea-desktop.plm').write_text(scene, encoding='utf-8')
(root / 'marea-desktop.luau').write_text(logic, encoding='utf-8')
print('Generated native Windows desktop profile (Linux originals preserved).')
