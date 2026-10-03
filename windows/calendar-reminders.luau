-- A queued command is not delivery. Keep the event eligible until Windows
-- confirms its own history entry, and keep its tag across retries/restarts.
return function(native_sys, notice, cal, save, tr)
    local pending, retry_at = {}, setmetatable({}, { __mode = "k" })
    local function contains(event)
        return table.find(cal.events, event) ~= nil
    end
    every(20000, function()
        local now = os.time()
        local date = os.date("%Y-%m-%d", now)
        local time = os.date("*t", now)
        local minute = time.hour * 60 + time.min
        for _, event in ipairs(cal.events) do
            local h, m = tostring(event.time or ""):match("^(%d%d):(%d%d)$")
            local due = h and m and tonumber(h) < 24 and tonumber(m) < 60 and tonumber(h) * 60 + tonumber(m)
            if event.date ~= date or not due or minute >= due + 5 or event.told then
                retry_at[event] = nil
            elseif minute >= due and not pending[event] and now >= (retry_at[event] or 0) then
                if not event.notice_tag then
                    event.notice_tag = string.format("%08x%08x", bit32.band(now, 0xffffffff), math.random(0, 0x7fffffff))
                    save()
                end
                pending[event] = true
                local function complete(error, code)
                    pending[event] = nil
                    if not contains(event) then retry_at[event] = nil; return end
                    if code == 0 then
                        event.told = true
                        retry_at[event] = nil
                        save()
                    else
                        retry_at[event] = os.time() + 60
                        notice("No se pudo enviar el recordatorio: " .. tostring(error):match("[^\n]+"))
                    end
                end
                local ok, error = pcall(native_sys.call_async, "notifications.publish",
                    { tr("Calendar") .. " · " .. event.title, event.date .. " · " .. event.time, event.notice_tag }, complete)
                if not ok then complete(error, -1) end
            end
        end
    end)
end
