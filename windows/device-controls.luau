-- Native calls can wait for a driver or an OS confirmation. Keep that wait
-- outside Lua, and settle requests only after both completion and readback.
return function(native, notice)
    local wifi, bluetooth, pending, epoch = {}, {}, {}, { wifi = 0, bluetooth = 0 }
    local refreshing, joining = {}, nil
    local wifi_rows, wifi_offset = {}, 0
    local bluetooth_rows, bluetooth_offset = {}, 0
    fact.bt_scanning = false
    local function failed(message) notice(tostring(message):match("[^\n]+")) end
    local function call(name, args, done)
        local ok, error = pcall(native.call_async, name, args, done)
        if not ok then done(tostring(error), -1) end
    end
    local function ask(name, done)
        local ok, error = pcall(native.ask_async, name, {}, done)
        if not ok then done(nil, tostring(error)) end
    end
    local function finish(kind, request, error)
        if pending[kind] ~= request then return end
        pending[kind] = nil
        if error then failed(error)
        elseif text.windows_status == request.message then fact.windows_notice = false end
    end
    local function confirm(kind, state)
        local request = pending[kind]
        if not request or state.available == false or (state.error and state.error ~= "") then return end
        request.confirmed = request.matches(state)
        if request.accepted and request.confirmed then finish(kind, request) end
    end
    local function start(kind, name, args, message, matches)
        if pending[kind] then notice(pending[kind].message); return false end
        local request = { message = message, matches = matches, running = true }
        pending[kind] = request
        notice(message)
        after(25000, function()
            if pending[kind] ~= request then return end
            request.expired = true
            if request.running then
                request.message = "Windows sigue procesando la solicitud; todavia no hay confirmacion."
                notice(request.message)
            else finish(kind, request, "Windows no ha confirmado el cambio solicitado.") end
        end)
        call(name, args, function(error, code)
            if pending[kind] ~= request then return end
            request.running = false
            if code ~= 0 then finish(kind, request, error); return end
            request.accepted = true
            if request.confirmed then finish(kind, request)
            elseif request.expired then
                -- A pairing wizard may legitimately outlive the initial wait.
                -- Give its successful OS result time to reach the subscription.
                after(25000, function()
                    if pending[kind] == request then finish(kind, request, "Windows no ha confirmado el cambio solicitado.") end
                end)
            end
        end)
        return pending[kind] == request
    end
    local function show_wifi()
        wifi_offset = math.clamp(wifi_offset, 0, math.max(math.ceil(#wifi_rows / 8) - 1, 0) * 8)
        local rows = {}
        for index = wifi_offset + 1, math.min(wifi_offset + 8, #wifi_rows) do
            rows[#rows + 1] = wifi_rows[index]
        end
        model.networks = rows
        fact.windows_wifi_pages = #wifi_rows > 8
        fact.windows_wifi_previous = wifi_offset > 0
        fact.windows_wifi_next = wifi_offset + 8 < #wifi_rows
        text.windows_wifi_page = #wifi_rows == 0 and "" or string.format("%d–%d / %d", wifi_offset + 1, wifi_offset + #rows, #wifi_rows)
    end
    on("windows_wifi_page", function(step)
        wifi_offset += (step or 0) > 0 and 8 or -8
        show_wifi()
        emit("windows_wifi_paged")
    end)
    local function wifi_state(state)
        epoch.wifi += 1
        wifi = state
        fact.windows_wifi_present = state.present == true
        fact["switched_on.1"] = state.enabled == true
        text.windows_wifi_status = state.error ~= nil and state.error ~= "" and state.error
            or (not state.present and "No hay adaptador Wi-Fi en este equipo."
            or not state.enabled and "Wi-Fi apagado" or "No se han encontrado redes.")
        local networks = table.clone(state.networks or {})
        table.sort(networks, function(a, b)
            if a.current ~= b.current then return a.current end
            if a.signal ~= b.signal then return a.signal > b.signal end
            if a.interface ~= b.interface then return a.interface < b.interface end
            if a.ssid ~= b.ssid then return a.ssid < b.ssid end
            return a.profile < b.profile
        end)
        local rows, seen = {}, {}
        for _, network in ipairs(networks) do
            local key = network.interface .. "|" .. network.ssid .. "|" .. network.profile
            if not seen[key] then seen[key] = true; rows[#rows + 1] = network end
        end
        wifi_rows = rows
        show_wifi()
        confirm("wifi", state)
    end
    local function show_bluetooth()
        bluetooth_offset = math.clamp(bluetooth_offset, 0, math.max(math.ceil(#bluetooth_rows / 8) - 1, 0) * 8)
        local rows = {}
        for index = bluetooth_offset + 1, math.min(bluetooth_offset + 8, #bluetooth_rows) do
            local row = table.clone(bluetooth_rows[index])
            if row.transport == "le" then row.name = row.name .. " · LE" end
            rows[#rows + 1] = row
        end
        model.gadgets = rows
        fact.windows_bluetooth_pages = #bluetooth_rows > 8
        fact.windows_bluetooth_previous = bluetooth_offset > 0
        fact.windows_bluetooth_next = bluetooth_offset + 8 < #bluetooth_rows
        text.windows_bluetooth_page = #bluetooth_rows == 0 and "" or string.format("%d–%d / %d", bluetooth_offset + 1, bluetooth_offset + #rows, #bluetooth_rows)
    end
    on("windows_bluetooth_page", function(step)
        bluetooth_offset += (step or 0) > 0 and 8 or -8
        show_bluetooth()
        emit("windows_bluetooth_paged")
    end)
    local function bluetooth_state(state)
        epoch.bluetooth += 1
        bluetooth = state
        fact.windows_bluetooth_present = state.present == true
        fact["switched_on.2"] = state.enabled == true
        text.windows_bluetooth_status = state.error ~= nil and state.error ~= "" and state.error
            or (not state.present and "No hay adaptador Bluetooth."
            or not state.enabled and "Bluetooth apagado"
            or state.le_ready == false and (not state.warning or state.warning == "") and "Cargando dispositivos Bluetooth…"
            or "No hay dispositivos emparejados.")
        text.windows_bluetooth_summary = not state.present and "No disponible" or state.enabled and "Activado" or "Apagado"
        text.windows_bluetooth_warning = state.warning or ""
        local rows = table.clone(state.devices or {})
        table.sort(rows, function(a, b)
            if a.current ~= b.current then return a.current end
            if (a.pairable == true) ~= (b.pairable == true) then return a.pairable == true end
            if a.name ~= b.name then return a.name < b.name end
            return a.id < b.id
        end)
        bluetooth_rows = rows
        show_bluetooth()
        confirm("bluetooth", state)
    end
    native.watch("network.wifi", wifi_state)
    native.watch("bluetooth", bluetooth_state)
    on("flip", function(k)
        if k ~= 1 and k ~= 2 then return end
        local kind, state = k == 1 and "wifi" or "bluetooth", k == 1 and wifi or bluetooth
        if not state.present then failed(state.error or "No hay un adaptador disponible."); return end
        local target = not state.enabled
        start(kind, k == 1 and "network.radio" or "bluetooth.radio", { target },
            target and "Activando radio…" or "Apagando radio…", function(value) return value.enabled == target end)
    end)
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
    on("scan", function(k)
        if k == 1 then
            if not wifi.present then failed(wifi.error or "No hay adaptador Wi-Fi."); return end
            if refreshing.wifi then return end
            refreshing.wifi = true
            call("network.scan", {}, function(error, code)
                refreshing.wifi = nil
                if code ~= 0 then failed(error); return end
                refresh("wifi", "network.wifi", wifi_state)
            end)
        elseif k == 2 then refresh("bluetooth", "bluetooth.state", bluetooth_state) end
    end)
    on("bt_scan", function()
        if not bluetooth.present then failed(bluetooth.error or "No hay adaptador Bluetooth."); return end
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
                if current.interface == network.interface and current.ssid == network.ssid and current.current == connected then return true end
            end
            return false
        end
    end
    on("pick_network", function(index)
        local network = model.networks[index + 1]
        if not network then return end
        if pending.wifi then notice(pending.wifi.message); return end
        if network.current then
            start("wifi", "network.disconnect", { network.interface }, "Desconectando…", network_matches(network, false))
        elseif network.profile == "" then
            if not network.joinable then notice("Esta red necesita un perfil WPA3 o de empresa ya configurado."); return end
            joining = network
            text.windows_wifi_name = network.name
            text.windows_wifi_password = ""
            fact.windows_wifi_join = true
        else
            start("wifi", "network.connect", { network.interface, network.profile }, "Conectando a " .. network.name .. "…", network_matches(network, true))
        end
    end)
    on("windows_wifi_submit", function()
        if not joining or not fact.windows_wifi_join then return end
        local network, password = joining, text.windows_wifi_password or ""
        if pending.wifi then notice(pending.wifi.message); return end
        if start("wifi", "network.join", { network.interface, network.ssid, password },
            "Conectando a " .. network.name .. "…", network_matches(network, true)) then
            text.windows_wifi_password = ""
            fact.windows_wifi_join = false
            joining = nil
        end
    end)
    on("fact:windows_wifi_join", function(open)
        if not open then text.windows_wifi_password = ""; joining = nil end
    end)
    on("pick_gadget", function(index)
        local device = model.gadgets[index + 1]
        if not device then return end
        if device.pairable then
            start("bluetooth", "bluetooth.pair", { device.id }, "Confirma el emparejamiento en el dialogo de Windows.", function(state)
                for _, current in ipairs(state.devices or {}) do
                    if current.id == device.id and current.paired then return true end
                end
                return false
            end)
            return
        end
        if not device.controllable then
            notice(device.transport == "le" and (device.paired
                and "Emparejado por Windows. La conexion depende del perfil o de la aplicacion del dispositivo."
                or "Windows no permite emparejar este dispositivo. Puede requerir su propia aplicacion.")
                or "Este dispositivo no expone control de conexion de audio: " .. device.name)
            return
        end
        local target = not device.current
        start("bluetooth", "bluetooth.connect", { device.id, target },
            (target and "Conectando " or "Desconectando ") .. device.name .. "…", function(state)
                for _, current in ipairs(state.devices or {}) do
                    if current.id == device.id and current.current == target then return true end
                end
                return false
            end)
    end)
end
