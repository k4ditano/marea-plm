return function(native_run, native_sys, notice)
    local state, busy, sequence = {}, false, 0
    local function paint()
        fact.windows_startup_available = state.available == true
        fact.windows_startup_busy = busy
        fact.windows_startup_enabled = state.enabled == true
        text.windows_startup_status = tr(busy and "Checking…"
            or state.reason == "installed-only" and "Available after installation"
            or state.reason == "another-installation" and "Managed by another installation"
            or state.blocked and "Disabled in Windows startup apps"
            or state.reason == "error" and "Could not read startup settings"
            or state.enabled and "Starts when you sign in" or "Start manually")
    end
    local function request(action)
        if busy then return end
        busy = true; paint()
        sequence += 1
        local ticket = sequence
        local ok = pcall(native_run, "powershell.exe", {"-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", "tools/startup.ps1", "-Action", action}, function(output, code)
            if ticket ~= sequence or not busy then return end
            local decoded, value = pcall(json.decode, output or "")
            state = decoded and type(value) == "table" and value or {reason="error"}
            busy = false; paint()
            if code ~= 0 then notice(tr("Could not update startup settings")) end
        end, {cwd="."})
        if not ok then busy = false; state = {reason="error"}; paint(); notice(tr("Could not update startup settings")) end
        after(15000, function()
            if ticket ~= sequence or not busy then return end
            sequence += 1; busy = false; state = {reason="error"}; paint()
            notice(tr("Could not update startup settings"))
        end)
    end
    on("windows_toggle_startup", function()
        if state.available ~= true then return end
        -- If Windows disabled a registered entry, remove it rather than claiming
        -- that rewriting Run overrode the operating system's decision.
        request(state.registered and "disable" or "enable")
    end)
    on("fact:page", function(value) if value == "settings" then request("state") end end)
    on("fact:locale", paint)
    on("windows_language_updated", paint)
    paint()
    request("state")
end
