-- Transport for the upstream Deriva protocol. This does not provide its store.
return function(native_run)
    local function absolute(path)
        return type(path) == "string" and not path:find("[%z\r\n]")
            and (path:match("^%a:[/\\]") or path:match("^[/\\][/\\][^/\\]+[/\\][^/\\]+")) ~= nil
    end
    local function file_path(uri)
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
    local function invoke(args, done)
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
            local result = value.result or value
            if type(result) ~= "table" then
                done(nil, "Deriva devolvió un resultado inválido.")
                return
            end
            if args[1] == "where" and not absolute(result.blobs) then
                done(nil, "Deriva no proporcionó una carpeta de archivos de Windows válida.")
                return
            end
            if args[1] == "list" or args[1] == "search" then
                if type(result.items) ~= "table" then
                    done(nil, "Deriva no proporcionó una lista de resultados válida.")
                    return
                end
                for key, item in pairs(result.items) do
                    if type(key) ~= "number" or key < 1 or key > #result.items or key % 1 ~= 0 or type(item) ~= "table" then
                        done(nil, "Deriva devolvió una entrada inválida.")
                        return
                    end
                    for _, field in ipairs({"id", "canonical_url", "title", "blob_name", "excerpt", "source", "blob_hash", "preview_path", "source_url", "type"}) do
                        if item[field] ~= nil and type(item[field]) ~= "string" then
                            done(nil, "Deriva devolvió una entrada inválida.")
                            return
                        end
                    end
                    local time = item.captured_at
                    if time ~= nil and (type(time) ~= "number" or time ~= time or time < 0 or time > 253402300799000) then
                        done(nil, "Deriva devolvió una fecha inválida.")
                        return
                    end
                end
            end
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
    return invoke, file_path
end
