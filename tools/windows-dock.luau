local language = tostring(sys.ask("env", "MAREA_LOCALE") or "en")
local monitor = tostring(sys.ask("env", "MAREA_DOCK_MONITOR") or "")
fact.locale = language == "es" and "es" or "en"
local closing, querying, again = false, false, false
local function geometry()
    if closing then return end
    if querying then again = true; return end
    querying = true
    local completed = false
    local function done(output, code)
        if completed then return end
        completed = true
        querying = false
        if closing then return end
        local ok, screens = pcall(json.decode, tostring(output or ""))
        local found
        if code == 0 and ok and type(screens) == "table" then
            for _, value in ipairs(screens) do if value.name == monitor then found = value; break end end
        end
        local bounds, work = found and found.bounds, found and found.work
        local scale = found and tonumber(found.scale)
        if bounds and work and scale and scale > 0 and work.width > 0 and work.height > 0
            and work.x >= bounds.x and work.y >= bounds.y
            and work.x + work.width <= bounds.x + bounds.width
            and work.y + work.height <= bounds.y + bounds.height then
            fact.dock_left = (work.x - bounds.x) / scale
            fact.dock_width = work.width / scale
            fact.dock_bottom = (bounds.y + bounds.height - work.y - work.height) / scale
            fact.dock_ready = true
            fact.dock_failed = false
            text.dock_status = ""
        else
            fact.dock_ready = false
            fact.dock_failed = true
            text.dock_status = tr("The dock could not read this screen.")
        end
        if again then again = false; geometry() end
    end
    local ok, error = pcall(run, "pleamar-wm", {"monitors"}, done)
    if not ok then done(tostring(error), 1) end
end
on("dock_close", function()
    if closing then return end
    closing = true
    local completed = false
    local function done(output, code)
        if completed then return end
        completed = true
        if code ~= 0 then
            closing = false
            text.dock_status = tr("The dock could not close.")
        end
    end
    local ok, error = pcall(run, "pleamar-wm", {"--say", "windows-dock", "quit"}, done)
    if not ok then done(tostring(error), 1) end
end)
on("fact:screen.width", geometry)
on("fact:screen.height", geometry)
-- A changing catalog must not leave a menu pointing at a different program.
on("fact:win.docks.0", function() fact.dock_menu = -1 end)
for i = 0, 11 do
    on("text:win.dock.0." .. i .. ".name", function() fact.dock_menu = -1 end)
end
geometry()
