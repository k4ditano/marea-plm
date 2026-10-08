-- Native Windows services. Unsupported features are never synthesized.
local native_sys = sys
local native_run = run
local native_spawn = spawn
local function notice(message)
    text.windows_status = message
    fact.windows_notice = true
    log("Windows:", message)
end
local function perform(name, ...)
    fact.windows_notice = false
    local ok, error = pcall(native_sys.call_async, name, { ... }, function(error, code)
        if code ~= 0 then notice(name .. ": " .. tostring(error):match("[^\n]+")) end
    end)
    if not ok then notice(name .. ": " .. tostring(error):match("[^\n]+")) end
    return ok
end
local run_agent_reader = install_agent_reader(native_run, notice)
install_media_controls(native_sys, notice)
install_startup(native_run, native_sys, notice)

on("windows_lock", function() perform("session.lock") end)
on("windows_lock_info", function() notice("El bloqueo utiliza la pantalla segura de Windows.") end)
on("fact:page", function(page)
    fact.windows_notice = false
end)
local brightness = {}
native_sys.watch("brightness", function(state) brightness = state end)
local brightness_monitor, brightness_revision = nil, 0
local function select_brightness_monitor(k)
    if fact["hosts." .. k] ~= true then return end
    local name = text["screen." .. k .. ".name"]
    if name and name ~= "" and name ~= brightness_monitor then
        brightness_monitor = name
        brightness_revision += 1
        local revision = brightness_revision
        local function failed(error)
            if revision ~= brightness_revision then return end
            brightness_monitor = nil
            notice(error)
        end
        local ok, error = pcall(native_sys.call_async, "brightness.monitor", { name }, function(error, code)
            if code ~= 0 then failed(error) end
        end)
        if not ok then failed(tostring(error)) end
    end
end
for k = 0, 2 do
    on("fact:hosts." .. k, function() select_brightness_monitor(k) end)
    on("text:screen." .. k .. ".name", function() select_brightness_monitor(k) end)
    select_brightness_monitor(k)
end
on("windows_display_info", function()
    notice(brightness.present and ("Brillo de " .. (brightness.name or "la pantalla activa"))
        or brightness.error or "Esta pantalla no permite cambiar el brillo.")
end)
install_level_controls(native_sys, notice)
local watch_notifications, refresh_notification_row, notification_age = install_notification_controls(native_sys, notice)
native_sys.watch("tray.state", function(state)
    if state.available == false then notice(state.error or "La bandeja de Windows no está disponible.") end
end)
local sys = {
    ask_async = native_sys.ask_async,
    call_async = native_sys.call_async,
    watch = function(name, callback)
        if name == "notifications" then return watch_notifications(callback) end
        return native_sys.watch(name, callback)
    end,
    ask = function(name, ...)
        if name == "env" then
            local variable = ...
            if variable == "HOME" then variable = "USERPROFILE" end
            return native_sys.ask(name, variable)
        end
        return native_sys.ask(name, ...)
    end,
    call = function(name, ...)
        perform(name, ...)
    end,
}
local seen = {}
local weather = install_weather(native_run, native_sys, notice)
local run = function(command, args, callback, options)
    if command == "curl" then return weather(args, callback) end
    if command == "timedatectl" then
        -- A Windows time-zone ID is not a city. Let the calendar's city field
        -- choose the location instead of making a misleading geographic guess.
        if callback then after(1, function() callback("", 0) end) end
        return
    end
    if command == "node" and args and #args == 2 and args[1] == "tools/reservas" and args[2] == "--lines" then
        return run_agent_reader(callback)
    end
    if command == "xdg-open" then
        native_sys.call_async("shell.open", { args[1] }, function(error, code)
            if code ~= 0 then notice(error) end
            if callback then callback(error, code) end
        end)
        return
    end
    if not seen[command] then log("Windows: external integration unavailable:", command); seen[command] = true end
    if command == "grim" or command == "slurp" or command == "wf-recorder" then notice("Esta integración externa no está disponible en Windows.") end
    if callback then after(1, function() callback("", -1) end) end
end
local spawn = function(command, args, on_line, on_exit, options)
    if command == "agent/sandbox" then
        return native_spawn("marea-agent", args, on_line, on_exit, options)
    end
    notice("No disponible en Windows: " .. command)
    error("Windows profile cannot start " .. command)
end
