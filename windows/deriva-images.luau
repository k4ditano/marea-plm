-- Only the current page requests images. The caller serializes enrichment.
return function(native, native_run, drift_run)
    local function thumbnail(source, w, h, mode, done)
        local function result(path, error)
            if error then log("deriva · preview:", error) end
            done(type(path) == "string" and path ~= "" and path or nil, error)
        end
        local ok, error = pcall(native.ask_async, "images.thumbnail", {source, w, h, mode}, result)
        if not ok then result(nil, tostring(error)) end
    end
    local function enrich(it, url, done)
        local finished = false
        local function finish(item)
            if finished then return end
            finished = true
            done(item)
        end
        local function fetched(output, code)
            local ok, envelope = pcall(json.decode, tostring(output or ""))
            local found = ok and type(envelope) == "table" and envelope.ok == true and envelope.result
            if code ~= 0 or type(found) ~= "table" then return finish(nil) end
            local params = {id = it.id}
            for _, key in ipairs({"title", "excerpt", "author"}) do
                if type(found[key]) == "string" and found[key] ~= "" then params[key] = found[key] end
            end
            local function send(picture)
                if picture == nil and params.title == nil and params.excerpt == nil and params.author == nil then return finish(nil) end
                local args = {"call", "enrich", "--params", json.encode(params)}
                if picture then table.insert(args, "--preview-file"); table.insert(args, picture) end
                drift_run(args, function(r) finish(r and r.item) end)
            end
            if type(found.image_file) ~= "string" or found.image_file == "" then return send(nil) end
            thumbnail(found.image_file, 800, 800, "fit", function(picture)
                pcall(native_run, "node", {"tools/deriva-fetch.mjs", "--release", found.image_file}, function() end, {cwd = "."})
                send(picture)
            end)
        end
        local ok = pcall(native_run, "node", {"tools/deriva-fetch.mjs", "--url", url}, fetched, {cwd = "."})
        if not ok then finish(nil) end
    end
    return thumbnail, enrich
end
