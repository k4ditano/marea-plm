-- Native completion is the only authority for the saved card. Stopping the
-- animation does not mean the encoder has flushed its MP4 index yet.
do
    local busy, starting, stopping, requested = false, false, false, false
    local last_video
    fact.windows_recording_busy = false
    local function failed(error)
        busy, starting, stopping, requested = false, false, false, false
        fact.windows_recording_busy = false
        fact.taping = false
        if fact.face == "rec" or fact.face == "count" then emit("stop") end
        fact.open = true
        fact.page = "none"
        notice("Grabación: " .. tostring(error):match("[^\n]+"))
    end
    local function ask(name, args, callback)
        local ok, error = pcall(native_sys.ask_async, name, args, callback)
        if not ok then callback(nil, error) end
    end
    local poll, stop
    local function update(value, error)
        if error then
            -- A rejected poll did not stop the native recorder. Retain
            -- ownership and retry stopping instead of leaving it hidden.
            notice("Grabación: " .. tostring(error))
            stop()
            if fact.face == "rec" then emit("stop") end
            after(500, poll)
            return
        end
        if value.state == "error" then
            failed(value.error .. (value.path ~= "" and (" · Archivo parcial: " .. value.path) or ""))
        elseif value.state == "saved" or value.state == "cancelled" then
            busy, starting, stopping, requested = false, false, false, false
            fact.windows_recording_busy = false
            fact.taping = false
            if fact.face == "rec" then emit("stop") end
            if value.state == "saved" and value.frames > 0 then
                last_video = value.path
                text["reel.name"] = last_video:match("[^/\\]+$") or last_video
                log("recording · saved", last_video, "· frames", value.frames)
                after(700, function() emit("celebrate"); emit("recorded") end)
            end
        else
            fact.taping = requested and not stopping and value.state == "recording"
            after(250, poll)
        end
    end
    poll = function()
        if busy then
            if not requested and not starting and not stopping then stop() end
            ask("recording.state", {}, update)
        end
    end
    stop = function()
        requested = false
        fact.taping = false
        if not busy or starting or stopping then return end
        stopping = true
        ask("recording.stop", {}, function(_, error)
            if error then
                stopping = false
                notice("No se pudo detener la grabación: " .. tostring(error))
            end
            -- The existing poll keeps waiting for finalization, including after
            -- a transient command error. Never create a second polling chain.
        end)
    end
    on("stop", stop)
    on("fact:face", function(face)
        if face ~= "rec" or busy then return end
        busy, starting, stopping, requested = true, true, false, true
        fact.windows_recording_busy = true
        local monitor = text["screen." .. tostring(fact.nook_screen or 0) .. ".name"] or ""
        ask("recording.start", { monitor }, function(value, error)
            starting = false
            if error then failed(error); return end
            if not requested or fact.face ~= "rec" then stop() end
            update(value)
        end)
    end)
    on("reel_watch", function()
        if last_video then perform("shell.open", last_video) end
    end)
    on("reel_folder", function()
        ask("recording.folder", {}, function(path, error)
            if error then notice(error) else perform("shell.open", path) end
        end)
    end)
    on("reel_copy", function()
        if last_video then perform("clipboard.set", last_video) end
    end)
end
