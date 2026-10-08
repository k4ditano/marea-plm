-- WinGet uses exact package identities; visible names never become commands.
return function(native_run, native_spawn, hooks, notice)
    local sw = {list={}, found={}, scroll=0, checked=0, generation=0, looking=false, busy=false}
    local arguments = {"-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", "tools/software.ps1"}
    local function request(payload, answer, progress)
        local result
        local ok, id = pcall(native_spawn, "powershell.exe", arguments, function(line)
            local decoded, value = pcall(json.decode, line)
            if not decoded or type(value) ~= "table" then return end
            if value.type == "result" then result = value
            elseif progress then progress(value) end
        end, function(output, code)
            answer(result or {ok=false, error=output ~= "" and output or tr("WinGet did not answer")})
        end, {cwd=".", input=json.encode(payload), errors=true})
        if not ok then answer({ok=false, error=tostring(id)}) end
        return ok and id or nil
    end
    local function when()
        if sw.checked == 0 then return "" end
        local minutes = math.floor((os.time() - sw.checked) / 60)
        return minutes < 1 and tr("checked just now") or string.format(tr("checked %d min ago"), minutes)
    end
    local function paint()
        local ticked = 0
        for _, p in ipairs(sw.list) do if not p.skip then ticked += 1 end end
        fact["sw.count"], fact["sw.ticked"] = #sw.list, ticked
        fact["sw.aur"], fact["sw.news"], fact["sw.pacnew"] = 0, 0, 0
        text["sw.summary"] = string.format(tr("%d to update"), #sw.list) .. " · WinGet"
        text["sw.when"] = when()
        sw.scroll = math.clamp(sw.scroll, 0, math.max(0, #sw.list - 7))
        local rows = {}
        for i = sw.scroll + 1, math.min(#sw.list, sw.scroll + 7) do
            local p = sw.list[i]
            rows[#rows+1] = {name=p.name, versions=p.old .. " → " .. p.version, aur=false, skip=p.skip == true}
        end
        model["sw.rows"] = rows
        fact["sw.more"] = math.max(0, #sw.list - sw.scroll - 7)
    end
    local function check()
        if sw.looking or sw.busy then return end
        sw.looking = true
        fact["sw.looking"] = true
        text["sw.error"] = ""
        if #sw.list == 0 then fact["sw.state"] = "scanning" end
        request({action="scan"}, function(value)
            sw.looking = false; fact["sw.looking"] = false
            if value.ok ~= true then
                if not sw.busy and not sw.pending then
                    text["sw.error"] = tr("WinGet unavailable") .. ": " .. tostring(value.error or "")
                    fact["sw.state"] = "broken"
                end
                return
            end
            local skipped = {}
            for _, p in ipairs(sw.list) do skipped[p.id] = p.skip end
            sw.list = value.items or {}
            for _, p in ipairs(sw.list) do p.skip = skipped[p.id] == true end
            sw.checked = os.time()
            local state = fact["sw.state"]
            if not sw.busy and not sw.pending and state ~= "finished" and state ~= "failed" then
                fact["sw.state"] = "ready"
            end
            paint()
        end)
    end
    -- Only one catalogue process at a time. Typing replaces the queued query,
    -- and no module/runtime remains resident when a query has finished.
    local querying, queued
    local function catalogue(q, answer)
        if querying then queued = {q, answer}; return end
        querying = true
        request({action="search", query=q}, function(value)
            querying = false
            answer(value)
            if queued then local next = queued; queued = nil; catalogue(next[1], next[2]) end
        end)
    end
    local function search()
        local q = tostring(text["sw.query"] or ""):match("^%s*(.-)%s*$")
        sw.generation += 1
        local generation = sw.generation
        sw.found = {}; model["sw.found"] = {}
        fact["sw.typed"] = #q >= 2
        fact["sw.searching"] = #q >= 2
        text.windows_sw_search_error = ""
        if #q < 2 then return end
        after(350, function()
            if generation ~= sw.generation then return end
            catalogue(q, function(value)
                if generation ~= sw.generation then return end
                fact["sw.searching"] = false
                if value.ok ~= true then
                    text.windows_sw_search_error = tr("WinGet unavailable") .. ": " .. tostring(value.error or "")
                    return
                end
                sw.found = value.items or {}
                local rows = {}
                for i = 1, math.min(6, #sw.found) do
                    local p = sw.found[i]
                    rows[i] = {name=p.name, repo="WinGet", version=p.version, about=p.id, installed=p.installed == true, aur=false}
                end
                model["sw.found"] = rows
            end)
        end)
    end
    local function ask(kind, packages)
        if sw.busy or sw.pending then return end
        sw.before = fact["sw.state"]
        sw.pending = {action=kind, packages=packages}
        text["sw.asking"] = kind == "install" and string.format(tr("Install %s with WinGet?"), packages[1].name)
            or string.format(tr("Update %d selected programs with WinGet?"), #packages)
        fact["sw.state"] = "unlocking"
    end
    local function forget()
        if not sw.pending or sw.busy then return end
        sw.pending = nil
        fact["sw.state"] = sw.before == "unlocking" and "ready" or sw.before
    end
    local function finish(value)
        sw.busy = false; sw.token = nil
        fact["sw.can_stop"], fact["sw.stopping"] = false, false
        fact["sw.reboot"] = value.reboot == true
        fact.windows_sw_indeterminate = false
        fact["sw.state"] = value.ok == true and "finished" or "failed"
        local completed = {}
        for _, id in ipairs(value.completed or {}) do completed[id] = true end
        local remaining = {}
        for _, p in ipairs(sw.list) do if not completed[p.id] then remaining[#remaining+1] = p end end
        sw.list = remaining; paint()
        if value.ok == true then
            fact["sw.progress"] = 1
            text["sw.result"] = sw.operation.action == "install" and string.format(tr("%s is installed"), sw.operation.packages[1].name)
                or string.format(tr("Updated %d packages"), #(value.completed or {}))
        else
            text["sw.result"] = tr(value.cancelled and "Stopped" or "It did not finish")
            text["sw.error"] = tostring(value.error or tr("WinGet did not answer"))
        end
        -- Refresh only when leaving the result; keep its error and partial
        -- completion visible instead of replacing them with a scan immediately.
        sw.checked = 0
    end
    on("sw_auth", function()
        if not sw.pending or sw.busy or fact["sw.state"] ~= "unlocking" then return end
        sw.operation = sw.pending; sw.pending = nil; sw.busy = true
        fact["sw.state"], fact["sw.progress"] = "working", 0
        fact["sw.can_stop"], fact["sw.stopping"], fact["sw.reboot"] = false, false, false
        fact.windows_sw_indeterminate = true
        text["sw.stage"], text["sw.line"], text["sw.error"] = tr("Starting"), "", ""
        text["sw.item"] = sw.operation.packages[1].name
        request(sw.operation, finish, function(value)
            if value.type == "started" then sw.token = value.token; fact["sw.can_stop"] = true
            elseif value.type == "progress" then
                local percent = tonumber(value.percent) or -1
                fact.windows_sw_indeterminate = percent < 0
                fact["sw.progress"] = math.clamp(percent / 100, 0, 1)
                text["sw.stage"] = tr(value.stage or "Working")
                text["sw.item"] = value.item or text["sw.item"]
                text["sw.line"] = tr("WinGet is applying the selected changes")
            end
        end)
    end)
    on("sw_go", function()
        if sw.looking or fact["sw.state"] ~= "ready" then return end
        local packages = {}
        for _, p in ipairs(sw.list) do
            if not p.skip then packages[#packages+1] = {id=p.id, name=p.name, version=p.version} end
        end
        if #packages > 0 then ask("update", packages) end
    end)
    on("sw_install", function(index)
        local p = sw.found[(index or 0) + 1]
        if p and not p.installed then ask("install", {{id=p.id, name=p.name, version=p.version}}) end
    end)
    on("sw_stop", function()
        if not sw.busy or not sw.token or fact["sw.stopping"] then return end
        fact["sw.stopping"] = true
        native_run("powershell.exe", arguments, function(output, code)
            if code ~= 0 and sw.busy then fact["sw.stopping"] = false; notice(tr("Could not request cancellation")) end
        end, {cwd=".", input=json.encode({action="cancel", token=sw.token})})
    end)
    on("sw_forget", forget)
    on("sw_open", function() paint(); if sw.checked == 0 or os.time() - sw.checked > 1800 then check() end end)
    on("sw_check", check)
    on("sw_toggle", function(i)
        if fact["sw.state"] ~= "ready" then return end
        local p = sw.list[sw.scroll + (i or 0) + 1]
        if p then p.skip = not p.skip; paint() end
    end)
    on("sw_all", function()
        if fact["sw.state"] ~= "ready" then return end
        local skip = (fact["sw.ticked"] or 0) > 0
        for _, p in ipairs(sw.list) do p.skip = skip end
        paint()
    end)
    on("sw_scroll", function(w) sw.scroll += (w or 0) > 0 and -2 or 2; paint() end)
    on("sw_back", function()
        if sw.busy then return end
        fact["sw.state"] = "ready"; check(); search()
    end)
    on("sw_terminal", function() check() end)
    on("text:sw.query", search)
    on("fact:page", function(page) if page ~= "software" then forget() end end)
    on("windows_language_updated", paint)
    hooks.software = function(tab)
        fact.open, fact.page, fact["sw.tab"] = true, "software", tab or "updates"
        if sw.checked == 0 or os.time() - sw.checked > 1800 then check() end
        paint()
    end
    hooks.packages = function(q, answer)
        if #q < 3 or #q > 160 or sw.busy then answer({}); return end
        catalogue(q, function(value)
            local rows = {}
            if value.ok then
                for _, p in ipairs(value.items or {}) do
                    if #rows < 2 and not p.installed then
                        rows[#rows+1] = {name=p.name, kind_label=tr("Install") .. " · WinGet", icon="", glyph=5, package=p.id}
                    end
                end
            end
            answer(rows)
        end)
    end
    hooks.install = function(id) hooks.software("catalogue"); text["sw.query"] = id; search() end
    after(60000, check)
    every(3 * 3600 * 1000, check)
    every(60000, function() if fact.page == "software" then text["sw.when"] = when() end end)
    paint()
end
