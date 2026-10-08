"""Exercise the modern native radio pages in real Luau, with hardware mocked."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('device-controls.luau').read_text(encoding='utf-8')
checks = r'''
local fact, text, model, events, watches, calls, queries, timers = {}, {}, {}, {}, {}, {}, {}, {}
local reject, language = false, ""
local function tr(s) return language .. s end
local function on(name, f) events[name] = events[name] or {}; table.insert(events[name], f) end
local function fire(name, value) for _, f in ipairs(events[name] or {}) do f(value) end end
local function emit() error("Lua must not relay its own handlers through emit") end
local function after(_, f) timers[#timers + 1] = f end
local function notice(s) text.windows_status = s; fact.windows_notice = true end
local native = {
    call = function() error("synchronous command") end, ask = function() error("synchronous query") end,
    watch = function(name, f) watches[name] = f end,
    call_async = function(name, args, done)
        if reject then error("queue full") end
        calls[#calls + 1] = {name = name, args = args, done = done}
    end,
    ask_async = function(name, args, done)
        if reject then error("queue full") end
        queries[#queries + 1] = {name = name, args = args, done = done}
    end,
}
local hooks = {language = {}}
local install = (function()
__MODULE__
end)()
install(native, notice, hooks, tr)
local function net(id, profile, active, strength)
    return {interface = id, ssid = "43617361", name = "Casa ñ", profile = profile or "saved", current = active == true,
        signal = strength or 1, joinable = true, secure = true}
end
local ws, bs
local function wifi(nets, adapters, enabled)
    ws = {present = true, available = true, enabled = enabled ~= false, networks = nets, adapters = adapters or {}}
    watches["network.wifi"](ws)
end
local function bt(devices)
    bs = {present = true, available = true, enabled = true, devices = devices}
    watches.bluetooth(bs)
end
local function flush()
    for _, q in ipairs(queries) do
        if not q.completed and (q.name == "network.wifi" or q.name == "bluetooth.state") then
            q.completed = true; q.done(q.name == "network.wifi" and ws or bs, nil)
        end
    end
end
local function last(name)
    local c = calls[#calls]
    assert(c and c.name == name, "expected " .. name .. ", got " .. tostring(c and c.name))
    return c
end
wifi({net("A"), net("B", "saved", false, 0.2)})
bt({{id = "audio-guid", name = "Audio", current = false, controllable = true}})
fire("pick_network", 0)
local c = last("network.connect")
assert(c.args[1] == "A" and c.args[2] == "saved" and fact["wifi.state"] == 4)
local count = #calls; fire("pick_network", 0); assert(#calls == count)
wifi({net("A", "other", true), net("B", "saved", true)})
c.done("", 0); flush()
assert(fact.windows_notice, "different profile/adapter confirmed connection")
wifi({net("A", "saved", true), net("B")})
assert(not fact.windows_notice and fact["wifi.state"] == 2 and #model.networks == 1)
fire("wifi_disconnect"); c = last("network.disconnect"); c.done("", 0); flush()
wifi({}, {{id = "B", disconnected = true}})
assert(fact.windows_notice, "another adapter confirmed disconnection")
wifi({}, {{id = "A", disconnected = true}})
assert(not fact.windows_notice)

-- Password input keeps identity even when discovery reorders the visible rows.
wifi({net("A", ""), net("B", "", false, 0.2)})
fire("pick_network", 0); assert(fact.asking == 0)
text.wifi_pw = "secret test value"
wifi({net("B", "", false, 1), net("A", "", false, 0.1)})
fire("join"); c = last("network.join")
assert(c.args[1] == "A" and c.args[3] == "secret test value" and text.wifi_pw == "" and fact.asking == -1)
fire("wifi_disconnect"); local cancel = last("network.disconnect")
count = #calls; fire("wifi_disconnect"); assert(#calls == count, "duplicate cancellation queued")
c.done("connection cancelled", -1)
assert(fact.windows_notice and text.windows_status == "Disconnecting…", "obsolete callback replaced cancellation")
cancel.done("", 0); wifi({}, {{id = "A", disconnected = true}}); flush()
assert(not fact.windows_notice)

-- All networks remain reachable; duplicate SSIDs on distinct interfaces remain distinct.
local nets = {}
for i = 1, 21 do nets[i] = net(string.format("W%02d", i), "profile-" .. i, false, 1 - i / 100) end
nets[22] = table.clone(nets[1])
wifi(nets)
assert(#model.networks == 5 and fact["wifi.total"] == 21)
for _ = 1, 30 do fire("wifi_scroll", -1) end
assert(fact["wifi.offset"] == 16 and #model.networks == 5)
fire("wifi_forget", 4); c = last("network.forget")
assert(c.args[1] == "W21" and c.args[2] == "profile-21")
c.done("access denied", -1); assert(text.windows_status == "access denied")
fire("wifi_forget", 4); last("network.forget").done("", 0); flush()
assert(not fact.windows_notice, "native verified deletion was ignored")
wifi({nets[1]}); assert(fact["wifi.offset"] == 0)

-- A share reply arriving after close/network change cannot revive credentials.
wifi({net("A", "saved", true)})
fire("wifi_share"); local q = queries[#queries]
assert(q.name == "network.share" and q.args[1] == "A" and q.args[2] == "saved")
count = #queries; fire("wifi_share"); assert(#queries == count)
fire("fact:page", "none"); assert(last("network.unshare"))
q.done({password = "private", qr = "private.png"}, nil)
assert(text["wifi.password"] == "" and #model.wifi_qr == 0 and not fact["wifi.sharing"])
count = #calls; fire("wifi_copy"); assert(#calls == count)
fire("wifi_share"); queries[#queries].done(nil, "password permission denied")
count = #calls; fire("wifi_copy"); assert(#calls == count, "error message was copied as a password")
fire("wifi_share"); queries[#queries].done({password = "private", qr = "temporary ñ.png", open = false}, nil)
assert(fact["wifi.has_qr"] and model.wifi_qr[1].pic == "temporary ñ.png")
fire("wifi_copy"); assert(last("clipboard.set").args[1] == "private")
wifi({net("B", "saved", true)})
assert(not fact["wifi.sharing"] and text["wifi.password"] == "" and #model.wifi_qr == 0)
fire("wifi_share"); queries[#queries].done({password = "", qr = "open.png", open = true}, nil)
count = #calls; fire("wifi_copy"); assert(#calls == count)
fire("fact:open", false); assert(not fact["wifi.has_qr"])

-- Cached audio endpoints do not pretend to be unpairable Bluetooth addresses.
count = #calls; fire("bt_forget", 0); assert(#calls == count and not model.bt_mine[1].forgetable)
fire("pick_gadget", 0); c = last("bluetooth.connect"); assert(c.args[1] == "audio-guid")
c.done("driver refused", -1); assert(text.windows_status == "driver refused")
bt({{id = "001122AABBCC", name = "Mouse", paired = true, current = false, controllable = false}})
assert(model.bt_mine[1].forgetable and not model.bt_mine[1].actionable)
count = #calls; fire("pick_gadget", 0); assert(#calls == count)
fire("bt_forget", 0); c = last("bluetooth.forget"); assert(c.args[1] == "001122AABBCC")
c.done("", 0); flush(); assert(not fact["bt.busy"])
local many = {}
for i = 1, 21 do many[i] = {id = string.format("ble:%03d", i), name = "Same name", current = false, paired = false, pairable = true, transport = "le"} end
bt(many); assert(#model.bt_near == 5 and #model.bt_mine == 0)
for _ = 1, 4 do fire("windows_bluetooth_page", 1) end
assert(#model.bt_near == 1 and text.windows_bluetooth_page == "21–21 / 21")
fire("pick_gadget", 0); c = last("bluetooth.pair"); assert(c.args[1] == "ble:021")
for _, f in ipairs(table.clone(timers)) do f() end
count = #calls; fire("pick_gadget", 0); assert(#calls == count, "timeout queued a second pairing wizard")
many[21].paired, many[21].pairable = true, false
bt(many); assert(fact["bt.busy"], "readback completed a still-running command")
c.done("", 0); flush(); assert(not fact["bt.busy"])
fire("scan", 2); q = queries[#queries]
bt({}); q.done({present = true, enabled = false, devices = {}}, nil)
assert(fact["bt.on"], "old query overwrote a newer subscription")
fire("bt_scan"); q = queries[#queries]
assert(q.name == "bluetooth.discover" and fact.bt_scanning)
q.done(nil, "radio off"); assert(not fact.bt_scanning and text.windows_status == "radio off")
reject = true; fire("flip", 1); assert(text.windows_status:find("queue full")); reject = false
fire("flip", 1); c = last("network.radio"); c.done("radio refused", -1)
wifi({net("A")}, {}, false)
fire("wifi_power"); c = last("network.radio"); assert(c.args[1] == true)
c.done("", 0); wifi({net("A")}); flush()
fire("wifi_rescan"); c = last("network.scan")
count = #calls; fire("wifi_rescan"); assert(#calls == count)
c.done("location denied", -1); assert(not fact["wifi.scanning"] and text.windows_status == "location denied")
language = "ES:"; for _, f in ipairs(hooks.language) do f() end
assert(text.windows_bluetooth_summary == "ES:On")
watches["network.wifi"]({present = false, enabled = false, networks = {}, error = "WLAN unavailable"})
watches.network({online = true, kind = "wired", name = "Ethernet"})
assert(fact["wifi.state"] == 3 and not fact.windows_wifi_present)
count = #calls; fire("wifi_rescan"); fire("wifi_power"); assert(#calls == count)
log("PASS: native radio pages, identity, paging, readback, cancellation, QR cleanup, translation and capability limits")
'''.replace('__MODULE__', module)
run_checks(args, checks, 'PASS: native radio pages', 'radio-pages')
