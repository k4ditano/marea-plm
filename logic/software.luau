-- ── software: updates, and programs to install ─────────────────────
--  What the system has to update is looked at in the background every three
--  hours with `checkupdates` —a database of its own: nothing of the system's
--  is touched— and the AUR's helper (yay or paru), if there is one. Updating
--  is done here and not in a terminal: her field asks for the password, which
--  goes to `sudo -S` by its input and nowhere else —not a file, not an
--  argument, not the environment, which other programs can read—, and the
--  package manager's lines, read in English, say what it is doing as it does
--  it. Afterwards, whether to restart and which settings files are left to
--  review. The catalogue looks for programs the same way.
--  marea.luau loads it, and hands it what it uses of its own.
return function(shared)
    local hooks, say = shared.hooks, shared.say
    local sw = {
        list = {},          -- { name, old, new, aur, size, skip }
        scroll = 0,
        checked = 0,        -- when it was last looked at (os.time)
        news_at = 0,        -- and the news
        looking = false,
        helper = nil,       -- "yay" or "paru": the AUR's
        job = nil,          -- the package manager at work
        pw = nil,           -- kept only while it works, to be able to stop it
        what = nil,         -- { kind = "update" } or { kind = "install", name, aur }
        before = "ready",   -- the state to go back to if the password is not given
        run = nil,          -- what its lines have said so far
        found = {},
        search_gen = 0,
        installed = nil,    -- name -> true, for the finder
        news = {},
        last_upgrade = 0,
        saved = { seen = {}, told = {}, many_day = "" },
    }
    local SW_ROWS = 7
    local SW_C = { LC_ALL = "C" }
    local SW_DB = (sys.ask("env", "XDG_RUNTIME_DIR") or "/tmp") .. "/marea-checkupdates/"

    do
        local ok, saved = pcall(sys.ask, "files.read", "software.json", "json")
        if ok and type(saved) == "table" then
            sw.saved.seen = type(saved.seen) == "table" and saved.seen or {}
            sw.saved.told = type(saved.told) == "table" and saved.told or {}
            sw.saved.many_day = tostring(saved.many_day or "")
        end
    end
    local function sw_save()
        pcall(sys.call, "files.write", "software.json", sw.saved)
    end

    --  The AUR's helper, if there is one: yay, or paru.
    run("yay", { "--version" }, function(_, code)
        if code == 0 then sw.helper = "yay"; return end
        run("paru", { "--version" }, function(_, c2) if c2 == 0 then sw.helper = "paru" end end)
    end)

    local function sw_trim(s)
        return (tostring(s or ""):gsub("^%s+", ""):gsub("%s+$", ""))
    end
    --  What a terminal would colour: out.
    local function sw_plain(s)
        return (tostring(s or ""):gsub("\27%[[%d;]*[A-Za-z]", ""):gsub("\r", ""))
    end
    local function sw_human(bytes)
        if bytes >= 1024 ^ 3 then return string.format("%.1f GB", bytes / 1024 ^ 3) end
        if bytes >= 1024 ^ 2 then return string.format("%.0f MB", bytes / 1024 ^ 2) end
        if bytes > 0 then return string.format("%.0f KB", math.max(1, bytes / 1024)) end
        return ""
    end
    local function sw_when()
        if sw.checked == 0 then return "" end
        local d = os.time() - sw.checked
        if d < 90 then return tr("checked just now") end
        if d < 3600 then return string.format(tr("checked %d min ago"), math.floor(d / 60)) end
        return string.format(tr("checked at %s"), os.date("%H:%M", sw.checked))
    end

    local function sw_paint()
        local total, aur, ticked, size = #sw.list, 0, 0, 0
        for _, p in ipairs(sw.list) do
            if p.aur then aur += 1 end
            if not p.skip then
                ticked += 1
                size += p.size or 0
            end
        end
        fact["sw.count"] = total
        fact["sw.aur"] = aur
        fact["sw.ticked"] = ticked
        local parts = { string.format(tr("%d to update"), total) }
        if aur > 0 then parts[#parts + 1] = string.format(tr("%d from the AUR"), aur) end
        if size > 0 then parts[#parts + 1] = string.format(tr("%s to download"), sw_human(size)) end
        text["sw.summary"] = table.concat(parts, " · ")
        text["sw.when"] = sw_when()
        sw.scroll = math.clamp(sw.scroll, 0, math.max(0, total - SW_ROWS))
        local rows = {}
        for i = sw.scroll + 1, math.min(total, sw.scroll + SW_ROWS) do
            local p = sw.list[i]
            rows[#rows + 1] = { name = p.name, versions = p.old .. "  →  " .. p.new, aur = p.aur, skip = p.skip }
        end
        model["sw.rows"] = rows
        fact["sw.more"] = math.max(0, total - sw.scroll - SW_ROWS)
        local n = sw.news[1]
        fact["sw.news"] = #sw.news
        text["sw.news.title"] = n and n.title or ""
        text["sw.news.date"] = n and (os.date("%d/%m", n.time) .. (#sw.news > 1 and " · " .. string.format(tr("%d more"), #sw.news - 1) or "")) or ""
    end
    table.insert(hooks.language, sw_paint)

    --  A notice, only when it is worth one: news Arch asks you to read before
    --  updating, or a long list waiting (once a day).
    local function sw_tell()
        local changed = false
        for _, n in ipairs(sw.news) do
            if not sw.saved.told[n.link] then
                sw.saved.told[n.link] = true
                changed = true
                run("notify-send", { "-a", "Marea", tr("Arch news before updating"), n.title }, function() end)
            end
        end
        local today = os.date("%Y-%m-%d")
        if #sw.list >= 40 and sw.saved.many_day ~= today then
            sw.saved.many_day = today
            changed = true
            run("notify-send", { "-a", "Marea", string.format(tr("%d updates waiting"), #sw.list),
                                 tr("Software, in her control center, updates them") }, function() end)
        end
        if changed then sw_save() end
    end

    --  How much each repository package weighs to download, from the same
    --  database `checkupdates` refreshed.
    local SW_UNITS = { B = 1, KiB = 1024, MiB = 1024 ^ 2, GiB = 1024 ^ 3 }
    local function sw_sizes()
        local names = {}
        for _, p in ipairs(sw.list) do
            if not p.aur then names[#names + 1] = p.name end
        end
        if #names == 0 then return end
        local args = { "-Si", "--dbpath", SW_DB, "--" }
        for _, n in ipairs(names) do args[#args + 1] = n end
        run("pacman", args, function(out)
            local sizes, name = {}, nil
            for line in tostring(out):gmatch("[^\n]+") do
                local n = line:match("^Name%s*:%s*(%S+)")
                if n then name = n end
                local v, u = line:match("^Download Size%s*:%s*([%d%.]+)%s*(%a+)")
                if v and name then sizes[name] = (tonumber(v) or 0) * (SW_UNITS[u] or 1) end
            end
            for _, p in ipairs(sw.list) do
                if sizes[p.name] then p.size = sizes[p.name] end
            end
            sw_paint()
        end, { env = SW_C })
    end

    local function sw_check()
        if sw.looking or sw.job then return end
        sw.looking = true
        local st = fact["sw.state"]
        if #sw.list > 0 then fact["sw.looking"] = true
        elseif st == "idle" or st == "broken" or st == "ready" then fact["sw.state"] = "scanning" end
        local repos, aur, waiting = nil, {}, 2
        local function finish()
            waiting -= 1
            if waiting > 0 then return end
            sw.looking = false
            fact["sw.looking"] = false
            local now = fact["sw.state"]
            if repos == nil then
                text["sw.error"] = tr("The repositories did not answer: is there a connection?")
                if now == "scanning" then fact["sw.state"] = "broken" end
                sw_paint()
                return
            end
            --  What was left out stays out until it is ticked again.
            local skip = {}
            for _, p in ipairs(sw.list) do
                if p.skip then skip[p.name] = true end
            end
            local list = {}
            for _, p in ipairs(repos) do p.skip = skip[p.name] == true; list[#list + 1] = p end
            for _, p in ipairs(aur) do p.skip = skip[p.name] == true; list[#list + 1] = p end
            sw.list = list
            sw.checked = os.time()
            if now == "scanning" or now == "idle" or now == "broken" then fact["sw.state"] = "ready" end
            sw_paint()
            sw_sizes()
            sw_tell()
        end
        --  0, there are; 2, there are none; anything else, it could not ask.
        run("checkupdates", { "--nocolor" }, function(out, code)
            if code == 0 or code == 2 then
                repos = {}
                for line in tostring(out):gmatch("[^\n]+") do
                    local name, old, new = sw_plain(line):match("^(%S+) (%S+) %-> (%S+)")
                    if name then repos[#repos + 1] = { name = name, old = old, new = new, aur = false } end
                end
            end
            finish()
        end, { env = { LC_ALL = "C", CHECKUPDATES_DB = SW_DB } })
        if sw.helper then
            run(sw.helper, { "-Qua" }, function(out)
                for line in tostring(out):gmatch("[^\n]+") do
                    local name, old, new = sw_plain(line):match("^(%S+) (%S+) %-> (%S+)")
                    if name then aur[#aur + 1] = { name = name, old = old, new = new, aur = true } end
                end
                finish()
            end, { env = SW_C })
        else
            finish()
        end
    end

    --  Arch's news since the last full update, from its feed: a big change says
    --  there what to do before updating.
    local SW_MONTHS = { Jan = 1, Feb = 2, Mar = 3, Apr = 4, May = 5, Jun = 6, Jul = 7, Aug = 8, Sep = 9, Oct = 10, Nov = 11, Dec = 12 }
    local function sw_unescape(s)
        s = tostring(s or ""):gsub("^%s*<!%[CDATA%[(.-)%]%]>%s*$", "%1")
        return (s:gsub("&lt;", "<"):gsub("&gt;", ">"):gsub("&quot;", "\""):gsub("&#39;", "'"):gsub("&#x27;", "'"):gsub("&amp;", "&"))
    end
    local function sw_read_news()
        sw.news_at = os.time()
        run("grep", { "-a", "-F", "starting full system upgrade", "/var/log/pacman.log" }, function(out)
            local last = 0
            for y, mo, d, h, mi in tostring(out):gmatch("%[(%d+)%-(%d+)%-(%d+)[T ](%d+):(%d+)") do
                last = os.time({ year = tonumber(y), month = tonumber(mo), day = tonumber(d), hour = tonumber(h), min = tonumber(mi) })
            end
            --  Never further back than three months: a system never updated
            --  from here would have every piece of news ever written.
            sw.last_upgrade = math.max(last, os.time() - 90 * 86400)
            run("curl", { "-fsSL", "--max-time", "15", "https://archlinux.org/feeds/news/" }, function(xml, code)
                if code ~= 0 then return end
                local items = {}
                for item in tostring(xml):gmatch("<item>(.-)</item>") do
                    local title = sw_unescape(item:match("<title>(.-)</title>"))
                    local link = sw_trim(item:match("<link>(.-)</link>"))
                    local d, mon, y, h, mi = tostring(item:match("<pubDate>(.-)</pubDate>") or ""):match("(%d+) (%a+) (%d+) (%d+):(%d+)")
                    if d and SW_MONTHS[mon] and link ~= "" then
                        local t = os.time({ year = tonumber(y), month = SW_MONTHS[mon], day = tonumber(d), hour = tonumber(h), min = tonumber(mi) })
                        if t > sw.last_upgrade and not sw.saved.seen[link] then
                            items[#items + 1] = { title = title, link = link, time = t }
                        end
                    end
                end
                table.sort(items, function(a, b) return a.time > b.time end)
                sw.news = items
                sw_paint()
                sw_tell()
            end)
        end)
    end

    -- ── at work ──
    local SW_OPS = { upgrading = true, installing = true, reinstalling = true, downgrading = true, removing = true }
    local function sw_progress(p)
        local r = sw.run
        if p > r.progress then
            r.progress = p
            fact["sw.progress"] = p
        end
    end
    local function sw_stage(words, item)
        text["sw.stage"] = words
        if item then text["sw.item"] = item end
    end
    --  A package's name from its file's: `firefox-131.0-1-x86_64` → `firefox`.
    local function sw_pkgname(file)
        return (file:gsub("%-[^%-]+%-[^%-]+%-[^%-]+$", ""))
    end
    local function sw_line(raw)
        local r = sw.run
        if r == nil then return end
        local line = sw_plain(raw)
        local clean = sw_trim(line)
        if clean == "" or clean:find("^%[sudo%]") then return end
        r.log[#r.log + 1] = clean
        if #r.log > 6 then table.remove(r.log, 1) end
        text["sw.line"] = table.concat(r.log, "\n", math.max(1, #r.log - 3))
        local n = clean:match("^Packages? %((%d+)%)")
        if n then
            r.total = tonumber(n)
            r.dl, r.ops = 0, 0
            return
        end
        if clean:find("^:: Synchronizing package databases") then
            sw_stage(tr("Refreshing the lists"), "")
            sw_progress(0.03)
        elseif clean:find("^:: Retrieving packages") then
            sw_stage(tr("Downloading"), "")
            sw_progress(0.06)
        elseif line:match("^ (%S+) downloading%.%.%.$") and r.total > 0 then
            local file = line:match("^ (%S+) downloading")
            r.dl += 1
            sw_stage(tr("Downloading"), string.format(tr("%s · %d of %d"), sw_pkgname(file), math.min(r.dl, r.total), r.total))
            sw_progress(r.base + (0.06 + 0.34 * math.min(r.dl, r.total) / r.total) * (1 - r.base))
        elseif clean:find("^checking keyring") or clean:find("^checking package integrity") or clean:find("^loading package files")
            or clean:find("^checking for file conflicts") or clean:find("^checking available disk space") then
            sw_stage(tr("Checking what was downloaded"), "")
            sw_progress(r.base + 0.42 * (1 - r.base))
        elseif clean:find("^:: Processing package changes") then
            --  From here on it is changing the system: it is not stopped halfway.
            sw_stage(r.kind == "install" and tr("Installing") or tr("Updating"), "")
            fact["sw.can_stop"] = false
            sw_progress(r.base + 0.45 * (1 - r.base))
        elseif clean:find("^:: Running post%-transaction hooks") then
            sw_stage(tr("Finishing"), "")
            sw_progress(r.base + 0.9 * (1 - r.base))
        elseif clean:match("^==> Making package: (%S+)") then
            --  An AUR package, built here: that can be stopped.
            local name = clean:match("^==> Making package: (%S+)")
            r.builds += 1
            if r.builds == 1 then r.base = r.progress end
            fact["sw.can_stop"] = true
            sw_stage(string.format(tr("Building %s"), name), r.aur_total > 0 and string.format(tr("%d of %d from the AUR"), math.min(r.builds, r.aur_total), r.aur_total) or "")
            if r.aur_total > 0 then sw_progress(r.base + (0.95 - r.base) * (r.builds - 1) / r.aur_total) end
        else
            local verb, name = clean:match("^(%a+) (%S+)%.%.%.$")
            if verb and SW_OPS[verb] and r.total > 0 then
                r.ops += 1
                r.done += 1
                if verb ~= "removing" then r.changed[name] = true end
                sw_stage(r.kind == "install" and tr("Installing") or tr("Updating"), string.format(tr("%s · %d of %d"), name, math.min(r.ops, r.total), r.total))
                sw_progress(r.base + (0.45 + 0.45 * r.ops / r.total) * (1 - r.base))
            end
            local i, of = clean:match("^%((%d+)/(%d+)%) ")
            if i and text["sw.stage"] == tr("Finishing") then
                sw_progress(r.base + (0.9 + 0.1 * tonumber(i) / math.max(tonumber(of), 1)) * (1 - r.base))
            end
            if clean:match("installed as (%S+%.pacnew)") then r.pacnew += 1 end
            if clean:find("^error:") or clean:find("^ ?%-> ") and clean:find("[Ee]rror") then r.error = clean end
            if clean:find("incorrect password") or clean:find("no password was provided") then r.wrongpw = true end
        end
    end

    --  What only starts at boot: the kernel and its modules, the drivers, the
    --  system's own pieces.
    local SW_BOOT = { "^linux", "^nvidia", "^systemd$", "^glibc$", "^mesa$", "ucode$", "^lib32%-nvidia", "^lib32%-mesa$" }
    local function sw_after(r)
        fact["sw.reboot"] = false
        for name in pairs(r.changed) do
            for _, pat in ipairs(SW_BOOT) do
                if name:find(pat) and not name:find("^linux%-api%-headers") then fact["sw.reboot"] = true end
            end
        end
        --  And the kernel running whose modules are gone: certainly.
        run("uname", { "-r" }, function(rel)
            run("test", { "-d", "/usr/lib/modules/" .. sw_trim(rel) }, function(_, code)
                if code ~= 0 then fact["sw.reboot"] = true end
            end)
        end)
    end

    local function sw_done(_, code)
        local r = sw.run
        sw.job = nil
        sw.pw = nil
        fact["sw.can_stop"] = false
        fact["sw.stopping"] = false
        if r == nil then return end
        if code == 0 then
            sw_progress(1)
            fact["sw.state"] = "finished"
            if r.kind == "install" then
                text["sw.result"] = string.format(tr("%s is installed"), r.name)
            elseif r.done > 0 then
                text["sw.result"] = string.format(tr("Updated %d packages"), r.done)
            else
                text["sw.result"] = tr("There was nothing left to update")
            end
            fact["sw.pacnew"] = r.pacnew
            sw_after(r)
            sw.installed = nil
        else
            fact["sw.state"] = "failed"
            text["sw.result"] = r.stopped and tr("Stopped") or (r.wrongpw and tr("The password was not accepted") or tr("It did not finish"))
            local lines = {}
            if r.error then lines[1] = r.error end
            for i = math.max(1, #r.log - 3), #r.log do
                if r.log[i] ~= r.error then lines[#lines + 1] = r.log[i] end
            end
            text["sw.error"] = table.concat(lines, "\n")
        end
        log("software ·", r.kind, "ended with", code)
        --  And a fresh look, whatever happened.
        after(800, sw_check)
    end

    --  The same thing, asked for by hand in a terminal: for what wanted an answer.
    local function sw_by_hand(w)
        local helper = sw.helper
        if w.kind == "install" then
            if w.aur and helper then return { helper, "-S", w.name } end
            return { "sudo", "pacman", "-S", w.name }
        end
        if helper then return { helper, "-Syu" } end
        return { "sudo", "pacman", "-Syu" }
    end

    local function sw_start(pw)
        local w = sw.what
        local helper = sw.helper
        local cmd, args
        local aur_total = 0
        local function helper_args(a)
            a[#a + 1] = "--noconfirm"
            a[#a + 1] = "--sudoloop"
            a[#a + 1] = "--sudoflags"
            a[#a + 1] = "-S"
            if helper == "yay" then
                for _, x in ipairs({ "--answerclean", "None", "--answerdiff", "None", "--answeredit", "None", "--answerupgrade", "None" }) do a[#a + 1] = x end
            else
                a[#a + 1] = "--skipreview"
            end
            return a
        end
        if w.kind == "update" then
            local ignore = {}
            for _, p in ipairs(sw.list) do
                if p.skip then ignore[#ignore + 1] = p.name
                elseif p.aur then aur_total += 1 end
            end
            if helper and aur_total > 0 then
                cmd, args = helper, helper_args({ "-Syu" })
            else
                cmd, args = "sudo", { "-S", "-p", "", "pacman", "-Syu", "--noconfirm" }
            end
            if #ignore > 0 then
                args[#args + 1] = "--ignore"
                args[#args + 1] = table.concat(ignore, ",")
            end
        elseif w.aur then
            cmd, args = helper, helper_args({ "-S", "--needed" })
            args[#args + 1] = w.name
            aur_total = 1
        else
            cmd, args = "sudo", { "-S", "-p", "", "pacman", "-S", "--needed", "--noconfirm", "--", w.name }
        end
        --  The helper's own `sudo -v` (its --sudoloop) asks for the password
        --  on a terminal, where nobody answers: it is validated first by
        --  `sudo -S`, in the very process that becomes the helper (`exec`), and
        --  sudo keeps it by that process when there is no terminal, so the
        --  helper's `sudo -v` only keeps it fresh through long AUR builds.
        if helper and cmd == helper then
            local wrapped = { "-c", 'sudo -S -p "" -v && exec "$0" "$@"', helper }
            for _, a in ipairs(args) do wrapped[#wrapped + 1] = a end
            cmd, args = "sh", wrapped
        end
        sw.run = { kind = w.kind, name = w.name, total = 0, dl = 0, ops = 0, done = 0, builds = 0, aur_total = aur_total,
                   base = 0, progress = 0, changed = {}, pacnew = 0, log = {}, error = nil, wrongpw = false, stopped = false }
        sw.pw = pw
        fact["sw.progress"] = 0
        fact["sw.reboot"] = false
        fact["sw.pacnew"] = 0
        fact["sw.can_stop"] = true
        fact["sw.stopping"] = false
        text["sw.line"] = ""
        sw_stage(w.kind == "install" and string.format(tr("Installing %s"), w.name) or tr("Starting"), "")
        fact["sw.state"] = "working"
        log("software ·", cmd, table.concat(args, " "))
        local ok, id = pcall(spawn, cmd, args, sw_line, sw_done, { input = pw .. "\n", errors = true, env = SW_C })
        if ok then
            sw.job = id
        else
            sw.run.error = tostring(id)
            sw_done(nil, -1)
        end
    end

    -- ── what the page asks ──
    local function sw_opened()
        if not sw.looking and not sw.job and os.time() - sw.checked > 30 * 60 then sw_check() end
        if os.time() - sw.news_at > 6 * 3600 then sw_read_news() end
        sw_paint()
    end
    on("sw_open", sw_opened)
    on("sw_check", function()
        sw_check()
        sw_read_news()
    end)
    on("sw_toggle", function(i)
        local p = sw.list[sw.scroll + (i or 0) + 1]
        if p == nil or fact["sw.state"] ~= "ready" then return end
        p.skip = not p.skip
        sw_paint()
    end)
    on("sw_all", function()
        local any = false
        for _, p in ipairs(sw.list) do
            if not p.skip then any = true end
        end
        for _, p in ipairs(sw.list) do p.skip = any end
        sw_paint()
    end)
    on("sw_scroll", function(w)
        sw.scroll += (w or 0) > 0 and -2 or 2
        sw_paint()
    end)
    local function sw_ask(words)
        sw.before = fact["sw.state"]
        text["sw.asking"] = words
        text["sw.pw"] = ""
        fact["sw.state"] = "unlocking"
    end
    on("sw_go", function()
        if fact["sw.state"] ~= "ready" or (fact["sw.ticked"] or 0) < 1 then return end
        sw.what = { kind = "update" }
        sw_ask(string.format(tr("Your password, to update %d packages"), fact["sw.ticked"]))
    end)
    on("sw_install", function(i)
        local f = sw.found[(i or 0) + 1]
        if f == nil or f.installed or sw.job then return end
        if f.aur and not sw.helper then
            say(tr("The AUR needs yay or paru"))
            return
        end
        sw.what = { kind = "install", name = f.name, aur = f.aur }
        sw_ask(string.format(tr("Your password, to install %s"), f.name))
    end)
    on("sw_forget", function()
        if fact["sw.state"] ~= "unlocking" then return end
        text["sw.pw"] = ""
        fact["sw.state"] = (sw.before == "unlocking" or sw.before == "working") and "ready" or sw.before
    end)
    --  The password: checked first, on its own (`-k`, whatever sudo remembers),
    --  so a wrong one is said at once and not after the lists are refreshed.
    on("sw_auth", function()
        if fact["sw.state"] ~= "unlocking" or fact["sw.verifying"] then return end
        local pw = text["sw.pw"] or ""
        text["sw.pw"] = ""
        if pw == "" then return end
        fact["sw.verifying"] = true
        run("sudo", { "-S", "-k", "-p", "", "-v" }, function(_, code)
            fact["sw.verifying"] = false
            if fact["sw.state"] ~= "unlocking" then return end
            if code ~= 0 then
                emit("sw_wrong")
                text["sw.asking"] = tr("That was not it (or this user cannot use sudo)")
                return
            end
            sw_start(pw)
        end, { input = pw .. "\n", env = SW_C })
    end)
    --  Stopping: what it is downloading or building. The package manager runs as
    --  root, so it is asked to stop with the same password.
    on("sw_stop", function()
        if sw.job == nil or not fact["sw.can_stop"] then return end
        fact["sw.stopping"] = true
        if sw.run then sw.run.stopped = true end
        kill(sw.job, "int")
        pcall(run, "pkill", { "-INT", "-x", "makepkg" }, function() end)
        if sw.pw then
            run("sudo", { "-S", "-p", "", "pkill", "-INT", "-x", "pacman" }, function() end, { input = sw.pw .. "\n" })
        end
    end)
    on("sw_back", function()
        if fact["sw.state"] ~= "finished" and fact["sw.state"] ~= "failed" then return end
        fact["sw.state"] = (#sw.list > 0 or sw.checked > 0) and "ready" or "scanning"
        sw_paint()
    end)
    on("sw_news", function()
        local n = sw.news[1]
        if n == nil then return end
        run("xdg-open", { n.link }, function() end)
    end)
    on("sw_skip_news", function()
        local n = table.remove(sw.news, 1)
        if n == nil then return end
        sw.saved.seen[n.link] = true
        sw_save()
        sw_paint()
    end)
    local function sw_terminal(words)
        --  It answers when the terminal is closed; at once, and with −1, if
        --  there is no kitty to open.
        run("kitty", { "--hold", table.unpack(words) }, function(_, code)
            if code == -1 then say(tr("No kitty to open a terminal with")) end
        end, { output = false })
    end
    on("sw_terminal", function()
        if sw.what then sw_terminal(sw_by_hand(sw.what)) end
    end)
    on("sw_review", function()
        sw_terminal({ "sudo", "pacdiff" })
    end)
    on("fact:page", function(p)
        if p ~= "software" and fact["sw.state"] == "unlocking" then
            text["sw.pw"] = ""
            fact["sw.state"] = (sw.before == "unlocking" or sw.before == "working") and "ready" or sw.before
        end
    end)

    -- ── the catalogue ──
    --  The repositories first —their database is here, it answers at once—,
    --  then the AUR, which is asked over the network. The closest names first.
    local function sw_parse_search(out, aur)
        local found, last = {}, nil
        for line in tostring(out):gmatch("[^\n]+") do
            line = sw_plain(line)
            local repo, name, version, rest = line:match("^(%S+)/(%S+) (%S+)(.*)$")
            if repo then
                last = { name = name, repo = repo, version = version, about = "", aur = aur,
                         installed = rest:find("%[installed") ~= nil or rest:find("%(Installed") ~= nil }
                found[#found + 1] = last
            elseif last and line:find("^%s+") then
                last.about = sw_trim(line)
            end
        end
        return found
    end
    local function sw_rank(q, list)
        for k, f in ipairs(list) do
            local n = f.name:lower()
            f.rank = (n == q and 0) or (n:sub(1, #q) == q and 1) or (n:find(q, 1, true) and 2) or 3
            f.order = k
        end
        table.sort(list, function(a, b)
            if a.rank ~= b.rank then return a.rank < b.rank end
            if a.aur ~= b.aur then return not a.aur end
            return a.order < b.order
        end)
        return list
    end
    local function sw_words(q)
        local args = {}
        for w in q:gmatch("%S+") do
            args[#args + 1] = (w:gsub("([%.%^%$%*%+%?%(%)%[%]%{%}%|\\])", "\\%1"))
        end
        return args
    end
    local function sw_show_found(list)
        local rows = {}
        for k = 1, math.min(#list, 6) do
            local f = list[k]
            rows[k] = { name = f.name, repo = f.aur and "AUR" or f.repo, version = f.version, about = f.about, installed = f.installed, aur = f.aur }
        end
        sw.found = list
        model["sw.found"] = rows
    end
    local function sw_search()
        local q = sw_trim(text["sw.query"]):lower()
        fact["sw.typed"] = #q >= 2
        sw.search_gen += 1
        local mine = sw.search_gen
        if #q < 2 then
            fact["sw.searching"] = false
            sw_show_found({})
            return
        end
        fact["sw.searching"] = true
        after(280, function()
            if mine ~= sw.search_gen then return end
            local args = { "-Ss", "--" }
            for _, w in ipairs(sw_words(q)) do args[#args + 1] = w end
            run("pacman", args, function(out)
                if mine ~= sw.search_gen then return end
                local repo = sw_parse_search(out, false)
                sw_show_found(sw_rank(q, repo))
                if not sw.helper then
                    fact["sw.searching"] = false
                    return
                end
                local aur_args = { "-Ssa", "--" }
                for _, w in ipairs(sw_words(q)) do aur_args[#aur_args + 1] = w end
                run(sw.helper, aur_args, function(out2)
                    if mine ~= sw.search_gen then return end
                    local all = sw_parse_search(out2, true)
                    for _, f in ipairs(repo) do all[#all + 1] = f end
                    sw_show_found(sw_rank(q, all))
                    fact["sw.searching"] = false
                end, { env = SW_C })
            end, { env = SW_C })
        end)
    end
    on("text:sw.query", sw_search)

    --  From the finder: her pages, and a program not installed yet that is
    --  named, which opens the catalogue on it.
    hooks.software = function(tab)
        fact.open = true
        fact.page = "software"
        fact["sw.tab"] = tab or "updates"
        sw_opened()
    end
    hooks.packages = function(q, answer)
        local args = { "-Ss", "--" }
        for _, w in ipairs(sw_words(q)) do args[#args + 1] = w end
        run("pacman", args, function(out)
            local rows = {}
            for _, f in ipairs(sw_rank(q, sw_parse_search(out, false))) do
                if #rows < 2 and not f.installed and f.rank < 3 then
                    rows[#rows + 1] = { name = f.name, kind_label = tr("Install") .. " · " .. f.repo, icon = "", glyph = 5, package = f.name }
                end
            end
            answer(rows)
        end, { env = SW_C })
    end
    hooks.install = function(name)
        hooks.software("catalogue")
        text["sw.query"] = name
        sw_search()
    end

    --  In the background: a first look a minute after starting, and then every
    --  three hours; the text of «when» kept fresh while the page is open.
    after(60 * 1000, function()
        sw_check()
        sw_read_news()
    end)
    every(3 * 3600 * 1000, function()
        sw_check()
        sw_read_news()
    end)
    every(60 * 1000, function()
        if fact.page == "software" then text["sw.when"] = sw_when() end
    end)
end
