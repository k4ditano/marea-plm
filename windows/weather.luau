-- Windows ships curl.exe; run that native binary directly, without a shell.
return function(native_run, native_sys, notice)
    local system = native_sys.ask("env", "SystemRoot")
    return function(args, callback)
        local url = type(args) == "table" and args[4]
        if not system or not url or #args ~= 4 or args[1] ~= "-s" or args[2] ~= "--max-time" or args[3] ~= "10"
            or not (url:match("^https://api%.open%-meteo%.com/v1/forecast%?")
                or url:match("^https://geocoding%-api%.open%-meteo%.com/v1/search%?")) then
            if callback then callback("", -1) end
            return
        end
        return native_run("curl.exe", {"--silent", "--show-error", "--fail", "--max-time", "10", url}, function(out, code)
            if code ~= 0 then notice("No se pudo consultar el tiempo. Comprueba la conexión e inténtalo de nuevo.") end
            if callback then callback(code == 0 and out or "", code) end
        end, {cwd = system .. "\\System32"})
    end
end
