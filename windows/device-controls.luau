-- Native calls can wait for a driver or an OS confirmation. Keep that wait
-- outside Lua, and settle requests only after both completion and readback.
return function(native, notice, hooks, tr)
    local wifi, bluetooth, pending, epoch = {}, {}, {}, { wifi = 0, bluetooth = 0 }
    local refreshing, joining = {}, nil
    local wifi_rows, shown_nets, wifi_offset, current, wired = {}, {}, 0, nil, {}
    local shown_devices, sharing, shared_password, share_version, share_running = {}, nil, nil, 0, false
    local show_wifi, show_bluetooth, refresh_wifi, refresh_bluetooth, unshare
    local function same_network(a, b)
        return a ~= nil and b ~= nil and a.interface == b.interface and a.ssid == b.ssid and a.profile == b.profile
    end
    local bluetooth_rows, bluetooth_offset = {}, 0
    fact.bt_scanning = false
    local function failed(message) notice(tostring(message):match("[^\n]+")) end
    local function call(name, args, done)
        local ok, error = pcall(native.call_async, name, args, done)
        if not ok then done(tostring(error), -1) end
    end
    local function ask(name, done, args)
        local ok, error = pcall(native.ask_async, name, args or {}, done)
        if not ok then done(nil, tostring(error)) end
    end
    local function finish(kind, request, error)
        if pending[kind] ~= request then return end
        pending[kind] = nil
        if error then failed(error)
        elseif text.windows_status == request.message then fact.windows_notice = false end
        if kind == "wifi" then show_wifi() else show_bluetooth() end
    end
    local function confirm(kind, state)
        local request = pending[kind]
        if not request or state.available == false or (state.error and state.error ~= "") then return end
        request.confirmed = request.matches(state)
        if request.accepted and request.confirmed then finish(kind, request) end
    end
    local function start(kind, name, args, message, matches, row)
        if pending[kind] then notice(pending[kind].message); return false end
        local request = { message = message, matches = matches, running = true, command = name, row = row }
        pending[kind] = request
        notice(message)
        if kind == "wifi" then show_wifi() else show_bluetooth() end
        after(25000, function()
            if pending[kind] ~= request then return end
            request.expired = true
            if request.running then
                request.message = tr("Windows is still processing the request.")
                notice(request.message)
            else finish(kind, request, tr("Windows did not confirm the requested change.")) end
        end)
        call(name, args, function(error, code)
            if pending[kind] ~= request then return end
            request.running = false
            if code ~= 0 then finish(kind, request, error); return end
            request.accepted = true
            -- These native commands verify the deletion before returning.
            if name == "network.forget" or name == "bluetooth.forget" then request.confirmed = true end
            if request.confirmed then finish(kind, request)
            elseif request.expired then
                -- A pairing wizard may legitimately outlive the initial wait.
                -- Give its successful OS result time to reach the subscription.
                after(25000, function()
                    if pending[kind] == request then finish(kind, request, tr("Windows did not confirm the requested change.")) end
                end)
            end
            if kind == "wifi" then refresh_wifi() else refresh_bluetooth() end
        end)
        return true
    end
    show_wifi = function()
        wifi_offset = math.clamp(wifi_offset, 0, math.max(#wifi_rows - 5, 0))
        local rows = {}
        shown_nets = {}
        for index = wifi_offset + 1, math.min(wifi_offset + 5, #wifi_rows) do
            local n = wifi_rows[index]
            shown_nets[#shown_nets + 1] = n
            local signal = math.clamp(n.signal or 0, 0, 1)
            rows[#rows + 1] = {name = n.name, signal = signal, percent = math.floor(signal * 100 + 0.5),
                current = n.current == true, known = n.profile ~= "", secure = n.secure == true}
        end
        model.networks = rows
        fact["wifi.offset"], fact["wifi.total"] = wifi_offset, #wifi_rows
        local state, title, status = 1, tr("Not connected"), tr("Choose a network below")
        local request = pending.wifi
        if request and (request.command == "network.join" or request.command == "network.connect") then
            state, title, status = 4, request.row.name, tr("Joining…")
        elseif current then
            local p = math.floor((current.signal or 0) * 100 + 0.5)
            local quality = p >= 75 and "Excellent signal" or p >= 50 and "Good signal" or p >= 25 and "Fair signal" or "Weak signal"
            state, title, status = 2, current.name, string.format("%s · %d%%", tr(quality), p)
        elseif wired.online and wired.kind == "wired" then
            state, title, status = 3, tr("Connected by cable"), wired.name or ""
        elseif not wifi.present then
            state, title, status = 0, tr("Wi-Fi is unavailable"), text.windows_wifi_status
        elseif not wifi.enabled then
            state, title, status = 0, tr("Wi-Fi is off"), tr("Its radio is resting")
        elseif wifi.error and wifi.error ~= "" then status = wifi.error end
        fact["wifi.state"], text["wifi.title"], text["wifi.status"] = state, title, status
        fact.windows_wifi_strength = current and (current.signal or 0) * 100 or 0
        if sharing and not same_network(sharing, current) then unshare() end
    end
    on("wifi_scroll", function(w)
        if joining or fact["wifi.sharing"] or w == 0 then return end
        wifi_offset += w > 0 and -1 or 1
        show_wifi()
    end)
    local function wifi_state(state)
        epoch.wifi += 1
        wifi = state
        fact.windows_wifi_present = state.present == true
        fact["switched_on.1"] = state.enabled == true
        text.windows_wifi_status = state.error ~= nil and state.error ~= "" and state.error
            or (not state.present and tr("No Wi-Fi adapter is available.")
            or not state.enabled and tr("Wi-Fi is off") or tr("No networks found. Press Look again to scan."))
        local networks = table.clone(state.networks or {})
        table.sort(networks, function(a, b)
            if a.current ~= b.current then return a.current end
            if (a.profile ~= "") ~= (b.profile ~= "") then return a.profile ~= "" end
            if a.signal ~= b.signal then return a.signal > b.signal end
            if a.interface ~= b.interface then return a.interface < b.interface end
            if a.ssid ~= b.ssid then return a.ssid < b.ssid end
            return a.profile < b.profile
        end)
        local rows, seen = {}, {}
        current = nil
        for _, network in ipairs(networks) do
            seen[network.interface] = seen[network.interface] or {}
            local adapter = seen[network.interface]
            adapter[network.ssid] = adapter[network.ssid] or {}
            if not adapter[network.ssid][network.profile] then
                adapter[network.ssid][network.profile] = true
                if network.current and not current then current = network else rows[#rows + 1] = network end
            end
        end
        wifi_rows = rows
        show_wifi()
        confirm("wifi", state)
    end
    local function can_forget(d)
        return d.paired == true and (d.id:sub(1, 4) == "ble:" or (#d.id == 12 and d.id:match("^%x+$") ~= nil))
    end
    show_bluetooth = function()
        bluetooth_offset = math.clamp(bluetooth_offset, 0, math.max(math.ceil(#bluetooth_rows / 5) - 1, 0) * 5)
        local mine, near = {}, {}
        for index = bluetooth_offset + 1, math.min(bluetooth_offset + 5, #bluetooth_rows) do
            local d = bluetooth_rows[index]
            local list = (d.paired == true or d.controllable == true) and mine or near
            list[#list + 1] = d
        end
        shown_devices = {}
        local function row(d, base)
            shown_devices[#shown_devices + 1] = d
            local busy = pending.bluetooth and pending.bluetooth.row and pending.bluetooth.row.id == d.id
            local state = busy and 2 or d.current and 1 or d.paired and 0 or d.pairable and 3 or 0
            local status = busy and tr("Working…") or d.current and tr("Connected") or d.paired and tr("Paired")
                or d.pairable and tr("New · press Pair") or d.controllable and tr("Audio connection") or tr("Needs its device application")
            return {name = d.name ~= "" and d.name or d.id, status = status, kind = d.controllable and 1 or 0,
                state = state, battery = -1, base = base, forgetable = can_forget(d),
                actionable = d.pairable == true or d.controllable == true,
                action = busy and "…" or tr(d.pairable and "Pair" or d.controllable and (d.current and "Disconnect" or "Connect") or "Info")}
        end
        local a, b = {}, {}
        for _, d in ipairs(mine) do a[#a + 1] = row(d, 0) end
        for _, d in ipairs(near) do b[#b + 1] = row(d, #mine) end
        model.bt_mine, model.bt_near = a, b
        fact["bt.present"], fact["bt.on"] = bluetooth.present == true, bluetooth.present == true and bluetooth.enabled == true
        fact["bt.busy"] = pending.bluetooth ~= nil
        fact.windows_bluetooth_pages = #bluetooth_rows > 5
        fact.windows_bluetooth_previous = bluetooth_offset > 0
        fact.windows_bluetooth_next = bluetooth_offset + 5 < #bluetooth_rows
        text.windows_bluetooth_page = #bluetooth_rows == 0 and "" or string.format("%d–%d / %d", bluetooth_offset + 1, bluetooth_offset + #a + #b, #bluetooth_rows)
    end
    on("windows_bluetooth_page", function(step)
        bluetooth_offset += (step or 0) > 0 and 5 or -5
        show_bluetooth()
    end)
    local function bluetooth_state(state)
        epoch.bluetooth += 1
        bluetooth = state
        fact.windows_bluetooth_present = state.present == true
        fact["switched_on.2"] = state.enabled == true
        text.windows_bluetooth_status = state.error ~= nil and state.error ~= "" and state.error
            or (not state.present and tr("No Bluetooth adapter is available.")
            or not state.enabled and tr("Bluetooth is off")
            or state.le_ready == false and (not state.warning or state.warning == "") and tr("Loading Bluetooth devices…")
            or tr("Nothing paired yet. Press Search to find what is near."))
        text.windows_bluetooth_summary = not state.present and tr("Unavailable") or state.enabled and tr("On") or tr("Off")
        text.windows_bluetooth_warning = state.warning or ""
        local rows = table.clone(state.devices or {})
        table.sort(rows, function(a, b)
            local am, bm = a.paired == true or a.controllable == true, b.paired == true or b.controllable == true
            if am ~= bm then return am end
            if a.current ~= b.current then return a.current end
            if (a.pairable == true) ~= (b.pairable == true) then return a.pairable == true end
            if a.name ~= b.name then return a.name < b.name end
            return a.id < b.id
        end)
        bluetooth_rows = rows
        show_bluetooth()
        confirm("bluetooth", state)
    end
    local function power(k)
        if k ~= 1 and k ~= 2 then return end
        local kind, state = k == 1 and "wifi" or "bluetooth", k == 1 and wifi or bluetooth
        if not state.present then failed(state.error or tr("No adapter is available.")); return end
        local target = not state.enabled
        start(kind, k == 1 and "network.radio" or "bluetooth.radio", { target },
            target and tr("Turning the radio on…") or tr("Turning the radio off…"), function(value) return value.enabled == target end)
    end
    on("flip", power)
    local function refresh(kind, query, apply)
        if refreshing[kind] then return end
        refreshing[kind] = true
        local revision = epoch[kind]
        ask(query, function(value, error)
            refreshing[kind] = nil
            if error then failed(error)
            elseif epoch[kind] == revision then apply(value) end
        end)
    end
    refresh_wifi = function() refresh("wifi", "network.wifi", wifi_state) end
    refresh_bluetooth = function() refresh("bluetooth", "bluetooth.state", bluetooth_state) end
    on("wifi_power", function() if not wifi.enabled then power(1) end end)
    on("bt_power", function() if not bluetooth.enabled then power(2) end end)
    local function scan(k)
        if k == 1 then
            if not wifi.present then failed(wifi.error or tr("No Wi-Fi adapter is available.")); return end
            if fact["wifi.scanning"] then return end
            fact["wifi.scanning"] = true
            call("network.scan", {}, function(error, code)
                if code ~= 0 then fact["wifi.scanning"] = false; failed(error); return end
                -- Scheduling the WLAN scan is not its completion.
                after(4000, function() fact["wifi.scanning"] = false; refresh_wifi() end)
            end)
        elseif k == 2 then refresh("bluetooth", "bluetooth.state", bluetooth_state) end
    end
    on("scan", scan)
    on("wifi_rescan", function() scan(1) end)
    on("bt_scan", function()
        if not bluetooth.present then failed(bluetooth.error or tr("No Bluetooth adapter is available.")); return end
        if fact.bt_scanning then return end
        fact.bt_scanning = true
        local revision = epoch.bluetooth
        ask("bluetooth.discover", function(value, error)
            fact.bt_scanning = false
            if error then failed(error)
            else
                if value.warning and value.warning ~= "" then failed(value.warning) end
                if epoch.bluetooth == revision then bluetooth_state(value)
                else refresh("bluetooth", "bluetooth.state", bluetooth_state) end
            end
        end)
    end)
    local function network_matches(network, connected)
        return function(state)
            if not connected then
                for _, adapter in ipairs(state.adapters or {}) do
                    if adapter.id == network.interface and adapter.disconnected == true then return true end
                end
            end
            for _, current in ipairs(state.networks or {}) do
                if current.interface == network.interface and current.ssid == network.ssid and current.current == connected
                    and (not connected or network.profile == "" or current.profile == network.profile) then return true end
            end
            return false
        end
    end
    local function stop_asking()
        fact.asking, text.wifi_pw, joining = -1, "", nil
    end
    local function join(network, password)
        if pending.wifi then notice(pending.wifi.message); return end
        stop_asking()
        start("wifi", network.profile == "" and "network.join" or "network.connect",
            network.profile == "" and {network.interface, network.ssid, password or ""} or {network.interface, network.profile},
            tr("Joining…"), network_matches(network, true), network)
    end
    on("pick_network", function(index)
        local n = shown_nets[index + 1]
        if not n or n.current then return end
        if pending.wifi then notice(pending.wifi.message); return end
        if n.profile == "" and not n.joinable then notice(tr("This network needs an existing WPA3 or enterprise profile.")); return end
        if n.profile == "" and n.secure then
            joining, text["ask.name"], text.wifi_pw, fact.asking = n, n.name, "", index
        else join(n) end
    end)
    on("join", function() if joining then join(joining, text.wifi_pw or "") end end)
    on("forget_ask", stop_asking)
    on("wifi_forget", function(index)
        local n = shown_nets[index + 1]
        if n and n.profile ~= "" then
            start("wifi", "network.forget", {n.interface, n.profile}, tr("Forgetting the saved network…"), function() return false end, n)
        end
    end)
    on("wifi_disconnect", function()
        local request = pending.wifi
        local n = request and request.row or current
        if not n or (request and request.command == "network.disconnect") then return end
        if request and request.command ~= "network.join" and request.command ~= "network.connect" then return end
        -- A single cancellation follows the connection on the same worker.
        pending.wifi = nil
        if sharing then unshare() end
        start("wifi", "network.disconnect", {n.interface}, tr("Disconnecting…"), network_matches(n, false), n)
    end)
    unshare = function()
        if sharing == nil and shared_password == nil and not fact["wifi.has_qr"] then return end
        share_version += 1
        sharing, shared_password = nil, nil
        fact["wifi.sharing"], fact["wifi.has_qr"] = false, false
        text["wifi.password"], text["wifi.share_hint"] = "", ""
        model.wifi_qr = {}
        call("network.unshare", {}, function(error, code) if code ~= 0 then failed(error) end end)
    end
    local function share()
        if not current or current.profile == "" or share_running then return end
        stop_asking()
        share_version += 1
        local version = share_version
        sharing, shared_password, share_running = current, nil, true
        fact["wifi.sharing"], fact["wifi.has_qr"] = true, false
        model.wifi_qr = {}
        text["wifi.password"] = "…"
        text["wifi.share_hint"] = string.format(tr("Scan it with your phone to join «%s»."), current.name)
        ask("network.share", function(value, error)
            share_running = false
            if version ~= share_version or not same_network(sharing, current) then return end
            if error then text["wifi.password"] = tr("It could not be read"); failed(error); return end
            shared_password = nil
            if not value.open then shared_password = value.password end
            text["wifi.password"] = value.open and tr("None: it is open") or value.password
            model.wifi_qr = {{pic = value.qr}}
            fact["wifi.has_qr"] = value.qr ~= nil and value.qr ~= ""
        end, {current.interface, current.profile})
    end
    hooks.wifi_share = share
    on("wifi_share", share)
    on("wifi_unshare", unshare)
    on("wifi_copy", function()
        if not shared_password or shared_password == "" then return end
        call("clipboard.set", {shared_password}, function(error, code)
            if code ~= 0 then failed(error) else notice(tr("Password copied")) end
        end)
    end)
    on("fact:page", function(page)
        if page ~= "wifi" then stop_asking(); if sharing then unshare() end end
    end)
    on("fact:open", function(open)
        if not open then stop_asking(); if sharing then unshare() end end
    end)
    on("pick_gadget", function(index)
        local device = shown_devices[index + 1]
        if not device then return end
        if device.pairable then
            start("bluetooth", "bluetooth.pair", { device.id }, tr("Confirm pairing in the Windows dialog."), function(state)
                for _, current in ipairs(state.devices or {}) do
                    if current.id == device.id and current.paired then return true end
                end
                return false
            end, device)
            return
        end
        if not device.controllable then
            notice(device.transport == "le" and (device.paired
                and tr("Paired by Windows. Connection is managed by the device profile or its application.")
                or tr("Windows cannot pair this device. It may need its own application."))
                or tr("This device has no audio connection control: ") .. device.name)
            return
        end
        local target = not device.current
        start("bluetooth", "bluetooth.connect", { device.id, target },
            (target and tr("Connecting ") or tr("Disconnecting ")) .. device.name .. "…", function(state)
                for _, current in ipairs(state.devices or {}) do
                    if current.id == device.id and current.current == target then return true end
                end
                return false
            end, device)
    end)
    on("bt_forget", function(index)
        local d = shown_devices[index + 1]
        if d and can_forget(d) then
            start("bluetooth", "bluetooth.forget", {d.id}, tr("Removing the pairing…"), function() return false end, d)
        end
    end)
    table.insert(hooks.language, function() wifi_state(wifi); bluetooth_state(bluetooth) end)
    native.watch("network.wifi", wifi_state)
    native.watch("bluetooth", bluetooth_state)
    native.watch("network", function(state) wired = state or {}; show_wifi() end)
end
