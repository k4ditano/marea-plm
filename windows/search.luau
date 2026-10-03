local function search()
    local q = search_match.fold(text.query or ""):match("^%s*(.-)%s*$")
    generation += 1
    local mine = generation
    local candidates = {}
    local function add(row, score)
        if score ~= nil then candidates[#candidates + 1] = { row = row, score = score } end
    end
    for _, a in ipairs(apps) do
        add({ name = a.name, kind_label = tr("Application"), icon = a.icon, exec = a.exec }, search_match.score(a.name, q))
    end
    if #q >= 2 then
        for k, o in ipairs(OWN) do
            if o[5] ~= "wm" or hooks.in_wm then
                local name = tr(o[1])
                local score = search_match.score(name, q) or search_match.score(o[2], q)
                add({name = name, kind_label = "Marea", icon = "", glyph = o[3], own = k}, score)
            end
        end
        for _, w in ipairs(open_windows) do
            local title, class = tostring(w.title or ""), tostring(w.class or "")
            add({name = title ~= "" and title or class, kind_label = tr("Window"), icon = class, window_id = w.id},
                search_match.score(title .. " " .. class, q))
        end
    end
    table.sort(candidates, function(a, b)
        if a.score ~= b.score then return a.score > b.score end
        return prefer(a.row, b.row)
    end)
    local list = {}
    for i = 1, math.min(7, #candidates) do list[i] = candidates[i].row end
    text.windows_search_status = ""
    paint(q, list)
    if #q < 3 then return end
    text.windows_search_status = tr("Searching files…")
    after(120, function()
        if mine ~= generation then return end
        sys.ask_async("search.files", {home_dir, q}, function(result, error)
            if mine ~= generation then return end
            if error then text.windows_search_status = tr("File search unavailable"); log("search:", error); return end
            local items = result.items or {}
            -- Keep files reachable even when many applications match the query.
            while #items > 0 and #list > 4 do table.remove(list) end
            for _, item in ipairs(items) do
                if #list >= 7 then break end
                list[#list + 1] = { name = item.name, kind_label = tr(item.directory and "Folder" or "File"),
                    icon = "windows-file:" .. item.path, filepath = item.path, path = item.path }
            end
            text.windows_search_status = result.truncated and tr("Partial file results · refine your search") or ""
            local selected = (model.results or {})[(fact.selected or 0) + 1]
            paint(q, list)
            if selected then
                local function key(row) return row.filepath or row.exec or row.window_id or row.own end
                for i, row in ipairs(list) do
                    if key(row) == key(selected) then fact.selected = i - 1; break end
                end
            end
        end)
    end)
end
