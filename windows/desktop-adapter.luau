-- Native Windows services. Unsupported features are never synthesized.
local native_sys = sys
local native_run = run
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

local hotkey_sequence
native_sys.watch("hotkeys", function(value)
    local previous = hotkey_sequence
    hotkey_sequence = value.sequence
    if previous ~= nil and previous ~= value.sequence and value.event == "search" then emit("search") end
end)
local search_shortcut = native_sys.ask("env", "MAREA_SEARCH_HOTKEY") or "Ctrl+Alt+Space"
if search_shortcut ~= "" then
    perform("hotkeys.bind", "search", search_shortcut)
else
    perform("hotkeys.unbind", "search")
end
on("windows_lock", function() perform("session.lock") end)
on("windows_lock_info", function() notice("El bloqueo utiliza la pantalla segura de Windows.") end)
on("fact:page", function(page)
    fact.windows_notice = false
end)
install_device_controls(native_sys, notice)
local brightness = {}
native_sys.watch("brightness", function(state) brightness = state end)
local function select_brightness_monitor(k)
    if fact["hosts." .. k] ~= true then return end
    local name = text["screen." .. k .. ".name"]
    if name and name ~= "" then
        local ok, error = pcall(native_sys.call_async, "brightness.monitor", { name }, function(error, code)
            if code ~= 0 then notice(error) end
        end)
        if not ok then notice(tostring(error)) end
    end
end
for k = 0, 1 do
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
local spawn = function(command)
    notice("No disponible en Windows: " .. command)
    error("Windows profile cannot start " .. command)
end
