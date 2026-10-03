"""Generate a native desktop profile; keep the upstream Linux files untouched."""
from pathlib import Path
import re
import json

root = Path(__file__).resolve().parents[1]
scene = (root / 'marea.plm').read_text(encoding='utf-8')
logic = (root / 'marea.luau').read_text(encoding='utf-8')

def replace_once(source, old, new):
    assert source.count(old) == 1, f'Upstream changed: {old[:80]}'
    return source.replace(old, new, 1)

def remove_between(source, begin, end, replacement=''):
    start = source.index(begin)
    stop = source.index(end, start)
    return source[:start] + replacement + source[stop:]

scene = remove_between(scene, '    surface lockscreen {', '    // ── the adventure\'s stage')
scene = re.sub(r'^        run: .*$', '        run: "node", "deriva-worker", "curl.exe"', scene, flags=re.M)
scene = replace_once(scene, 'text "Reading your windows…" {', 'text windows_agents_status {')
logic = replace_once(logic, 'if g.observed then\n                local ago = now - g.observed', '''if #g.limits == 0 then table.insert(parts, "Sin datos de cuota") end
            if g.observed and g.observed <= now then
                local ago = now - g.observed''')
logic = replace_once(logic, 'local fresh = g and g.observed and now - g.observed < 900', 'local fresh = g and g.observed and now >= g.observed and now - g.observed < 900')
scene = scene.replace('"network",', '"network", "network.*", "bluetooth", "bluetooth.*",')
scene = scene.replace('"apps.launch",', '"apps.*",')
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
scene = replace_once(scene, 'fact hidden = true', 'fact hidden = false')
scene = replace_once(scene, 'fact demo = true', 'fact demo = false')
# The main Marea panels are only 820x680; their screen facts are not the
# full wallpaper area. Publish each tide surface's actual measured geometry.
scene = replace_once(scene, 'model tidepics max 1 { pic: image 1280, 720 }', '''model tidepics max 2 { pic: image 1280, 720 }
    repeat k in 0..2 {
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
scene = replace_once(scene, 'zone box track.$k { at: sx, track_top + track_h / 2; size: 34 - 6 * four, track_h + 18; corner: 17; cursor: pointer; active: content > 0.9 and (k < 3 or rain_on) }', 'zone box track.$k { at: sx, track_top + track_h / 2; size: 34, track_h + 18; corner: 17; cursor: pointer; active: content > 0.9 and windows_level_available.$k }')
scene = replace_once(scene, 'zone box icon.$k { at: sx, iy; size: 30, 30; corner: 15; cursor: pointer; active: content > 0.9 and (k < 3 or rain_on) }', 'zone box icon.$k { at: sx, iy; size: 30, 30; corner: 15; cursor: pointer; active: content > 0.9 and (k == 0 or windows_level_available.$k) }')
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
scene = replace_once(scene, 'model gadgets max 8 { name: text; current: bool; paired: bool;', 'model gadgets max 8 { name: text; current: bool; paired: bool; controllable: bool; pairable: bool;')
# A cached Windows audio endpoint is reconnectable; it is not a newly
# discovered device offering pairing. Unknown pairing state stays unknown.
scene = replace_once(scene, 'fresh: not c.paired)', 'fresh: c.pairable)')
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
scene = scene.replace('text "Looking for networks…"', 'text windows_wifi_status')
scene = replace_once(scene, 'text pick(bt_scanning, "Nothing paired", "Looking around…")', 'text windows_bluetooth_status')
scene = scene.replace('show: page == wifi\n                for r in networks', 'show: page == wifi and not windows_wifi_join\n                for r in networks')
scene = scene.replace('column network_list {', 'column network_list {\n                view: 456, 290')
scene = replace_once(scene, '            //  Its password, asked for in place:', '            on windows_wifi_paged { network_list.scroll: 0 ~0ms }\n            //  Its password, asked for in place:')
scene = scene.replace('column gadget_list {', 'column gadget_list {\n                view: 456, 290')
scene = replace_once(scene, '            on press radar_btn { emit bt_scan }', '''            on press radar_btn { emit bt_scan }
            on windows_bluetooth_paged { gadget_list.scroll: 0 ~0ms }
            group {
                show: page == bluetooth
                text windows_bluetooth_warning { at: card.x, card.top + 470; anchor: center; width: 430; lines: 2; size: 10.5; color: #8b8f95 }
                group {
                    show: windows_bluetooth_pages
                    text windows_bluetooth_page { at: card.x, card.top + 425; anchor: center; size: 11; color: ink }
                    box windows_bt_previous { at: card.x - 170, card.top + 425; size: 104, 30; corner: 10; color: #30383a; cursor: pointer; show: windows_bluetooth_previous }
                    text "Anterior" { at: card.x - 170, card.top + 425; anchor: center; size: 11; color: ink; show: windows_bluetooth_previous }
                    box windows_bt_next { at: card.x + 170, card.top + 425; size: 104, 30; corner: 10; color: #30383a; cursor: pointer; show: windows_bluetooth_next }
                    text "Siguiente" { at: card.x + 170, card.top + 425; anchor: center; size: 11; color: ink; show: windows_bluetooth_next }
                    on press windows_bt_previous { emit windows_bluetooth_page(-1) }
                    on press windows_bt_next { emit windows_bluetooth_page(1) }
                }
            }''')
scene = scene.replace('show: page == wifi and networks.count < 1', 'width: 430; lines: 3; show: page == wifi and networks.count < 1 and not windows_wifi_join')
# Several virtual endpoints are common on Windows. Both lists must remain
# reachable instead of extending beyond the bottom of the card.
scene = scene.replace('column output_list {\n                    at: card.x - 228, card.top + 132', 'column output_list {\n                    view: 456, 126\n                    at: card.x - 228, card.top + 132')
scene = scene.replace('column mic_list {\n                    at: card.x - 228, card.top + 164 + output_list.height', 'column mic_list {\n                    view: 456, 126\n                    at: card.x - 228, card.top + 306')
scene = scene.replace('card.top + 150 + output_list.height', 'card.top + 292')
scene = scene.replace('on press icon.1 {', 'on press icon.0 { emit windows_display_info }\n            on press icon.1 {')
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
    fact windows_wifi_pages = false
    fact windows_wifi_previous = false
    fact windows_wifi_next = false
    text windows_wifi_page = ""
    event windows_wifi_page ->
    event windows_wifi_paged
    fact windows_bluetooth_present = false
    fact windows_bluetooth_pages = false
    fact windows_bluetooth_previous = false
    fact windows_bluetooth_next = false
    text windows_bluetooth_page = ""
    text windows_bluetooth_warning = ""
    event windows_bluetooth_page ->
    event windows_bluetooth_paged
    text windows_wifi_status = "Leyendo Wi-Fi…"
    text windows_bluetooth_status = "Leyendo Bluetooth…"
    text windows_bluetooth_summary = "Leyendo dispositivos…"
    fact windows_wifi_join = false
    text windows_wifi_name = ""
    text windows_wifi_password = ""
    event windows_wifi_submit ->
    event windows_display_info ->
    event windows_lock ->
    event windows_lock_info ->
    group {
        show: open and page == wifi and windows_wifi_join
        text windows_wifi_name { at: card.x, card.top + 134; anchor: center; width: 430; lines: 1; size: 15; color: ink }
        text "Contrasena de la red" { at: card.x - 208, card.top + 181; anchor: left center; size: 12; color: ink }
        box { at: card.x, card.top + 220; size: 436, 44; corner: 10; color: #20282a }
        input windows_wifi_password { at: card.x - 202, card.top + 220; width: 400; size: 16; color: ink; secret: true; placeholder: "Contrasena" }
        box wifi_join_button { at: card.x + 112, card.top + 290; size: 200, 42; corner: 10; color: mint; cursor: pointer }
        text "Conectar" { at: card.x + 112, card.top + 290; anchor: center; size: 13; color: #142720 }
        box wifi_cancel_button { at: card.x - 112, card.top + 290; size: 200, 42; corner: 10; color: #30383a; cursor: pointer }
        text "Cancelar" { at: card.x - 112, card.top + 290; anchor: center; size: 13; color: ink }
        on press wifi_join_button { emit windows_wifi_submit }
        on press wifi_cancel_button { windows_wifi_join = false }
    }
    group {
        show: open and page == wifi and not windows_wifi_join
        group {
            show: windows_wifi_pages
            text windows_wifi_page { at: card.x, card.top + 425; anchor: center; size: 11; color: ink }
            box windows_wifi_previous_button { at: card.x - 170, card.top + 425; size: 104, 30; corner: 10; color: #30383a; cursor: pointer; show: windows_wifi_previous }
            text "Anterior" { at: card.x - 170, card.top + 425; anchor: center; size: 11; color: ink; show: windows_wifi_previous }
            box windows_wifi_next_button { at: card.x + 170, card.top + 425; size: 104, 30; corner: 10; color: #30383a; cursor: pointer; show: windows_wifi_next }
            text "Siguiente" { at: card.x + 170, card.top + 425; anchor: center; size: 11; color: ink; show: windows_wifi_next }
            on press windows_wifi_previous_button { emit windows_wifi_page(-1) }
            on press windows_wifi_next_button { emit windows_wifi_page(1) }
        }
        box wifi_refresh { at: card.x, card.top + if(windows_wifi_pages, 470, 425); size: 210, 32; corner: 10; color: #30383a; cursor: pointer; show: windows_wifi_present }
        text "Buscar redes" { at: card.x, card.top + if(windows_wifi_pages, 470, 425); anchor: center; size: 12; color: ink; show: windows_wifi_present }
        on press wifi_refresh { emit scan(1) }
    }
    on change windows_wifi_join while windows_wifi_join { focus windows_wifi_password }
    on change page while page != wifi { windows_wifi_join = false }
    on key Return while windows_wifi_join { emit windows_wifi_submit }
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
wall_area = '                zone box walls_area { from: card.x - 228, card.top + 100; size: 456, 340; active: page == walls and paging > 0.9 }'
scene = replace_once(scene, wall_area + '\n', '')
scene = replace_once(scene, '                show: page == walls\n                grid {',
                     '                show: page == walls\n' + wall_area + '\n                grid {')

logic = remove_between(logic, '-- ── the three cards', '-- ── sound:')
# The Linux launcher builds Deriva on demand. Windows installs its binary;
# keep the real adapter error/retry footer instead of promising a Rust build.
scene = replace_once(scene, '''                group {
                    show: drift.missing
                    text "Deriva needs its library, deriva-worker." { at: card.x, card.y + 20; anchor: center; size: 12.5; weight: 500; color: ink }
                    text "She builds it herself when she starts, if Rust (cargo) is installed." { at: card.x, card.y + 42; anchor: center; size: 11.5; color: #8b8f95 }
                }
''', '')
# Background scroll zones must precede the clickable cards they cover.
drift_area = '                zone box drift_area { from: dx0, dy0 + 50; size: 456, 312; active: page == drift and paging > 0.9 and not drift.missing }'
scene = replace_once(scene, drift_area + '\n', '')
scene = replace_once(scene, '                let dy0 = card.top + 96\n', '                let dy0 = card.top + 96\n' + drift_area + '\n')
scene = replace_once(scene, 'show: drift.kept < 1', 'show: windows_deriva_loaded and not windows_deriva_busy and drift.count < 1')
scene = replace_once(scene, 'text "{drift.kept, 0} kept" {', 'text "{drift.kept, 0} kept" { opacity: if(windows_deriva_loaded, 1, 0);')
scene = replace_once(scene, 'at: dx0, dy0 + 50; columns: 2; gap: 12; width: 456; row: 150', 'show: windows_deriva_loaded\n                    at: dx0, dy0 + 50; columns: 2; gap: 12; width: 456; row: 150')
scene = replace_once(scene, '            on scroll drift_area', '''            group {
                show: page == drift
                text windows_deriva_status { at: card.x - 228, card.top + 480; anchor: left center; width: 350; lines: 3; size: 10.5; color: #8b8f95 }
                box windows_deriva_refresh { at: card.x + 179, card.top + 480; size: 98, 30; corner: 10; color: #30383a; cursor: pointer; show: not windows_deriva_busy }
                text "Actualizar" { at: card.x + 179, card.top + 480; anchor: center; size: 11; color: ink; show: not windows_deriva_busy }
                on press windows_deriva_refresh { emit drift_open }
            }
            on scroll drift_area''')
logic = remove_between(logic, 'local DRIFT = "deriva-worker"', 'local function host_of', '''local drift_run, drift_file_path = install_deriva_worker(native_run)
local drift_preview = install_deriva_preview(native_run)
local drift_items, drift_offset, drift_blobs = {}, 0, nil
local drift_generation = 0
model.drift = {}
fact.windows_deriva_loaded = false
fact.windows_deriva_busy = false
text.windows_deriva_status = "Deriva: esperando al servicio de biblioteca."

''')
logic = replace_once(logic, 'if drift_blobs == nil or type(h) ~= "string" or #h < 4 then return "" end',
    'if drift_blobs == nil or type(h) ~= "string" or #h < 4 or #h > 128 or not h:match("^%x+$") then return "" end')
logic = replace_once(logic, 'source = source, kind =', 'source = tostring(source or ""), kind =')
logic = replace_once(logic, 'math.floor((it.captured_at or 0) / 1000)', 'math.floor((tonumber(it.captured_at) or 0) / 1000)')
logic = replace_once(logic, 'local function show_drift()\n', 'local show_drift\nshow_drift = function()\n')
logic = replace_once(logic, '    model.drift = cards\n', '''    model.drift = cards
    for k = drift_offset + 1, math.min(drift_offset + 4, #drift_items) do
        drift_preview(drift_items[k], function(item)
            -- Search/paging can change while the preview is downloading.
            for index, current in ipairs(drift_items) do
                if current.id == item.id then
                    drift_items[index] = item
                    show_drift()
                    break
                end
            end
        end)
    end
''')
logic = remove_between(logic, 'local function drift_load()\n', '--  Typing searches, a moment after the last key.', '''local function drift_load()
    drift_generation += 1
    local mine = drift_generation
    fact.windows_deriva_busy = true
    text.windows_deriva_status = "Leyendo Deriva…"
    local q = text.drift_q or ""
    local args = q == "" and {"list", "--limit", "60"} or {"search", "--query", q, "--limit", "60"}
    local function load()
        drift_run(args, function(r, error)
            if mine ~= drift_generation then return end
            fact.windows_deriva_busy = false
            if not r then fact["drift.missing"] = not fact.windows_deriva_loaded; text.windows_deriva_status = error; return end
            fact["drift.missing"] = false
            fact.windows_deriva_loaded = true
            text.windows_deriva_status = #r.items == 0 and (q == "" and "Biblioteca vacía." or "Sin resultados para esta búsqueda.") or ""
            drift_items, drift_offset = r.items, 0
            if q == "" then fact["drift.kept"] = #drift_items end
            show_drift()
        end)
    end
    if drift_blobs then load(); return end
    drift_run({"where"}, function(r, error)
        if mine ~= drift_generation then return end
        if not r then
            fact["drift.missing"] = true
            fact.windows_deriva_busy = false
            text.windows_deriva_status = error
            return
        end
        drift_blobs = r.blobs
        load()
    end)
end
on("drift_open", drift_load)
''')
logic = replace_once(logic, '    drift_typed = drift_typed + 1', '''    drift_generation += 1 -- Invalidate in-flight replies before the debounce ends.
    drift_typed = drift_typed + 1''')
logic = replace_once(logic, '        if l:match("^file://") then\n            local p = url_decode(l:gsub("^file://[^/]*", ""))', '''        if l:lower():match("^file://") then
            local p = drift_file_path(l)
            if not p then
                invalid += 1
                continue
            end''')
logic = replace_once(logic, '    local urls, groups, words = {}, {}, {}', '''    local urls, groups, words = {}, {}, {}
    local invalid = 0
    local raw, preserve_text = tostring(data or ""), false
    if mime ~= "text/uri-list" then
        for line in raw:gmatch("[^\\r\\n]+") do
            local l = line:match("^%s*(.-)%s*$")
            if l ~= "" and not l:lower():match("^file://") and not l:match("^https?://%S+$") then preserve_text = true end
        end
    end''')
logic = replace_once(logic, '    if #requests == 0 then return end', '''    -- Plain prose keeps its indentation, blank lines, headings and embedded URLs.
    if preserve_text then requests = {{type = "text", text = raw}}; invalid = 0 end
    if #requests == 0 and invalid == 0 then return end''')
logic = replace_once(logic, '            words[#words + 1] = l', '            if mime == "text/uri-list" then invalid += 1 else words[#words + 1] = l end')
logic = replace_once(logic, 'local saved, duplicates, failed, left = 0, 0, 0, #requests', 'local saved, duplicates, failed, left = 0, 0, invalid, #requests')
logic = replace_once(logic, '''    local function finished()
        if saved > 0 then''', '''    local function finished()
        if failed > 0 then
            fact["drift.result"] = 3
            text["drift.toast"] = string.format("Guardados: %d · Ya estaban: %d · Fallidos: %d", saved, duplicates, failed)
        elseif saved > 0 then''')
logic = replace_once(logic, '    for _, req in ipairs(requests) do', '    if left == 0 then finished(); return end\n    for _, req in ipairs(requests) do')
logic = replace_once(logic, 'duplicates = duplicates + (r.duplicates or 0)', 'duplicates = duplicates + (r.duplicates or 0)\n                failed = failed + (r.failed or 0)')
logic = replace_once(logic, 'failed = failed + 1', 'failed = failed + (req.paths and #req.paths or 1)')
logic = replace_once(logic, 'hooks.keep_copied = keep_copied', 'hooks.keep_copied = keep_copied\nif fact.page == "drift" then drift_load() end')
logic = remove_between(logic, '-- ── the system tray', '-- ── the photograph',
    (root / 'windows/tray.luau').read_text(encoding='utf-8') + '\n\n')
logic = remove_between(logic, '--  In the pictures folder', '-- ── the recording',
    (root / 'windows/screenshots.luau').read_text(encoding='utf-8') + '\n\n')
logic = remove_between(logic, '-- ── the recording', '-- ── the desktop wallpaper',
    (root / 'windows/recording.luau').read_text(encoding='utf-8') + '\n\n')
logic = remove_between(logic, '-- ── the pages', '-- ── the finder')
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
logic = replace_once(logic, '        fact["alive." .. k] = f ~= nil', '''        local key = f and (f.id or f) or nil
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
logic = replace_once(logic, 'on("resolve", function(k)\n    local f = rows[k]\n    if f == nil then return end',
    'on("resolve", function(k)\n    local f = rows[k]\n    if f == nil or f.done then return end')
logic = replace_once(logic, 'on("dismiss", function(k)\n    local f = rows[k]\n    if f == nil then return end',
    'on("dismiss", function(k)\n    local f = rows[k]\n    if f == nil or f.done then return end')

logic = replace_once(logic, '    sys.call("notifications.keep", true)', '    -- Windows remains responsible for toast expiration.')
logic = replace_once(logic, 'local function quiet_for(n)\n', 'local function quiet_for(n)\n    if fact.windows_notifications_sync then return true end\n')
logic = replace_once(logic, 'text["row." .. k .. ".age"] = tr(AGES[k])', 'text["row." .. k .. ".age"] = notification_age(f.time, os.time(), tr("now"))')
logic = replace_once(logic, 'return { id = n.id, app = app, title = n.title, detail = n.body,', 'return { id = n.id, app = app, title = n.title, detail = n.body, time = n.time,')
logic = replace_once(logic, 'arrive({ id = n.id, app = string.upper(', 'arrive({ id = n.id, time = n.time, app = string.upper(')
logic = replace_once(logic, 'on("fact:tray_open", refill)', '''on("fact:tray_open", refill)
local function refresh_notification_ages()
    if fact.tray_open then render() end
    after(30000, refresh_notification_ages)
end
after(30000, refresh_notification_ages)''')
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
# Development shells often inject C.UTF-8; it is not a user language choice.
logic = replace_once(logic, 'value ~= "C" and value ~= "POSIX"', 'value ~= "C" and not value:match("^C%.") and value ~= "POSIX"')
# Keep the original portable animation/calendar/settings logic. Linux command
# integrations fail explicitly in the adapter, and are never executed.
logic = replace_once(logic, 'local WALLPAPER = settings.wallpaper or "/usr/share/wallpapers/cachyos-wallpapers/GreenFeathers.png"', 'local WALLPAPER = ""')
logic = remove_between(logic, '--  Only the `swaybg`', '-- ── her home:')
logic = remove_between(logic, '-- ── the wallpapers, and the tide', '--  Which monitor each copy is,',
    (root / 'windows/wallpapers.luau').read_text(encoding='utf-8') + '\n\n')
adapter = (root / 'windows/desktop-adapter.luau').read_text(encoding='utf-8')
adapter = 'local install_weather = (function()\n' + (root / 'windows/weather.luau').read_text(encoding='utf-8') + '\nend)()\n' + adapter
adapter = 'local install_media_controls = (function()\n' + (root / 'windows/media-controls.luau').read_text(encoding='utf-8') + '\nend)()\n' + adapter
adapter = 'local install_media_volume = (function()\n' + (root / 'windows/media-volume.luau').read_text(encoding='utf-8') + '\nend)()\n' + adapter
adapter = 'local install_deriva_worker = (function()\n' + (root / 'windows/deriva-worker.luau').read_text(encoding='utf-8') + '\nend)()\n' + adapter
adapter = 'local install_deriva_preview = (function()\n' + (root / 'windows/deriva-preview.luau').read_text(encoding='utf-8') + '\nend)()\n' + adapter
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
