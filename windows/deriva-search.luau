-- Keep the semantic model warm, with at most one request and one newer query.
return function(native_spawn, validate)
    local worker, active, queued, idle, timeout = nil, nil, nil, nil, nil
    local serial = 0
    local pump
    local function clear_timer(which)
        if which then cancel(which) end
    end
    local function retire()
        clear_timer(idle); idle = nil
        local old = worker
        worker = nil
        if old and old.handle then pcall(kill, old.handle) end
    end
    local function completed(result, error)
        clear_timer(timeout); timeout = nil
        local job = active
        active = nil
        if job then job.done(result, error) end
        if queued then pump()
        else idle = after(120000, function() idle = nil; retire() end) end
    end
    pump = function()
        if active or not queued then return end
        clear_timer(idle); idle = nil
        active, queued = queued, nil
        if not worker then
            local session = {}
            worker = session
            local ok, handle = pcall(native_spawn, "deriva-worker", {"stdio"}, function(line)
                if worker ~= session or not active then return end
                local valid, value = pcall(json.decode, tostring(line or ""))
                if not valid or type(value) ~= "table" or value.id ~= active.id then return end
                if value.ok == true and type(value.result) == "table" and type(value.result.items) == "table" then
                    local result, error = validate("search", value.result)
                    completed(result, error)
                else
                    local error = type(value.error) == "table" and value.error.message
                    completed(nil, type(error) == "string" and error or "Deriva could not complete the search.")
                end
            end, function()
                if worker ~= session then return end
                worker = nil
                completed(nil, "Deriva's search worker stopped.")
            end, {stdin = "open", cwd = "."})
            if not ok or handle == nil then worker = nil; return completed(nil, "Deriva's search worker could not start.") end
            session.handle = handle
        end
        local id = active.id
        local ok, accepted = pcall(write, worker.handle, json.encode({v = 1, id = id, method = "search", params = active.params}) .. "\n")
        if not ok or not accepted then retire(); return completed(nil, "Deriva's search worker stopped accepting requests.") end
        timeout = after(60000, function()
            if not active or active.id ~= id then return end
            retire()
            completed(nil, "Deriva's search timed out. Try again.")
        end)
    end
    return function(params, done)
        serial += 1
        local old = queued
        queued = {params = params, done = done, id = "s" .. serial}
        if old then old.done(nil, "Search superseded") end
        pump()
    end
end
