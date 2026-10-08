"""Keep the current library UI and replace its platform-bound operations."""
def apply(scene, logic, root):
    def once(source, old, new):
        assert source.count(old) == 1, old[:100]
        return source.replace(old, new, 1)

    begin = logic.index('local function deriva()\n')
    end = logic.index('\nend\nderiva()', begin) + len('\nend\nderiva()')
    part = logic[begin:end]
    start = part.index('    local DRIFT = ')
    stop = part.index('    local function host_of', start)
    init = '''    local invoke, drift_file_path, validate = (function()
__TRANSPORT__
    end)()(native_run)
    local function drift_run(args, done)
        invoke(args, function(result, error)
            if error then text.windows_deriva_status = tr(error) end
            if done then done(result, error) end
        end)
    end
    local function call(method, params, done)
        drift_run({"call", method, "--params", json.encode(params)}, done)
    end
    local search_call = (function()
__SEARCH__
    end)()(native_spawn, validate)
    local thumbnail, enrich = (function()
__IMAGES__
    end)()(native_sys, native_run, drift_run)
    local items, offset = {}, 0
    local view = "all"
    local folders, counts, chip_keys = {}, {today = 0, fav = 0}, {}
    fact.windows_deriva_loaded = false
    fact.windows_deriva_busy = false
    text.windows_deriva_status = tr("Waiting for the library service…")
    model.drift = {}
    local function drift_where(done)
        drift_run({"where"}, function(r)
            fact["drift.missing"] = r == nil
            if r then text.windows_deriva_status = "" end
            if done then done() end
        end)
    end
    drift_where()
    local function toast(words)
        fact["drift.result"] = 1
        text["drift.toast"] = words
        emit("say_toast")
    end
'''
    for key, name in [('TRANSPORT', 'deriva-worker'), ('SEARCH', 'deriva-search'), ('IMAGES', 'deriva-images')]:
        init = init.replace('__' + key + '__', (root / 'windows' / (name + '.luau')).read_text(encoding='utf-8'))
    part = part[:start] + init + part[stop:]
    part = once(part, 'if type(it.source_url) == "string" and it.source_url ~= "" then return it.source_url end', '''if type(it.source_url) == "string" and it.source_url ~= "" then
            if it.source_url:sub(1, 7):lower() == "file://" then return drift_file_path(it.source_url) or "" end
            return it.source_url
        end''')
    part = once(part, '        return it.blob_path or ""', '''        if type(it.canonical_url) == "string" and it.canonical_url ~= "" then return it.canonical_url end
        return it.blob_path or ""''')
    part = once(part, '    local THUMBS = home_dir .. "/.cache/marea/deriva"\n    run("mkdir", { "-p", THUMBS }, function() end)\n    local thumbs, making = {}, {}',
                '    local thumbs, thumb_busy = {}, false')
    part = once(part, 'local thumb = thumbs[it.id]', 'local thumb = thumbs[cover_of(it)]')
    # Byte slicing through a UTF-8 codepoint used to remove letters in notes.
    part = once(part, '    local function paint_cards()', '''    local function excerpt(words)
        words = ("\\n" .. tostring(words or "")):gsub("\\n%s*#+%s*", "\\n"):gsub("\\n+", "\\n"):sub(2)
        local cut = utf8.offset(words, 221)
        return cut and words:sub(1, cut - 1) or words
    end
    local function paint_cards()''')
    part = once(part, 'excerpt = ("\\n" .. tostring(it.excerpt or "")):gsub("\\n%s*#+%s*", "\\n"):gsub("\\n+", "\\n"):sub(2, 221),', 'excerpt = excerpt(it.excerpt),')
    start = part.index('    local function make_thumbs()')
    stop = part.index('    -- ── what is looked at', start)
    part = part[:start] + '''    local function make_thumbs()
        if thumb_busy or fact.page ~= "drift" then return end
        for k = offset * 3 + 1, math.min(offset * 3 + 6, #items) do
            local src = cover_of(items[k])
            if src and thumbs[src] == nil then
                thumb_busy = true
                thumbnail(src, 288, 168, "crop", function(path)
                    thumb_busy = false
                    thumbs[src] = path or false
                    paint_cards()
                    make_thumbs()
                end)
                return
            end
        end
    end
    local tried, fetching = {}, false
    local show
    local function fetch_next()
        if fetching or fact.page ~= "drift" or view == "trash" then return end
        for k = offset * 3 + 1, math.min(offset * 3 + 6, #items) do
            local it = items[k]
            local url = url_of(it)
            if url and cover_of(it) == nil and not tried[it.id] then
                tried[it.id], fetching = true, true
                enrich(it, url, function(item)
                    fetching = false
                    if item and item.id == it.id then
                        for index, current in ipairs(items) do
                            if current.id == item.id then items[index] = item end
                        end
                        paint_cards()
                        make_thumbs()
                    end
                    fetch_next()
                end)
                return
            end
        end
    end
    show = function()
        paint_cards()
        make_thumbs()
        fetch_next()
    end

''' + part[stop:]
    part = once(part, '        local mine = loading\n', '''        local mine = loading
        fact.windows_deriva_busy = true
        text.windows_deriva_status = tr("Reading the library…")
        fact["drift.moving"] = -1
        local function read(method, params, done)
            invoke({"call", method, "--params", json.encode(params)}, done)
        end
''')
    part = once(part, '        local function got(list, empty)\n            if mine ~= loading then return end\n            items = list or {}', '''        local function got(list, empty, error)
            if mine ~= loading then return end
            fact.windows_deriva_busy = false
            if list == nil then
                text.windows_deriva_status = tr(error or "Deriva could not read the library. Try again.")
                return
            end
            fact.windows_deriva_loaded = true
            fact["drift.missing"] = false
            text.windows_deriva_status = ""
            items = list''')
    part = once(part, '''return call("list", { limit = 200, tag = tag:lower() }, function(r)
                    got(r and r.items, string.format(tr("Nothing tagged #%s"), tag))''', '''return call("list", { limit = 200, tag = tag:lower() }, function(r, error)
                    got(r and r.items, string.format(tr("Nothing tagged #%s"), tag), error)''')
    part = once(part, '''return search_call({ query = q, limit = 60 }, function(r)
                got(r and r.items, string.format(tr("Nothing matches «%s»"), q))''', '''return search_call({ query = q, limit = 60 }, function(r, error)
                got(r and r.items, string.format(tr("Nothing matches «%s»"), q), error)''')
    part = once(part, '''call("home", params, function(r)
            if r == nil then return got({}, "") end''', '''call("home", params, function(r, error)
            if mine ~= loading then return end
            if r == nil then return got(nil, "", error) end''')
    part = once(part, 'return call("list", { limit = 200, tag = tag:lower() }', 'return read("list", { limit = 200, tag = tag:lower() }')
    part = once(part, '        call("home", params, function(r, error)', '        read("home", params, function(r, error)')
    part = once(part, '        typed = typed + 1', '''        loading += 1 -- A reply to the previous text is stale during the debounce too.
        typed = typed + 1''')
    part = once(part, '''                local words = r and r.text ~= "" and r.text or it.excerpt or ""
                --  wl-copy stays behind serving it: nothing to wait for.
                run("wl-copy", {}, nil, { input = words, output = false })
                toast(tr("Copied"))''', '''                if not r or type(r.text) ~= "string" then return end
                native_sys.call_async("clipboard.set", {r.text}, function(error, code)
                    if code == 0 then toast(tr("Copied"))
                    else text.windows_deriva_status = tr("Could not copy the note.") .. " " .. tostring(error or "") end
                end)''')
    # Serialize a favourite mutation per capture; roll both the star and count
    # back on failure. A new query may replace the visible object in the meantime.
    part = once(part, '    on("drift_fav", function(i)', '    local favouriting = {}\n    on("drift_fav", function(i)')
    part = once(part, '        local now = not it.favorite', '''        if favouriting[it.id] then return end
        favouriting[it.id] = true
        local now = not it.favorite''')
    part = once(part, '            if r == nil then it.favorite = not now; paint_cards() end', '''            favouriting[it.id] = nil
            if r == nil then
                it.favorite = not now
                counts.fav = math.max(0, counts.fav + (now and -1 or 1))
                for _, current in ipairs(items) do if current.id == it.id then current.favorite = not now end end
                paint_cards(); paint_chips()
            end''')
    part = once(part, '    local moving = nil', '    local moving, move_folders = nil, {}')
    part = once(part, '        moving = it', '        moving = it\n        move_folders = {}')
    part = once(part, '            local f = folders[k]', '            local f = folders[k]\n            move_folders[k] = f')
    part = once(part, '        local f = folders[(k or 0) + 1]\n        if (k or 0) + 1 > math.min(#folders, 5) then f = nil end', '''        if type(k) ~= "number" or k < 0 or k > #move_folders or k % 1 ~= 0 then return end
        local f = move_folders[k + 1]
        move_folders = {}''')
    part = once(part, '        local urls, groups, words = {}, {}, {}', '''        local urls, groups, words = {}, {}, {}
        local invalid = 0
        local raw, preserve_text = tostring(data or ""), false
        if mime ~= "text/uri-list" then
            for line in raw:gmatch("[^\\r\\n]+") do
                local l = line:match("^%s*(.-)%s*$")
                if l ~= "" and not l:lower():match("^file://") and not l:match("^https?://%S+$") then preserve_text = true end
            end
        end''')
    part = once(part, '''            if l:match("^file://") then
                local p = url_decode(l:gsub("^file://[^/]*", ""))''', '''            if l:lower():match("^file://") then
                local p = drift_file_path(l)
                if not p then invalid += 1; continue end''')
    part = once(part, '                words[#words + 1] = l', '                if mime == "text/uri-list" then invalid += 1 else words[#words + 1] = l end')
    part = once(part, '        if #requests == 0 then return end', '''        if preserve_text then requests = {{type = "text", text = raw}}; invalid = 0 end
        if #requests == 0 and invalid == 0 then return end''')
    part = once(part, 'local saved, duplicates, failed, left = 0, 0, 0, #requests', 'local saved, duplicates, failed, left = 0, 0, invalid, #requests')
    part = once(part, '            if saved > 0 then', '''            if failed > 0 then
                fact["drift.result"] = 3
                text["drift.toast"] = string.format(tr("Saved: %d · Already kept: %d · Failed: %d"), saved, duplicates, failed)
            elseif saved > 0 then''')
    part = once(part, '        for _, req in ipairs(requests) do', '        if left == 0 then finished(); return end\n        for _, req in ipairs(requests) do')
    part = once(part, '                    duplicates = duplicates + (r.duplicates or 0)', '                    duplicates = duplicates + (r.duplicates or 0)\n                    failed = failed + (r.failed or 0)')
    part = once(part, '                    failed = failed + 1', '                    failed = failed + (req.paths and #req.paths or 1)')
    part = once(part, '\nend\nderiva()', '\n    if fact.page == "drift" then load() end\nend\nderiva()')
    logic = logic[:begin] + part + logic[end:]

    start = scene.index('    component DriftButton(')
    stop = scene.index('    // ── the wardrobe', start)
    page = scene[start:stop]
    page = once(page, 'show: not drift.missing and drift.found < 1', 'show: windows_deriva_loaded and not windows_deriva_busy and not drift.missing and drift.found < 1')
    page = once(page, 'at: dx0, dy0 + 84; columns: 3;', 'show: windows_deriva_loaded\n                    at: dx0, dy0 + 84; columns: 3;')
    page = once(page, 'text "She builds it herself when she starts, if Rust (cargo) is installed."', 'text "Reinstall the Windows package if its library worker is missing."')
    # The six cards end at 492. Put feedback above the search rather than
    # overlaying the bottom row as the previous four-card footer did.
    page = once(page, '        let dy0 = card.top + 96', '''        let dy0 = card.top + 96
        text windows_deriva_status { at: card.x - 228, card.top + 83; anchor: left center; width: 350; lines: 1; size: 10; color: #8b8f95 }
        text "Refresh" { at: card.x + 212, card.top + 83; anchor: right center; size: 10; color: mint; show: not windows_deriva_busy }
        zone box windows_deriva_refresh { from: card.x + 152, card.top + 73; size: 76, 20; cursor: pointer; active: page == drift and paging > 0.9 and not windows_deriva_busy }
        on release windows_deriva_refresh { emit drift_open }''')
    scene = scene[:start] + page + scene[stop:]
    scene = once(scene, '"files",', '"images", "files",')
    return scene, logic
