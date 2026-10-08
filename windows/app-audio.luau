-- One bounded worker per Core Audio instance. Readback, not command acceptance,
-- ends the preview; an ended stream never transfers its gesture to another.
return function(native, notice, changed)
    local sessions = {}
    local paint
    local function redraw()
        if paint then return end
        paint = after(16, function() paint = nil; changed() end)
    end
    local function valid(v) return type(v) == "number" and v == v and v >= 0 and v <= 1 end
    local function clear_timer(s, key)
        if s[key] then cancel(s[key]); s[key] = nil end
    end
    local function settled(s)
        if s.running or s.queued_volume ~= nil or s.queued_mute ~= nil then return end
        if s.wanted_volume ~= nil and valid(s.actual_volume) and math.abs(s.actual_volume - s.wanted_volume) < 0.005 then
            s.wanted_volume = nil
        end
        if s.wanted_mute == s.actual_mute then s.wanted_mute = nil end
        if s.wanted_volume == nil and s.wanted_mute == nil then clear_timer(s, "confirmation") end
    end
    local pump
    pump = function(id, s)
        if sessions[id] ~= s or s.running or s.scheduled or (s.queued_volume == nil and s.queued_mute == nil) then return end
        s.scheduled = after(16, function()
            s.scheduled = nil
            if sessions[id] ~= s then return end
            local kind = s.queued_volume ~= nil and "volume" or "mute"
            local value = s["queued_" .. kind]
            if value == nil then return end
            s["queued_" .. kind] = nil
            local request = { revision = s.revision }
            s.running = request
            local function done(error, code)
                if sessions[id] ~= s or s.running ~= request then return end
                clear_timer(s, "timeout")
                s.running, s.timed_out = nil, false
                if request.revision == s.revision then
                    if code ~= 0 then
                        s.wanted_volume, s.wanted_mute = nil, nil
                        notice(tostring(error):match("[^\n]+") or "Audio request failed")
                    else
                        settled(s)
                        if s.wanted_volume ~= nil or s.wanted_mute ~= nil then
                            clear_timer(s, "confirmation")
                            s.confirmation = after(3500, function()
                                s.confirmation = nil
                                if sessions[id] ~= s or request.revision ~= s.revision then return end
                                s.wanted_volume, s.wanted_mute = nil, nil
                                notice("The application has not confirmed the audio change.")
                                redraw()
                            end)
                        end
                    end
                end
                redraw()
                pump(id, s)
            end
            s.timeout = after(4500, function()
                s.timeout = nil
                if sessions[id] ~= s or s.running ~= request then return end
                s.timed_out = true
                s.revision += 1
                s.wanted_volume, s.wanted_mute, s.queued_volume, s.queued_mute = nil, nil, nil, nil
                notice("The application is not responding to audio controls.")
                redraw()
            end)
            local ok, error = pcall(native.call_async, "audio.app_" .. kind, { id, value }, done)
            if not ok then done(error, -1) end
        end)
    end
    local function request(id, kind, value)
        local s = sessions[id]
        if not s or s.timed_out then return false end
        clear_timer(s, "confirmation")
        s.revision += 1
        s["wanted_" .. kind], s["queued_" .. kind] = value, value
        pump(id, s)
        redraw()
        return true
    end
    return {
        observe = function(rows)
            local present = {}
            for _, row in ipairs(rows or {}) do
                if type(row.id) == "string" and row.id ~= "" and valid(row.volume) and type(row.muted) == "boolean" then
                    local s = sessions[row.id] or { revision = 0 }
                    sessions[row.id], present[row.id] = s, true
                    s.actual_volume, s.actual_mute = row.volume, row.muted
                    settled(s)
                end
            end
            for id, s in pairs(sessions) do
                if not present[id] then
                    sessions[id] = nil
                    for _, key in ipairs({ "scheduled", "confirmation", "timeout" }) do clear_timer(s, key) end
                end
            end
        end,
        volume = function(id, value)
            if not valid(value) then return false end
            return request(id, "volume", value)
        end,
        mute = function(id)
            local s = sessions[id]
            if not s then return false end
            local current = s.wanted_mute
            if current == nil then current = s.actual_mute end
            return request(id, "mute", not current)
        end,
        preview = function(id, volume, muted)
            local s = sessions[id]
            if not s then return volume, muted end
            if s.wanted_volume ~= nil then volume = s.wanted_volume end
            if s.wanted_mute ~= nil then muted = s.wanted_mute end
            return volume, muted
        end,
    }
end
