-- ── the chat: talking to her, and her hands on the desktop ─────────
--  Her AI is the Pi SDK in a sandbox (`agent/`), spoken to in JSON lines.
--  It PROPOSES; this decides. Looking (the windows, a picture of one) is done
--  at once; anything that changes something becomes a card in the thread
--  that you allow or not, and only then is it done, with pleamar-wm's agent
--  hands (`pleamar-wm agent …`): her own pointer and keyboard, never yours.
--  What happened is what this says happened, never what the model says.
--  marea.luau loads it, and hands it what it uses of its own.
return function(shared)
    local hooks, settings, save_settings, home_dir = shared.hooks, shared.settings, shared.save_settings, shared.home_dir
    local base = sys.ask("env", "XDG_STATE_HOME")
    if base == nil or base == "" then base = home_dir .. "/.local/state" end
    local STATE = base .. "/marea-plm/agent"
    --  How her hands are run: what they say went wrong comes back too, and
    --  the cursor on the desktop is labelled hers.
    local HANDS = { errors = true, env = { PLEAMAR_AGENT_NAME = "Marea" } }
    local DEFAULT_MODEL = "openai-codex/gpt-5.6-luna"
    local function chosen() return type(settings.chat_model) == "string" and settings.chat_model or DEFAULT_MODEL end
    local PROVIDERS = { ["openai-codex"] = "ChatGPT" }
    local models = {}
    fact["chat.free"] = settings.chat_free == true
    on("fact:chat.free", function() save_settings() end)
    local function show_models()
        local out = {}
        for k, name in ipairs(models) do
            out[k] = { name = name:gsub("^[^/]+/", ""), on = name == chosen() and 1 or 0 }
        end
        model["chat.models"] = out
    end
    local ROWS = 24
    local rows = {}          -- the whole thread: { kind, text, detail, state, id }
    local history = {}       -- what is handed back to a fresh worker: { role, text }
    local worker = nil
    local ready = false
    local queue = {}         -- lines for the worker until it is ready
    local live = nil         -- the row of her answer arriving
    --  What is seen of it: the model hands the whole answer over in about a
    --  second, so it is shown at a reading pace instead —letter by letter,
    --  hurrying when far behind—, and keeps going after the model is done.
    local shown_row = nil
    local shown = 0
    local revealing = false
    local asks = {}          -- proposal id -> { row, tool, args }
    local programs = {}      -- pid -> program, from the last list of windows
    local looks = 0
    local idle_timer = nil
    local stopped_by_pill = false
    --  How the turn ended, for her tasks (see «her tasks» below), and what
    --  they do when one ends.
    local ending = nil
    local turn_over = nil
    local running_task = nil  -- the task she is doing on her own now (its id)
    local task_do             -- her task tools (below)
    local task_days           -- «every day», «Mon, Wed»… (below)
    local secrets, secret_named -- the passwords you saved for her (below)
    local usable = false

    local function letters(s)
        local ok, n = pcall(utf8.len, s)
        return ok and n or #s
    end

    --  The first `n` letters of a text.
    local function first_letters(s, n)
        local ok, b = pcall(utf8.offset, s, n + 1)
        if ok and b then return s:sub(1, b - 1) end
        return s
    end

    local painting = false
    local function paint()
        if painting then return end
        painting = true
        after(16, function()
            painting = false
            local first = math.max(1, #rows - ROWS + 1)
            local out = {}
            for k = first, #rows do
                local r = rows[k]
                local words = r.text
                if k == shown_row then words = first_letters(words, shown) end
                out[#out + 1] = { kind = r.kind, text = words, detail = r.detail or "", state = r.state or 0 }
            end
            model["chat.rows"] = out
            if shown_row and shown_row >= first then
                fact["chat.live"] = shown_row - first
                fact["chat.letters"] = shown
            else
                fact["chat.live"] = -1
            end
        end)
    end
    table.insert(hooks.language, paint)
    --  The last letters shown fade in (the scene's `chat.letters`): past the
    --  end it goes on a little, so the last ones finish fading too.
    local TAIL = 12
    local function reveal()
        if revealing then return end
        revealing = true
        local function tick()
            if not shown_row or not rows[shown_row] then
                revealing = false
                return
            end
            local total = letters(rows[shown_row].text)
            local behind = total - shown
            if behind <= -TAIL then
                --  All of it seen, and the model done with it.
                if shown_row ~= live then
                    shown_row = nil
                    revealing = false
                    paint()
                    return
                end
            else
                shown = shown + math.clamp(math.floor(behind / 12), 2, 10)
                paint()
            end
            after(33, tick)
        end
        after(33, tick)
    end
    local function add(kind, text, detail, state)
        rows[#rows + 1] = { kind = kind, text = text or "", detail = detail or "", state = state or 0 }
        paint()
        --  It falls into the thread (after it is painted).
        after(20, function() emit("chat_landed") end)
        return #rows
    end
    local function status(words)
        text["chat.status"] = words or ""
    end

    local function save()
        local keep = {}
        for k = math.max(1, #rows - 60), #rows do
            local r = rows[k]
            if r.kind ~= 4 or r.state ~= 0 then keep[#keep + 1] = { kind = r.kind, text = r.text, detail = r.detail, state = r.state } end
        end
        pcall(sys.call, "files.write", "chat.json", { rows = keep, history = history })
    end
    do
        local ok, saved = pcall(sys.ask, "files.read", "chat.json", "json")
        if ok and type(saved) == "table" then
            rows = type(saved.rows) == "table" and saved.rows or {}
            history = type(saved.history) == "table" and saved.history or {}
        end
    end

    local function send(m)
        local line = json.encode(m) .. "\n"
        if worker and ready then
            if not write(worker, line) then log("chat · the worker did not hear") end
        else
            queue[#queue + 1] = line
        end
    end

    -- ── doing what she proposes ──
    local WORDS = {
        desktop_windows = "Looking at your windows",
        desktop_look = "Looking at %s",
        desktop_click = "Click in %s",
        desktop_type = "Type in %s",
        desktop_type_secret = "Type a saved password in %s",
        desktop_key = "A key in %s",
        desktop_hotkey = "Keys in %s",
        desktop_scroll = "Scroll in %s",
        desktop_drag = "Drag in %s",
        desktop_focus = "Bring %s forward",
        desktop_to_monitor = "Move %s to another monitor",
        open_app = "Open %s",
    }
    --  A window as desktop_windows names it: «4521», or «4521.3» for one of
    --  a program's several. Anything else is no window.
    local function window_name(v)
        local name = tostring(v or "")
        if name:match("^%d+$") or name:match("^%d+%.%d+$") then return name end
        return "0"
    end
    local function program(args, tool)
        if args.name and tool ~= "desktop_type_secret" then return tostring(args.name) end
        return programs[window_name(args.pid)] or ("the window " .. tostring(args.pid or "?"))
    end
    local function said(tool, args)
        return string.format(tr(WORDS[tool] or tool), program(args, tool))
    end
    local function agent_args(tool, a)
        local pid = window_name(a.pid)
        local n = function(v) return tostring(tonumber(v) or 0) end
        if tool == "desktop_windows" then return { "agent", "windows" } end
        if tool == "desktop_click" then return { "agent", "click", pid, n(a.x), n(a.y), tostring(a.button or "left"), tostring(math.floor(tonumber(a.count) or 1)) } end
        if tool == "desktop_type" then return { "agent", "type", pid, tostring(a.text or "") } end
        if tool == "desktop_key" then return { "agent", "key", pid, tostring(a.key or "") } end
        if tool == "desktop_hotkey" then return { "agent", "hotkey", pid, tostring(a.keys or "") } end
        if tool == "desktop_scroll" then return { "agent", "scroll", pid, n(a.x), n(a.y), tostring(a.direction or "down"), tostring(math.floor(tonumber(a.steps) or 3)) } end
        if tool == "desktop_drag" then return { "agent", "drag", pid, n(a.x1), n(a.y1), n(a.x2), n(a.y2) } end
        if tool == "desktop_focus" then return { "agent", "focus", pid } end
        if tool == "desktop_to_monitor" then return { "agent", "send", pid, tostring(math.floor(tonumber(a.monitor) or 0)) } end
        return nil
    end
    --  A program by what the model calls it: its name, its .desktop id, its
    --  command or its class; or what it is («a file manager», «archivos»),
    --  by the usual ones of that kind that are installed.
    local KINDS = {
        { words = { "file", "files", "archivos", "explorador", "explorer", "file manager", "gestor de archivos", "carpetas", "folders" }, apps = { "dolphin", "nautilus", "thunar", "nemo", "pcmanfm", "caja" } },
        { words = { "terminal", "consola", "console", "shell" }, apps = { "kitty", "alacritty", "foot", "konsole", "gnome-terminal", "wezterm", "ghostty" } },
        { words = { "browser", "navegador", "web", "internet" }, apps = { "zen", "firefox", "chromium", "brave", "chrome", "vivaldi", "librewolf" } },
        { words = { "text editor", "editor", "editor de texto", "notepad", "bloc de notas" }, apps = { "gnome-text-editor", "kate", "gedit", "mousepad", "code", "zed" } },
        { words = { "calculator", "calculadora" }, apps = { "calculator", "calculadora", "kcalc", "qalculate" } },
        { words = { "settings", "ajustes", "configuración", "configuracion" }, apps = { "settings", "systemsettings", "ajustes" } },
    }
    local function app_matches(a, want)
        for _, field in ipairs({ a.name, a.id, a.exec, a.wmclass }) do
            if type(field) == "string" and field:lower():find(want, 1, true) then return true end
        end
        return false
    end
    local function find_app(name)
        local want = name:lower():gsub("^%s+", ""):gsub("%s+$", "")
        if want == "" then return nil end
        for _, a in ipairs(shared.apps()) do
            if a.name:lower() == want then return a end
        end
        for _, a in ipairs(shared.apps()) do
            if app_matches(a, want) then return a end
        end
        for _, kind in ipairs(KINDS) do
            for _, w in ipairs(kind.words) do
                if want == w or want:find(w, 1, true) then
                    for _, candidate in ipairs(kind.apps) do
                        for _, a in ipairs(shared.apps()) do
                            if app_matches(a, candidate) then return a end
                        end
                    end
                end
            end
        end
        return nil
    end

    local function finish_row(row, ok, denied)
        if row and rows[row] then
            rows[row].state = denied and 3 or (ok and 1 or 2)
            paint()
        end
    end
    local function answer(id, ok, words, extra)
        local m = { type = "result", id = id, ok = ok, text = words or "" }
        if extra then for k, v in pairs(extra) do m[k] = v end end
        send(m)
    end
    local function perform(id, tool, args, row)
        if tool:sub(1, 5) == "task_" then
            task_do(id, tool, args, row)
            return
        end
        fact["chat.state"] = "acting"
        status(said(tool, args))
        if tool == "open_app" then
            local found = find_app(tostring(args.name or ""))
            if found then
                --  Opened by her hands (`pleamar-wm agent open`): the monitor
                --  she works on lights first, and the window opens there
                --  without taking your keyboard. A session without that:
                --  as any program is opened.
                local exec = tostring(found.exec):gsub("%%%a", ""):gsub("%s+$", "")
                local argv = { "agent", "open" }
                local m = tonumber(args.monitor)
                if m then
                    argv[#argv + 1] = "--monitor"
                    argv[#argv + 1] = tostring(math.floor(m))
                end
                argv[#argv + 1] = "--"
                argv[#argv + 1] = exec
                run("pleamar-wm", argv, function(out, code)
                    local where = code == 0 and tostring(out):match("on monitor (%d+)")
                    if not where then pcall(sys.call, "apps.launch", found.exec) end
                    finish_row(row, true)
                    answer(id, true, "Opened " .. found.name .. (where and (" on monitor " .. where .. ", where you work, without the user's keyboard") or ", on the monitor where the user is") .. ". Its window may take a moment to show: desktop_windows to find it.")
                end, HANDS)
                return
            end
            local names = {}
            for _, a in ipairs(shared.apps()) do names[#names + 1] = a.name end
            finish_row(row, false)
            answer(id, false, "No installed program matches that. These are the ones there are: " .. table.concat(names, ", "))
            return
        end
        if tool == "desktop_type_secret" then
            --  From your keyring straight to the window: never in her words,
            --  never on a command line (the agent reads it from its input).
            local name = tostring(args.name or "")
            local _, known = secret_named(name)
            if not known then
                finish_row(row, false)
                answer(id, false, "There is no password saved under «" .. name .. "». The names there are: " .. (#secrets > 0 and table.concat(secrets, ", ") or "none"))
                return
            end
            run("secret-tool", { "lookup", "service", "marea-plm", "name", known }, function(out, code)
                local secret = tostring(out or ""):gsub("\n$", "")
                if code ~= 0 or secret == "" then
                    finish_row(row, false)
                    answer(id, false, "Marea could not read that password from the keyring.")
                    return
                end
                run("pleamar-wm", { "agent", "type", window_name(args.pid), "-" }, function(o2, c2)
                    finish_row(row, c2 == 0)
                    answer(id, c2 == 0, c2 == 0 and ("Typed the password saved as «" .. known .. "».") or tostring(o2))
                end, { errors = true, env = { PLEAMAR_AGENT_NAME = "Marea" }, input = secret })
            end)
            return
        end
        if tool == "desktop_look" then
            looks += 1
            fact["chat.looking"] = true
            local name = "look-" .. (looks % 3) .. ".png"
            run("pleamar-wm", { "agent", "look", window_name(args.pid), STATE .. "/" .. name }, function(out, code)
                --  The glass stays on her face a moment: the look is seen.
                after(600, function() fact["chat.looking"] = false end)
                if code == 0 then
                    local w, h = tostring(out):match("(%d+)x(%d+)")
                    finish_row(row, true)
                    answer(id, true, string.format("A picture of %s, %sx%s pixels.", program(args), w or "?", h or "?"), { image = { path = "/state/" .. name } })
                else
                    finish_row(row, false)
                    answer(id, false, tostring(out))
                end
            end, HANDS)
            return
        end
        local argv = agent_args(tool, args)
        if not argv then
            finish_row(row, false)
            answer(id, false, "Marea does not know that tool.")
            return
        end
        if tool == "desktop_windows" then
            run("pleamar-wm", argv, function(out, code)
                if code ~= 0 then
                    finish_row(row, false)
                    answer(id, false, tostring(out))
                    return
                end
                programs = {}
                for line in tostring(out):gmatch("[^\n]+") do
                    local pid, app = line:match("^%s*([%d%.]+)%s+(%S+)%s+«")
                    if pid then
                        --  A dialog is called by what it is, not by the
                        --  program that draws it (a portal's).
                        if line:find("dialog of", 1, true) then app = tr("a dialog") end
                        programs[pid] = app
                    end
                end
                run("pleamar-wm", { "agent", "monitors" }, function(screens)
                    finish_row(row, true)
                    answer(id, true, tostring(out) .. "\n\nMonitors:\n" .. tostring(screens))
                end, HANDS)
            end, HANDS)
            return
        end
        run("pleamar-wm", argv, function(out, code)
            --  Stopped from the monitor's pill: the whole turn ends, not
            --  only this step.
            if code ~= 0 and tostring(out):find("stopped the agent", 1, true) then
                finish_row(row, false)
                answer(id, false, "The user stopped you from the monitor. Stop now.")
                stopped_by_pill = true
                send({ type = "cancel" })
                return
            end
            finish_row(row, code == 0)
            answer(id, code == 0, code == 0 and (out ~= "" and tostring(out) or "Done.") or tostring(out))
        end, HANDS)
    end

    -- ── her memory ──
    --  What she keeps between conversations, in her folder: facts about you
    --  and notes on how to do things (memory.json), and the conversations
    --  that came before (chat-YYYYMMDD-HHMMSS.json, kept on «new»). She keeps
    --  them herself, without a card: each one is shown in the thread as it
    --  is kept, and Settings › What she remembers forgets any of it.
    local MAX_FACTS, MAX_NOTES, MAX_TALKS = 200, 100, 300
    local memory = { facts = {}, notes = {}, next = 1 }
    do
        local ok, saved = pcall(sys.ask, "files.read", "memory.json", "json")
        if ok and type(saved) == "table" then
            memory.facts = type(saved.facts) == "table" and saved.facts or {}
            memory.notes = type(saved.notes) == "table" and saved.notes or {}
            memory.next = tonumber(saved.next) or (#memory.facts + #memory.notes + 1)
        end
    end
    local shelf = {}         -- what Settings lists, in its order: { kind, id }
    local function talks()
        local ok, names = pcall(sys.ask, "files.list")
        local out = {}
        if ok and type(names) == "table" then
            for _, n in ipairs(names) do
                if type(n) == "string" and n:match("^chat%-%d+%-%d+%.json$") then out[#out + 1] = n end
            end
        end
        table.sort(out, function(a, b) return a > b end)
        return out
    end
    local function show_memory()
        local out = {}
        shelf = {}
        for k = #memory.facts, 1, -1 do
            local f = memory.facts[k]
            out[#out + 1] = { kind = 1, text = tostring(f.text or ""), detail = "" }
            shelf[#shelf + 1] = { kind = 1, id = f.id }
        end
        for k = #memory.notes, 1, -1 do
            local n = memory.notes[k]
            out[#out + 1] = { kind = 2, text = tostring(n.title or ""), detail = tostring(n.when or "") }
            shelf[#shelf + 1] = { kind = 2, id = n.id }
        end
        while #out > 24 do table.remove(out); table.remove(shelf) end
        model["mem.items"] = out
        local n = #talks()
        text["mem.talks"] = n == 0 and tr("None kept yet") or string.format(tr("%d kept on this computer"), n)
        text["mem.summary"] = string.format(tr("%d things, %d notes"), #memory.facts, #memory.notes)
        fact["mem.kept"] = n
    end
    table.insert(hooks.language, show_memory)
    local function keep_memory()
        pcall(sys.call, "files.write", "memory.json", memory)
        show_memory()
    end
    --  The passwords you saved for her tasks (Settings › Her tasks ›
    --  Passwords): their names here (secrets.json), the passwords in your
    --  system keyring (secret-tool, «service marea-plm»). She is told the
    --  names; Marea types a password for her without her ever seeing it.
    secrets = {}
    do
        local ok, saved = pcall(sys.ask, "files.read", "secrets.json", "json")
        if ok and type(saved) == "table" and type(saved.names) == "table" then secrets = saved.names end
    end
    local function show_secrets()
        local out = {}
        for k, n in ipairs(secrets) do
            out[k] = { name = tostring(n) }
            if k >= 12 then break end
        end
        model["keys.rows"] = out
    end
    local function keep_secrets()
        pcall(sys.call, "files.write", "secrets.json", { names = secrets })
        show_secrets()
    end
    secret_named = function(name)
        for k, n in ipairs(secrets) do
            if string.lower(tostring(n)) == string.lower(tostring(name or "")) then return k, n end
        end
        return nil
    end
    on("keys_keep", function()
        local name = tostring(text["keys.name"] or ""):match("^%s*(.-)%s*$")
        local value = tostring(text["keys.value"] or "")
        if name == "" or value == "" then text["keys.status"] = tr("A name and a password, both"); return end
        if #name > 60 then name = name:sub(1, 60) end
        run("secret-tool", { "store", "--label=Marea: " .. name, "service", "marea-plm", "name", name }, function(_, code)
            if code ~= 0 then text["keys.status"] = tr("The keyring did not take it"); return end
            if not secret_named(name) then secrets[#secrets + 1] = name end
            keep_secrets()
            text["keys.name"] = ""
            text["keys.value"] = ""
            text["keys.status"] = string.format(tr("Kept as «%s»"), name)
        end, { input = value, errors = true })
    end)
    on("keys_drop", function(i)
        local name = secrets[(tonumber(i) or -1) + 1]
        if not name then return end
        run("secret-tool", { "clear", "service", "marea-plm", "name", name }, function() end)
        local k = secret_named(name)
        if k then table.remove(secrets, k) end
        keep_secrets()
        text["keys.status"] = ""
    end)
    show_secrets()

    --  What goes to her in every conversation (her worker trims it to fit).
    local function for_her()
        local facts, notes = {}, {}
        for _, f in ipairs(memory.facts) do facts[#facts + 1] = { id = f.id, text = f.text } end
        for _, n in ipairs(memory.notes) do notes[#notes + 1] = { title = n.title, when = n.when } end
        return { facts = facts, notes = notes, secrets = secrets }
    end
    --  The conversation as it is, kept to look back on, when a new one starts.
    local function keep_talk()
        local said = {}
        for _, r in ipairs(rows) do
            if r.kind == 1 or r.kind == 2 then said[#said + 1] = { kind = r.kind, text = r.text } end
        end
        if #said == 0 then return end
        pcall(sys.call, "files.write", "chat-" .. os.date("%Y%m%d-%H%M%S") .. ".json", { at = os.time(), rows = said })
        local all = talks()
        for k = MAX_TALKS + 1, #all do pcall(sys.call, "files.remove", all[k]) end
    end

    local function trimmed(v, n)
        return first_letters((tostring(v or ""):match("^%s*(.-)%s*$")), n)
    end
    local function words_of(q)
        local out = {}
        for w in string.lower(q):gmatch("[%w\128-\255]+") do
            if #w >= 2 then out[#out + 1] = w end
        end
        return out
    end
    local function hits(s, words)
        local low, n = string.lower(s), 0
        for _, w in ipairs(words) do
            if low:find(w, 1, true) then n += 1 end
        end
        return n
    end
    local function note_named(title)
        local want = string.lower(trimmed(title, 80))
        for k, n in ipairs(memory.notes) do
            if string.lower(tostring(n.title)) == want then return k, n end
        end
        for k, n in ipairs(memory.notes) do
            if string.lower(tostring(n.title)):find(want, 1, true) then return k, n end
        end
        return nil
    end
    --  A turn of a conversation, as a search answers it.
    local function quoted(r)
        local who = r.kind == 1 and "User" or "You"
        return who .. ": " .. first_letters((tostring(r.text or ""):gsub("%s+", " ")), 400)
    end

    local function remember(id, tool, args)
        local function row(words) return add(3, words, "", 0) end
        if tool == "memory_save" then
            local t = trimmed(args.text, 300)
            if t == "" then answer(id, false, "Nothing to keep."); return end
            for _, f in ipairs(memory.facts) do
                if string.lower(tostring(f.text)) == string.lower(t) then answer(id, true, "Already kept, as [" .. f.id .. "]."); return end
            end
            local r = row(tr("Remembered: ") .. t)
            local fid = "f" .. memory.next
            memory.next += 1
            memory.facts[#memory.facts + 1] = { id = fid, text = t, at = os.time() }
            while #memory.facts > MAX_FACTS do table.remove(memory.facts, 1) end
            keep_memory()
            finish_row(r, true)
            answer(id, true, "Kept, as [" .. fid .. "].")
        elseif tool == "memory_forget" then
            local want = trimmed(args.id, 16):gsub("[%[%]]", "")
            for k, f in ipairs(memory.facts) do
                if f.id == want then
                    table.remove(memory.facts, k)
                    keep_memory()
                    finish_row(row(tr("Forgot: ") .. tostring(f.text)), true)
                    answer(id, true, "Forgotten.")
                    return
                end
            end
            answer(id, false, "There is no fact [" .. want .. "].")
        elseif tool == "memory_learn" then
            local title, when, how = trimmed(args.title, 80), trimmed(args.when, 200), trimmed(args.how, 3000)
            if title == "" or how == "" then answer(id, false, "A note needs a title and the steps."); return end
            local r = row(tr("Noted how to: ") .. title)
            local k = note_named(title)
            local note = { id = "n" .. memory.next, title = title, when = when, how = how, at = os.time() }
            memory.next += 1
            if k and string.lower(tostring(memory.notes[k].title)) == string.lower(title) then
                table.remove(memory.notes, k)
            end
            memory.notes[#memory.notes + 1] = note
            while #memory.notes > MAX_NOTES do table.remove(memory.notes, 1) end
            keep_memory()
            finish_row(r, true)
            answer(id, true, "Written down.")
        elseif tool == "memory_recall" then
            local words = words_of(tostring(args.query or ""))
            local found = {}
            for k = #memory.facts, 1, -1 do
                local f = memory.facts[k]
                local n = hits(tostring(f.text), words)
                if n > 0 then found[#found + 1] = { n = n, line = "[" .. f.id .. "] " .. tostring(f.text) } end
            end
            table.sort(found, function(a, b) return a.n > b.n end)
            local lines = {}
            for k = 1, math.min(12, #found) do lines[k] = found[k].line end
            finish_row(row(tr("Remembering: ") .. trimmed(args.query, 60)), true)
            answer(id, true, #lines > 0 and table.concat(lines, "\n") or "Nothing kept about that.")
        elseif tool == "memory_read" then
            local _, n = note_named(tostring(args.title or ""))
            finish_row(row(tr("Reading her note: ") .. trimmed(n and n.title or args.title, 60)), n ~= nil)
            if n then
                answer(id, true, tostring(n.title) .. "\nWhen: " .. tostring(n.when) .. "\n\n" .. tostring(n.how))
            else
                answer(id, false, "There is no note with that title.")
            end
        elseif tool == "memory_search" then
            local q = trimmed(args.query, 200)
            local words = words_of(q)
            local r = row(tr("Looking back: ") .. first_letters(q, 60))
            if #words == 0 then finish_row(r, false); answer(id, false, "Say what to look for."); return end
            local need = math.max(1, math.ceil(#words / 2))
            local found = {}
            --  (Not the question just asked: it is what is being looked for.)
            local asking = nil
            for k = #rows, 1, -1 do
                if rows[k].kind == 1 then asking = rows[k]; break end
            end
            local function look(said, when)
                for k, t in ipairs(said) do
                    if #found >= 8 then return end
                    if t ~= asking and (t.kind == 1 or t.kind == 2) and hits(tostring(t.text), words) >= need then
                        local before = said[k - 1]
                        local s = "— " .. when .. "\n"
                        if before and (before.kind == 1 or before.kind == 2) then s = s .. quoted(before) .. "\n" end
                        found[#found + 1] = s .. quoted(t)
                    end
                end
            end
            look(rows, "this conversation")
            for _, name in ipairs(talks()) do
                if #found >= 8 then break end
                local ok, talk = pcall(sys.ask, "files.read", name, "json")
                if ok and type(talk) == "table" and type(talk.rows) == "table" then
                    local y, mo, d = name:match("^chat%-(%d%d%d%d)(%d%d)(%d%d)")
                    look(talk.rows, string.format("%s-%s-%s", y or "?", mo or "?", d or "?"))
                end
            end
            finish_row(r, true)
            answer(id, true, #found > 0 and table.concat(found, "\n\n") or "Nothing said about that, in this conversation or the ones kept.")
        else
            answer(id, false, "Marea does not know that tool.")
        end
    end
    on("mem_forget", function(i)
        local it = shelf[(tonumber(i) or -1) + 1]
        if not it then return end
        local list = it.kind == 1 and memory.facts or memory.notes
        for k, x in ipairs(list) do
            if x.id == it.id then table.remove(list, k); break end
        end
        keep_memory()
    end)
    --  Pressed once, it asks to be sure; again within four seconds, it deletes.
    local sure, sure_timer = false, nil
    on("mem_clear_talks", function()
        if not sure then
            sure = true
            fact["mem.sure"] = true
            if sure_timer then cancel(sure_timer) end
            sure_timer = after(4000, function() sure_timer = nil; sure = false; fact["mem.sure"] = false end)
            return
        end
        if sure_timer then cancel(sure_timer); sure_timer = nil end
        sure = false
        fact["mem.sure"] = false
        for _, name in ipairs(talks()) do pcall(sys.call, "files.remove", name) end
        show_memory()
    end)
    on("fact:section", function(v)
        if v == "memory" then show_memory() end
    end)
    show_memory()

    -- ── the worker ──
    local function stop_idle()
        if idle_timer then cancel(idle_timer); idle_timer = nil end
    end
    local function rest_later()
        stop_idle()
        --  Three minutes without a word, and the worker goes (a hundred MB
        --  of Node): the next message starts it again with the thread.
        idle_timer = after(3 * 60 * 1000, function()
            idle_timer = nil
            if worker and (fact["chat.state"] == "idle" or fact["chat.state"] == "offline") and fact["chat.signing"] ~= true then
                write(worker, json.encode({ type = "shutdown" }) .. "\n")
            end
        end)
    end
    local function settle(state)
        fact["chat.state"] = state or "idle"
        status("")
        live = nil
        paint()
        run("pleamar-wm", { "agent", "done" }, function() end, HANDS)
        save()
        rest_later()
        local how = ending or { ok = false, said = "" }
        ending = nil
        if turn_over then turn_over(how) end
    end
    local function on_event(m)
        local kind = m.type
        if kind == "ready" then
            ready = true
            usable = m.usable == true
            text["chat.model"] = m.model or ""
            models = type(m.models) == "table" and m.models or {}
            show_models()
            fact["chat.signed_in"] = m.reason ~= "signed_out"
            local provider = tostring(m.model or chosen()):match("^([^/]+)/") or ""
            text["chat.account"] = string.format(tr("Signed in with %s"), PROVIDERS[provider] or provider)
            if m.usable then
                if fact["chat.state"] == "offline" or fact["chat.state"] == "starting" then
                    fact["chat.state"] = "idle"
                    status("")
                end
            else
                fact["chat.state"] = "offline"
                --  Signed out, the panel itself says so and offers the way in.
                status(m.reason == "signed_out" and "" or tr("That model cannot be used with her account: choose another in Settings"))
            end
            for _, line in ipairs(queue) do write(worker, line) end
            queue = {}
        elseif kind == "login_url" then
            fact["chat.signing"] = true
            run("xdg-open", { tostring(m.url) }, function() end)
        elseif kind == "login_done" then
            fact["chat.signing"] = false
            if not m.ok and m.reason ~= "cancelled" then
                status(tr("The sign-in did not finish: ") .. tostring(m.reason or "?"))
            end
        elseif kind == "delta" then
            if live == nil then
                live = add(2, "")
                shown_row, shown = live, 0
                fact["chat.state"] = "thinking"
                status(tr("Thinking…"))
            end
            rows[live].text = rows[live].text .. (m.text or "")
            reveal()
        elseif kind == "propose" then
            live = nil
            local tool, args = tostring(m.tool), (type(m.args) == "table" and m.args or {})
            local looks_only = tool == "desktop_windows" or tool == "desktop_look"
            --  Her memory: kept in sight, never asked.
            if tool:sub(1, 7) == "memory_" then
                remember(m.id, tool, args)
            --  Her tasks: a new one is asked (it will act alone later), unless
            --  you gave her free hands (below).
            elseif tool:sub(1, 5) == "task_" and tool ~= "task_schedule" then
                task_do(m.id, tool, args, nil)
            --  Doing one of her tasks on her own: you said she may do all of it.
            elseif running_task and tool ~= "task_schedule" then
                local row = add(3, said(tool, args), looks_only and "" or tostring(args.why or ""), 0)
                perform(m.id, tool, args, row)
            --  Free hands: no card, except for a step that is the final one
            --  (it sends, buys, deletes…): that one is always asked. A task of
            --  her own is kept at once too, and the chat says so.
            elseif looks_only or (fact["chat.free"] == true and args.final ~= true) then
                local line, why = said(tool, args), looks_only and "" or tostring(args.why or "")
                if tool == "task_schedule" then
                    line = string.format(tr("Kept as a task: %s, at %s"), task_days(args.days), tostring(args.time or "?"))
                    why = tostring(args.what or "")
                end
                local row = add(3, line, why, 0)
                perform(m.id, tool, args, row)
            else
                local detail = said(tool, args)
                local body = tostring(args.why or "")
                if tool == "task_schedule" then
                    detail = tr("A task of her own")
                    body = tostring(args.what or "") .. "\n" .. string.format(tr("%s, at %s"), task_days(args.days), tostring(args.time or "?"))
                end
                if tool == "desktop_type" then body = body .. "\n«" .. tostring(args.text or "") .. "»" end
                if tool == "desktop_hotkey" then body = body .. "  (" .. tostring(args.keys or "") .. ")" end
                if tool == "desktop_key" then body = body .. "  (" .. tostring(args.key or "") .. ")" end
                local row = add(4, body, detail, 0)
                asks[m.id] = { row = row, tool = tool, args = args }
                fact["chat.state"] = "awaiting"
                status(tr("Waiting for you"))
                --  Asked while closed: open, so it is seen.
                if fact.chatting ~= true then fact.chatting = true end
            end
        elseif kind == "done" then
            if live then history[#history + 1] = { role = "assistant", text = rows[live].text } end
            ending = { ok = true, said = live and rows[live].text or "" }
            settle("idle")
        elseif kind == "cancelled" then
            ending = { ok = false, said = stopped_by_pill and tr("You stopped her from the monitor.") or tr("Stopped.") }
            add(5, stopped_by_pill and tr("You stopped her from the monitor.") or tr("Stopped."))
            stopped_by_pill = false
            settle("idle")
        elseif kind == "failed" then
            if m.reason == "no_model" or m.reason == "not_started" then
                ending = { ok = false, said = tr("She is not signed in.") }
                add(5, tr("She could not hear it: she is not signed in (Settings › Talking with her)."))
            else
                ending = { ok = false, said = tr("Something went wrong: ") .. tostring(m.reason or "?") }
                add(5, tr("Something went wrong: ") .. tostring(m.reason or "?"))
            end
            settle(usable and "idle" or "offline")
        end
    end
    local function start_worker()
        if worker then return end
        ready = false
        fact["chat.state"] = "starting"
        status(tr("Waking up…"))
        local partial = ""
        local said_why = nil
        local ok, id = pcall(spawn, "agent/sandbox", {}, function(line)
            if line:sub(1, 1) ~= "{" then
                log("chat · " .. line)
                --  The sandbox's own words when something it needs is not
                --  there (bubblewrap, node, her packages): those are shown.
                if line:sub(1, 7) == "marea: " then said_why = line:sub(8) end
                return
            end
            local good, m = pcall(json.decode, line)
            if good and type(m) == "table" then on_event(m) end
        end, function(_, code)
            log("chat · the worker ended", code)
            worker = nil
            ready = false
            if said_why then
                fact["chat.state"] = "offline"
                status(tr("Her engine cannot start: ") .. said_why)
                if #rows > 0 and rows[#rows].kind == 1 then add(5, tr("Her engine cannot start: ") .. said_why) end
                queue = {}
                return
            end
            if fact["chat.state"] ~= "idle" and fact["chat.state"] ~= "offline" then
                ending = { ok = false, said = tr("Her engine stopped.") }
                add(5, tr("Her engine stopped."))
                settle("idle")
            end
        end, { stdin = "open", errors = true })
        if not ok then
            fact["chat.state"] = "offline"
            status(tr("Her engine could not start: ") .. tostring(id))
            return
        end
        worker = id
        local recent = {}
        for k = math.max(1, #history - 40), #history do recent[#recent + 1] = history[k] end
        local line = json.encode({ type = "start", model = chosen(), locale = fact.locale, history = recent, memory = for_her() }) .. "\n"
        write(worker, line)
    end

    -- ── her tasks: what she does on her own, at a time ──
    --  «Every day at 8:00, open my bank in Zen and tell me the balance.» She
    --  keeps them in her folder (tasks.json), you allow each one as it is
    --  made, and Settings › Her tasks lists them. At its time a task runs as
    --  a prompt of its own, in a conversation of its own (the one there was
    --  is kept to look back on), with her hands free: you said she may do all
    --  of it. When it ends a notice says how it went. If it could not run at
    --  its time —the screen locked, the computer off, her account out—, a
    --  notice says why and asks whether to do it now.
    local tasks, task_next = {}, 1
    do
        local ok, saved = pcall(sys.ask, "files.read", "tasks.json", "json")
        if ok and type(saved) == "table" then
            tasks = type(saved.tasks) == "table" and saved.tasks or {}
            task_next = tonumber(saved.next) or (#tasks + 1)
        end
    end
    local task_shelf = {}     -- Settings' rows, in order: the task's id
    local waiting_tasks = {}  -- due while she was busy with you: after
    local today = function() return os.date("%Y-%m-%d") end
    --  When Marea started today: what was due before then, she was not there for.
    local born_day, born_at = today(), (function() local d = os.date("*t"); return d.hour * 60 + d.min end)()
    --  Days by their first three letters, in English or Spanish, with or
    --  without accents (her model may write «lunes, miércoles»).
    local WEEK = { sun = 1, mon = 2, tue = 3, wed = 4, thu = 5, fri = 6, sat = 7,
                   dom = 1, lun = 2, mar = 3, mie = 4, jue = 5, vie = 6, sab = 7 }
    local function day_of(word)
        local w = string.lower(word):gsub("á", "a"):gsub("é", "e"):gsub("í", "i"):gsub("ó", "o"):gsub("ú", "u")
        return WEEK[w:sub(1, 3)]
    end
    local WEEK_NAMES = { "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat" }
    local function minutes_of(hhmm)
        local h, m = tostring(hhmm or ""):match("^(%d%d?):(%d%d)$")
        return h and (tonumber(h) * 60 + tonumber(m)) or nil
    end
    local function due_today(t)
        local d = os.date("*t")
        local days = string.lower(tostring(t.days or "daily"))
        if days == "daily" or days == "" then return true end
        if days == "weekdays" then return d.wday >= 2 and d.wday <= 6 end
        if days == "weekends" then return d.wday == 1 or d.wday == 7 end
        local once = days:match("^once:(%d%d%d%d%-%d%d%-%d%d)$")
        if once then return once == today() end
        for w in days:gmatch("[^%s,;/]+") do
            if day_of(w) == d.wday then return true end
        end
        return false
    end
    task_days = function(days)
        days = string.lower(tostring(days or "daily"))
        if days == "daily" or days == "" then return tr("Every day") end
        if days == "weekdays" then return tr("Weekdays") end
        if days == "weekends" then return tr("Weekends") end
        local once = days:match("^once:(%d%d%d%d%-%d%d%-%d%d)$")
        if once then return once end
        local out = {}
        for w in days:gmatch("[^%s,;/]+") do
            local k = day_of(w)
            if k then out[#out + 1] = tr(WEEK_NAMES[k]) end
        end
        return #out > 0 and table.concat(out, ", ") or days
    end
    local function short(s, n) return first_letters((tostring(s or ""):gsub("%s+", " ")), n or 60) end
    local function show_tasks()
        local out = {}
        task_shelf = {}
        for _, t in ipairs(tasks) do
            local last, state = tr("Not done yet"), 0
            if t.last then
                last = (t.last.ok and tr("Done ") or tr("Not done ")) .. os.date("%d/%m %H:%M", t.last.at or 0) .. (t.last.said ~= "" and (" · " .. short(t.last.said, 80)) or "")
                state = t.last.ok and 1 or 2
            end
            if running_task == t.id then last, state = tr("Doing it now…"), 3 end
            out[#out + 1] = { when = tostring(t.time), days = task_days(t.days), what = short(t.what, 120), last = last, state = state, on = t.on == false and 0 or 1 }
            task_shelf[#task_shelf + 1] = t.id
            if #out >= 12 then break end
        end
        model["tasks.rows"] = out
        local n = 0
        for _, t in ipairs(tasks) do if t.on ~= false then n += 1 end end
        text["tasks.summary"] = n == 0 and tr("None yet") or string.format(tr("%d on"), n)
    end
    table.insert(hooks.language, show_tasks)
    local function keep_tasks()
        pcall(sys.call, "files.write", "tasks.json", { tasks = tasks, next = task_next })
        show_tasks()
    end
    local function task_by_id(id)
        for k, t in ipairs(tasks) do
            if t.id == id then return t, k end
        end
        return nil
    end
    local function notice(title, body, actions, then_)
        local argv = { "-a", "Marea", "-i", "dialog-information" }
        for _, a in ipairs(actions or {}) do argv[#argv + 1] = "--action=" .. a[1] .. "=" .. a[2] end
        argv[#argv + 1] = title
        argv[#argv + 1] = body
        run("notify-send", argv, function(out) if then_ then then_(tostring(out or ""):match("%S+") or "") end end)
    end

    local run_task
    --  It could not be done at its time: you are told why, once that day,
    --  and asked whether she should do it now.
    local function missed(t, why)
        if t.missed == today() then return end
        t.missed = today()
        keep_tasks()
        log("tasks · «" .. short(t.what, 40) .. "» not done at " .. tostring(t.time) .. ": " .. why)
        notice(tr("Marea could not do a task"),
            string.format(tr("«%s», at %s: %s. Shall she do it now?"), short(t.what, 90), tostring(t.time), why),
            { { "now", tr("Do it now") }, { "skip", tr("Leave it") } },
            function(chosen)
                local again = task_by_id(t.id)
                if chosen == "now" and again then run_task(again) end
            end)
    end
    run_task = function(t)
        if running_task then
            waiting_tasks[#waiting_tasks + 1] = t.id
            return
        end
        if fact.locked == true then missed(t, tr("the screen was locked")); return end
        local state = fact["chat.state"]
        if state == "thinking" or state == "acting" or state == "awaiting" or state == "starting" then
            --  Busy with you: when you are done.
            for _, w in ipairs(waiting_tasks) do if w == t.id then return end end
            waiting_tasks[#waiting_tasks + 1] = t.id
            return
        end
        if fact["chat.signed_in"] == false then missed(t, tr("she is not signed in")); return end
        running_task = t.id
        t.last = { day = today(), at = os.time(), ok = false, said = "" }
        keep_tasks()
        log("tasks · doing «" .. short(t.what, 40) .. "»")
        --  A conversation of its own: the one there was, kept to look back on.
        keep_talk()
        rows, history, asks, live = {}, {}, {}, nil
        shown_row, shown = nil, 0
        if worker and ready then send({ type = "reset" }) end
        add(1, tr("Task") .. " · " .. tostring(t.time) .. "\n" .. tostring(t.what))
        history[#history + 1] = { role = "user", text = tostring(t.what) }
        stop_idle()
        start_worker()
        fact["chat.state"] = "thinking"
        status(tr("Doing one of her tasks…"))
        send({ type = "prompt", text = "[Task] " .. tostring(t.what), now = os.date("%Y-%m-%d %H:%M, %A") })
    end
    turn_over = function(how)
        if not running_task then
            --  One that waited for you to finish.
            local id = table.remove(waiting_tasks, 1)
            local t = id and task_by_id(id)
            if t then after(1500, function() run_task(t) end) end
            return
        end
        local t = task_by_id(running_task)
        running_task = nil
        if t then
            t.last = { day = today(), at = os.time(), ok = how.ok == true, said = short(how.said, 300) }
            if tostring(t.days):match("^once:") then t.on = false end
            keep_tasks()
            notice(how.ok and tr("Marea did a task") or tr("Marea could not finish a task"),
                (how.said ~= "" and short(how.said, 220) or short(t.what, 120)),
                { { "open", tr("See it") } },
                function(chosen) if chosen == "open" or chosen == "default" then fact.chatting = true end end)
        end
        local id = table.remove(waiting_tasks, 1)
        local next_t = id and task_by_id(id)
        if next_t then after(1500, function() run_task(next_t) end) end
    end
    --  Every half minute: the ones due now.
    every(30000, function()
        local d = os.date("*t")
        local now = d.hour * 60 + d.min
        for _, t in ipairs(tasks) do
            local at = minutes_of(t.time)
            local done_today = t.last and t.last.day == today()
            if t.on ~= false and at and now >= at and not done_today and t.missed ~= today() and due_today(t) then
                if born_day == today() and at < born_at then
                    missed(t, tr("the computer was off, or Marea was not running"))
                else
                    run_task(t)
                end
            end
        end
    end)

    task_do = function(id, tool, args, row)
        local function done(ok, words)
            if row then finish_row(row, ok) end
            answer(id, ok, words)
        end
        if tool == "task_schedule" then
            local time = tostring(args.time or "")
            local h, m = time:match("^(%d%d?):(%d%d)$")
            if not h or tonumber(h) > 23 or tonumber(m) > 59 then return done(false, "The time must be HH:MM, 24-hour.") end
            local what = first_letters((tostring(args.what or ""):match("^%s*(.-)%s*$")), 1500)
            if what == "" then return done(false, "Say what to do.") end
            local t = { id = "t" .. task_next, what = what, time = string.format("%02d:%02d", tonumber(h), tonumber(m)), days = string.lower(tostring(args.days or "daily")), on = true, made = os.time() }
            task_next += 1
            --  Made for a time already past today: from tomorrow, not now.
            local d = os.date("*t")
            if minutes_of(t.time) <= d.hour * 60 + d.min and not t.days:match("^once:") then t.last = { day = today(), at = 0, ok = true, said = "" } end
            tasks[#tasks + 1] = t
            keep_tasks()
            done(true, string.format("Kept as [%s]: %s at %s.", t.id, task_days(t.days), t.time))
        elseif tool == "task_list" then
            local lines = {}
            for _, t in ipairs(tasks) do
                local last = t.last and (os.date("%Y-%m-%d %H:%M", t.last.at or 0) .. (t.last.ok and " done: " or " not done: ") .. short(t.last.said, 120)) or "never run"
                lines[#lines + 1] = string.format("[%s] %s at %s%s: %s (last: %s)", t.id, tostring(t.days), tostring(t.time), t.on == false and " (paused)" or "", short(t.what, 200), last)
            end
            if row then finish_row(row, true) end
            answer(id, true, #lines > 0 and table.concat(lines, "\n") or "No tasks.")
        elseif tool == "task_cancel" then
            local want = tostring(args.id or ""):gsub("[%[%]%s]", "")
            local t, k = task_by_id(want)
            if not t then return done(false, "There is no task [" .. want .. "].") end
            table.remove(tasks, k)
            keep_tasks()
            if not row then finish_row(add(3, tr("Forgot the task: ") .. short(t.what, 60), "", 0), true) end
            done(true, "Removed.")
        end
    end
    on("task_flip", function(i)
        local t = task_by_id(task_shelf[(tonumber(i) or -1) + 1] or "")
        if not t then return end
        t.on = t.on == false
        keep_tasks()
    end)
    on("task_drop", function(i)
        local _, k = task_by_id(task_shelf[(tonumber(i) or -1) + 1] or "")
        if k then table.remove(tasks, k); keep_tasks() end
    end)
    on("task_now", function(i)
        local t = task_by_id(task_shelf[(tonumber(i) or -1) + 1] or "")
        if t then run_task(t) end
    end)
    on("fact:section", function(v)
        if v == "tasks" then show_tasks() end
    end)
    show_tasks()

    -- ── what the panel asks ──
    on("chat_send", function()
        local words = tostring(text["chat.input"] or "")
        if words:match("^%s*$") then return end
        local state = fact["chat.state"]
        if state == "thinking" or state == "acting" or state == "awaiting" or state == "starting" then return end
        text["chat.input"] = ""
        add(1, words)
        history[#history + 1] = { role = "user", text = words }
        stop_idle()
        start_worker()
        fact["chat.state"] = "thinking"
        status(tr("Thinking…"))
        send({ type = "prompt", text = words, now = os.date("%Y-%m-%d %H:%M, %A") })
    end)
    local function decide(i, yes)
        local first = math.max(1, #rows - ROWS + 1)
        local row = first + (i or 0)
        for id, a in pairs(asks) do
            if a.row == row then
                asks[id] = nil
                if yes then
                    rows[row].state = 3
                    local tool_row = add(3, said(a.tool, a.args), tostring(a.args.why or ""), 0)
                    perform(id, a.tool, a.args, tool_row)
                else
                    rows[row].state = 2
                    paint()
                    answer(id, false, "", { denied = true })
                    fact["chat.state"] = "thinking"
                end
                return
            end
        end
    end
    on("chat_allow", function(i) decide(i, true) end)
    on("chat_deny", function(i) decide(i, false) end)
    on("chat_stop", function()
        for id, a in pairs(asks) do
            asks[id] = nil
            if rows[a.row] then rows[a.row].state = 2 end
        end
        send({ type = "cancel" })
        status(tr("Stopping…"))
        run("pleamar-wm", { "agent", "done" }, function() end, HANDS)
    end)
    on("chat_new", function()
        if worker then write(worker, json.encode({ type = "shutdown" }) .. "\n") end
        keep_talk()
        rows, history, asks, live = {}, {}, {}, nil
        shown_row, shown = nil, 0
        fact["chat.state"] = "idle"
        status("")
        paint()
        save()
    end)
    on("chat", function() paint() end)
    --  Opening the chat wakes her engine: whether she is signed in is known
    --  before the first word, and the first answer comes sooner.
    on("fact:chatting", function(v)
        if v == true and not worker then start_worker(); rest_later() end
    end)
    --  Settings › Talking with her: her engine wakes to say how she is.
    on("fact:section", function(v)
        if v == "talk" and not worker then start_worker(); rest_later() end
    end)
    on("chat_login", function()
        start_worker()
        send({ type = "login", provider = (chosen():match("^([^/]+)/") or "openai-codex") })
    end)
    on("chat_login_cancel", function()
        if worker then write(worker, json.encode({ type = "login_cancel" }) .. "\n") end
        fact["chat.signing"] = false
    end)
    on("chat_pick", function(i)
        local name = models[(tonumber(i) or -1) + 1]
        if not name or name == chosen() then return end
        settings.chat_model = name
        save_settings()
        text["chat.model"] = name
        show_models()
        --  The next word starts her with it (the thread goes along).
        if worker and fact["chat.state"] == "idle" then write(worker, json.encode({ type = "shutdown" }) .. "\n") end
    end)
    paint()
    hooks.chat = function() fact.chatting = true; paint() end
end
