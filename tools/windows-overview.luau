local language = tostring(sys.ask("env", "MAREA_LOCALE") or "en")
fact.locale = language == "es" and "es" or "en"
local closing, selected, attempt = false, nil, 0
local function close()
    if closing then return end
    closing = true
    local ok, error = pcall(run, "pleamar-wm", {"--say", "windows-overview", "quit"}, function(output, code)
        if code ~= 0 then
            closing = false
            text.overview_status = tr("The window view could not close.")
        end
    end)
    if not ok then closing = false; text.overview_status = tostring(error) end
end
local function focused()
    if selected ~= nil and fact["win.focus"] == selected then close() end
end
on("overview_close", close)
on("overview_select", function(slot)
    if type(slot) ~= "number" or slot % 1 ~= 0 or slot < 0 or slot >= 32 then return end
    if fact["win." .. slot .. ".open"] ~= true then return end
    selected = slot
    attempt += 1
    local mine = attempt
    text.overview_status = ""
    focused()
    after(1000, function()
        if attempt == mine and selected == slot and not closing then
            selected = nil
            text.overview_status = tr("Windows did not activate this window. Try selecting it again.")
        end
    end)
end)
on("fact:win.focus", focused)
