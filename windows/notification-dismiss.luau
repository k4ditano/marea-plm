-- Installed beside the notification rows. A row only disappears permanently
-- after Windows accepts its dismissal; failed commands restore the same item.
local notification_pending = {}
local function dismiss_native(id)
    if notification_pending[id] then return end
    notification_pending[id] = true
    local original
    for _, row in ipairs(rows) do if row.id == id then original = row end end
    local function complete(error, code)
        notification_pending[id] = nil
        if code == 0 then
            finished[id] = true
            for _, row in ipairs(rows) do
                if row.id == id then row.done = true; row.flying = nil end
            end
            if live then
                for k = #live, 1, -1 do if live[k].id == id then table.remove(live, k) end end
            end
            refill(true)
        else
            finished[id] = nil
            for k, row in ipairs(rows) do
                if row.id == id then
                    row.done, row.flying = false, nil
                    windows_row_keys[k] = nil
                end
            end
            -- The slot may already contain a newer notification. Restore by ID.
            if original then
                original.done, original.flying = false, nil
                local category = original.cat
                local count = 0
                for _, item in ipairs(live or {}) do
                    if not finished[item.id] and not snoozed[item.id] and row_of(item).cat == category then count += 1 end
                end
                fact["n." .. category] = count
            end
            refill(true)
            notice(tostring(error))
        end
        render()
        cap_counts()
    end
    local ok, error = pcall(native_sys.call_async, "notifications.dismiss", {id}, complete)
    if not ok then complete(error, -1) end
end
