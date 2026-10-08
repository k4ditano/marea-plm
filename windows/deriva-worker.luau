-- Transport for the upstream Deriva protocol. This does not provide its store.
return function(native_run)
    local function absolute(path)
        return type(path) == "string" and not path:find("[%z\r\n]")
            and (path:match("^%a:[/\\]") or path:match("^[/\\][/\\][^/\\]+[/\\][^/\\]+")) ~= nil
    end
    local function file_path(uri)
        -- Older Windows workers stored canonical Win32 paths after file://.
        -- Keep those captures usable; new workers emit a percent-encoded URI.
        local legacy = uri:sub(8)
        if uri:sub(1, 7):lower() == "file://" and legacy:sub(1, 4) == [[\\?\]] then
            legacy = legacy:sub(5)
            if legacy:sub(1, 4):upper() == [[UNC\]] then legacy = "//" .. legacy:sub(5) end
            legacy = legacy:gsub("\\", "/")
            if absolute(legacy) and utf8.len(legacy) then return legacy end
            return nil
        end
        local host, path = uri:match("^[Ff][Ii][Ll][Ee]://([^/]*)(/.*)$")
        if not host or path:find("[?#]") or host:find("[%%@:\\]") then return nil end
        if path:gsub("%%%x%x", ""):find("%%") then return nil end
        path = path:gsub("%%(%x%x)", function(h) return string.char(tonumber(h, 16)) end)
        if host == "" or host:lower() == "localhost" then
            path = path:gsub("^/(%a:/)", "%1")
        else
            path = "//" .. host .. path
        end
        if not absolute(path) or not utf8.len(path) then return nil end
        return path
    end
    local function valid_item(item)
        if type(item) ~= "table" or type(item.id) ~= "string" or item.id == "" then return false end
        for _, field in ipairs({"canonical_url", "title", "blob_name", "blob_path", "excerpt", "source", "blob_hash", "preview_path", "source_url", "type"}) do
            if item[field] ~= nil and type(item[field]) ~= "string" then return false end
        end
        local time = item.captured_at
        if time ~= nil and (type(time) ~= "number" or time ~= time or time < 0 or time > 253402300799000) then return false end
        if item.favorite ~= nil and type(item.favorite) ~= "boolean" then return false end
        if item.spaces ~= nil then
            if type(item.spaces) ~= "table" then return false end
            for _, id in pairs(item.spaces) do if type(id) ~= "string" then return false end end
        end
        return true
    end
    local function validate(method, result)
        if type(result) ~= "table" then return nil, "Deriva returned an invalid result." end
        if method == "where" and not absolute(result.blobs) then return nil, "Deriva did not provide a Windows library folder." end
        if method == "home" or method == "list" or method == "search" then
            if type(result.items) ~= "table" then return nil, "Deriva did not provide a list of captures." end
            for key, item in pairs(result.items) do
                if type(key) ~= "number" or key < 1 or key > #result.items or key % 1 ~= 0 or not valid_item(item) then
                    return nil, "Deriva returned an invalid capture."
                end
            end
        end
        if result.item ~= nil and not valid_item(result.item) then return nil, "Deriva returned an invalid capture." end
        if method == "home" then
            if type(result.stats) ~= "table" or type(result.sections) ~= "table" then return nil, "Deriva returned an invalid library summary." end
            for _, field in ipairs({"captures", "trashed"}) do
                local count = result.stats[field]
                if type(count) ~= "number" or count < 0 or count % 1 ~= 0 then return nil, "Deriva returned an invalid capture count." end
            end
            for _, section in pairs(result.sections) do
                if type(section) ~= "table" or type(section.kind) ~= "string" then return nil, "Deriva returned an invalid folder." end
                if section.kind == "space" and (type(section.id) ~= "string" or type(section.name) ~= "string"
                    or (section.color ~= nil and type(section.color) ~= "string")) then return nil, "Deriva returned an invalid folder." end
                if section.count ~= nil and (type(section.count) ~= "number" or section.count < 0 or section.count % 1 ~= 0) then return nil, "Deriva returned an invalid folder count." end
            end
        end
        return result
    end
    local function invoke(args, done)
        done = done or function() end
        local delivered = false
        local function complete(output, code)
            if delivered then return end
            delivered = true
            local ok, value = pcall(json.decode, tostring(output or ""))
            if ok and type(value) == "table" and value.ok == false then
                local detail = type(value.error) == "table" and value.error.message or nil
                done(nil, "Deriva: " .. (type(detail) == "string" and detail:sub(1, 240) or "no pudo completar la operación."))
                return
            end
            if code ~= 0 then
                done(nil, code == -1 and "Deriva no pudo ejecutar deriva-worker. Comprueba su instalación nativa para Windows y PATH."
                    or "Deriva terminó con error (código " .. tostring(code) .. ").")
                return
            end
            if not ok or type(value) ~= "table" then
                done(nil, "Deriva devolvió una respuesta que no se puede leer.")
                return
            end
            local result, failure = validate(args[1] == "call" and args[2] or args[1], value.result or value)
            if not result then done(nil, failure); return end
            if args[1] == "ingest" then
                for _, key in ipairs({"saved", "duplicates", "failed"}) do
                    local count = result[key]
                    if count ~= nil and (type(count) ~= "number" or count < 0 or count % 1 ~= 0) then
                        done(nil, "Deriva no confirmó cuántos elementos se guardaron.")
                        return
                    end
                end
                if (result.saved or 0) + (result.duplicates or 0) + (result.failed or 0) == 0 then
                    done(nil, "Deriva no confirmó ningún elemento guardado.")
                    return
                end
            end
            done(result)
        end
        local ok, error = pcall(native_run, "deriva-worker", args, complete, {cwd = "."})
        if not ok then complete(tostring(error), -1) end
    end
    return invoke, file_path, validate
end
