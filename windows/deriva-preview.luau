-- Only visible YouTube cards request enrichment, one process at a time.
return function(native_run)
    local attempted, queue, busy = {}, {}, false
    local function pump()
        if busy or #queue == 0 then return end
        local job = table.remove(queue, 1)
        busy = true
        local delivered = false
        local function complete(output, code)
            if delivered then return end
            delivered = true
            local ok, response = pcall(json.decode, tostring(output or ""))
            local item = ok and type(response) == "table" and response.ok == true
                and type(response.result) == "table" and response.result.item or nil
            if code == 0 and type(item) == "table" and item.id == job.id then
                local valid = true
                for _, key in ipairs({"title", "source_url", "canonical_url", "preview_path", "type", "source"}) do
                    if item[key] ~= nil and type(item[key]) ~= "string" then valid = false end
                end
                if valid then job.done(item) end
            end
            busy = false
            pump()
        end
        local ok = pcall(native_run, "node", {"tools/deriva-preview.mjs", "--id", job.id}, complete, {cwd = "."})
        if not ok then complete("", -1) end
    end
    return function(item, done)
        if item.source ~= "youtube" or type(item.id) ~= "string" or #item.id < 16 or #item.id > 64
            or not item.id:match("^%x+$") or (item.preview_path and item.preview_path ~= "") then return end
        if attempted[item.id] and os.clock() - attempted[item.id] < 120 then return end
        if #queue >= 4 then return end
        attempted[item.id] = os.clock()
        queue[#queue + 1] = {id = item.id, done = done}
        pump()
    end
end
