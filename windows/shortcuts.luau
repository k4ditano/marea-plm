return function(native_sys, notice, hooks)
    local bindings = {["Win"]="search", ["Win+Space"]="search", ["Win+Shift+A"]="chat",
        ["Win+A"]="controls", ["Win+I"]="settings", ["Win+Tab"]="windows", ["Win+N"]="notifications", ["Win+W"]="layout",
        ["Win+D"]="dock", ["Win+M"]="minimize", ["Win+Shift+M"]="restore_last", ["Win+Q"]="close", ["Win+F"]="fullscreen",
        ["Win+Left"]="focus_previous", ["Win+Up"]="focus_previous",
        ["Win+Right"]="focus_next", ["Win+Down"]="focus_next"}
    local actions = {search="search", chat="chat", controls="windows_controls", settings="settings", notifications="open_tray"}
    local sequence, generation = nil, 0
    local enabled, available, busy, unsaved = false, false, true, false
    local shortcut = native_sys.ask("env", "MAREA_SEARCH_HOTKEY") or "Ctrl+Alt+Space"
    local function paint()
        fact.windows_key_enabled, fact.windows_key_available, fact.windows_key_busy = enabled, available, busy
        text.windows_key_status = tr(busy and "Checking…" or not available and "Keyboard shortcuts unavailable"
            or unsaved and "Changed for this session; saving failed"
            or enabled and "Windows key reserved for Marea" or "Windows key works normally")
        text.windows_search_hint = shortcut ~= "" and string.format(tr("Search also opens with %s"), shortcut) or tr("Search remains available in her menu")
    end
    native_sys.watch("hotkeys", function(value)
        local previous = sequence
        sequence = value.sequence
        if previous == nil or previous == sequence then return end
        local action = actions[value.event]
        if action then emit(action)
        elseif value.event == "windows" and hooks.windows_overview then hooks.windows_overview()
        elseif value.event == "dock" and hooks.windows_dock then hooks.windows_dock()
        elseif value.event == "layout" and hooks.windows_toggle_layout then hooks.windows_toggle_layout()
        elseif value.event == "minimize" and hooks.windows_minimize then hooks.windows_minimize()
        elseif value.event == "restore_last" and hooks.windows_restore_last then hooks.windows_restore_last()
        elseif value.event == "focus_next" and hooks.windows_focus_next then hooks.windows_focus_next()
        elseif value.event == "focus_previous" and hooks.windows_focus_previous then hooks.windows_focus_previous()
        elseif value.event == "close" and hooks.windows_close then hooks.windows_close()
        elseif value.event == "fullscreen" and hooks.windows_fullscreen then hooks.windows_fullscreen() end
    end)
    local args = shortcut == "" and {"search"} or {"search", shortcut}
    local ok, error = pcall(native_sys.call_async, shortcut == "" and "hotkeys.unbind" or "hotkeys.bind", args, function(output, code)
        if code ~= 0 then notice(tr("Could not register the search shortcut") .. " " .. tostring(output or "")) end
    end)
    if not ok then notice(tostring(error)) end
    local function apply(wanted, persist)
        busy = true; generation += 1; local mine = generation; paint()
        local function finish(message)
            if mine ~= generation then return end
            busy = false; paint()
            if message then notice(message) end
        end
        local function confirm(command_error)
            local queued, problem = pcall(native_sys.ask_async, "hotkeys.state", {}, function(state, query_error)
                if mine ~= generation then return end
                available = query_error == nil and type(state) == "table" and state.available == true
                if available then enabled = state.windows_key == true end
                if not available or command_error or enabled ~= wanted then
                    finish(tr("Could not change keyboard shortcuts") .. " " .. tostring(command_error or query_error or "")); return
                end
                if not persist then finish(); return end
                local saved, problem = pcall(native_sys.call_async, "files.write", {"shortcuts.json", {version=1, windows_key=enabled}}, function(output, code)
                    if mine ~= generation then return end
                    unsaved = code ~= 0
                    finish(unsaved and tr("Could not save keyboard shortcuts. The current session keeps your choice.") or nil)
                end)
                if not saved then unsaved = true; finish(tostring(problem)) end
            end)
            if not queued then available = false; finish(tostring(problem)) end
        end
        local queued, problem = pcall(native_sys.call_async, "hotkeys.windows", {wanted and bindings or false}, function(output, code)
            if mine ~= generation then return end
            confirm(code ~= 0 and tostring(output or "") or nil)
        end)
        if not queued then confirm(tostring(problem)) end
        after(15000, function()
            if mine ~= generation or not busy then return end
            generation += 1; busy = false; available = false; paint()
            notice(tr("Keyboard shortcuts did not respond. Reopen this page to check their state."))
        end)
    end
    on("windows_toggle_key", function() if available and not busy then apply(not enabled, true) end end)
    on("fact:section", function(section)
        if section ~= "windows_shortcuts" or busy then return end
        local mine = generation
        local queued, problem = pcall(native_sys.ask_async, "hotkeys.state", {}, function(state, error)
            if mine ~= generation or busy then return end
            available = error == nil and type(state) == "table" and state.available == true
            if available then enabled = state.windows_key == true end
            paint()
        end)
        if not queued then available = false; paint(); notice(tostring(problem)) end
    end)
    on("fact:locale", paint)
    on("windows_language_updated", paint)
    paint()
    local loaded = false
    local queued = pcall(native_sys.ask_async, "files.read", {"shortcuts.json", "json"}, function(settings, error)
        if loaded then return end
        loaded = true
        apply(error == nil and type(settings) == "table" and settings.version == 1 and settings.windows_key == true, false)
    end)
    if not queued then loaded = true; apply(false, false) end
    after(10000, function() if not loaded then loaded = true; apply(false, false) end end)
end
