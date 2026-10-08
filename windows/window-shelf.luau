-- Keep six stable faces while retaining the complete native window catalog.
-- Native identifiers expire when a window leaves the catalog; never use HWNDs.
local stone_slots, stone_faces, away = {}, {}, {}
local stone_seq = 0
local restoring = false
local function set_stones(list)
    local order = {}
    away = {}
    for _, window in ipairs(list or {}) do
        if window.minimized and window.id ~= nil and away[window.id] == nil then
            away[window.id] = window
            order[#order + 1] = window.id
        end
    end
    for k = 1, 6 do
        if stone_slots[k] ~= nil and away[stone_slots[k]] == nil then
            stone_slots[k] = nil
            if stone_faces[k] then stone_faces[k].present = false end
        end
    end
    for _, id in ipairs(order) do
        local slot
        for k = 1, 6 do if stone_slots[k] == id then slot = k; break end end
        if not slot then
            for k = 1, 6 do
                if stone_slots[k] == nil then
                    slot = k; stone_slots[k] = id; stone_seq += 1
                    stone_faces[k] = { seq = stone_seq }
                    break
                end
            end
        end
        if slot then
            local window, face = away[id], stone_faces[slot]
            face.title = (window.title and window.title ~= "" and window.title) or window.class or ""
            face.icon = window.icon or ""
            -- The first Unicode codepoint, not the first byte of a UTF-8 title.
            local length = utf8.offset(face.title, 2) or (#face.title + 1)
            face.letter = face.icon == "" and face.title:sub(1, length - 1):upper() or ""
            face.present = true
        end
    end
    local rows = {}
    for k = 1, 6 do
        rows[k] = stone_faces[k] or { title = "", icon = "", letter = "", present = false, seq = 0 }
    end
    model.stones = rows
end
local function restore(ids)
    if restoring then return end
    restoring = true
    local cursor, first_error = 0, nil
    local function next_window()
        cursor += 1
        local id = ids[cursor]
        while id ~= nil and away[id] == nil do cursor += 1; id = ids[cursor] end
        if id == nil then
            restoring = false
            if first_error then notice(first_error) end
            return
        end
        -- One request at a time even with more windows than the worker queue.
        local ok, error = pcall(native_sys.call_async, "window.restore", { id }, function(error, code)
            if code ~= 0 and not first_error then first_error = tostring(error) end
            next_window()
        end)
        if not ok then
            restoring = false
            notice(tostring(error))
        end
    end
    next_window()
end
hooks.restore_all = function()
    local ids = {}
    for id in pairs(away) do ids[#ids + 1] = id end
    table.sort(ids)
    restore(ids)
end
on("restore_stone", function(k)
    if type(k) ~= "number" or k % 1 ~= 0 or k < 0 or k >= 6 then return end
    local id = stone_slots[k + 1]
    if id ~= nil then restore({ id }) end
end)
