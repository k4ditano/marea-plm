-- The native worker owns the frozen pixels. Neither PNG encoding nor region
-- selection can block the scene's gestures, timers or service subscriptions.
fact.windows_capture_busy = false
local started = false
local function shot_failed(error)
    started = false
    fact.windows_capture_busy = false
    emit("shot_cancelled")
    if error then
        fact.open = true
        fact.page = "none"
        notice("Captura: " .. tostring(error):match("[^\n]+"))
    end
end
local function ask_shot(name, args, callback)
    local ok, error = pcall(native_sys.ask_async, name, args, callback)
    if not ok then shot_failed(error) end
    return ok
end
on("gone", function()
    if fact.purpose ~= "shot" or not fact.windows_capture_busy or started then return end
    started = true
    local scope = fact.scope
    after(200, function()
        ask_shot("screenshot.freeze", { scope }, function(id, error)
            if error then shot_failed(error); return end
            emit("frozen")
            ask_shot("screenshot.finish", { id }, function(result, failure)
                if failure then shot_failed(failure); return end
                fact.windows_capture_busy = false
                started = false
                if result.cancelled then emit("shot_cancelled"); return end
                text.windows_capture_path = result.path
                emit("shoot")
                log("photo ·", result.path)
                if not result.clipboard then
                    fact.open = true
                    notice("Foto guardada; portapapeles: " .. tostring(result.clipboard_error))
                end
            end)
        end)
    end)
end)
