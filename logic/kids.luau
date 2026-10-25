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

    local function F(k, name, v) fact["ch." .. k .. "." .. name] = v end
    local function T(k, name, v) text["ch." .. k .. "." .. name] = v end

    local function first_letters(s, n)
        local ok, b = pcall(utf8.offset, s, n + 1)
        if ok and b then return s:sub(1, b - 1) end
        return s
    end

    -- ── how many, and who works ──────────────────────────────────────
    local BUSY = { starting = true, thinking = true, acting = true, awaiting = true }
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
    local function refuses(kid, tool, args)
        if tool ~= "desktop_windows" and not DESKTOP[tool] then
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
    }
    local function program(kid, args)
        if tostring(args.pid or ""):match("^(%d+)") == kid.window.pid then return nice(kid.window.app) end
        return kid.programs[window_name(args.pid)] or ("the window " .. tostring(args.pid or "?"))
    end
    local function said(kid, tool, args)
        if tool == "desktop_windows" then return tr("Looking at the window…") end
        return string.format(tr(JOINED_WORDS[tool] or "Working in %s…"), program(kid, args))
    end

    -- ── the worker of a child ────────────────────────────────────────
    local leave   -- let go of a child (below)
    local function set_state(kid, st)
        kid.state = st
        F(kid.k, "state", st)
        count()
    end
    local function status(kid, words) T(kid.k, "status", words or "") end

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
    local function settle(kid, st)
        set_state(kid, st or "idle")
        status(kid, "")
        kid.live = nil
        agent_done()
        rest_later(kid)
        local how = kid.ending or { ok = false, said = "" }
        kid.ending = nil
        --  What it says goes where the user is looking: under its box.
        if tostring(how.said or "") ~= "" then
            T(kid.k, "said", first_letters(tostring(how.said), 260))
            F(kid.k, "said_on", true)
        end
    end

    --  The tool it proposed: free hands in its window, no cards.
    local function perform(kid, id, tool, args)
        set_state(kid, "acting")
        status(kid, said(kid, tool, args))
        hands.exec(tool, args, {
            scope = kid.scope,
            programs = kid.programs,
            name = function(a) return program(kid, a) end,
            prefix = "kid" .. kid.k .. "-look",
            secret = function(a, done) chat.type_secret(a, done) end,
        }, function(ok, words, extra, flags)
            if kids[kid.k] ~= kid then return end
            answer(kid, id, ok, words, extra)
            if kid.state == "acting" then set_state(kid, "thinking") end
            --  Stopped from the monitor's pill: the whole turn ends, not only this step.
            if flags and flags.stopped then
                kid.stopped_by_pill = true
                send(kid, { type = "cancel" })
            end
            --  Its window closed: nothing to hold on to any more.
            if flags and flags.gone then
                leave(kid.k, string.format(tr("%s closed: I let go of it."), kid.window.app))
            end
        end)
    end

    local function on_event(kid, m)
        local kind = m.type
        if kind == "ready" then
            kid.ready = true
            kid.usable = m.usable == true
            if m.usable then
                if kid.state == "offline" or kid.state == "starting" then
                    set_state(kid, "idle")
                    status(kid, "")
                end
            else
                set_state(kid, "offline")
                status(kid, m.reason == "signed_out" and tr("She is not signed in.") or tr("That model cannot be used with her account: choose another in Settings"))
            end
            for _, line in ipairs(kid.queue) do write(kid.worker, line) end
            kid.queue = {}
        elseif kind == "delta" then
            if kid.live == nil then
                kid.live = ""
                set_state(kid, "thinking")
                status(kid, tr("Thinking…"))
            end
            kid.live = kid.live .. (m.text or "")
        elseif kind == "propose" then
            kid.live = nil
            local tool, args = tostring(m.tool), (type(m.args) == "table" and m.args or {})
            local refused = refuses(kid, tool, args)
            if refused then
                answer(kid, m.id, false, refused)
            else
                perform(kid, m.id, tool, args)
            end
        elseif kind == "done" then
            if kid.live and kid.live ~= "" then kid.history[#kid.history + 1] = { role = "assistant", text = kid.live } end
            kid.ending = { ok = true, said = kid.live or "" }
            settle(kid, "idle")
        elseif kind == "cancelled" then
            kid.ending = { ok = false, said = kid.stopped_by_pill and tr("You stopped her from the monitor.") or tr("Stopped.") }
            kid.stopped_by_pill = false
            settle(kid, "idle")
        elseif kind == "failed" then
            if m.reason == "no_model" or m.reason == "not_started" then
                kid.ending = { ok = false, said = tr("She is not signed in.") }
            else
                kid.ending = { ok = false, said = tr("Something went wrong: ") .. tostring(m.reason or "?") }
            end
            settle(kid, kid.usable and "idle" or "offline")
        end
    end

    local function start_worker(kid)
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
            if kids[kid.k] ~= kid then return end
            if said_why then
                set_state(kid, "offline")
                status(kid, tr("Her engine cannot start: ") .. said_why)
                kid.queue = {}
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
        --  A worker that never says it is ready does not leave the child waiting for good.
        after(60000, function()
            if kids[kid.k] == kid and kid.worker == id and not kid.ready and kid.state == "starting" then
                set_state(kid, "offline")
                status(kid, tr("Her engine cannot start: ") .. "…")
            end
        end)
    end

    local function ask(kid, words)
        if kid.state == "thinking" or kid.state == "acting" or kid.state == "awaiting" or kid.state == "starting" then return end
        T(kid.k, "said", "")
        F(kid.k, "said_on", false)
        kid.history[#kid.history + 1] = { role = "user", text = words }
        if kid.idle_timer then cancel(kid.idle_timer); kid.idle_timer = nil end
        start_worker(kid)
        set_state(kid, "thinking")
        status(kid, tr("Thinking…"))
        send(kid, { type = "prompt", text = words, now = os.date("%Y-%m-%d %H:%M, %A"), free = true,
                    joined = { pid = kid.window.pid, app = kid.window.app, title = kid.window.title },
                    secrets = chat.secrets() })
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
        local f = frame(w)
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
        for k = 0, 9 do argv[#argv + 1] = "get x." .. k end
        for k = 0, 9 do argv[#argv + 1] = "get y." .. k end
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
                    for s = 0, 9 do
                        local x, y = v[s + 1], v[s + 11]
                        if x and y and math.abs(x - f.x) < 2.5 and math.abs(y - f.y) < 2.5 then kid.slot = s break end
                    end
                end
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
        run("pleamar-wm", { "--say", "wm", "get dragging", "get mouse.x", "get mouse.y", "get grab.x", "get grab.y" }, function(out, code)
            if gen ~= loop.gen or my ~= loop.chain then return end
            if not any_kid() then loop.running = false; return end
            local v, i = {}, 0
            for line in tostring(out):gmatch("[^\n]+") do
                i = i + 1
                v[i] = tonumber(line)
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
                        local bar = bars[kid.cur.screen or 0] or 0
                        show_box(kid, { x = math.floor(kid.carry_at.x), y = math.floor(kid.carry_at.y) + bar, w = kid.cur.w, h = kid.cur.h, screen = kid.cur.screen })
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
                local need_slot, need_bars = {}, false
                local gone = {}
                for _, kid in pairs(kids) do
                    local mine
                    for _, w in ipairs(list) do
                        if w.pid == kid.window.pid then mine = w end
                    end
                    local kwait = kid.calm and kid.calm < 25 and 45 or 120
                    if not mine then
                        kid.missed = (kid.missed or 0) + 1
                        if kid.missed >= 2 then gone[#gone + 1] = kid end
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
        --  Its worker goes with it.
        if kid.worker then
            local id = kid.worker
            kid.worker = nil
            write(id, json.encode({ type = "shutdown" }) .. "\n")
            after(600, function() kill(id) end)
        end
        F(k, "on", false)
        F(k, "carry", false)
        F(k, "hidden", false)
        F(k, "said_on", false)
        F(k, "state", "idle")
        T(k, "app", ""); T(k, "name", ""); T(k, "said", ""); T(k, "status", ""); T(k, "input", "")
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
            scope = { pid = found.pid, dialogs = {} }, programs = {},
            queue = {}, history = {}, state = "idle", ready = false,
        }
        kids[k] = kid
        T(k, "app", found.app)
        T(k, "name", nice(found.app))
        T(k, "said", ""); T(k, "status", ""); T(k, "input", "")
        F(k, "said_on", false)
        F(k, "state", "idle")
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
        ask(kid, words)
    end)
    on("kid_stop", function(k)
        local kid = kids[tonumber(k)]
        if not kid then return end
        send(kid, { type = "cancel" })
        status(kid, tr("Stopping…"))
        if not kid.worker then settle(kid, "idle") end
    end)
    --  The next word wakes up the model it is told about in Settings: a child's worker follows the
    --  main chat's model; one that is awake finishes its sentence with the old one.
end
