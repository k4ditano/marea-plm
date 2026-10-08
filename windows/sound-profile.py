"""Adapt the current upstream mixer to asynchronous native Windows controls."""
from pathlib import Path
import re


def replace(source, old, new):
    assert source.count(old) == 1, f'Upstream sound changed: {old[:70]}'
    return source.replace(old, new, 1)


def apply(scene, logic, root: Path):
    module = (root / 'windows/app-audio.luau').read_text(encoding='utf-8')
    logic = 'local install_app_audio = (function()\n' + module + '\nend)()\n' + logic
    logic = replace(logic, '    local shown_apps = {}', '''    local paint_sound
    local app_audio = install_app_audio(native_sys, function(message) notice(tr(message)) end,
        function() if paint_sound then paint_sound() end end)
    local app_controls, app_ids, app_serial = {}, {}, 0
    local app_drag, app_order
    local shown_apps = {}''')
    logic = replace(logic, '    local function paint_sound()', '    paint_sound = function()')
    logic = replace(logic, '        audio_state = state or {}\n        paint_sound()', '''        audio_state = state or {}
        app_audio.observe(audio_state.apps)
        local controls, ids = {}, {}
        for _, a in ipairs(audio_state.apps or {}) do
            if type(a.id) == "string" and a.id ~= "" then
                local control = app_controls[a.id]
                if not control then app_serial += 1; control = app_serial end
                controls[a.id], ids[control] = control, a.id
            end
        end
        app_controls, app_ids = controls, ids
        text.windows_mixer_status = audio_state.apps_error or ""
        paint_sound()''')
    logic = replace(logic, '        local list = audio_state.apps or {}', '''        local list = audio_state.apps or {}
        if app_order then
            local latest, pinned = {}, {}
            for _, a in ipairs(list) do latest[a.id] = a end
            for _, a in ipairs(app_order) do
                local row = latest[a.id] or table.clone(a)
                if not latest[a.id] then row.playing = false end
                pinned[#pinned + 1] = row
            end
            list = pinned
        end''')
    logic = replace(logic, '            local title = a.title or ""', '''            local volume, muted = app_audio.preview(a.id, a.volume, a.muted)
            local title = a.title or ""''')
    logic = replace(logic, 'volume = math.clamp(a.volume or 0, 0, 1), muted = a.muted == true',
                    'control = app_controls[a.id] or 0, volume = math.clamp(volume or 0, 0, 1), muted = muted == true')
    logic = replace(logic, '''        local a = shown_apps[math.floor(v / 1000) + 1]
        if a then pcall(sys.call, "audio.app_volume", a.id, (v % 1000) / 100) end''',
                    '        if app_drag then app_audio.volume(app_drag, (v % 1000) / 100) end')
    logic = replace(logic, '''        local a = shown_apps[i + 1]
        if a then pcall(sys.call, "audio.app_mute", a.id) end''',
                    '        local id = app_ids[i]\n        if id then app_audio.mute(id) end')
    logic = replace(logic, '    on("app_volume", function(v)', '''    on("windows_app_press", function(control)
        app_drag = app_ids[control]
        app_order = app_drag and table.clone(audio_state.apps or {}) or nil
    end)
    on("windows_app_release", function()
        app_drag, app_order = nil, nil
        paint_sound()
    end)
    on("app_volume", function(v)''')
    logic = replace(logic, '    on("sound_scroll", function(w)',
                    '    on("sound_scroll", function(w)\n        if app_order then return end')
    scene = replace(scene, 'model sound_apps max 3 { name: text;',
                    'model sound_apps max 3 { control: number; name: text;')
    scene = replace(scene, '    event app_mute ->', '''    event windows_app_press ->
    event windows_app_release ->
    on change page while page != sound { emit windows_app_release }
    event app_mute ->''')
    scene = replace(scene, 'on press mute { emit app_mute(a.index) }',
                    'on press mute { emit app_mute(a.control) }')
    scene = replace(scene, 'on press track { emit app_volume(',
                    'on press track { emit windows_app_press(a.control); emit app_volume(')
    scene = replace(scene, '        on drag track { emit app_volume(',
                    '        on release track { emit windows_app_release }\n        on drag track { emit app_volume(')
    scene = replace(scene, '    text sound.more = ""', '    text sound.more = ""\n    text windows_mixer_status = ""')
    scene = replace(scene, 'model outputs max 5', 'model outputs max 32')
    scene = replace(scene, 'model mics max 4', 'model mics max 32')
    start = scene.index('    // ── sound: a mixer')
    end = scene.index('    on key Escape while page == sound', start)
    sound = scene[start:end]
    assert sound.count('n * 32 + 10') == 3
    sound = sound.replace('n * 32 + 10', 'min(n, 5) * 32 + 10')
    sound, count = re.subn(r'(?m)^(\s*)column \{\n([ \t]*)at: lx \+ 36, dy \+ 3',
        lambda m: m[1] + 'column {\n' + m[2] + 'view: 416, 160\n' + m[2] + 'at: lx + 36, dy + 3', sound)
    assert count == 2
    scene = scene[:start] + sound + scene[end:]
    scene = replace(scene, 'text "Nothing is playing right now." {', '''text windows_mixer_status { at: card.x, ay + 148; anchor: center; width: 450; lines: 2; size: 10.5; color: #ef7a66 }
        text "Nothing is playing right now." {''')
    # Sound's second pair of sliders uses the same low-latency state as the
    # control center. An absent microphone remains unavailable here as well.
    scene = replace(scene, 'let val = pick(k, vol_level, mic_level)',
                    'let val = if(pick(k, windows_level_available.1, windows_level_available.2), if(pick(k, windows_level_pending.1, windows_level_pending.2), pick(k, windows_level_target.1, windows_level_target.2), pick(k, sound.volume, sound.input)), 0)')
    for slot, event in ((0, 'set_volume'), (1, 'set_mic')):
        expr = 'clamp((pointer.x - (card.x - 168)) / 330, 0, 1)'
        for gesture in ('press', 'drag'):
            scene = replace(scene, f'on {gesture} level.{slot} {{ emit {event}({expr}) }}',
                f'on {gesture} level.{slot} {{ windows_level_drag.{slot + 1} = true; windows_level_pending.{slot + 1} = true; windows_level_target.{slot + 1}: {expr} ~16ms; emit {event}({expr}) }}')
        scene = replace(scene, f'        on drag level.{slot}',
            f'        on release level.{slot} {{ windows_level_drag.{slot + 1} = false; windows_level_pending.{slot + 1} = true; windows_level_target.{slot + 1}: {expr} ~16ms; emit {event}({expr}) }}\n        on drag level.{slot}')
    scene = replace(scene, 'zone box level.$k { from: lx + 52, py + 44; size: 346, 22; cursor: pointer; active: page == sound and paging > 0.9 and sound.choosing == 0',
                    'zone box level.$k { from: lx + 52, py + 44; size: 346, 22; cursor: pointer; active: page == sound and paging > 0.9 and sound.choosing == 0 and pick(k, windows_level_available.1, windows_level_available.2)')
    return scene, logic
