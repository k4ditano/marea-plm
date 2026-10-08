-- Coalesce drags to the newest level; all commands retain the player's identity.
return function(native_sys, notice)
    local player, actual, available = "", 0, false
    local queued, running, scheduled, serial, blocked = nil, nil, false, 0, false
    local pump
    local function paint()
        fact.windows_media_can_volume = available and not blocked
        fact.windows_media_volume = actual
        text.windows_media_volume_status = tr("Player volume unavailable")
    end
    pump = function()
        if running or scheduled or not queued then return end
        scheduled = true
        after(16, function()
            scheduled = false
            if running or not queued then return end
            local request = queued
            queued, running = nil, request
            local function done(error, code)
                if running ~= request then return end
                running, blocked = nil, false
                if request.player == player and request.serial == serial then
                    if code ~= 0 then
                        fact.windows_media_volume_pending = false
                        notice(tostring(error))
                    else
                        -- Read back from Core Audio; an accepted command alone
                        -- is not confirmation of the displayed value.
                        local ok, error = pcall(native_sys.ask_async, "media.state", {}, function(state)
                            if request.serial ~= serial or request.player ~= player then return end
                            if state and state.player == player and state.can_volume then actual = state.volume end
                            fact.windows_media_volume_pending = false
                            paint()
                        end)
                        if not ok then fact.windows_media_volume_pending = false; notice(tostring(error)) end
                        after(3500, function()
                            if request.serial == serial and fact.windows_media_volume_pending then
                                fact.windows_media_volume_pending = false; paint()
                                notice(tr("Player volume did not respond"))
                            end
                        end)
                    end
                end
                paint(); pump()
            end
            local ok, error = pcall(native_sys.call_async, "media.volume", {request.player, request.value}, done)
            if not ok then done(error, -1) end
            after(4500, function()
                if running ~= request then return end
                blocked, queued = true, nil
                serial += 1
                fact.windows_media_volume_pending = false
                paint()
                notice(tr("Player volume did not respond"))
            end)
        end)
    end
    on("windows_set_media_volume", function(value)
        if not available or blocked or type(value) ~= "number" or value ~= value then return end
        serial += 1
        queued = {player = player, serial = serial, value = math.clamp(value, 0, 1)}
        fact.windows_media_volume_pending = true
        pump()
    end)
    paint()
    return function(state)
        state = type(state) == "table" and state or {}
        if player ~= state.player then
            player, queued = state.player or "", nil
            serial += 1
            fact.windows_media_volume_pending = false
            fact.windows_media_volume_drag = false
        end
        available = state.available == true and state.can_volume == true and type(state.volume) == "number"
        actual = available and math.clamp(state.volume, 0, 1) or 0
        if not available then queued = nil; fact.windows_media_volume_pending = false end
        paint()
    end
end
