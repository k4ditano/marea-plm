"""Check asynchronous native controls without touching adapters or audio."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('device-controls.luau').read_text(encoding='utf-8')
checks = r'''
local fact, text, model, events, watches, calls, queries, timers = {}, {}, {}, {}, {}, {}, {}, {}
local reject = false
local function on(name, callback) events[name] = callback end
local emitted = {}
local function emit(name) emitted[#emitted + 1] = name end
local function after(_, callback) table.insert(timers, callback) end
local function notice(value) text.windows_status = value; fact.windows_notice = true end
local native = {
    call = function() error("synchronous native command") end,
    ask = function() error("synchronous native query") end,
    watch = function(name, callback) watches[name] = callback end,
    call_async = function(name, args, callback)
        if reject then error("command queue full") end
        table.insert(calls, { name = name, args = args, done = callback })
    end,
    ask_async = function(name, args, callback)
        if reject then error("query queue full") end
        table.insert(queries, { name = name, done = callback })
    end,
}
local install = (function()
__MODULE__
end)()
install(native, notice)
local function network(interface, current, profile, signal)
    return { interface = interface, name = "Same SSID", ssid = "45535041", profile = profile or "saved", current = current, signal = signal or 1, joinable = true }
end
local function wifi(a, b)
    watches["network.wifi"]({ available = true, present = true, enabled = true, networks = { network("A", a), network("B", b, "saved", 0.2) } })
end
local function bt(current)
    watches.bluetooth({ available = true, present = true, enabled = true, devices = { { id = "audio-1", name = "Headphones", current = current, controllable = true } } })
end
wifi(false, false); bt(false)
events.pick_network(0)
assert(#calls == 1 and calls[1].name == "network.connect" and calls[1].args[1] == "A")
events.pick_network(0)
assert(#calls == 1, "double click queued duplicate connection")
wifi(false, true)
calls[1].done("", 0)
assert(fact.windows_notice, "another adapter with the same SSID confirmed the request")
wifi(true, true)
assert(not fact.windows_notice, "matching adapter/SSID did not confirm")
events.pick_network(0)
wifi(false, false)
assert(fact.windows_notice, "readback alone cleared a command still running")
calls[2].done("", 0)
assert(not fact.windows_notice, "readback before callback was lost")
-- A newer subscription must win over a slow explicit refresh.
events.scan(2); events.scan(2)
assert(#queries == 1)
bt(true)
queries[1].done({ present = true, enabled = false, devices = {} }, nil)
assert(fact["switched_on.2"] and model.gadgets[1].current, "stale query overwrote newer subscription")
events.pick_gadget(0)
assert(calls[3].name == "bluetooth.connect" and calls[3].args[2] == false)
calls[3].done("driver refused", -1)
assert(text.windows_status == "driver refused" and model.gadgets[1].current)
events.pick_gadget(0); calls[4].done("", 0)
notice("unrelated error")
bt(false)
assert(fact.windows_notice and text.windows_status == "unrelated error", "confirmation hid an unrelated error")
reject = true
events.flip(1)
assert(text.windows_status:find("queue full"))
reject = false
events.flip(1)
assert(#calls == 5, "enqueue failure kept the control busy")
-- Timeout does not allow an unbounded queue behind a slow driver.
for _, timer in ipairs(timers) do timer() end
events.flip(1)
assert(#calls == 5 and text.windows_status:find("procesando"))
watches["network.wifi"]({ available = true, present = true, enabled = false, networks = {} })
calls[5].done("", 0)
assert(not fact.windows_notice, "late confirmed completion left a false timeout")
-- A failed join clears the entered password once the native request is queued.
watches["network.wifi"]({ present = true, enabled = true, networks = { network("A", false, "") } })
events.pick_network(0)
assert(fact.windows_wifi_join)
text.windows_wifi_password = "test password"
events.windows_wifi_submit()
assert(calls[6].name == "network.join" and calls[6].args[3] == "test password")
assert(text.windows_wifi_password == "" and not fact.windows_wifi_join)
calls[6].done("wrong password", -1)
assert(text.windows_status == "wrong password")
events.scan(1); events.scan(1)
assert(#calls == 7 and calls[7].name == "network.scan")
calls[7].done("location denied", -1)
assert(text.windows_status == "location denied")
reject = true
events.scan(2)
assert(text.windows_status:find("queue full"))
reject = false
events.scan(2)
assert(#queries == 2, "query enqueue failure left refresh busy")
queries[2].done(nil, "adapter removed")
assert(text.windows_status == "adapter removed")
events.bt_scan(); events.bt_scan()
assert(#queries == 3 and queries[3].name == "bluetooth.discover" and fact.bt_scanning)
queries[3].done(nil, "radio off")
assert(not fact.bt_scanning and text.windows_status == "radio off")
events.bt_scan()
queries[4].done({ present = true, enabled = true, devices = {
    { id = "001122AABBCC", name = "New device", current = false, paired = false, pairable = true },
} }, nil)
assert(not fact.bt_scanning and model.gadgets[1].pairable)
events.pick_gadget(0)
assert(calls[8].name == "bluetooth.pair" and calls[8].args[1] == "001122AABBCC")
calls[8].done("pairing cancelled", -1)
assert(text.windows_status == "pairing cancelled" and not model.gadgets[1].paired)
events.pick_gadget(0)
calls[9].done("", 0)
assert(fact.windows_notice, "pairing succeeded before readback")
watches.bluetooth({ present = true, enabled = true, devices = {
    { id = "001122AABBCC", name = "New device", current = true, paired = true, pairable = false },
} })
assert(not fact.windows_notice, "paired identity did not confirm")
-- A disappeared SSID still disconnects when the selected adapter confirms it.
wifi(true, false)
events.pick_network(0)
assert(calls[10].name == "network.disconnect")
calls[10].done("", 0)
watches["network.wifi"]({ present = true, enabled = true, networks = {}, adapters = { { id = "B", disconnected = true } } })
assert(fact.windows_notice, "another adapter confirmed disconnection")
watches["network.wifi"]({ present = true, enabled = true, networks = {}, adapters = { { id = "A", disconnected = true } } })
assert(not fact.windows_notice, "disappearing SSID could not confirm disconnection")
-- Every discovered identity remains reachable beyond the first eight rows.
local many = {}
for index = 1, 21 do
    many[index] = { id = string.format("ble:%03d", index), name = "Same name", current = false,
        paired = false, pairable = true, controllable = false, transport = "le" }
end
watches.bluetooth({ present = true, enabled = true, devices = many })
assert(#model.gadgets == 8 and model.gadgets[1].id == "ble:001" and fact.windows_bluetooth_next)
events.windows_bluetooth_page(1)
assert(model.gadgets[1].id == "ble:009" and fact.windows_bluetooth_previous)
assert(emitted[#emitted] == "windows_bluetooth_paged", "paging did not reset the scroll view")
events.windows_bluetooth_page(1)
assert(#model.gadgets == 5 and model.gadgets[5].id == "ble:021" and not fact.windows_bluetooth_next)
events.pick_gadget(4)
assert(calls[#calls].name == "bluetooth.pair" and calls[#calls].args[1] == "ble:021", "paged pairing chose another identity")
calls[#calls].done("pairing cancelled", -1)
watches.bluetooth({ present = true, enabled = true, devices = { many[1] } })
assert(#model.gadgets == 1 and model.gadgets[1].id == "ble:001" and not fact.windows_bluetooth_pages)
-- A watch arriving during discovery must not make the scan lose its results.
events.bt_scan()
local discovery = queries[#queries]
watches.bluetooth({ present = true, enabled = true, devices = {} })
discovery.done({ present = true, enabled = true, devices = many, warning = "classic radio refused inquiry" }, nil)
assert(text.windows_status == "classic radio refused inquiry", "partial discovery failure was hidden")
assert(queries[#queries].name == "bluetooth.state", "stale discovery was not refreshed")
queries[#queries].done({ present = true, enabled = true, devices = many }, nil)
assert(model.gadgets[1].id == "ble:001")
-- Enumeration in progress and unpairable advertisements are not false successes.
watches.bluetooth({ present = true, enabled = true, le_ready = false, devices = {} })
assert(text.windows_bluetooth_status:find("Cargando"))
local unpairable = { id = "ble:advertisement", name = "Beacon", paired = false,
    pairable = false, controllable = false, transport = "le" }
watches.bluetooth({ present = true, enabled = true, le_ready = true, devices = { unpairable } })
local call_count = #calls
events.pick_gadget(0)
assert(#calls == call_count and text.windows_status:find("no permite emparejar"), "an unpairable advertisement was reported as paired")
unpairable.paired = true
watches.bluetooth({ present = true, enabled = true, devices = { unpairable } })
events.pick_gadget(0)
assert(#calls == call_count and text.windows_status:find("Emparejado por Windows"))
-- The PLM model holds one page; it must not truncate the Wi-Fi catalog.
local networks = {}
for index = 1, 21 do
    networks[index] = network(string.format("W%02d", index), false, "saved-" .. index, 1 - index / 100)
end
networks[22] = table.clone(networks[1])
watches["network.wifi"]({ present = true, enabled = true, networks = networks })
assert(#model.networks == 8 and fact.windows_wifi_next, "Wi-Fi catalog was truncated to the first eight networks")
assert(text.windows_wifi_page == "1–8 / 21", "duplicate identity counted as another network")
events.windows_wifi_page(1)
assert(model.networks[1].interface == "W09" and fact.windows_wifi_previous)
assert(emitted[#emitted] == "windows_wifi_paged", "Wi-Fi paging did not reset the scroll view")
events.windows_wifi_page(1)
assert(#model.networks == 5 and model.networks[5].interface == "W21" and not fact.windows_wifi_next)
events.pick_network(4)
assert(calls[#calls].name == "network.connect" and calls[#calls].args[1] == "W21" and calls[#calls].args[2] == "saved-21",
    "paged connection chose another adapter or profile")
calls[#calls].done("test connection refused", -1)
events.windows_wifi_page(1)
assert(model.networks[5].interface == "W21", "paging beyond the last page lost rows")
events.windows_wifi_page(-1)
assert(model.networks[1].interface == "W09")
watches["network.wifi"]({ present = true, enabled = true, networks = { networks[1] } })
assert(#model.networks == 1 and model.networks[1].interface == "W01" and not fact.windows_wifi_pages)
watches["network.wifi"]({ present = true, enabled = true, networks = {} })
assert(#model.networks == 0 and text.windows_wifi_page == "" and not fact.windows_wifi_previous and not fact.windows_wifi_next)
-- Equal signal levels still have a stable identity order across scans.
local tied = { network("Z", false), network("A", false), network("Y", true) }
watches["network.wifi"]({ present = true, enabled = true, networks = tied })
assert(model.networks[1].interface == "Y" and model.networks[2].interface == "A" and model.networks[3].interface == "Z")
watches["network.wifi"]({ present = true, enabled = true, networks = { tied[2], tied[1], tied[3] } })
assert(model.networks[1].interface == "Y" and model.networks[2].interface == "A" and model.networks[3].interface == "Z")
-- An Ethernet connection does not create a Wi-Fi radio. Missing adapters
-- expose a reason and cannot enqueue a scan, discovery or radio command.
watches["network.wifi"]({ available = true, present = false, enabled = false, networks = {} })
watches.bluetooth({ available = true, present = false, enabled = false, devices = {} })
local missing_calls, missing_queries = #calls, #queries
events.flip(1); events.scan(1); events.flip(2); events.bt_scan()
assert(#calls == missing_calls and #queries == missing_queries)
assert(not fact.windows_wifi_present and not fact.windows_bluetooth_present and not fact["switched_on.1"])
assert(text.windows_wifi_status:find("No hay adaptador") and text.windows_bluetooth_summary == "No disponible")
log("PASS: async device controls, duplicate clicks, adapter identity, stale reads, failures, timeout and password cleanup")
log("PASS: Bluetooth LE identities, pagination beyond eight devices and discovery/watch races")
log("PASS: Wi-Fi pagination, adapter/profile identity, stable scans, shrinking catalogs and missing radios")
'''.replace('__MODULE__', module)
run_checks(args, checks, 'PASS: async device controls', 'devices')
