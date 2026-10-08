-- The renderer follows the pointer. These workers apply only the newest value
-- and keep that preview until the native service confirms it or reports failure.
return function(native_sys, notice)
    local levels = {
        [0] = { command = "brightness.level", available = false, revision = 0 },
        [1] = { command = "audio.volume", available = false, revision = 0 },
        [2] = { command = "audio.input", available = false, revision = 0 },
    }
    local function clear_confirmation(state)
        if state.confirmation then cancel(state.confirmation); state.confirmation = nil end
    end
    local function settle(k)
        local state = levels[k]
        if not state.running and state.queued == nil and state.wanted ~= nil
            and state.actual ~= nil and math.abs(state.actual - state.wanted) <= 0.015
            and not fact["windows_level_drag." .. k] then
            fact["windows_level_pending." .. k] = false
            clear_confirmation(state)
        end
    end
    local pump
    pump = function(k)
        local state = levels[k]
        if state.running or state.scheduled or state.queued == nil then return end
        state.scheduled = true
        after(k == 0 and 80 or 16, function()
            state.scheduled = false
            local value, revision = state.queued, state.revision
            if value == nil then return end
            state.queued = nil
            local request = {}
            state.running = request
            local timeout
            local function completed(error, code)
                if state.running ~= request then return end
                if timeout then cancel(timeout); timeout = nil end
                state.running = false
                state.timed_out = false
                fact["windows_level_available." .. k] = state.available
                if state.revision == revision then
                    if code ~= 0 then
                        fact["windows_level_pending." .. k] = false
                        notice(state.command .. ": " .. tostring(error):match("[^\n]+"))
                    else
                        settle(k)
                        if fact["windows_level_pending." .. k] then
                            state.confirmation = after(3500, function()
                                state.confirmation = nil
                                if state.revision == revision and fact["windows_level_pending." .. k]
                                    and not fact["windows_level_drag." .. k] then
                                    fact["windows_level_pending." .. k] = false
                                    notice("El dispositivo no ha confirmado el nivel solicitado.")
                                end
                            end)
                        end
                    end
                end
                pump(k)
            end
            timeout = after(4500, function()
                timeout = nil
                if state.running ~= request then return end
                -- The OS call may still be running. Keep it serialized, but
                -- stop showing an unconfirmed value and reject more gestures
                -- until it returns; do not fill the worker queue behind it.
                state.timed_out = true
                state.revision += 1
                state.wanted, state.queued = nil, nil
                fact["windows_level_available." .. k] = false
                fact["windows_level_drag." .. k] = false
                fact["windows_level_pending." .. k] = false
                notice("El dispositivo no ha respondido. Espera a que termine la operación antes de reintentar.")
            end)
            local ok, error = pcall(native_sys.call_async, state.command, { value }, completed)
            if not ok then completed(error, -1) end
        end)
    end
    local events = { [0] = "set_brightness", "set_volume", "set_mic" }
    for k = 0, 2 do
        on(events[k], function(value)
            local state = levels[k]
            if not state.available or state.timed_out then
                fact["windows_level_pending." .. k] = false
                notice(state.timed_out and "El dispositivo sigue ocupado. Espera antes de reintentar."
                    or state.error or "Este dispositivo no permite cambiar el nivel.")
                return
            end
            state.revision += 1
            clear_confirmation(state)
            -- A release notification may settle the preceding request before
            -- the renderer's final value reaches Lua in the next message.
            fact["windows_level_pending." .. k] = true
            state.wanted = math.clamp(value, 0, 1)
            if state.steps and #state.steps > 0 then
                local wanted, nearest = state.wanted, state.steps[1]
                for _, step in ipairs(state.steps) do
                    if math.abs(step - wanted) < math.abs(nearest - wanted) then nearest = step end
                end
                state.wanted = nearest
            end
            state.queued = state.wanted
            pump(k)
        end)
        on("fact:windows_level_drag." .. k, function()
            after(32, function() settle(k) end)
        end)
    end
    on("fact:open", function(open)
        if not open then
            for k = 0, 2 do fact["windows_level_drag." .. k] = false; settle(k) end
        end
    end)
    local function observe(k, actual, available, error, steps)
        local state = levels[k]
        state.actual = actual
        state.available = available and type(actual) == "number" and actual >= 0 and actual <= 1
        state.error, state.steps = error, steps
        fact["windows_level_available." .. k] = state.available and not state.timed_out
        if not state.available then
            -- Invalidate an in-flight reply and discard unsent values. A new
            -- default device must not inherit the previous device's gesture.
            state.revision += 1
            clear_confirmation(state)
            state.wanted, state.queued = nil, nil
            fact["windows_level_drag." .. k] = false
            fact["windows_level_pending." .. k] = false
        end
        settle(k)
    end
    native_sys.watch("audio", function(value)
        observe(1, value.volume, true, "No hay una salida de audio activa.")
        observe(2, value.input, true, "No hay un micrófono activo.")
    end)
    native_sys.watch("brightness", function(value)
        observe(0, value.level, value.present == true, value.error, value.levels)
    end)
end
