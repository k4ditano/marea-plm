"""Bind the upstream radio pages to Windows without replacing their layout."""
import re
def apply(scene, logic):
    def once(source, old, new):
        assert source.count(old) == 1, old[:100]
        return source.replace(old, new, 1)

    start = logic.index('    --  The control center\'s two switches.')
    end = logic.index('    -- ── sound:', start)
    logic = logic[:start] + '    install_device_controls(native_sys, notice, hooks, tr)\n\n' + logic[end:]
    for model in ('bt_mine', 'bt_near'):
        start = scene.index('    model ' + model + ' max ')
        end = scene.index('\n', start)
        line = scene[start:end].replace('max 4', 'max 5')
        line = line.replace('; base: number }', '; base: number; forgetable: bool; actionable: bool; action: text }')
        scene = scene[:start] + line + scene[end:]
    scene = once(scene, 'net.strength > (a - 1) * 25 and wifi.state >= 2', 'windows_wifi_strength > (a - 1) * 25 and wifi.state == 2')
    scene, count = re.subn(r'show: wifi.state == 0(\n\s+Pill)', r'show: wifi.state == 0 and windows_wifi_present\1', scene)
    assert count == 1
    scene = once(scene, 'text "Turn it on to see the networks around you."', 'text windows_wifi_status')
    scene = once(scene, 'text "Looking for networks…"', 'text windows_wifi_status')
    # Lua writes do not echo fact handlers into the same VM. Render rules also
    # clear the prompt/QR when navigation comes from the finder or another hook.
    scene = once(scene, '    on submit wifi_pw { emit join }', '''    on submit wifi_pw { emit join }
    on change page while page != wifi { emit wifi_unshare; emit forget_ask }
    on change open while not open { emit wifi_unshare; emit forget_ask }''')
    scene = once(scene, 'active: page == wifi and paging > 0.9 and asking < 0', 'active: page == wifi and paging > 0.9 and asking < 0 and windows_wifi_present')
    scene = once(scene, 'text pick(bt_scanning, "Nothing paired yet. Press Search to find what is near.", "Looking around…")', 'text windows_bluetooth_status')
    start = scene.index('    component BtRow(')
    end = start + re.search(r'\n\s*group \{\n\s*show: page == bluetooth', scene[start:]).start()
    row = scene[start:end].replace('d.state != 3', 'd.forgetable')
    row = once(row, 'text pick(d.state, "Connect", "Disconnect", "…", "Pair")',
               'text d.action')
    row = row.replace('if(d.state == 3 or d.state == 0, 1, 0)', 'if(d.actionable and (d.state == 3 or d.state == 0), 1, 0)')
    scene = scene[:start] + row + scene[end:]
    scene = once(scene, '    on press radar_btn { emit bt_scan }', '''    on press radar_btn { emit bt_scan }
    group {
        show: page == bluetooth
        text windows_bluetooth_warning { at: card.x, card.top + 470; anchor: center; width: 430; lines: 2; size: 10.5; color: #8b8f95 }
        group {
            show: windows_bluetooth_pages
            text windows_bluetooth_page { at: card.x, card.top + 425; anchor: center; size: 11; color: ink }
            box windows_bt_previous { at: card.x - 170, card.top + 425; size: 104, 30; corner: 10; color: #30383a; cursor: pointer; show: windows_bluetooth_previous }
            text "Previous" { at: card.x - 170, card.top + 425; anchor: center; size: 11; color: ink; show: windows_bluetooth_previous }
            box windows_bt_next { at: card.x + 170, card.top + 425; size: 104, 30; corner: 10; color: #30383a; cursor: pointer; show: windows_bluetooth_next }
            text "Next" { at: card.x + 170, card.top + 425; anchor: center; size: 11; color: ink; show: windows_bluetooth_next }
            on press windows_bt_previous { emit windows_bluetooth_page(-1) }
            on press windows_bt_next { emit windows_bluetooth_page(1) }
        }
    }''')
    return scene, logic
