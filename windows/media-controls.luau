-- Keep playback state native; accepting a command is not playback confirmation.
return function(native_sys, notice)
    local observe_volume = install_media_volume(native_sys, notice)
    local state, busy, sequence, revision = {}, false, 0, 0
    local artwork
    local function paint()
        local available = state.available == true and type(state.player) == "string" and state.player ~= ""
        local art = available and type(state.art) == "string" and state.art or ""
        if art ~= artwork then
            artwork = art
            model.windows_media_cover = art ~= "" and {{pic = art}} or {}
        end
        fact.windows_media_has_art = art ~= ""
        fact.windows_media_available = available
        fact.windows_media_busy = busy
        fact.windows_media_can_toggle = available and not busy and state.can_toggle == true
        fact.windows_media_can_previous = available and not busy and state.can_previous == true
        fact.windows_media_can_next = available and not busy and state.can_next == true
        text.windows_media_status = state.error and state.error ~= "" and "Reproductor no disponible" or tr("Nothing playing")
    end
    local function update(value)
        value = type(value) == "table" and value or {}
        if value.player ~= state.player then sequence += 1; busy = false end
        if value.error and value.error ~= "" and value.error ~= state.error then notice(value.error) end
        state = value
        observe_volume(value)
        revision += 1
        paint()
    end
    paint()
    if not native_sys.watch("media", update) then
        update({error = "El servicio multimedia de Windows no está disponible"})
    end
    local function refresh(ticket)
        local observed = revision
        local function done(value, error)
            if ticket ~= sequence then return end
            busy = false
            if revision == observed then
                update(error and { error = tostring(error) } or value)
            else
                paint()
            end
        end
        local ok, error = pcall(native_sys.ask_async, "media.state", {}, done)
        if not ok then done(nil, error) end
    end
    local function send(command, capability)
        if busy or not fact.windows_media_available or state[capability] ~= true then return end
        sequence += 1
        local ticket = sequence
        busy = true
        fact.windows_notice = false
        paint()
        local function done(error, code)
            if ticket ~= sequence then return end
            if code ~= 0 then notice(tostring(error):match("[^\n]+") or "El reproductor rechazó la orden") end
            refresh(ticket)
        end
        local ok, error = pcall(native_sys.call_async, command, {state.player}, done)
        if not ok then done(error, -1) end
        after(4500, function()
            if ticket ~= sequence or not busy then return end
            sequence += 1
            busy = false
            paint()
            notice("El reproductor no respondió a tiempo")
        end)
    end
    on("play_pause", function() send("media.toggle", "can_toggle") end)
    on("previous", function() send("media.previous", "can_previous") end)
    on("next", function() send("media.next", "can_next") end)
end
