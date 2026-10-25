-- Marea's logic, in pieces: her hands on the desktop, shared.
-- The main chat (logic/chat.luau) and each of her children (logic/kids.luau) do what their
-- engine proposes through this: pleamar-wm's agent hands (`pleamar-wm agent …`), a pointer and a
-- keyboard of her own, never the user's. Who may touch which window is decided by the caller
-- (a child is tied to one window with `o.scope`); how a tool is run is here, once.
return function(shared)
    local home_dir = shared.home_dir
    local base = sys.ask("env", "XDG_STATE_HOME")
    if base == nil or base == "" then base = home_dir .. "/.local/state" end
    local STATE = base .. "/marea-plm/agent"
    --  How her hands are run: what they say went wrong comes back too, and
    --  the cursor on the desktop is labelled hers.
    local HANDS = { errors = true, env = { PLEAMAR_AGENT_NAME = "Marea" } }

    --  A window as desktop_windows names it: «4521», or «4521.3» for one of
    --  a program's several. Anything else is no window.
    local function window_name(v)
        local name = tostring(v or "")
        if name:match("^%d+$") or name:match("^%d+%.%d+$") or name:match("^%d+%.?%d*:[%w_-]+$") then return name end
        return "0"
    end
    --  A program as it is said to a person: «kitty» is «Kitty», «org.mozilla.firefox» is
    --  «Firefox».
    local function nice(app)
        local last = tostring(app or ""):match("([^%.]+)$") or tostring(app or "")
        return (last:gsub("^%l", string.upper))
    end
    local function agent_args(tool, a)
        local pid = window_name(a.pid)
        local n = function(v) return tostring(tonumber(v) or 0) end
        if tool == "desktop_windows" then return { "agent", "windows" } end
        --  By element (@24, from the window's tree): `--` ends the options, so a
        --  text that starts with @ or -- is text.
        local function element(v) v = tostring(v or "") if v:match("^@%d+$") then return v end end
        if tool == "desktop_tree" then
            local argv = { "agent", "tree", pid }
            if element(a.within) then argv[#argv + 1] = "--within" argv[#argv + 1] = element(a.within) end
            if type(a.role) == "string" and a.role:match("^[a-z_]+$") then argv[#argv + 1] = "--role" argv[#argv + 1] = a.role end
            if a.since == true then argv[#argv + 1] = "--since" end
            if tonumber(a.max) then argv[#argv + 1] = "--max" argv[#argv + 1] = tostring(math.floor(tonumber(a.max))) end
            return argv
        end
        if tool == "desktop_find" then return { "agent", "find", pid, "--text", tostring(a.text or "") } end
        if tool == "desktop_press" then
            local argv = { "agent", "press", pid }
            if element(a.element) then argv[#argv + 1] = element(a.element)
            else argv[#argv + 1] = "--text" argv[#argv + 1] = tostring(a.text or "") argv[#argv + 1] = "--first" end
            if a.button == "right" or a.button == "middle" then argv[#argv + 1] = a.button end
            return argv
        end
        if tool == "desktop_fill" then
            local argv = { "agent", "type", pid }
            if element(a.element) then argv[#argv + 1] = element(a.element) end
            if a.replace == true then argv[#argv + 1] = "--set" end
            argv[#argv + 1] = "--"
            argv[#argv + 1] = tostring(a.text or "")
            return argv
        end
        if tool == "desktop_steps" then
            local lines = {}
            for _, line in ipairs(type(a.steps) == "table" and a.steps or {}) do
                line = tostring(line):gsub("[\r\n]", " ")
                --  `type -` and `run -` read the input, which these lines are.
                if not line:match("^%s*type%s+%-%s*$") and not line:match("^%s*run%s+%-") then lines[#lines + 1] = line end
            end
            if #lines == 0 then return nil end
            return { "agent", "do", pid }, table.concat(lines, "\n") .. "\n"
        end
        if tool == "desktop_wait" then
            local until_ = tostring(a["until"] or "")
            local seconds = tostring(math.max(1, math.min(30, math.floor(tonumber(a.seconds) or 10)))) .. "s"
            if until_ == "has" or until_ == "gone" then return { "agent", "wait", pid, until_, "--text", tostring(a.text or ""), seconds } end
            if until_ == "changed" or until_ == "dialog" then return { "agent", "wait", pid, until_, seconds } end
            if until_ == "settled" then return { "agent", "wait", pid, "settled", "1s", seconds } end
            return nil
        end
        if tool == "desktop_run" then
            local seconds = tostring(math.max(1, math.min(300, math.floor(tonumber(a.seconds) or 30)))) .. "s"
            return { "agent", "run", pid, "-", seconds }, tostring(a.command or "")
        end
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

    --  What the pictures she takes are called: one counter for each prefix, three names
    --  each, so that a picture is not overwritten while the model still reads it, and the
    --  main chat's and each child's never meet.
    local looks = {}

    --  Does one of the desktop tools and calls `done(ok, words, extra, flags)` when it is over.
    --    o.scope      nil, or { pid = "4521", dialogs = {} }: the one window she may see in a
    --                 list of windows, and the dialogs it opened (filled in here)
    --    o.programs   the table the pids of the windows seen go into, with their program
    --    o.name(args) how a window is called in words
    --    o.prefix     the prefix of her pictures' names
    --    o.looking(b) she is taking a picture (the glass on her face), or no longer is
    --    o.secret(args, done)  types a saved password (the caller keeps the passwords)
    --  `flags.stopped`: the user stopped the agent from the monitor; `flags.gone`: the window is
    --  not there any more.
    local function exec(tool, args, o, done)
        local scope = o.scope
        if tool == "desktop_type_secret" then
            o.secret(args, done)
            return
        end
        if tool == "desktop_look" then
            local prefix = o.prefix or "look"
            looks[prefix] = (looks[prefix] or 0) + 1
            if o.looking then o.looking(true) end
            local name = prefix .. "-" .. (looks[prefix] % 3) .. ".png"
            run("pleamar-wm", { "agent", "look", window_name(args.pid), STATE .. "/" .. name }, function(out, code)
                --  The glass stays on her face a moment: the look is seen.
                after(600, function() if o.looking then o.looking(false) end end)
                if code == 0 then
                    local w, h = tostring(out):match("(%d+)x(%d+)")
                    done(true, string.format("A picture of %s, %sx%s pixels.", o.name(args), w or "?", h or "?"), { image = { path = "/state/" .. name } })
                else
                    done(false, tostring(out))
                end
            end, HANDS)
            return
        end
        if tool == "terminal_wait" then
            --  What runs in a terminal, waited for until it is done: an AI agent (the window
            --  manager knows its state: working, ready, asking) by looking every two seconds;
            --  anything else by the terminal being quiet.
            local pid = window_name(args.pid)
            local window = pid:match("^(%d+)")
            local limit = math.max(5, math.min(600, math.floor(tonumber(args.seconds) or 60)))
            local started = 0
            local target = pid:find(":", 1, true) and pid or nil   -- PID:SHELL, said or found below
            local function finish(ok, head)
                --  And what it printed: the screen's lines.
                run("pleamar-wm", { "agent", "tree", target or pid }, function(out, code)
                    done(ok, head .. "\n\n" .. (code == 0 and tostring(out) or ""))
                end, HANDS)
            end
            local function look()
                run("pleamar-wm", { "term", "list" }, function(out, code)
                    local state, program
                    for line in tostring(out):gmatch("[^\n]+") do
                        if line:match("terminal " .. window .. "%s") then
                            program, state = line:match("terminal %d+%s+(%S+)%s*%((%w+)%)")
                            program = program or line:match("terminal %d+%s+(%S+)")
                            target = target or (window .. ":" .. tostring(line:match("^%s*(%d+)")))
                            break
                        end
                    end
                    if code ~= 0 or program == nil then
                        finish(false, "That terminal is not there any more or is not one.")
                        return
                    end
                    if state == nil then
                        --  No AI agent there: a command in a shell, waited for until the shell is
                        --  ready for another.
                        run("pleamar-wm", { "agent", "wait", target or pid, "prompt", limit .. "s" }, function(o2, c2)
                            if c2 == 0 then
                                finish(true, "The terminal is ready again.")
                            else
                                finish(true, "Still running after " .. limit .. " s: wait again if it should take longer.")
                            end
                        end, { errors = false })
                        return
                    end
                    if state ~= "working" then
                        finish(true, program .. " is " .. state .. ".")
                        return
                    end
                    if started >= limit then
                        finish(true, program .. " is still working after " .. limit .. " s: wait again if it should take longer.")
                        return
                    end
                    started = started + 2
                    after(2000, look)
                end, { errors = false })
            end
            if not window then
                done(false, "That is no window.")
                return
            end
            look()
            return
        end
        local argv, stdin = agent_args(tool, args)
        if not argv then
            done(false, "Marea does not know that tool.")
            return
        end
        if tool == "desktop_windows" then
            run("pleamar-wm", argv, function(out, code)
                if code ~= 0 then
                    done(false, tostring(out))
                    return
                end
                local programs = o.programs
                for k in pairs(programs) do programs[k] = nil end
                if scope then
                    --  One window and the dialogs it opened: nothing else of the desktop is seen.
                    for k in pairs(scope.dialogs) do scope.dialogs[k] = nil end
                    local kept = {}
                    for line in tostring(out):gmatch("[^\n]+") do
                        local lp = line:match("^%s*([%d%.]+)%s")
                        if lp then
                            local owner = line:match("dialog of ([%d%.]+)")
                            if owner and owner:match("^%d+") == scope.pid then scope.dialogs[lp] = true end
                            if lp:match("^%d+") == scope.pid or scope.dialogs[lp] then kept[#kept + 1] = line end
                        end
                    end
                    out = table.concat(kept, "\n")
                end
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
                    done(true, tostring(out) .. "\n\nMonitors:\n" .. tostring(screens))
                end, HANDS)
            end, HANDS)
            return
        end
        run("pleamar-wm", argv, function(out, code)
            --  Stopped from the monitor's pill: the whole turn ends, not
            --  only this step.
            if code ~= 0 and tostring(out):find("stopped the agent", 1, true) then
                done(false, "The user stopped you from the monitor. Stop now.", nil, { stopped = true })
                return
            end
            --  Its window closed: nothing to hold on to any more.
            local gone = code ~= 0 and tostring(out):find("window gone", 1, true) ~= nil
            done(code == 0, code == 0 and (out ~= "" and tostring(out) or "Done.") or tostring(out), nil, gone and { gone = true } or nil)
        end, stdin and { errors = true, env = HANDS.env, input = stdin } or HANDS)
    end

    return { HANDS = HANDS, STATE = STATE, window_name = window_name, nice = nice, agent_args = agent_args, exec = exec }
end
