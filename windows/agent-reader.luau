-- Reuse the portable reader. Only Node and this repository's fixed helper are
-- launched; failures leave old observations dated rather than inventing quotas.
return function(native_run, notice)
    local failure
    on("fact:page", function(page)
        if page == "agents" and failure then notice(failure) end
    end)
    return function(callback)
        text.windows_agents_status = "Leyendo las cuotas de agentes…"
        local function complete(output, code)
            failure = code ~= 0 and "No se pudo leer el uso de agentes. Comprueba que Node.js 22.7 o posterior este instalado y disponible en PATH." or nil
            text.windows_agents_status = failure or "Todavia no hay datos de uso de Claude Code o Codex."
            if failure and fact.page == "agents" then notice(failure) end
            if callback then callback(output, code) end
        end
        local ok, error = pcall(native_run, "node", { "tools/reservas", "--lines" }, complete, { cwd = "." })
        if not ok then complete(tostring(error), -1) end
    end
end
