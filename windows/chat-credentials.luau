    -- Windows is the source of both names and values. No second JSON index
    -- can claim a password was kept when the vault rejected it.
    secrets = {}
    local key_page, key_token, key_rows = 0, 0, {}
    local key_busy = false
    local function show_secrets()
        local pages = math.max(1, math.ceil(#secrets / 12))
        key_page = math.clamp(key_page, 0, pages - 1)
        fact["keys.page"], fact["keys.pages"], fact["keys.count"] = key_page + 1, pages, #secrets
        text["keys.page_label"] = string.format("%d / %d", key_page + 1, pages)
        local out = {}
        key_rows = {}
        for i = key_page * 12 + 1, math.min(#secrets, (key_page + 1) * 12) do
            key_token += 1
            out[#out + 1] = { name = secrets[i], token = key_token }
            key_rows[key_token] = secrets[i]
        end
        model["keys.rows"] = out
    end
    secret_named = function(name)
        for i, value in ipairs(secrets) do
            if string.lower(value) == string.lower(tostring(name or "")) then return i, value end
        end
    end
    local function key_error()
        text["keys.status"] = tr("Windows could not update the saved passwords. Try again.")
    end
    local function refresh_secrets(done)
        local function loaded(value, problem)
            if problem or type(value) ~= "table" then
                fact["keys.readable"] = false
                key_error()
            else
                secrets = value
                fact["keys.readable"] = true
                text["keys.status"] = ""
                show_secrets()
            end
            key_busy = false
            if done then done(not problem and type(value) == "table") end
        end
        local ok = pcall(native_sys.ask_async, "credentials.list", {}, loaded)
        if not ok then loaded(nil, "unavailable") end
    end
    on("keys_keep", function()
        if key_busy then return end
        local name = first_letters(tostring(text["keys.name"] or ""):match("^%s*(.-)%s*$"), 60)
        local value = tostring(text["keys.value"] or "")
        if name == "" or value == "" then text["keys.status"] = tr("A name and a password, both"); return end
        key_busy = true
        local function complete(_, code)
            if code ~= 0 then key_busy = false; key_error(); return end
            if text["keys.value"] == value then text["keys.value"] = "" end
            if text["keys.name"] == name then text["keys.name"] = "" end
            refresh_secrets(function(ok)
                if ok then text["keys.status"] = string.format(tr("Kept as «%s»"), name) end
            end)
        end
        local ok = pcall(native_sys.call_async, "credentials.set", {name, value}, complete)
        if not ok then complete(nil, -1) end
    end)
    on("keys_drop", function(token)
        local name = key_rows[tonumber(token)]
        if key_busy or not name then return end
        key_busy = true
        local function complete(_, code)
            if code ~= 0 then key_busy = false; key_error(); return end
            refresh_secrets(function(ok) if ok then text["keys.status"] = "" end end)
        end
        local ok = pcall(native_sys.call_async, "credentials.remove", {name}, complete)
        if not ok then complete(nil, -1) end
    end)
    on("keys_page", function(delta)
        if key_busy or (delta ~= 1 and delta ~= -1) then return end
        key_page += delta
        show_secrets()
        emit("keys_page_changed")
    end)
    on("fact:section", function(section)
        if section == "keys" and not key_busy then key_busy = true; refresh_secrets() end
    end)
    fact["keys.readable"] = false
    key_busy = true
    refresh_secrets()
