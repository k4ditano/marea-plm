-- ── the system pages: Wi-Fi, Bluetooth, sound and focus ──────────
--  All of it from pleamar's own services —NetworkManager, BlueZ and the
--  sound server, spoken to directly—, and flipped from what they say rather
--  than from what was assumed.
--  marea.luau loads it, and hands it what it uses of its own.
return function(shared)
    local hooks = shared.hooks
    local net_state, bt_state, audio_state = {}, {}, {}
    local runtime = sys.ask("env", "XDG_RUNTIME_DIR") or "/tmp"
    local function toast(words)
        fact["drift.result"] = 1
        text["drift.toast"] = words
        emit("say_toast")
    end

    --  The control center's two switches.
    on("flip", function(k)
        if k == 1 then
            pcall(sys.call, "network.wifi", not net_state.wifi)
        elseif k == 2 then
            pcall(sys.call, "bluetooth.power", not bt_state.powered)
        end
    end)

    -- ── Wi-Fi ──────────────────────────────────────────────────────
    --  On top, the connection in use; below, the rest in range, the known
    --  ones first and then by strength, five at a time (the wheel goes
    --  through them). A new network with a password asks for it in place;
    --  one already known, or open, joins at once. Whichever is being joined
    --  breathes until the system says it is the one in use, or for 25 seconds.
    local joining_name, joining_since = nil, 0
    local asked_name = nil
    local failed_name, failed_until = nil, 0
    local shown_nets = {}
    local offset = 0

    local function quality(p)
        if p >= 75 then return tr("Excellent signal") end
        if p >= 50 then return tr("Good signal") end
        if p >= 25 then return tr("Fair signal") end
        return tr("Weak signal")
    end

    local function paint_networks()
        local current = nil
        local others = {}
        for _, n in ipairs(net_state.networks or {}) do
            if n.active then current = n
            else others[#others + 1] = n end
        end
        table.sort(others, function(a, b)
            if (a.known == true) ~= (b.known == true) then return a.known == true end
            return (a.strength or 0) > (b.strength or 0)
        end)
        offset = math.clamp(offset, 0, math.max(0, #others - 5))
        shown_nets = {}
        local rows = {}
        for k = offset + 1, math.min(#others, offset + 5) do
            local n = others[k]
            shown_nets[#shown_nets + 1] = n
            --  The networks' strength comes from 0 to 1; the one in use's, 0 to 100.
            local p = math.floor((n.strength or 0) * 100 + 0.5)
            rows[#rows + 1] = { name = n.ssid, signal = p / 100, percent = p, current = false, secure = n.secure == true, known = n.known == true }
        end
        model.networks = rows
        fact["wifi.offset"] = offset
        fact["wifi.total"] = #others
        fact["switched_on.1"] = net_state.wifi == true
        if joining_name ~= nil and current and current.ssid == joining_name then joining_name = nil end

        local wired = net_state.kind == "wired" and net_state.online
        local state, title, status
        if joining_name ~= nil then
            state, title, status = 4, joining_name, tr("Joining…")
        elseif wired then
            state, title, status = 3, tr("Connected by cable"), net_state.name or ""
        elseif not net_state.wifi then
            state, title, status = 0, tr("Wi-Fi is off"), tr("Its radio is resting")
        elseif current or (net_state.online and net_state.kind == "wifi") then
            local p = math.floor(current and (current.strength or 0) * 100 or (net_state.strength or 0) + 0.5)
            state, title, status = 2, current and current.ssid or net_state.name or "", string.format("%s · %d%%", quality(p), p)
        else
            state, title, status = 1, tr("Not connected"), tr("Choose a network below")
            if failed_name and os.time() < failed_until then
                status = string.format(tr("Could not join «%s»"), failed_name)
            end
        end
        fact["wifi.state"] = state
        text["wifi.title"] = title
        text["wifi.status"] = status
        if state ~= 2 and fact["wifi.sharing"] then fact["wifi.sharing"] = false end
    end
    table.insert(hooks.language, paint_networks)

    sys.watch("network", function(state)
        net_state = state or {}
        paint_networks()
    end)

    every(3000, function()
        if joining_name ~= nil and os.time() - joining_since > 25 then
            log("wi-fi · could not join", joining_name)
            failed_name, failed_until = joining_name, os.time() + 8
            joining_name = nil
            paint_networks()
        end
    end)

    local function join(name, password)
        joining_name, joining_since = name, os.time()
        failed_name = nil
        local ok, err = pcall(sys.call, "network.connect", name, password)
        if not ok then
            log("wi-fi · joining failed:", err)
            failed_name, failed_until = name, os.time() + 8
            joining_name = nil
        end
        paint_networks()
    end

    local function stop_asking()
        fact.asking = -1
        text.wifi_pw = ""
        asked_name = nil
    end

    on("pick_network", function(i)
        local n = shown_nets[i + 1]
        if n == nil then return end
        if n.secure and not n.known then
            asked_name = n.ssid
            text["ask.name"] = n.ssid
            text.wifi_pw = ""
            fact.asking = i
            return
        end
        stop_asking()
        join(n.ssid, nil)
    end)
    on("join", function()
        local name, password = asked_name, text.wifi_pw or ""
        stop_asking()
        if name ~= nil and password ~= "" then join(name, password) end
    end)
    on("forget_ask", stop_asking)

    on("wifi_forget", function(i)
        local n = shown_nets[i + 1]
        if n == nil then return end
        if pcall(sys.call, "network.forget", n.ssid) then
            toast(string.format(tr("Forgot «%s»"), n.ssid))
        end
    end)
    on("wifi_disconnect", function()
        joining_name = nil
        pcall(sys.call, "network.disconnect")
        paint_networks()
    end)
    on("wifi_power", function() pcall(sys.call, "network.wifi", true) end)
    on("wifi_rescan", function()
        pcall(sys.call, "network.scan")
        fact["wifi.scanning"] = true
        after(4000, function() fact["wifi.scanning"] = false end)
    end)
    on("wifi_scroll", function(w)
        offset = offset - (w > 0 and 1 or -1)
        paint_networks()
    end)

    --  Sharing it: the password NetworkManager keeps for the connection in
    --  use, and a code a phone's camera reads to join. The code is made by
    --  `qrencode` from its input —the password never goes in an argument—,
    --  into the user's runtime folder, and goes when the sharing ends.
    local qr_file = runtime .. "/marea-wifi-share.png"
    local qr_version = 0
    local function forget_qr()
        model.wifi_qr = {}
        fact["wifi.has_qr"] = false
        run("rm", { "-f", qr_file }, nil, { output = false })
    end
    local function qr_escape(s)
        return (tostring(s):gsub("([\\;,:\"])", "\\%1"))
    end
    local function share()
        local name = text["wifi.title"] or ""
        fact["wifi.sharing"] = true
        text["wifi.share_hint"] = string.format(tr("Scan it with your phone to join «%s»."), name)
        text["wifi.password"] = "…"
        forget_qr()
        run("nmcli", { "-t", "-f", "NAME,TYPE", "connection", "show", "--active" }, function(out)
            local id = nil
            for line in tostring(out):gmatch("[^\n]+") do
                local n, kind = line:match("^(.*):([^:]+)$")
                if kind == "802-11-wireless" and id == nil then id = n:gsub("\\:", ":") end
            end
            if id == nil then
                text["wifi.password"] = tr("It could not be read")
                return
            end
            run("nmcli", { "-s", "-g", "802-11-wireless-security.key-mgmt,802-11-wireless-security.psk", "connection", "show", "id", id }, function(sec, code)
                if code ~= 0 then
                    text["wifi.password"] = tr("It could not be read")
                    return
                end
                local lines = {}
                for l in (tostring(sec) .. "\n"):gmatch("([^\n]*)\n") do lines[#lines + 1] = l end
                local mgmt, psk = lines[1] or "", lines[2] or ""
                local open = mgmt == "" or mgmt == "none"
                text["wifi.password"] = open and tr("None: it is open") or psk
                local payload = open and string.format("WIFI:T:nopass;S:%s;;", qr_escape(name))
                    or string.format("WIFI:T:%s;S:%s;P:%s;;", mgmt == "sae" and "SAE" or "WPA", qr_escape(name), qr_escape(psk))
                run("qrencode", { "-o", qr_file, "-s", "8", "-m", "1", "-l", "M" }, function(_, qcode)
                    if qcode ~= 0 or not fact["wifi.sharing"] then return end
                    qr_version = qr_version + 1
                    model.wifi_qr = { { pic = qr_file .. "?" .. qr_version } }
                    fact["wifi.has_qr"] = true
                end, { input = payload })
            end)
        end)
    end
    on("wifi_share", share)
    --  The finder opens the page and shares at once: «compartir wifi».
    hooks.wifi_share = function()
        if fact["wifi.state"] == 2 then share() end
    end
    on("wifi_unshare", function()
        fact["wifi.sharing"] = false
        text["wifi.password"] = ""
        forget_qr()
    end)
    on("wifi_copy", function()
        local pw = text["wifi.password"] or ""
        if pw == "" or pw == "…" then return end
        run("wl-copy", {}, nil, { input = pw, output = false })
        toast(tr("Password copied"))
    end)

    -- ── Bluetooth ──────────────────────────────────────────────────
    --  Two lists: the paired ones —connected first— and, while looking, the
    --  new ones near. Each with a drawing by what it says it is.
    local KINDS = {
        ["audio-headphones"] = 1, ["audio-headset"] = 1,
        ["input-mouse"] = 2, ["input-keyboard"] = 3, ["phone"] = 4,
        ["computer"] = 5, ["input-gaming"] = 6, ["audio-card"] = 7, ["audio-speakers"] = 7,
    }
    local busy_address, busy_since, busy_word = nil, 0, ""
    local bt_rows = {}

    local function paint_gadgets()
        local mine, near = {}, {}
        for _, d in ipairs(bt_state.devices or {}) do
            if d.paired then mine[#mine + 1] = d
            elseif bt_state.discovering and (d.name or "") ~= "" then near[#near + 1] = d end
        end
        table.sort(mine, function(a, b)
            if (a.connected == true) ~= (b.connected == true) then return a.connected == true end
            return (a.name or "") < (b.name or "")
        end)
        local near_n = math.min(#near, #mine > 0 and math.max(2, 5 - #mine) or 5)
        local mine_n = math.min(#mine, 5 - (near_n > 0 and near_n or 0))
        if near_n == 0 then mine_n = math.min(#mine, 5) end
        bt_rows = {}
        local function row(d, base)
            bt_rows[#bt_rows + 1] = d
            local state, status
            if d.address == busy_address then
                state, status = 2, busy_word
            elseif d.connected then
                state, status = 1, tr("Connected")
            elseif d.paired then
                state, status = 0, tr("Paired")
            else
                state, status = 3, tr("New · press Pair")
            end
            return { name = d.name ~= "" and d.name or d.address, status = status, kind = KINDS[d.icon or ""] or 0,
                     state = state, battery = d.battery or -1, base = base }
        end
        local a, b = {}, {}
        for k = 1, mine_n do a[k] = row(mine[k], 0) end
        for k = 1, near_n do b[k] = row(near[k], mine_n) end
        model.bt_mine = a
        model.bt_near = b
        fact["switched_on.2"] = bt_state.powered == true
        fact.bt_scanning = bt_state.discovering == true
        fact["bt.present"] = bt_state.present ~= false
        fact["bt.on"] = bt_state.present ~= false and bt_state.powered == true
        fact["bt.busy"] = busy_address ~= nil
        local first = mine[1]
        text["bt.sub"] = (first and first.connected) and first.name or (bt_state.powered and tr("On") or tr("Off"))
    end
    table.insert(hooks.language, paint_gadgets)

    sys.watch("bluetooth", function(state)
        local was = {}
        for _, d in ipairs(bt_state.devices or {}) do was[d.address] = d.connected end
        bt_state = state or {}
        --  The one being worked on is done when its connection changed.
        if busy_address then
            for _, d in ipairs(bt_state.devices or {}) do
                if d.address == busy_address and was[d.address] ~= nil and was[d.address] ~= d.connected then busy_address = nil end
            end
        end
        paint_gadgets()
    end)
    every(3000, function()
        if busy_address and os.time() - busy_since > 20 then
            busy_address = nil
            paint_gadgets()
        end
    end)

    on("pick_gadget", function(i)
        local d = bt_rows[i + 1]
        if d == nil or d.address == nil or busy_address then return end
        busy_address, busy_since = d.address, os.time()
        busy_word = d.connected and tr("Disconnecting…") or (d.paired and tr("Connecting…") or tr("Pairing…"))
        paint_gadgets()
        local ok, err = pcall(sys.call, d.connected and "bluetooth.disconnect" or "bluetooth.connect", d.address)
        if not ok then
            log("bluetooth ·", err)
            busy_address = nil
            toast(string.format(tr("«%s» did not answer"), d.name or d.address))
            paint_gadgets()
        end
    end)
    on("bt_forget", function(i)
        local d = bt_rows[i + 1]
        if d == nil or d.address == nil then return end
        if pcall(sys.call, "bluetooth.forget", d.address) then
            toast(string.format(tr("Forgot «%s»"), d.name or d.address))
        end
    end)
    on("bt_power", function() pcall(sys.call, "bluetooth.power", true) end)
    on("bt_scan", function()
        pcall(sys.call, "bluetooth.scan", not bt_state.discovering)
    end)

    --  Opening a page asks for a fresh look: the networks around, and the gadgets
    --  near (it listens while the page is open, and stops when it closes).
    on("scan", function(k)
        if k == 1 then pcall(sys.call, "network.scan")
        elseif k == 2 and bt_state.powered and not bt_state.discovering then pcall(sys.call, "bluetooth.scan", true) end
    end)
    on("fact:page", function(p)
        if p ~= "bluetooth" and bt_state.discovering then pcall(sys.call, "bluetooth.scan", false) end
        if p ~= "wifi" then
            stop_asking()
            if fact["wifi.sharing"] then
                fact["wifi.sharing"] = false
                text["wifi.password"] = ""
                forget_qr()
            end
        end
        if p ~= "sound" then fact["sound.choosing"] = 0 end
    end)

    -- ── sound: where it plays, where it listens, and what plays ─────
    --  pleamar says which devices there are —`outputs` and `inputs`— and
    --  what is playing —`apps`, each stream with its level—; here they are
    --  only put in lists, the names trimmed (PipeWire's carry the whole card
    --  model) and each application given the icon the system knows it by.
    local function shorten(name)
        local clean = tostring(name):gsub("%s+", " ")
        if (utf8.len(clean) or 0) > 42 then clean = clean:sub(1, utf8.offset(clean, 42) - 1) .. "…" end
        return clean
    end
    local shown_apps = {}
    local apps_offset = 0
    --  Its icon: the one it gives, or that of the program it is, found in the
    --  applications the finder knows.
    local function icon_of(a)
        local wanted = { (a.binary or ""):lower(), (a.name or ""):lower(), (a.icon or ""):lower() }
        for _, e in ipairs(shared.apps()) do
            local keys = { (e.id or ""):lower(), (e.wmclass or ""):lower(), (e.name or ""):lower(),
                           ((e.exec or ""):match("^%S*") or ""):match("([^/]+)$") or "" }
            for _, w in ipairs(wanted) do
                if w ~= "" then
                    for _, k in ipairs(keys) do
                        if k ~= "" and (k == w or k:lower() == w) then return e.icon end
                    end
                end
            end
        end
        return nil
    end
    local function paint_sound()
        local outputs, mics = {}, {}
        local out_name, in_name = tr("No output"), tr("No microphone")
        for _, a in ipairs(audio_state.outputs or {}) do
            outputs[#outputs + 1] = { name = shorten(a.name), id = a.id, current = a.default == true }
            if a.default then out_name = shorten(a.name) end
        end
        for _, a in ipairs(audio_state.inputs or {}) do
            mics[#mics + 1] = { name = shorten(a.name), id = a.id, current = a.default == true }
            if a.default then in_name = shorten(a.name) end
        end
        model.outputs = outputs
        model.mics = mics
        text["sound.out_name"] = out_name
        text["sound.in_name"] = in_name
        local list = audio_state.apps or {}
        apps_offset = math.clamp(apps_offset, 0, math.max(0, #list - 3))
        shown_apps = {}
        local rows = {}
        for k = apps_offset + 1, math.min(#list, apps_offset + 3) do
            local a = list[k]
            shown_apps[#shown_apps + 1] = a
            local icon = icon_of(a)
            local title = a.title or ""
            if title == a.name then title = "" end
            local name = a.name ~= nil and a.name ~= "" and a.name or "?"
            rows[#rows + 1] = { name = name, title = title, icon = icon or "", has_icon = icon ~= nil,
                                letter = utf8.char(utf8.codepoint(name, 1)):upper(),
                                volume = math.clamp(a.volume or 0, 0, 1), muted = a.muted == true, playing = a.playing ~= false }
        end
        model.sound_apps = rows
        text["sound.more"] = #list > 3 and string.format(tr("%d of %d"), math.min(#list, apps_offset + 3), #list) or ""
    end
    table.insert(hooks.language, paint_sound)
    sys.watch("audio", function(state)
        audio_state = state or {}
        paint_sound()
    end)
    on("pick_device", function(i)
        --  The two lists go together: the first ones are outputs and the rest
        --  mics, which is how they are seen on the page.
        local outputs = model.outputs or {}
        local chosen = outputs[i + 1]
        if chosen == nil then chosen = (model.mics or {})[i - #outputs + 1] end
        if chosen ~= nil then pcall(sys.call, "audio.default", chosen.id) end
    end)
    on("app_volume", function(v)
        local a = shown_apps[math.floor(v / 1000) + 1]
        if a then pcall(sys.call, "audio.app_volume", a.id, (v % 1000) / 100) end
    end)
    on("app_mute", function(i)
        local a = shown_apps[i + 1]
        if a then pcall(sys.call, "audio.app_mute", a.id) end
    end)
    on("sound_scroll", function(w)
        apps_offset = apps_offset - (w > 0 and 1 or -1)
        paint_sound()
    end)

    -- ── focus ───────────────────────────────────────────────────────
    --  When it would end, said as the hour; and how much of today has
    --  been spent in it, kept on disk so that it survives a restart.
    --  And the length last chosen, which is the one offered next time.
    local focus = { day = "", minutes = 0, last = 25 }
    do
        local ok, saved = pcall(sys.ask, "files.read", "focus.json", "json")
        if ok and type(saved) == "table" then focus = saved end
    end
    fact["focus.mins"] = focus.last or 25
    local started = nil
    local function paint_focus()
        local chosen = tonumber(fact["focus.mins"]) or 25
        local mins = fact.haven and (tonumber(fact.remaining) or 0) or chosen
        text["focus.until"] = string.format(tr("until %s"), os.date("%H:%M", os.time() + mins * 60))
        local today = os.date("%Y-%m-%d")
        local m = focus.day == today and (focus.minutes or 0) or 0
        if started then m = m + math.floor((os.time() - started) / 60) end
        text["focus.today"] = m > 0 and string.format(tr("%d min of focus today"), m) or ""
    end
    table.insert(hooks.language, paint_focus)
    on("fact:focus.mins", function(m)
        paint_focus()
        if focus.last ~= m then
            focus.last = m
            pcall(sys.call, "files.write", "focus.json", focus)
        end
    end)
    on("fact:remaining", paint_focus)
    on("fact:haven", function(on_now)
        if on_now then
            started = started or os.time()
        elseif started then
            local today = os.date("%Y-%m-%d")
            if focus.day ~= today then focus = { day = today, minutes = 0 } end
            focus.minutes = (focus.minutes or 0) + math.floor((os.time() - started) / 60 + 0.5)
            started = nil
            pcall(sys.call, "files.write", "focus.json", focus)
        end
        paint_focus()
    end)
    every(30000, paint_focus)
    paint_focus()
end
