-- Marea's logic, in pieces: her children.
-- marea.luau loads it, and hands it what it uses of its own.
--
--  Drag her onto a window and a drop of her water buds off her and perches there: a child. She
--  can have up to four at once, each on a window of its own, each with its own conversation and
--  its own AI worker (agent/worker.mjs in `kid` mode, one sandboxed Node process each). The main
--  chat (logic/chat.luau, her panel, the whole desktop, builder mode) is another conversation and
--  has nothing to do with them.
--
--  The data model (scene/state/join.plm has the scene's half):
--    kids[k]          k is 0..3, the child's number: the scene's `ch.<k>.…` facts, texts and
--                     properties. nil while the slot is free.
--      .window        { pid, app, title }: the one window it works in
--      .scope         { pid, dialogs }: what it may see and touch (its window and its dialogs)
--      .worker        the process id of its worker, nil while it has none (it sleeps after three
--                     minutes of silence and wakes with its history)
--      .history       what is handed back to a fresh worker: { role, text }
--      .rows          its conversation and what it did, for its panel (scene/draw/kidpanel.plm)
--      .next          what you wrote while it worked: it runs one after another when it has answered
--      .paused .held  a pause holds what it would do next (the proposal or the result of a step)
--      .askfirst      a card for each step that is not only looking, `.asks` the ones that wait for you
--      .watches       what it does again every so many minutes while it lives (memory only: they end with
--                     the child, whatever ends it); .notes_made the notes it made, which only it may replace
--      .cur .slot …   what the follow loop knows of its window
--  Everything the scene sends carries the number (`emit join_send(k)`); everything the workers
--  say stays with the child whose worker said it. A tool that is not for the child's window is
--  refused here, whatever its model asks for.
return function(shared)
    local chat = shared.chat
    local hands = chat.hands
    local HANDS, nice, window_name = hands.HANDS, hands.nice, hands.window_name
    local settings = shared.settings

    local MAX = 4
    local kids = {}
    local nmon = 1
    --  Each child's worker is kept small: a heap of this many MB and a lower priority, so that
    --  four of them never make the desktop wait.
    local WORKER_ENV = { MAREA_AGENT_HEAP = "192", MAREA_AGENT_NICE = "10" }

    local BUSY = { starting = true, thinking = true, acting = true, awaiting = true }
    local function F(k, name, v) fact["ch." .. k .. "." .. name] = v end
    local function T(k, name, v) text["ch." .. k .. "." .. name] = v end

    local function first_letters(s, n)
        local ok, b = pcall(utf8.offset, s, n + 1)
        if ok and b then return s:sub(1, b - 1) end
        return s
    end
    local function letters(s)
        local ok, n = pcall(utf8.len, s)
        return ok and n or #s
    end

    -- ── how many, and who works ──────────────────────────────────────
    local function count()
        local n, working = 0, 0
        for _, kid in pairs(kids) do
            n = n + 1
            if BUSY[kid.state] then working = working + 1 end
        end
        fact["ch.n"] = n
        fact["ch.working"] = working
        return n, working
    end
    --  The window manager's «an agent is using this monitor» ends when nobody works: the main
    --  chat's turn and every child's.
    local function agent_done()
        local _, working = count()
        if working == 0 and not BUSY[fact["chat.state"]] then
            run("pleamar-wm", { "agent", "done" }, function() end, HANDS)
        end
    end

    -- ── what she may touch ───────────────────────────────────────────
    local DESKTOP = { desktop_look = true, desktop_tree = true, desktop_find = true, desktop_press = true, desktop_fill = true, desktop_steps = true, desktop_wait = true, terminal_wait = true, desktop_run = true, desktop_click = true, desktop_type = true, desktop_type_secret = true, desktop_key = true, desktop_hotkey = true, desktop_scroll = true, desktop_drag = true }
    --  Its window's pid is the only one a child touches (and its dialogs'); `desktop_windows` is the
    --  list of just those. Nothing that opens, moves or brings forward: that is the desktop's.
    --  What only a child has, done here and not by the hands (agent/tools.mjs: KID_ONLY_TOOLS): its watches, and
    --  its notes in one folder.
    local OWN = { watch_start = true, watch_list = true, watch_stop = true, notes_write = true, notes_read = true }
    --  A file chooser (save, open, upload) that a program opens is a window of its own, often of another
    --  program (Sonda, a portal's), and the window manager lists it as a dialog of the window only when it
    --  is one: a window that appears while a child works, and looks like one, is adopted as its dialog.
    local CHOOSER_APPS = { ["sonda"] = true, ["xdg-desktop-portal-gtk"] = true, ["xdg-desktop-portal-kde"] = true,
        ["xdg-desktop-portal-gnome"] = true, ["xdg-desktop-portal-hyprland"] = true, ["zenity"] = true, ["kdialog"] = true, ["yad"] = true }
    local CHOOSER_TITLES = { "^save", "^open", "^choose", "^select", "^upload", "^guardar", "^abrir", "^elegir", "^selecci", "^descargar", "^subir", "file chooser" }
    local function is_chooser(w)
        local app = tostring(w.app or ""):lower()
        local title = tostring(w.title or ""):lower()
        if CHOOSER_APPS[app] or title == "sonda" then return true end
        for _, pat in ipairs(CHOOSER_TITLES) do
            if title:find(pat) then return true end
        end
        return false
    end
    local function refuses(kid, tool, args)
        if tool ~= "desktop_windows" and not DESKTOP[tool] and not OWN[tool] then
            return "You are tied to one window (" .. kid.window.app .. "): you do not open programs, move windows or do anything else outside it. Do what is asked inside it."
        end
        if DESKTOP[tool] then
            local base = tostring(args.pid or ""):match("^(%d+)")
            local whole = tostring(args.pid or ""):match("^([%d%.]+)")
            if base ~= kid.window.pid and not kid.scope.dialogs[whole or ""] then
                return "You are tied to window " .. kid.window.pid .. " (" .. kid.window.app .. ") only: you cannot touch another one, not even another child's. Use pid " .. kid.window.pid .. "."
            end
        end
        return nil
    end
    --  What it says it is doing: the one thing it works on, in the words of someone who is doing it.
    local JOINED_WORDS = {
        desktop_look = "Looking at %s…",
        desktop_tree = "Reading %s…",
        desktop_find = "Searching in %s…",
        desktop_press = "Pressing a button in %s…",
        desktop_fill = "Filling in %s…",
        desktop_steps = "Working in %s…",
        desktop_wait = "Waiting for %s…",
        desktop_run = "Running a command in %s…",
        terminal_wait = "Waiting for %s to finish…",
        desktop_click = "Clicking in %s…",
        desktop_type = "Typing in %s…",
        desktop_type_secret = "Typing a saved password in %s…",
        desktop_key = "Pressing keys in %s…",
        desktop_hotkey = "Pressing keys in %s…",
        desktop_scroll = "Scrolling in %s…",
        desktop_drag = "Dragging in %s…",
        watch_start = "Setting up a watch…",
        watch_list = "Looking at its watches…",
        watch_stop = "Stopping a watch…",
        notes_write = "Writing a note…",
        notes_read = "Reading a note…",
    }
    local function program(kid, args)
        if tostring(args.pid or ""):match("^(%d+)") == kid.window.pid then return nice(kid.window.app) end
        return kid.programs[window_name(args.pid)] or ("the window " .. tostring(args.pid or "?"))
    end
    --  What it did, in a line of the activity log (the words of someone telling what they did).
    local function one_line(v, n)
        local w = tostring(v or ""):gsub("%s+", " "):match("^%s*(.-)%s*$")
        if letters(w) > n then w = first_letters(w, n) .. "…" end
        return w
    end
    local function did(kid, tool, args)
        local app = program(kid, args)
        local t = one_line(args.text, 40)
        if tool == "desktop_windows" or tool == "desktop_look" then return string.format(tr("Looked at %s"), app) end
        if tool == "desktop_tree" then return string.format(tr("Read %s"), app) end
        if tool == "desktop_find" then return string.format(tr("Searched «%s» in %s"), t, app) end
        if tool == "desktop_press" then
            if t ~= "" then return string.format(tr("Pressed «%s»"), t) end
            return string.format(tr("Pressed a button in %s"), app)
        end
        if tool == "desktop_fill" or tool == "desktop_type" then
            if t ~= "" then return string.format(tr("Typed «%s»"), t) end
            return string.format(tr("Typed in a field of %s"), app)
        end
        if tool == "desktop_type_secret" then return tr("Typed a saved password") end
        if tool == "desktop_steps" then return string.format(tr("Several steps in %s"), app) end
        if tool == "desktop_wait" or tool == "terminal_wait" then return string.format(tr("Waited for %s"), app) end
        if tool == "desktop_run" then return string.format(tr("Ran a command in %s"), app) end
        if tool == "desktop_click" then return string.format(tr("Clicked in %s"), app) end
        if tool == "desktop_key" then return string.format(tr("Pressed %s"), one_line(args.key, 20)) end
        if tool == "desktop_hotkey" then return string.format(tr("Pressed %s"), one_line(args.keys, 20)) end
        if tool == "desktop_scroll" then return string.format(tr("Scrolled in %s"), app) end
        if tool == "desktop_drag" then return string.format(tr("Dragged in %s"), app) end
        if tool == "watch_start" then return string.format(tr("Set a watch every %d minutes"), math.floor(tonumber(args.every_minutes) or 0)) end
        if tool == "watch_list" then return tr("Looked at its watches") end
        if tool == "watch_stop" then return string.format(tr("Stopped watch %s"), one_line(args.id, 8)) end
        if tool == "notes_write" then return string.format(tr("Wrote the note «%s»"), one_line(args.name, 40)) end
        if tool == "notes_read" then return string.format(tr("Read the note «%s»"), one_line(args.name, 40)) end
        return string.format(tr("Worked in %s"), app)
    end
    --  Tools that only look: never a card, even when it asks before acting.
    local LOOKS = { desktop_windows = true, desktop_look = true, desktop_tree = true, desktop_find = true, desktop_wait = true, terminal_wait = true, watch_list = true, notes_read = true }
    local function said(kid, tool, args)
        if tool == "desktop_windows" then return tr("Looking at the window…") end
        if OWN[tool] then return tr(JOINED_WORDS[tool]) end
        return string.format(tr(JOINED_WORDS[tool] or "Working in %s…"), program(kid, args))
    end

    -- ── the worker of a child ────────────────────────────────────────
    local leave   -- let go of a child (below)
    local relabel -- what its tab says (below)
    local function set_state(kid, st)
        kid.state = st
        F(kid.k, "state", st)
        count()
        relabel(kid)
    end
    --  Its panel (one at a time, `kp.k` says whose) shows its title and status too.
    local function panel_of(kid) return tonumber(fact["kp.k"]) == kid.k end
    local function status(kid, words)
        T(kid.k, "status", words or "")
        if panel_of(kid) then text["kp.status"] = words or "" end
    end

    --  What its tab says: the program, and while a task runs the first words of it.
    relabel = function(kid)
        local name = nice(kid.window.app)
        local task = kid.task and tostring(kid.task):gsub("%s+", " "):match("^%s*(.-)%s*$") or ""
        if task ~= "" and BUSY[kid.state] then name = name .. " · " .. first_letters(task, 22) .. (letters(task) > 22 and "…" or "") end
        if kid.watch_tag then name = name .. "  " .. kid.watch_tag end
        T(kid.k, "label", name)
        if panel_of(kid) then text["kp.title"] = name end
    end

    -- ── what it says, let out at a reading pace ──────────────────────
    --  The model hands its words over in a few seconds; they are shown at a pace that can be read
    --  (hurrying when far behind), as the main chat does, in the child's answer: the scene gets the part
    --  that has come (`said`) and how many letters it is (`letters`, for the ones that rise out of the
    --  water). The whole text is kept, up to a limit that no answer reaches.
    local paint_panel   -- the panel's thread (below)
    local SHOW_MAX = 20000
    local TAIL = 12
    local revealing = false
    local function reveal_step()
        local again = false
        for _, kid in pairs(kids) do
            local seg = kid.seg
            if seg and kid.shown then
                local total = letters(seg)
                if kid.shown < total + TAIL then
                    kid.shown = kid.shown + math.max(2, math.min(40, math.floor((total - kid.shown) / 10)))
                    T(kid.k, "said", kid.shown >= total and seg or first_letters(seg, kid.shown))
                    F(kid.k, "letters", kid.shown)
                    paint_panel(kid)
                    again = true
                end
            end
        end
        if again then after(33, reveal_step) else revealing = false end
    end
    local function reveal()
        if revealing then return end
        revealing = true
        after(33, reveal_step)
    end
    --  A new text for the answer: it starts at its beginning.
    local function say(kid, words, restart)
        kid.seg = first_letters(words, SHOW_MAX)
        if restart or not kid.shown then kid.shown = 0; F(kid.k, "letters", 0); T(kid.k, "said", "") end
        F(kid.k, "said_on", true)
        reveal()
    end
    --  No answer on show.
    local function unsay(kid)
        kid.seg, kid.shown = nil, nil
        T(kid.k, "said", "")
        F(kid.k, "said_on", false)
        F(kid.k, "letters", 0)
    end

    -- ── its conversation, for its panel ──────────────────────────────
    --  What was said and done, as the main chat shows its thread: 1 you, 2 the child, 3 something it did
    --  (state 0 going, 1 done, 2 failed, 3 denied, 4 held by a pause), 4 a card that asks you, 5 a note.
    --  Kept for the child's life (the last ROWS_MAX); the panel is painted with the last PANEL_ROWS.
    local ROWS_MAX, PANEL_ROWS = 80, 40
    local function add_row(kid, kind, words, detail, state)
        local r = { kind = kind, text = words or "", detail = detail or "", state = state or 0 }
        kid.rows[#kid.rows + 1] = r
        if #kid.rows > ROWS_MAX then table.remove(kid.rows, 1) end
        return r
    end
    paint_panel = function(kid)
        if not panel_of(kid) or kid.painting then return end
        kid.painting = true
        after(16, function()
            kid.painting = false
            if not panel_of(kid) or kids[kid.k] ~= kid then return end
            local first = math.max(1, #kid.rows - PANEL_ROWS + 1)
            kid.first = first
            local out = {}
            for i = first, #kid.rows do
                local r = kid.rows[i]
                local words = r.text
                if r == kid.live_row and kid.shown then words = first_letters(words, kid.shown) end
                out[#out + 1] = { kind = r.kind, text = words, detail = r.detail, state = r.state }
            end
            model["kp.rows"] = out
        end)
    end
    --  What waits to be run after the current task, and the cards that ask you.
    local function sync_queue(kid)
        F(kid.k, "q", #kid.next)
        for i = 0, 2 do
            local w = kid.next[i + 1]
            T(kid.k, "n." .. i, w and first_letters((tostring(w):gsub("%s+", " ")), 60) or "")
        end
    end
    local function sync_cards(kid)
        local n = 0
        local first
        for _, a in ipairs(kid.ask_order) do
            if kid.asks[a] then n = n + 1; first = first or kid.asks[a] end
        end
        F(kid.k, "cards", n)
        T(kid.k, "card", first and first.row.detail or "")
        T(kid.k, "cardbody", first and first.row.text or "")
    end

    local function send(kid, m)
        local line = json.encode(m) .. "\n"
        if kid.worker and kid.ready then
            if not write(kid.worker, line) then log("kids · the worker of child " .. kid.k .. " did not hear") end
        else
            kid.queue[#kid.queue + 1] = line
        end
    end
    local function answer(kid, id, ok, words, extra)
        local m = { type = "result", id = id, ok = ok, text = words or "" }
        if kid.notice then
            m.text = tostring(m.text) .. "\n\n[Marea: " .. kid.notice .. "]"
            kid.notice = nil
        end
        if extra then for k, v in pairs(extra) do m[k] = v end end
        send(kid, m)
    end
    --  A worker that has nothing to do for three minutes goes (a hundred MB of Node); the next
    --  message starts it again with the child's history.
    local function rest_later(kid)
        if kid.idle_timer then cancel(kid.idle_timer) end
        kid.idle_timer = after(3 * 60 * 1000, function()
            kid.idle_timer = nil
            if kid.worker and (kid.state == "idle" or kid.state == "offline") then
                write(kid.worker, json.encode({ type = "shutdown" }) .. "\n")
            end
        end)
    end
    local ask   -- (below)
    local watches_end, watch_finish, own_exec   -- its watches and its notes (below)
    local function notify(kid, words)
        run("notify-send", { "-a", "Marea", "-i", "dialog-information", string.format(tr("%s: done"), nice(kid.window.app)), one_line(words, 140) }, function() end)
    end
    local function settle(kid, st)
        set_state(kid, st or "idle")
        status(kid, "")
        kid.live, kid.live_row = nil, nil
        kid.held, kid.paused = {}, false
        F(kid.k, "paused", false)
        for id, a in pairs(kid.asks) do a.row.state = 2; kid.asks[id] = nil end
        kid.ask_order = {}
        sync_cards(kid)
        agent_done()
        rest_later(kid)
        local how = kid.ending or { ok = false, said = "" }
        kid.ending = nil
        --  A run of a watch (nobody is looking): its summary goes to the activity log, not to the answer's drop.
        if kid.watch_run then
            local w = kid.watch_run
            kid.watch_run, kid.task = nil, nil
            F(kid.k, "wrun", false)
            relabel(kid)
            watch_finish(kid, w, how)
            paint_panel(kid)
            if how.ok and #kid.next > 0 then
                local nxt = table.remove(kid.next, 1)
                sync_queue(kid)
                after(400, function()
                    if kids[kid.k] == kid and not BUSY[kid.state] then ask(kid, nxt) end
                end)
            end
            return
        end
        --  What it says goes where the user is looking: under its box (what streamed in already is there;
        --  a failure's words, not streamed, are put there now).
        local words = tostring(how.said or "")
        if words ~= "" and words ~= kid.seg then say(kid, words, true) end
        --  An answer that came while the bubble was minimised or the box put away: the chip says so.
        local away = fact["ch." .. kid.k .. ".min"] == true or fact["ch." .. kid.k .. ".shut"] == true
        if words ~= "" and away then F(kid.k, "new", true) end
        paint_panel(kid)
        --  What waited in line goes next (only after an answer: a stopped or failed task does not carry
        --  on to the next); and when all is done and nobody is looking at it, a word on the desktop.
        if how.ok and #kid.next > 0 then
            local nxt = table.remove(kid.next, 1)
            sync_queue(kid)
            after(400, function()
                if kids[kid.k] == kid and not BUSY[kid.state] then ask(kid, nxt) end
            end)
        elseif how.ok and words ~= "" and (away or fact["ch." .. kid.k .. ".hidden"] == true) then
            notify(kid, words)
        end
    end

    --  A pause: what it would do next waits (a proposal is not answered, the result of a step is not
    --  handed back) until it is resumed.
    local function hold_or(kid, fn)
        if kid.paused then
            kid.held[#kid.held + 1] = fn
            status(kid, tr("Paused"))
        else
            fn()
        end
    end
    local function set_paused(kid, on)
        if (kid.paused == true) == on then return end
        if on and not BUSY[kid.state] then return end
        kid.paused = on
        F(kid.k, "paused", on)
        if on then
            status(kid, tr("Paused"))
        else
            status(kid, kid.state == "idle" and "" or tr("Thinking…"))
            local list = kid.held
            kid.held = {}
            for _, fn in ipairs(list) do fn() end
        end
    end

    --  The tool it proposed: free hands in its window (or, when it is asked to ask first, once you
    --  allowed it).
    local function perform(kid, id, tool, args, row)
        kid.last_tool = os.time()
        row.state = 0
        paint_panel(kid)
        set_state(kid, "acting")
        status(kid, said(kid, tool, args))
        local exec = function(done)
            if OWN[tool] then
                own_exec(kid, tool, args, done)
                return
            end
            hands.exec(tool, args, {
                scope = kid.scope,
                programs = kid.programs,
                name = function(a) return program(kid, a) end,
                prefix = "kid" .. kid.k .. "-look",
                secret = function(a, done2) chat.type_secret(a, done2) end,
            }, done)
        end
        exec(function(ok, words, extra, flags)
            if kids[kid.k] ~= kid then return end
            row.state = ok and 1 or 2
            if not ok then row.detail = one_line(words, 70) end
            paint_panel(kid)
            hold_or(kid, function()
                answer(kid, id, ok, words, extra)
                if kid.state == "acting" then set_state(kid, "thinking") end
                status(kid, kid.state == "thinking" and tr("Thinking…") or "")
            end)
            --  Stopped from the monitor's pill: the whole turn ends, not only this step.
            if flags and flags.stopped then
                kid.stopped_by_pill = true
                send(kid, { type = "cancel" })
            end
            --  Its window closed: nothing to hold on to any more.
            if flags and flags.gone then
                --  Said by a tool: it may only be that the program has several windows now (the list
                --  names them PID.N) or a dialog; the window is let go only if no window of that
                --  program is left in the list.
                run("pleamar-wm", { "agent", "windows" }, function(out, code)
                    if kids[kid.k] ~= kid then return end
                    local base = tostring(kid.window.pid):match("^%d+")
                    local there = false
                    if code == 0 then
                        for line in tostring(out):gmatch("[^\n]+") do
                            local p = line:match("^%s*([%d%.]+)%s")
                            if p and p:match("^%d+") == base then there = true end
                        end
                    end
                    if code == 0 and not there then
                        leave(kid.k, string.format(tr("%s closed: I let go of it."), kid.window.app))
                    end
                end, HANDS)
            end
        end)
    end

    --  A card for a step that is not only looking (when it asks first): what it would do, with its words.
    local function card_body(tool, args)
        local body = tostring(args.why or "")
        if tool == "desktop_type" or tool == "desktop_fill" then body = body .. "\n«" .. tostring(args.text or "") .. "»" end
        if tool == "desktop_run" then body = body .. "\n" .. tostring(args.command or "") end
        if tool == "desktop_steps" and type(args.steps) == "table" then body = body .. "\n" .. table.concat(args.steps, "\n") end
        if tool == "desktop_hotkey" then body = body .. "  (" .. tostring(args.keys or "") .. ")" end
        if tool == "desktop_key" then body = body .. "  (" .. tostring(args.key or "") .. ")" end
        if tool == "watch_start" then body = body .. "\n" .. tostring(args.every_minutes or "?") .. " min: " .. tostring(args.what or "") end
        if tool == "notes_write" then body = body .. "\n" .. tostring(args.name or "") .. " (" .. tostring(args.mode or "append") .. ")" end
        return (body:gsub("^%s+", ""))
    end
    local function decide(kid, id, yes)
        local a = kid.asks[id]
        if not a then return end
        kid.asks[id] = nil
        sync_cards(kid)
        if yes then
            a.row.state = 3
            local row = add_row(kid, 3, did(kid, a.tool, a.args), tostring(a.args.why or ""), 0)
            perform(kid, id, a.tool, a.args, row)
        else
            a.row.state = 2
            paint_panel(kid)
            answer(kid, id, false, "", { denied = true })
            set_state(kid, "thinking")
        end
        if next(kid.asks) ~= nil then
            set_state(kid, "awaiting")
            status(kid, tr("Waiting for you"))
        end
    end
    local function first_ask(kid)
        for _, id in ipairs(kid.ask_order) do
            if kid.asks[id] then return id end
        end
    end

    local function on_event(kid, m)
        local kind = m.type
        if kind == "ready" then
            kid.ready = true
            kid.retried = false
            log("kids · the worker of child " .. kid.k .. " is ready", tostring(m.usable))
            kid.usable = m.usable == true
            if m.usable then
                if kid.state == "offline" or kid.state == "starting" then
                    set_state(kid, "idle")
                    status(kid, "")
                end
            else
                set_state(kid, "offline")
                status(kid, m.reason == "signed_out" and tr("She is not signed in.") or tr("That model cannot be used with her account: choose another in Settings"))
                watches_end(kid, tr("It cannot work"))
            end
            for _, line in ipairs(kid.queue) do write(kid.worker, line) end
            kid.queue = {}
        elseif kind == "delta" then
            if kid.live == nil then
                kid.live = ""
                set_state(kid, "thinking")
                status(kid, tr("Thinking…"))
                --  A new piece of its words: the bubble starts it over, at its top, following it.
                if not kid.watch_run then
                    kid.seg, kid.shown = "", 0
                    kid.live_row = add_row(kid, 2, "")
                end
            end
            kid.live = kid.live .. (m.text or "")
            if kid.watch_run then
                --  A watch run does not pop the answer open: its words are a line of the log.
                if kid.watch_row then kid.watch_row.text = string.format(tr("Watch %d: "), kid.watch_run.id) .. one_line(kid.live, 120) end
                paint_panel(kid)
            else
                if kid.live_row then kid.live_row.text = kid.live end
                say(kid, kid.live, false)
            end
        elseif kind == "propose" then
            kid.live, kid.live_row = nil, nil
            local tool, args = tostring(m.tool), (type(m.args) == "table" and m.args or {})
            local refused = refuses(kid, tool, args)
            if refused then
                add_row(kid, 3, did(kid, tool, args), one_line(refused, 70), 2)
                paint_panel(kid)
                answer(kid, m.id, false, refused)
            else
                local why = LOOKS[tool] and "" or tostring(args.why or "")
                local row = add_row(kid, 3, did(kid, tool, args), why, kid.paused and 4 or 0)
                paint_panel(kid)
                hold_or(kid, function()
                    if kid.askfirst and not LOOKS[tool] then
                        --  It asks first: a card with the step, and it waits for you.
                        row.kind, row.state, row.text, row.detail = 4, 0, card_body(tool, args), did(kid, tool, args)
                        kid.asks[m.id] = { row = row, tool = tool, args = args }
                        kid.ask_order[#kid.ask_order + 1] = m.id
                        set_state(kid, "awaiting")
                        status(kid, tr("Waiting for you"))
                        sync_cards(kid)
                        paint_panel(kid)
                    else
                        perform(kid, m.id, tool, args, row)
                    end
                end)
            end
        elseif kind == "done" then
            if kid.live and kid.live ~= "" then kid.history[#kid.history + 1] = { role = "assistant", text = kid.live } end
            kid.ending = { ok = true, said = kid.live or "" }
            settle(kid, "idle")
        elseif kind == "cancelled" then
            --  Stopped by the user: nothing to say about it (a bubble for «Stopped.» was a big box for a
            --  word he knows).
            kid.ending = { ok = false, said = "" }
            add_row(kid, 5, kid.stopped_by_pill and tr("You stopped it from the monitor.") or tr("Stopped."))
            kid.stopped_by_pill = false
            settle(kid, "idle")
        elseif kind == "failed" then
            if m.reason == "no_model" or m.reason == "not_started" then
                kid.ending = { ok = false, said = tr("She is not signed in.") }
            else
                kid.ending = { ok = false, said = tr("Something went wrong: ") .. tostring(m.reason or "?") }
            end
            add_row(kid, 5, kid.ending.said)
            settle(kid, kid.usable and "idle" or "offline")
        end
    end

    local start_worker
    function start_worker(kid)
        if kid.worker then return end
        kid.ready = false
        set_state(kid, "starting")
        status(kid, tr("Waking up…"))
        local said_why = nil
        local mine = {}
        local ok, id = pcall(spawn, "agent/sandbox", {}, function(line)
            if line:sub(1, 1) ~= "{" then
                log("kids · " .. kid.k .. " · " .. line)
                if line:sub(1, 7) == "marea: " then said_why = line:sub(8) end
                return
            end
            local good, m = pcall(json.decode, line)
            if good and type(m) == "table" and kids[kid.k] == kid then on_event(kid, m) end
        end, function(_, code)
            log("kids · the worker of child " .. kid.k .. " ended", code)
            if kid.worker == mine.id then kid.worker, kid.ready = nil, false end
            --  One we let go of to start another (it never said it was ready): nothing to say about it.
            if mine.retired then return end
            if kids[kid.k] ~= kid then return end
            if said_why then
                set_state(kid, "offline")
                status(kid, tr("Her engine cannot start: ") .. said_why)
                kid.queue = {}
                watches_end(kid, tr("Its engine cannot start"))
                return
            end
            if kid.state ~= "idle" and kid.state ~= "offline" then
                kid.ending = { ok = false, said = tr("Her engine stopped.") }
                settle(kid, "idle")
            end
        end, { stdin = "open", errors = true, env = WORKER_ENV })
        if not ok then
            set_state(kid, "offline")
            status(kid, tr("Her engine could not start: ") .. tostring(id))
            return
        end
        mine.id = id
        kid.worker = id
        local recent = {}
        for i = math.max(1, #kid.history - 40), #kid.history do recent[#recent + 1] = kid.history[i] end
        local model = type(settings.chat_model) == "string" and settings.chat_model or "openai-codex/gpt-5.6-luna"
        write(id, json.encode({ type = "start", mode = "kid", model = model, locale = fact.locale, history = recent, memory = { secrets = chat.secrets() } }) .. "\n")
        --  A worker that never says it is ready does not leave the child «thinking» for good (the state is
        --  «thinking», not «starting», as soon as it is asked something): after 25 s it is started again,
        --  once, with what was asked kept; and if that one does not answer either, the child says so.
        after(25000, function()
            if kids[kid.k] == kid and kid.worker == id and not kid.ready then
                log("kids · the worker of child " .. kid.k .. " did not say it was ready in 25 s")
                if not kid.retried then
                    kid.retried = true
                    mine.retired = true
                    kid.worker = nil
                    kill(id)
                    start_worker(kid)
                else
                    set_state(kid, "offline")
                    status(kid, tr("Her engine cannot start: ") .. "…")
                    kid.queue = {}
                end
            end
        end)
    end

    ask = function(kid, words)
        if BUSY[kid.state] then return end
        unsay(kid)
        kid.task = words
        add_row(kid, 1, words)
        paint_panel(kid)
        kid.history[#kid.history + 1] = { role = "user", text = words }
        if kid.idle_timer then cancel(kid.idle_timer); kid.idle_timer = nil end
        start_worker(kid)
        set_state(kid, "thinking")
        status(kid, tr("Thinking…"))
        send(kid, { type = "prompt", text = words, now = os.date("%Y-%m-%d %H:%M, %A"), free = true,
                    joined = { pid = kid.window.pid, app = kid.window.app, title = kid.window.title },
                    secrets = chat.secrets() })
    end

    -- ── its notes ────────────────────────────────────────────────────
    --  What a child finds it keeps in files: ONE folder, Documents/Marea (`xdg-user-dir DOCUMENTS`, or
    --  ~/Documents), and nothing outside it. The words go through here, host-side: the worker only proposes
    --  `notes_write`; its sandbox has no folder of the user's. The name is cleaned to letters, digits,
    --  spaces, dots and dashes (.md or .txt), never a path; 64 KB a write and 2 MB a file; `replace` only
    --  overwrites a file this child made in its life (a set of names it keeps), `append` adds a dated
    --  section to any file of the folder; a symbolic link is never written through. It is written with
    --  the `sh` Marea already may run (`cat >> "$1"`, the path an argument, the words on its input): no
    --  new permission.
    local NOTE_WRITE, NOTE_FILE, NOTE_READ = 65536, 2 * 1024 * 1024, 20000
    local notes = { dir = nil, waiting = nil }
    local function with_notes_dir(done)
        if notes.dir then done(notes.dir) return end
        if notes.waiting then notes.waiting[#notes.waiting + 1] = done return end
        notes.waiting = { done }
        local function finish(dir)
            local list = notes.waiting
            notes.waiting = nil
            notes.dir = dir
            for _, f in ipairs(list) do f(dir) end
        end
        run("xdg-user-dir", { "DOCUMENTS" }, function(out, code)
            local docs = code == 0 and tostring(out):match("^%s*(.-)%s*$") or ""
            if docs == "" or docs == shared.home_dir then docs = shared.home_dir .. "/Documents" end
            local dir = docs .. "/Marea"
            run("mkdir", { "-p", dir }, function(_, c2)
                finish(c2 == 0 and dir or nil)
            end, { errors = false })
        end, { errors = false })
    end
    local function note_name(raw, kid)
        local n = tostring(raw or "")
        n = n:gsub("[/\\]", " "):gsub("[^%w ._%-]", ""):gsub("%s+", " ")
        n = n:gsub("^[%s%.]+", ""):gsub("%s+$", "")
        local ext = n:lower():match("%.(%w+)$")
        if ext == "md" or ext == "txt" then n = n:sub(1, #n - #ext - 1) else ext = "md" end
        n = n:gsub("[%s%.]+$", "")
        if n == "" then n = nice(kid.window.app):lower() .. "-notes" end
        return n:sub(1, 56) .. "." .. ext
    end
    local function not_a_link(path, ok_cb, fail_cb)
        run("test", { "-L", path }, function(_, code)
            if code == 0 then fail_cb() else ok_cb() end
        end, { errors = false })
    end
    local function notes_exec(kid, tool, args, done)
        with_notes_dir(function(dir)
            if not dir then done(false, "The notes folder (Documents/Marea) cannot be made.") return end
            local name = note_name(args.name, kid)
            local path = dir .. "/" .. name
            if tool == "notes_read" then
                not_a_link(path, function()
                    run("sh", { "-c", 'head -c ' .. NOTE_READ .. ' -- "$1"', "sh", path }, function(out, code)
                        if code ~= 0 then done(false, "There is no note called " .. name .. " in Documents/Marea.") return end
                        done(true, tostring(out))
                    end, { errors = false })
                end, function() done(false, "That note is a link: it is not read.") end)
                return
            end
            local words = tostring(args.text or "")
            if words == "" then done(false, "There is nothing to write.") return end
            if #words > NOTE_WRITE then done(false, "Too long: 64 KB at a time at most.") return end
            local replace = args.mode == "replace"
            not_a_link(path, function()
                run("sh", { "-c", 'if [ -f "$1" ]; then wc -c < "$1"; else echo -1; fi', "sh", path }, function(out)
                    local size = tonumber(tostring(out):match("-?%d+")) or -1
                    local exists = size >= 0
                    if replace and exists and not kid.notes_made[name] then
                        done(false, name .. " was not made by you in this life: replace only works on your own notes; use mode append, or another name.")
                        return
                    end
                    if not replace and exists and size + #words > NOTE_FILE then
                        done(false, name .. " is full (2 MB): write to another note.")
                        return
                    end
                    local payload, script
                    if replace then
                        payload = words:sub(-1) == "\n" and words or (words .. "\n")
                        script = 'cat > "$1"'
                    else
                        payload = ((exists and size > 0) and "\n" or "") .. "## " .. os.date("%Y-%m-%d %H:%M") .. " · " .. nice(kid.window.app) .. "\n\n" .. words .. "\n"
                        script = 'cat >> "$1"'
                    end
                    run("sh", { "-c", script, "sh", path }, function(_, code)
                        if code ~= 0 then done(false, "Writing " .. name .. " failed.") return end
                        kid.notes_made[name] = true
                        kid.wrote = true
                        done(true, "Saved in " .. path .. " (" .. #payload .. " bytes " .. (replace and "written" or "added") .. "). Tell the user where.")
                    end, { errors = true, input = payload })
                end, { errors = false })
            end, function() done(false, name .. " is a link: it is not written through.") end)
        end)
    end

    -- ── its watches ──────────────────────────────────────────────────
    --  «Check this page every 10 minutes and note what is new.» A watch is the child's own and lives as long
    --  as the child does: it is a chain of timers in this process, a generation token on each, and nothing
    --  else. It is not saved, it is not a cron job or a systemd timer, it is not one of her tasks (those are
    --  in memory.json, and are not for children): when the child is let go, its window closes, its engine
    --  cannot work or Marea restarts, every watch is gone and stays gone. Up to three for each child, at most
    --  one run at a time (a tick that finds the child busy, or its window not shown, is skipped and the
    --  log says so), and each ends by itself after twelve hours.
    --  For tests only: MAREA_WATCH_UNIT_MS makes a «minute» that many milliseconds (default 60000) and
    --  MAREA_WATCH_EXPIRE_MS the twelve hours (default 43200000).
    local function env_number(name, default)
        local ok, v = pcall(sys.ask, "env", name)
        return ok and tonumber(v) or default
    end
    local WATCH_UNIT = env_number("MAREA_WATCH_UNIT_MS", 60000)
    local WATCH_EXPIRE = env_number("MAREA_WATCH_EXPIRE_MS", 12 * 3600 * 1000)
    local WATCH_MAX = 3
    local function every_words(m) return m % 60 == 0 and (m // 60) .. "h" or m .. "m" end
    local function clock(t) return os.date("%H:%M", t) end
    --  What the panel lists, and what the tab says («↻10m»).
    local function sync_watches(kid)
        local out, tag = {}, nil
        for _, id in ipairs(kid.watch_order) do
            local w = kid.watches[id]
            out[#out + 1] = { text = string.format(tr("Watch %d · every %s · next %s · ran %d"), w.id, every_words(w.every), clock(w.next_at), w.n), what = one_line(w.what, 70) }
            tag = (tag and "↻×" .. #kid.watch_order) or ("↻" .. every_words(w.every))
        end
        kid.watch_tag = tag
        F(kid.k, "wn", #out)
        if panel_of(kid) then model["kp.watches"] = out end
        relabel(kid)
    end
    local function watch_stop_one(kid, id)
        local w = kid.watches[id]
        if not w then return false end
        w.gen = w.gen + 1
        if w.timer then cancel(w.timer); w.timer = nil end
        kid.watches[id] = nil
        for i, v in ipairs(kid.watch_order) do
            if v == id then table.remove(kid.watch_order, i) break end
        end
        sync_watches(kid)
        return true
    end
    watches_end = function(kid, why)
        local any = #kid.watch_order > 0
        for _, id in ipairs({ table.unpack(kid.watch_order) }) do watch_stop_one(kid, id) end
        if any and why and kids[kid.k] == kid then
            add_row(kid, 5, string.format(tr("Its watches ended: %s."), why))
            paint_panel(kid)
        end
    end
    local function watch_prompt(kid, w)
        return string.format("[Watch %d, run %d] Nobody is looking: this is your watch %d, which the user asked you to keep every %d minutes. Do it now in your window, with free hands: %s\n\nCompare with what you noticed in the earlier runs (you keep your conversation). Write with notes_write only if there is something new. End with ONE short line and nothing after it: exactly NOTHING NEW if nothing is new; otherwise NEW: and what was new and where you wrote it.",
            w.id, w.n, w.id, w.every, w.what)
    end
    local watch_arm
    local function watch_skip(kid, w, why)
        add_row(kid, 3, string.format(tr("Watch %d: skipped, %s"), w.id, why), "", 3)
        paint_panel(kid)
    end
    local function watch_tick(kid, w)
        if os.time() >= w.expires then
            watch_stop_one(kid, w.id)
            add_row(kid, 5, string.format(tr("Watch %d ended: twelve hours are over."), w.id))
            paint_panel(kid)
            run("notify-send", { "-a", "Marea", "-i", "dialog-information", nice(kid.window.app) .. ": " .. string.format(tr("watch %d ended"), w.id), one_line(w.what, 100) }, function() end)
            return
        end
        watch_arm(kid, w)
        if kid.watch_run or BUSY[kid.state] then watch_skip(kid, w, tr("busy")) return end
        if fact["ch." .. kid.k .. ".hidden"] == true then watch_skip(kid, w, tr("its window is not shown")) return end
        if kid.state == "offline" then watch_skip(kid, w, tr("offline")) return end
        w.n = w.n + 1
        kid.watch_run, kid.wrote = w, false
        kid.task = string.format(tr("Watch %d"), w.id)
        F(kid.k, "wrun", true)
        kid.watch_row = add_row(kid, 3, string.format(tr("Watch %d: checking…"), w.id), "", 0)
        local words = watch_prompt(kid, w)
        kid.history[#kid.history + 1] = { role = "user", text = words }
        start_worker(kid)
        set_state(kid, "thinking")
        status(kid, string.format(tr("Watch %d: checking…"), w.id))
        sync_watches(kid)
        send(kid, { type = "prompt", text = words, now = os.date("%Y-%m-%d %H:%M, %A"), free = true,
                    joined = { pid = kid.window.pid, app = kid.window.app, title = kid.window.title },
                    secrets = chat.secrets() })
    end
    watch_arm = function(kid, w)
        w.next_at = os.time() + math.floor(w.every * WATCH_UNIT / 1000)
        local gen = w.gen
        w.timer = after(w.every * WATCH_UNIT, function()
            if kids[kid.k] ~= kid or kid.watches[w.id] ~= w or w.gen ~= gen then return end
            watch_tick(kid, w)
        end)
        sync_watches(kid)
    end
    --  A run is over: its last line says whether there was news. News (a line that starts with NEW, or a
    --  note written) makes the chip beat if the answer is put away, and a word on the desktop; nothing
    --  new is a line in the log and nothing else.
    watch_finish = function(kid, w, how)
        local row = kid.watch_row
        kid.watch_row = nil
        local last = ""
        for line in tostring(how.said or ""):gmatch("[^\n]+") do
            if line:match("%S") then last = line end
        end
        last = last:gsub("^%s+", ""):gsub("%s+$", "")
        local news = last:upper():match("^%**NEW[:%s]") ~= nil or (kid.wrote and not last:upper():match("^%**NOTHING NEW"))
        local shown = last:gsub("^%**NEW:%**%s*", ""):gsub("^%**NOTHING NEW%**", tr("nothing new"))
        local line = string.format(tr("Watch %d: "), w.id) .. one_line(how.ok and shown ~= "" and shown or (how.said ~= "" and how.said or tr("did not finish")), 120)
        if row then
            row.text, row.state = line, how.ok and 1 or 2
        else
            add_row(kid, 3, line, "", how.ok and 1 or 2)
        end
        kid.wrote = false
        if how.ok and news then
            if fact["ch." .. kid.k .. ".min"] == true or fact["ch." .. kid.k .. ".shut"] == true then F(kid.k, "new", true) end
            run("notify-send", { "-a", "Marea", "-i", "dialog-information", nice(kid.window.app) .. ": " .. tr("news"), one_line(shown, 140) }, function() end)
        end
        sync_watches(kid)
    end
    own_exec = function(kid, tool, args, done)
        if tool == "notes_write" or tool == "notes_read" then notes_exec(kid, tool, args, done) return end
        if tool == "watch_list" then
            if #kid.watch_order == 0 then done(true, "You have no watches.") return end
            local lines = {}
            for _, id in ipairs(kid.watch_order) do
                local w = kid.watches[id]
                lines[#lines + 1] = string.format("%d: every %d min, ran %d times, next at %s, ends at %s: %s", w.id, w.every, w.n, clock(w.next_at), clock(w.expires), one_line(w.what, 200))
            end
            done(true, table.concat(lines, "\n"))
            return
        end
        if tool == "watch_stop" then
            local id = tostring(args.id or ""):match("%d+")
            if id and watch_stop_one(kid, tonumber(id)) then done(true, "Watch " .. id .. " stopped.") else done(false, "You have no watch " .. tostring(args.id) .. ".") end
            return
        end
        --  watch_start
        local every = math.floor(tonumber(args.every_minutes) or 0)
        local what = tostring(args.what or ""):match("^%s*(.-)%s*$")
        if every < 1 or every > 1440 then done(false, "every_minutes has to be from 1 to 1440.") return end
        if what == "" then done(false, "A watch needs `what`: the instruction for each run.") return end
        if #kid.watch_order >= WATCH_MAX then done(false, "You already have " .. WATCH_MAX .. " watches: stop one first (watch_stop).") return end
        kid.watch_seq = (kid.watch_seq or 0) + 1
        local w = { id = kid.watch_seq, every = every, what = what:sub(1, 1500), why = tostring(args.why or ""), n = 0, gen = 1, expires = os.time() + math.floor(WATCH_EXPIRE / 1000) }
        kid.watches[w.id] = w
        kid.watch_order[#kid.watch_order + 1] = w.id
        watch_arm(kid, w)
        done(true, string.format("Watch %d set: every %d minutes, first run at %s. It lives only as long as you do: if the user lets you go, closes the window or restarts Marea it is gone, and it ends by itself at %s. Tell the user what you set up, how often and where you will write.", w.id, every, clock(w.next_at), clock(w.expires)))
    end

    -- ── windows and monitors ─────────────────────────────────────────
    --  Where the windows and the monitors are, as pleamar-wm's `agent` says it: the perch
    --  (scene/surfaces/join.plm) draws in desktop pixels.
    local function parse_windows(out)
        local list = {}
        for line in tostring(out):gmatch("[^\n]+") do
            local pid, app, title, w, h, x, y = line:match("^%s*([%d%.]+)%s+(%S+)%s+«(.-)»%s+(%d+)x(%d+) at (-?%d+),(-?%d+)")
            if not pid then
                --  Not shown (another workspace, minimised): no box, but it is there.
                local hpid, happ, htitle = line:match("^%s*([%d%.]+)%s+(%S+)%s+«(.-)»%s+hidden")
                if hpid then
                    list[#list + 1] = { pid = hpid, app = happ, title = htitle, w = 0, h = 0, x = 0, y = 0, screen = 0, hidden = true, dialog = line:find("dialog of", 1, true) ~= nil, keyboard = false }
                end
            end
            if pid then
                list[#list + 1] = {
                    pid = pid, app = app, title = title, w = tonumber(w), h = tonumber(h), x = tonumber(x), y = tonumber(y),
                    screen = tonumber(line:match("monitor (%d+)") or "0"),
                    dialog = line:find("dialog of", 1, true) ~= nil,
                    keyboard = line:find("has the keyboard", 1, true) ~= nil,
                }
            end
        end
        return list
    end
    --  Free windows have a title bar above the box `agent windows` gives (30 px, the window
    --  manager's `tb`); tiled ones have none. A child sits on the top of the whole frame, so each
    --  monitor's mode is asked of the window manager.
    local bars = {}
    local function read_bars(done)
        local left = 3
        for k = 0, 2 do
            run("pleamar-wm", { "--say", "wm", "get free." .. k }, function(out, code)
                local free = code == 0 and (tostring(out):match("^%s*1") ~= nil or tostring(out):match("true") ~= nil)
                bars[k] = free and 30 or 0
                left = left - 1
                if left == 0 and done then done() end
            end, { errors = false })
        end
    end
    local function read_monitors(done)
        run("pleamar-wm", { "agent", "monitors" }, function(out, code)
            if code == 0 then
                for line in tostring(out):gmatch("[^\n]+") do
                    local k, w, x, y = line:match("^%s*(%d+)%s+%S+%s+(%d+)x%d+ at (-?%d+),(-?%d+)")
                    k = tonumber(k)
                    if k and k < 3 then
                        nmon = math.max(nmon, k + 1)
                        fact["mon.x." .. k] = tonumber(x)
                        fact["mon.y." .. k] = tonumber(y)
                        fact["mon.w." .. k] = tonumber(w)
                    end
                end
            end
            read_bars(done)
        end, HANDS)
    end
    --  The whole frame of a window: its box and the title bar over it.
    local function frame(w)
        local bar = bars[w.screen or 0] or 0
        return { x = w.x, y = w.y - bar, w = w.w, h = w.h + bar }
    end
    --  The smallest window that holds the point: the one it is over. A dialog is not a window to
    --  join (it belongs to one), and a window that is one of a program's several (`PID.N`) has no
    --  name the hands could be held to.
    local function window_at(list, px, py)
        local best, best_f
        for _, w in ipairs(list) do
            local f = frame(w)
            if not w.dialog and w.app ~= "marea" and not w.pid:find(".", 1, true)
                and px >= f.x and px < f.x + f.w and py >= f.y and py < f.y + f.h then
                if not best or f.w * f.h < best_f.w * best_f.h then best, best_f = w, f end
            end
        end
        return best, best_f
    end
    local function show_box(kid, w)
        --  The window manager's own frame of the window (`kid.tf`, below) when it is known: it knows
        --  whether the window has a title bar and where the window's own margin (a client-side
        --  shadow, as Zen's) ends; the list of windows gives only its surface's box.
        local f = kid.tf or frame(w)
        local k = kid.k
        F(k, "x", f.x); F(k, "y", f.y); F(k, "w", f.w); F(k, "h", f.h)
        F(k, "screen", w.screen or 0)
    end
    --  Has a child already: one per window.
    local function taken(pid)
        for _, kid in pairs(kids) do
            if kid.window.pid == pid then return true end
        end
        return false
    end
    --  A word on the notch's side, for a few seconds (the scene says it: `kid.warn`).
    local warn_timer = nil
    local function warn(what)
        fact["kid.warn"] = what
        if warn_timer then cancel(warn_timer) end
        warn_timer = after(3200, function() warn_timer = nil; fact["kid.warn"] = "none" end)
    end

    -- ── the loop that keeps up with the windows ──────────────────────
    --  One loop for all the children: a window moved or resized carries its child, one that is
    --  gone lets it go, one on another workspace hides it. Every 45 ms while something moves,
    --  every 120 when everything is still; and a window carried by its title bar is followed
    --  every round (the scene follows the mouse itself in the meantime).
    local loop = { gen = 0, running = false, chain = 0, seen = -1 }
    local tick, poll
    local function any_kid() return next(kids) ~= nil end
    --  Which of the window manager's slots a window is: the one whose place (`x.N`, `y.N`, where the
    --  window is, its title bar included) is where `agent windows` says it, asked when it is still.
    --  A carried window is told apart by this, however fast it goes. One question for all the
    --  children that need it.
    local function find_slots(list)
        if #list == 0 then return end
        local argv = { "--say", "wm" }
        for _, n in ipairs({ "x", "y", "w", "h" }) do
            for k = 0, 9 do argv[#argv + 1] = "get " .. n .. "." .. k end
        end
        run("pleamar-wm", argv, function(out, code)
            if code ~= 0 then return end
            local v, i = {}, 0
            for line in tostring(out):gmatch("[^\n]+") do
                i = i + 1
                v[i] = tonumber(line)
            end
            for _, kid in ipairs(list) do
                if kids[kid.k] == kid and kid.cur then
                    local f = frame(kid.cur)
                    local sc = kid.cur.screen or 0
                    local ox, oy = fact["mon.x." .. sc] or 0, fact["mon.y." .. sc] or 0
                    local best, bd
                    for s = 0, 9 do
                        local x, y, w, h = v[s + 1], v[s + 11], v[s + 21], v[s + 31]
                        if x and y and w and h and w > 1 and h > 1 then
                            --  Its frame is the list's, or inside it: a window with a margin of its own
                            --  (a client-side shadow) has a frame smaller than the box it is listed with.
                            local dx, dy = ox + x - f.x, oy + y - f.y
                            if dx > -2.5 and dx < 60 and dy > -2.5 and dy < 60 + (bars[sc] or 0)
                                and w <= f.w + 2.5 and h <= f.h + 2.5 and w >= f.w - 80 and h >= f.h - 80 - (bars[sc] or 0) then
                                local d = math.abs(dx) + math.abs(dy)
                                if bd == nil or d < bd then best, bd = s, d end
                            end
                        end
                    end
                    if best then kid.slot = best end
                end
            end
        end, { errors = false })
    end
    --  Which children are covered by a window that is above their own: the window manager knows the
    --  windows' stacking (`stamp.N`, plus 50000 for a floating one, as the scene paints them), the places
    --  (`x.N`…), and which are open and shown. The ring of a child's window is covered when another
    --  window above it overlaps it; the child's own place (its band over the top edge, its box, its
    --  answer, its buttons) when one overlaps that band. One question for all of them, once a round.
    local function overlap(a, b)
        local w = math.min(a.x + a.w, b.x + b.w) - math.max(a.x, b.x)
        local h = math.min(a.y + a.h, b.y + b.h) - math.max(a.y, b.y)
        return w > 24 and h > 24
    end
    local function occlude()
        if not any_kid() then return end
        local argv = { "--say", "wm" }
        for sl = 0, 15 do
            for _, n in ipairs({ "x.", "y.", "w.", "h.", "stamp." }) do argv[#argv + 1] = "get " .. n .. sl end
            for _, n in ipairs({ "open", "minimized", "floating", "screen" }) do argv[#argv + 1] = "get win." .. sl .. "." .. n end
        end
        run("pleamar-wm", argv, function(out, code)
            if code ~= 0 or not any_kid() then return end
            local v, i = {}, 0
            for line in tostring(out):gmatch("[^\n]+") do
                i = i + 1
                v[i] = line
            end
            local wins = {}
            for sl = 0, 15 do
                local b = sl * 9
                if v[b + 6] == "true" and v[b + 7] ~= "true" then
                    local sc = tonumber(v[b + 9]) or 0
                    wins[sl] = {
                        x = (fact["mon.x." .. sc] or 0) + (tonumber(v[b + 1]) or 0), y = (fact["mon.y." .. sc] or 0) + (tonumber(v[b + 2]) or 0),
                        w = tonumber(v[b + 3]) or 0, h = tonumber(v[b + 4]) or 0,
                        z = (tonumber(v[b + 5]) or 0) + (v[b + 8] == "true" and 50000 or 0), screen = sc,
                    }
                end
            end
            for _, kid in pairs(kids) do
                local me = kid.slot and wins[kid.slot]
                local cov, covu = 0, 0
                if fact["ch." .. kid.k .. ".hidden"] == true then
                    cov, covu = 1, 1
                elseif me and kid.tf then
                    local f = kid.tf
                    local band = { x = f.x - 10, y = f.y - 70, w = f.w + 20, h = 100 }
                    for sl, o in pairs(wins) do
                        if sl ~= kid.slot and o.z > me.z and o.screen == me.screen then
                            if overlap(f, o) then cov = 1 end
                            if overlap(band, o) then covu = 1 end
                        end
                    end
                end
                --  The same answer twice in a row before it changes: a window passing by does not blink it.
                local want = cov * 2 + covu
                if kid.cov_seen == want and kid.cov_now ~= want then
                    kid.cov_now = want
                    F(kid.k, "cov", cov)
                    F(kid.k, "covu", covu)
                end
                kid.cov_seen = want
            end
        end, { errors = false })
    end
    local function reshow_all()
        for _, kid in pairs(kids) do
            if kid.cur then show_box(kid, kid.cur) end
        end
    end

    --  Carried by its title bar, the window is drawn at the mouse and its own place waits until it is
    --  let go, so the list is a second late: while one is carried and it is a child's (it starts where
    --  the child sits), the child's place is the mouse's, as the scene says it.
    tick = function()
        if loop.gen == 0 then return end
        local gen = loop.gen
        if not any_kid() then loop.running = false; return end
        loop.chain = loop.chain + 1
        local my = loop.chain
        local anycur = false
        for _, kid in pairs(kids) do if kid.cur then anycur = true end end
        if not anycur then return poll(my) end
        --  One question for the carry and for the true frame of each child's window (x.N, y.N, w.N, h.N).
        local argv = { "--say", "wm", "get dragging", "get mouse.x", "get mouse.y", "get grab.x", "get grab.y" }
        local order = {}
        for k = 0, 3 do
            local kid = kids[k]
            if kid and kid.slot and kid.cur and not kid.cur.hidden then
                order[#order + 1] = kid
                for _, n in ipairs({ "x", "y", "w", "h" }) do argv[#argv + 1] = "get " .. n .. "." .. kid.slot end
            end
        end
        run("pleamar-wm", argv, function(out, code)
            if gen ~= loop.gen or my ~= loop.chain then return end
            if not any_kid() then loop.running = false; return end
            local v, i = {}, 0
            for line in tostring(out):gmatch("[^\n]+") do
                i = i + 1
                v[i] = tonumber(line)
            end
            --  The true frames, kept up with while the window is not the one carried.
            for j, kid in ipairs(order) do
                local x, y, w, h = v[5 + 4 * (j - 1) + 1], v[5 + 4 * (j - 1) + 2], v[5 + 4 * (j - 1) + 3], v[5 + 4 * (j - 1) + 4]
                if code == 0 and x and y and w and h and w > 1 and h > 1 and not kid.carried and kids[kid.k] == kid and kid.cur then
                    local sc = kid.cur.screen or 0
                    local tf = { x = (fact["mon.x." .. sc] or 0) + x, y = (fact["mon.y." .. sc] or 0) + y, w = w, h = h }
                    local o = kid.tf
                    if not o or math.abs(o.x - tf.x) > 0.4 or math.abs(o.y - tf.y) > 0.4 or math.abs(o.w - tf.w) > 0.4 or math.abs(o.h - tf.h) > 0.4 then
                        kid.tf = tf
                        kid.calm = 0
                        show_box(kid, kid.cur)
                    end
                end
            end
            local carrying = false
            local ok_drag = code == 0 and v[1] and v[1] >= 0 and v[2] and v[3] and v[4] and v[5]
            local fx, fy
            if ok_drag then fx, fy = v[2] - v[4], v[3] - v[5] end
            --  Which child's window is the one carried: its slot is the one dragged, or (its slot not
            --  known yet) the window is where the mouse says. One at a time: the nearest.
            local who, best = nil, nil
            if ok_drag then
                for _, kid in pairs(kids) do
                    if kid.cur and not kid.cur.hidden then
                        local f = frame(kid.cur)
                        local d = math.abs(fx - f.x) + math.abs(fy - f.y)
                        local mine = kid.carried or (kid.slot and v[1] == kid.slot) or (not kid.slot and math.abs(fx - f.x) < 60 and math.abs(fy - f.y) < 60)
                        if mine and (best == nil or (kid.carried and not who.carried) or (kid.carried == who.carried and d < best)) then who, best = kid, d end
                    end
                end
            end
            for _, kid in pairs(kids) do
                if kid == who then
                    if not kid.carried and fact["ch." .. kid.k .. ".carry"] ~= true then
                        --  Where the window was taken: the scene follows the mouse from here (a
                        --  window manager that does not say it starts it here, a little late).
                        F(kid.k, "gx", v[4]); F(kid.k, "gy", v[5])
                        F(kid.k, "carry", true)
                    end
                    kid.carried = true
                    kid.calm = 0
                    kid.carry_at = { x = fx, y = fy }
                    carrying = true
                elseif kid.carried then
                    --  Let go: it stays where the mouse left it until the list says it.
                    kid.carried = false
                    --  (Already let go in the scene when the window manager said it.)
                    if kid.carry_at and kid.cur and fact["ch." .. kid.k .. ".carry"] == true then
                        if kid.tf then
                            kid.tf = { x = math.floor(kid.carry_at.x), y = math.floor(kid.carry_at.y), w = kid.tf.w, h = kid.tf.h }
                            show_box(kid, kid.cur)
                        else
                            local bar = bars[kid.cur.screen or 0] or 0
                            show_box(kid, { x = math.floor(kid.carry_at.x), y = math.floor(kid.carry_at.y) + bar, w = kid.cur.w, h = kid.cur.h, screen = kid.cur.screen })
                        end
                    end
                    F(kid.k, "carry", false)
                elseif fact["ch." .. kid.k .. ".carry"] == true and not kid.carried then
                    --  The scene guessed a carry (the window manager's event) that is not this child's.
                    F(kid.k, "carry", false)
                end
            end
            if carrying then
                after(25, tick)
                return
            end
            --  Still: the windows are looked at every fifth round; the carry, every one.
            loop.rounds = (loop.rounds or 0) + 1
            local calm = 99
            for _, kid in pairs(kids) do calm = math.min(calm, kid.calm or 99) end
            if calm < 25 or loop.rounds % 5 == 0 then poll(my) else after(120, tick) end
        end, { errors = false })
    end

    poll = function(my)
        local gen = loop.gen
        run("pleamar-wm", { "agent", "windows" }, function(out, code)
            if gen ~= loop.gen or my ~= loop.chain then return end
            if not any_kid() then loop.running = false; return end
            --  Close behind it while it moves (a round costs 10 ms), at ease when it is still.
            local wait = 120
            if code == 0 then
                local list = parse_windows(out)
                --  New windows that look like a file chooser while a child works: its dialogs.
                local now_pids, mine_base = {}, {}
                for _, kk in pairs(kids) do mine_base[tostring(kk.window.pid):match("^%d+")] = true end
                for _, w in ipairs(list) do now_pids[w.pid] = true end
                if loop.prev_pids then
                    for _, w in ipairs(list) do
                        local base = tostring(w.pid):match("^%d+")
                        if not loop.prev_pids[w.pid] and not w.hidden and not w.dialog and not mine_base[base] and is_chooser(w) then
                            local best
                            for _, kk in pairs(kids) do
                                if (kk.state == "thinking" or kk.state == "acting") and (not best or (kk.last_tool or 0) > (best.last_tool or 0)) then best = kk end
                            end
                            if best then
                                best.scope.adopted[w.pid] = true
                                best.scope.dialogs[w.pid] = true
                                best.notice = string.format("A window opened: pid %s, %s «%s». It is a dialog of your window (a save, open or file chooser): it is yours to use, with desktop_look and the other tools, until it closes.", tostring(w.pid), tostring(w.app), tostring(w.title))
                                log("kids · child " .. best.k .. " adopted the window " .. tostring(w.pid) .. " (" .. tostring(w.app) .. ") as its dialog")
                            end
                        end
                    end
                end
                loop.prev_pids = now_pids
                --  And the ones that closed are no longer its.
                for _, kk in pairs(kids) do
                    for p in pairs(kk.scope.adopted) do
                        if not now_pids[p] then kk.scope.adopted[p] = nil; kk.scope.dialogs[p] = nil end
                    end
                end
                local need_slot, need_bars = {}, false
                local gone = {}
                for _, kid in pairs(kids) do
                    local mine
                    for _, w in ipairs(list) do
                        if w.pid == kid.window.pid then mine = w end
                    end
                    local kwait = kid.calm and kid.calm < 25 and 45 or 120
                    if not mine then
                        --  A program with several windows lists them as PID.N: the window is not gone
                        --  while some window of its program is in the list.
                        local base, there = tostring(kid.window.pid):match("^%d+"), false
                        for _, w in ipairs(list) do
                            if tostring(w.pid):match("^%d+") == base then there = true end
                        end
                        if there then
                            kid.missed = 0
                        else
                            kid.missed = (kid.missed or 0) + 1
                            if kid.missed >= 2 then gone[#gone + 1] = kid end
                        end
                    elseif mine.hidden then
                        --  On another workspace (or minimised): the child is not shown, and it is not let go.
                        kid.missed = 0
                        if fact["ch." .. kid.k .. ".hidden"] ~= true then F(kid.k, "hidden", true) end
                        kid.carried = false
                        F(kid.k, "carry", false)
                        kwait = 300
                    else
                        kid.missed = 0
                        if fact["ch." .. kid.k .. ".hidden"] == true then F(kid.k, "hidden", false) end
                        kid.cur = mine
                        local box = mine.x .. "," .. mine.y .. "," .. mine.w .. "," .. mine.h .. "," .. mine.screen
                        if box ~= kid.last then
                            local moved_screen = kid.last ~= nil and tostring(kid.last):match(",(%d+)$") ~= tostring(mine.screen)
                            if kid.last ~= nil then kwait = 45; kid.calm = 0 end
                            kid.last = box
                            show_box(kid, mine)
                            kid.window.title = mine.title
                            --  Tiled turning free changes the title bar: the bars are looked at again
                            --  when it changes monitor or after it has been still for a moment.
                            if moved_screen then need_bars = true end
                        else
                            kid.calm = (kid.calm or 99) + 1
                            if kid.slot == nil or kid.calm == 3 then need_slot[#need_slot + 1] = kid end
                            if kid.calm == 25 then need_bars = true end
                            if kid.calm < 25 then kwait = 45 end
                        end
                    end
                    wait = math.min(wait, kwait)
                end
                for _, kid in ipairs(gone) do
                    if kids[kid.k] == kid then leave(kid.k, string.format(tr("%s closed: I let go of it."), kid.window.app)) end
                end
                find_slots(need_slot)
                occlude()
                if need_bars then read_bars(reshow_all) end
            end
            if any_kid() then after(wait, tick) else loop.running = false end
        end, HANDS)
    end

    local function start_loop()
        if loop.running then return end
        loop.running = true
        loop.gen = loop.gen + 1
        loop.chain = 0
        loop.seen = -1
        local gen = loop.gen
        after(600, tick)
        --  And if a round never heard back (the window manager busy while a window is resized), the
        --  loop is started again instead of standing still for good.
        local function watch()
            if gen ~= loop.gen or not loop.running then return end
            if loop.chain == loop.seen then tick() end
            loop.seen = loop.chain
            after(2500, watch)
        end
        after(2500, watch)
    end

    -- ── perching and letting go ──────────────────────────────────────
    function leave(k, why)
        local kid = kids[k]
        if not kid then return end
        kids[k] = nil
        if kid.idle_timer then cancel(kid.idle_timer) end
        --  Its watches live and die with it: every timer is cancelled and nothing is left.
        watches_end(kid)
        --  Its worker goes with it.
        if kid.worker then
            local id = kid.worker
            kid.worker = nil
            write(id, json.encode({ type = "shutdown" }) .. "\n")
            after(600, function() kill(id) end)
        end
        F(k, "on", false)
        F(k, "cov", 0); F(k, "covu", 0)
        F(k, "carry", false)
        F(k, "hidden", false)
        F(k, "said_on", false)
        F(k, "state", "idle")
        F(k, "letters", 0); F(k, "min", false); F(k, "shut", false); F(k, "new", false)
        F(k, "paused", false); F(k, "askfirst", false); F(k, "q", 0); F(k, "cards", 0); F(k, "wn", 0); F(k, "wrun", false)
        for i = 0, 2 do T(k, "n." .. i, "") end
        T(k, "card", ""); T(k, "cardbody", "")
        if tonumber(fact["kp.k"]) == k then fact["kp.k"] = -1 end
        T(k, "app", ""); T(k, "name", ""); T(k, "label", ""); T(k, "said", ""); T(k, "status", ""); T(k, "input", "")
        count()
        agent_done()
        log("kids · let go of child " .. k .. ": " .. tostring(why or kid.window.app))
        if not any_kid() then loop.running = false; loop.gen = loop.gen + 1 end
    end
    local function free_slot()
        for k = 0, MAX - 1 do
            if not kids[k] and (fact["ch." .. k .. ".phase"] or "none") == "none" then return k end
        end
        return nil
    end
    --  A child perches on a window: its slot is the scene's (`k`), and the scene brings it down onto
    --  the window's top edge (`dx`: how far along it).
    local function attach(k, found, dx)
        local kid = {
            k = k, window = { pid = found.pid, app = found.app, title = found.title },
            scope = { pid = found.pid, dialogs = {}, adopted = {} }, programs = {},
            queue = {}, history = {}, state = "idle", ready = false,
            rows = {}, asks = {}, ask_order = {}, next = {}, held = {},
            watches = {}, watch_order = {}, notes_made = {},
        }
        kids[k] = kid
        T(k, "app", found.app)
        T(k, "name", nice(found.app))
        T(k, "said", ""); T(k, "status", ""); T(k, "input", "")
        F(k, "said_on", false); F(k, "letters", 0); F(k, "min", false); F(k, "shut", false); F(k, "new", false)
        F(k, "state", "idle")
        F(k, "paused", false); F(k, "askfirst", false); F(k, "q", 0); F(k, "cards", 0); F(k, "wn", 0); F(k, "wrun", false)
        relabel(kid)
        F(k, "hidden", false)
        F(k, "carry", false)
        show_box(kid, found)
        F(k, "dx", dx or math.floor(found.w / 2))
        F(k, "on", true)
        kid.cur, kid.last = found, found.x .. "," .. found.y .. "," .. found.w .. "," .. found.h .. "," .. found.screen
        count()
        start_loop()
        emit("join_land." .. k)
    end

    --  `emit chat_attach`: the child perches on the window that has the keyboard (or on the one in
    --  `chat.target`, a pid), without anybody pulling it. The way a script, a key or a test does it.
    on("chat_attach", function()
        local want = tostring(text["chat.target"] or ""):gsub("%s", "")
        run("pleamar-wm", { "agent", "windows" }, function(out, code)
            if code ~= 0 then return end
            local found
            for _, w in ipairs(parse_windows(out)) do
                if not w.dialog and w.app ~= "marea" then
                    if (want == "" or want == "focus") and w.keyboard or want == w.pid then
                        found = w
                        break
                    end
                end
            end
            if not found then return end
            local k = free_slot()
            if not k then warn("full"); return end
            if taken(found.pid) then warn("taken"); return end
            text["chat.target"] = ""
            read_monitors(function() attach(k, found) end)
        end, HANDS)
    end)
    --  Let go of a child: its box's button, its tab's ×, or `emit chat_detach` (a number says which;
    --  none says the one whose window has the keyboard, or the only one there is).
    on("chat_detach", function(k)
        k = tonumber(k)
        if k then leave(k) return end
        local only, n = nil, 0
        for kk in pairs(kids) do only, n = kk, n + 1 end
        if n == 1 then leave(only) return end
        run("pleamar-wm", { "agent", "windows" }, function(out, code)
            if code ~= 0 then return end
            for _, w in ipairs(parse_windows(out)) do
                if w.keyboard then
                    for kk, kid in pairs(kids) do
                        if kid.window.pid == w.pid then leave(kk) return end
                    end
                end
            end
        end, HANDS)
    end)
    --  The scene started to follow a carried window with a guess of where it was taken; the exact
    --  place is the window manager's (`grab`), and it is said as soon as it is asked.
    on("carry_grab", function(k)
        k = tonumber(k)
        if not k or not kids[k] then return end
        run("pleamar-wm", { "--say", "wm", "get dragging", "get grab.x", "get grab.y" }, function(out, code)
            if code ~= 0 or fact["ch." .. k .. ".carry"] ~= true then return end
            local v, i = {}, 0
            for line in tostring(out):gmatch("[^\n]+") do
                i = i + 1
                v[i] = tonumber(line)
            end
            if v[1] and v[1] >= 0 and v[2] and v[3] then
                F(k, "gx", v[2]); F(k, "gy", v[3])
            end
        end, { errors = false })
    end)

    -- ── dropped on a window ──────────────────────────────────────────
    --  A child is pulled out of the notch (scene/rules/join.plm) and, while it is held, the windows
    --  are looked at to light the one under it. Let go over one, and it perches there.
    local grab_gen = 0
    on("join_grab", function(k)
        grab_gen = grab_gen + 1
        local gen = grab_gen
        read_monitors()
        local busy = false
        local function look()
            if gen ~= grab_gen or fact["ch." .. tostring(k) .. ".phase"] ~= "held" then return end
            if busy then after(120, look) return end
            busy = true
            run("pleamar-wm", { "agent", "windows" }, function(out, code)
                busy = false
                if gen == grab_gen and fact["ch." .. tostring(k) .. ".phase"] == "held" and code == 0 then
                    local w, f = window_at(parse_windows(out), fact["ptr.x"] or 0, fact["ptr.y"] or 0)
                    if w then
                        fact["hov.x"], fact["hov.y"], fact["hov.w"], fact["hov.h"] = f.x, f.y, f.w, f.h
                        text["hov.app"] = nice(w.app)
                        fact["hov.taken"] = taken(w.pid)
                    end
                    fact["hov.on"] = w ~= nil
                end
                after(160, look)
            end, HANDS)
        end
        look()
    end)
    on("join_drop", function(k)
        k = tonumber(k)
        if not k then return end
        grab_gen = grab_gen + 1
        local px, py = fact["ptr.x"] or 0, fact["ptr.y"] or 0
        --  The pointer that crosses to another monitor stops being told (the press belongs to the
        --  surface of the notch): the last place it knows is at the edge it was pulled across. That
        --  is not a window; the child goes back.
        local hx, hw = 0, 0
        for m = 0, 2 do
            if px >= (fact["mon.x." .. m] or 0) and px < (fact["mon.x." .. m] or 0) + (fact["mon.w." .. m] or 0) then
                hx, hw = fact["mon.x." .. m], fact["mon.w." .. m]
            end
        end
        if nmon > 1 and hw > 0 and (px - hx <= 24 or px - hx >= hw - 24) then
            fact["hov.on"] = false
            emit("join_none." .. k)
            return
        end
        run("pleamar-wm", { "agent", "windows" }, function(out, code)
            local target = code == 0 and window_at(parse_windows(out), px, py) or nil
            if not target then
                fact["hov.on"] = false
                emit("join_none." .. k)
                return
            end
            --  One child to a window: it goes back, and says why.
            if taken(target.pid) then
                fact["hov.on"] = false
                warn("taken")
                emit("join_none." .. k)
                return
            end
            attach(k, target, math.floor(px - target.x))
        end, HANDS)
    end)

    -- ── what its box asks ────────────────────────────────────────────
    --  Enter in a child's box (or its button): what is written is its task.
    on("join_send", function(k)
        local kid = kids[tonumber(k)]
        if not kid then return end
        local words = tostring(text["ch." .. kid.k .. ".input"] or "")
        if words:match("^%s*$") then return end
        T(kid.k, "input", "")
        --  While it works, what you write waits for its turn (and can be cancelled).
        if BUSY[kid.state] then
            if #kid.next < 5 then
                kid.next[#kid.next + 1] = words
                sync_queue(kid)
            end
            return
        end
        ask(kid, words)
    end)
    --  Stop: what it does ends, and so does what was waiting for it.
    local function stop(kid)
        kid.next = {}
        sync_queue(kid)
        kid.held = {}
        kid.paused = false
        F(kid.k, "paused", false)
        for id, a in pairs(kid.asks) do a.row.state = 2; kid.asks[id] = nil end
        kid.ask_order = {}
        sync_cards(kid)
        paint_panel(kid)
        send(kid, { type = "cancel" })
        status(kid, tr("Stopping…"))
        if not kid.worker then settle(kid, "idle") end
    end
    on("kid_stop", function(k)
        local kid = kids[tonumber(k)]
        if kid then stop(kid) end
    end)
    on("kid_pause", function(k)
        local kid = kids[tonumber(k)]
        if kid then set_paused(kid, not kid.paused) end
    end)
    on("kid_askfirst", function(k)
        local kid = kids[tonumber(k)]
        if not kid then return end
        kid.askfirst = not kid.askfirst
        F(kid.k, "askfirst", kid.askfirst)
    end)
    --  A queued message taken back out of the line (`n`: child * 3 + its place).
    on("kid_unq", function(n)
        n = tonumber(n)
        if not n then return end
        local kid = kids[n // 3]
        if kid and kid.next[n % 3 + 1] then
            table.remove(kid.next, n % 3 + 1)
            sync_queue(kid)
        end
    end)
    --  The card under a box: its first pending step is allowed or not.
    on("kid_allow", function(k) local kid = kids[tonumber(k)]; local id = kid and first_ask(kid); if id then decide(kid, id, true) end end)
    on("kid_deny", function(k) local kid = kids[tonumber(k)]; local id = kid and first_ask(kid); if id then decide(kid, id, false) end end)

    -- ── its panel ────────────────────────────────────────────────────
    --  One child's whole conversation at a time (scene/draw/kidpanel.plm): what was said, what it did, and
    --  the controls of that child.
    local function panel_kid()
        return kids[tonumber(fact["kp.k"]) or -1]
    end
    on("kp_open", function(k)
        k = tonumber(k)
        local kid = kids[k]
        if not kid then return end
        fact["kp.k"] = k
        text["kp.title"] = text["ch." .. k .. ".label"]
        text["kp.status"] = text["ch." .. k .. ".status"]
        text["kp.input"] = ""
        sync_watches(kid)
        paint_panel(kid)
    end)
    on("kp_unwatch", function(i)
        local kid = panel_kid()
        local id = kid and kid.watch_order[(tonumber(i) or -1) + 1]
        if id then
            watch_stop_one(kid, id)
            add_row(kid, 5, string.format(tr("Watch %d stopped."), id))
            paint_panel(kid)
        end
    end)
    on("kp_close", function() fact["kp.k"] = -1 end)
    on("kp_send", function()
        local kid = panel_kid()
        if not kid then return end
        local words = tostring(text["kp.input"] or "")
        if words:match("^%s*$") then return end
        text["kp.input"] = ""
        if BUSY[kid.state] then
            if #kid.next < 5 then kid.next[#kid.next + 1] = words; sync_queue(kid) end
        else
            ask(kid, words)
        end
    end)
    on("kp_stop", function() local kid = panel_kid(); if kid then stop(kid) end end)
    on("kp_pause", function() local kid = panel_kid(); if kid then set_paused(kid, not kid.paused) end end)
    on("kp_ask", function()
        local kid = panel_kid()
        if kid then
            kid.askfirst = not kid.askfirst
            F(kid.k, "askfirst", kid.askfirst)
        end
    end)
    --  The card in the thread: its place in the model (first + i).
    local function ask_of_row(kid, i)
        local row = kid.rows[(kid.first or 1) + (tonumber(i) or 0)]
        for id, a in pairs(kid.asks) do
            if a.row == row then return id end
        end
    end
    on("kp_allow", function(i) local kid = panel_kid(); local id = kid and ask_of_row(kid, i); if id then decide(kid, id, true) end end)
    on("kp_deny", function(i) local kid = panel_kid(); local id = kid and ask_of_row(kid, i); if id then decide(kid, id, false) end end)
    --  A new conversation: what was said is forgotten, and its engine starts over.
    on("kp_new", function()
        local kid = panel_kid()
        if not kid then return end
        if BUSY[kid.state] then stop(kid) end
        kid.history, kid.rows, kid.next, kid.held, kid.asks, kid.ask_order = {}, {}, {}, {}, {}, {}
        kid.task, kid.live, kid.live_row = nil, nil, nil
        unsay(kid)
        if kid.worker then
            local id = kid.worker
            kid.worker, kid.ready = nil, false
            write(id, json.encode({ type = "shutdown" }) .. "\n")
            after(600, function() kill(id) end)
        end
        set_state(kid, "idle")
        status(kid, "")
        sync_queue(kid)
        sync_cards(kid)
        paint_panel(kid)
    end)
    --  Its last answer, to the clipboard.
    on("kp_copy", function()
        local kid = panel_kid()
        if not kid then return end
        local last
        for i = #kid.rows, 1, -1 do
            if kid.rows[i].kind == 2 and kid.rows[i].text ~= "" then last = kid.rows[i].text; break end
        end
        if last then run("wl-copy", {}, function() end, { input = last }) end
    end)
    --  The next word wakes up the model it is told about in Settings: a child's worker follows the
    --  main chat's model; one that is awake finishes its sentence with the old one.
end
