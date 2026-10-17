-- ── building a piece of the desktop with her (BUILDER.md) ─────────
--  You draw where something should go —a bar along the top, a dock, a box
--  for a widget— and tell her in the chat what it should be. She writes it in
--  pleamar, and since pleamar paints a scene again each time it is saved, it
--  grows on your screen while she works. Every change is a version you can
--  undo; «Keep it» keeps it running with her, «Throw it away» takes it away.
--
--  Each creation is a folder in hers: creations/<id>/ with its scene, its
--  logic, its versions and creation.json (what it is, where, what it was
--  allowed, the conversation). Only this writes there: the model proposes,
--  and every file goes through the checks below before it is written.
--
--  What a creation may ask the system for is decided here by fixed rules,
--  never by the model: what is harmless goes through, what is dangerous is
--  refused, and anything else is asked of you in plain words.
--  marea.luau loads it; the chat (logic/chat.luau) hands it the builder's
--  tools and its conversation.
return function(shared)
    local hooks, home_dir = shared.hooks, shared.home_dir
    local FOLDER = tostring(sys.ask("files.folder") or "")
    local base = sys.ask("env", "XDG_STATE_HOME")
    if base == nil or base == "" then base = home_dir .. "/.local/state" end
    --  Where her engine can see a picture (its sandbox's /state).
    local STATE = base .. "/marea-plm/agent"
    local on_hyprland = (sys.ask("env", "HYPRLAND_INSTANCE_SIGNATURE") or "") ~= ""

    local current = nil      -- the creation being built: its record (creation.json)
    local surface_box        -- (below)
    local scene_id = nil     -- its scene, running (spawn's id)
    --  What its scene says (its logic's errors, its log(), its permissions):
    --  the last lines, for the model to read. Without them it could not tell
    --  its own mistake from pleamar's, and blamed pleamar.
    local said = {}
    local function heard(line)
        line = tostring(line)
        if line:match("^timing") or line:match("^cycle") or line:match("^render ·") or line:match("^text ") then return end
        said[#said + 1] = line
        if #said > 60 then table.remove(said, 1) end
    end
    local function lately()
        if #said == 0 then return "" end
        local from = math.max(1, #said - 30)
        return "\n\nWhat the creation has said lately (its log: logic errors, log(), permissions):\n" .. table.concat(said, "\n", from)
    end
    local skill = nil        -- pleamar's guide to writing scenes, read once
    local desktop = nil      -- and its guide to the desktop
    local source = ""        -- pleamar's source, where there is one
    local chat = nil         -- what the chat lends (see `attach`)

    fact["build.on"] = false
    text["build.name"] = ""

    local function where(id) return "creations/" .. id end
    --  The model calls them scene.plm and scene.luau; on disk they carry the
    --  creation's id, because pleamar names a scene's socket and its files
    --  folder after its file: two kept creations both called «scene» would
    --  answer for each other and share their things.
    local function disk(id, file)
        if file == "scene.plm" then return id .. ".plm" end
        if file == "scene.luau" then return id .. ".luau" end
        return file
    end
    local function path_of(id, file) return FOLDER .. "/" .. where(id) .. "/" .. disk(id, file) end
    local function record_save()
        if current then pcall(sys.call, "files.write", where(current.id) .. "/creation.json", current) end
    end
    local function read(id, file)
        local ok, t = pcall(sys.ask, "files.read", where(id) .. "/" .. disk(id, file))
        if ok and type(t) == "string" then return t end
        return nil
    end
    local function index()
        local ok, t = pcall(sys.ask, "files.read", "creations/index.json", "json")
        return (ok and type(t) == "table") and t or { list = {} }
    end
    local function index_save(ix) pcall(sys.call, "files.write", "creations/index.json", ix) end

    -- ── what a creation may ask the system for ──
    --  Programs, by what they do. Harmless ones are allowed without asking;
    --  dangerous ones are refused (the model is told to do without them);
    --  every shell and interpreter, and anything unknown, is asked, because
    --  through them anything can be done.
    local SAFE_RUN = {
        date = "read the date and time", playerctl = "control the music that is playing",
        brightnessctl = "change the screen's brightness", ["notify-send"] = "show notifications",
        wpctl = "change the volume", pactl = "change the volume and the sound devices",
        uptime = "see how long the computer has been on", uname = "see the system's name",
        hostname = "see the computer's name", whoami = "see your user name",
    }
    local DANGER_RUN = {
        rm = "delete files", rmdir = "delete folders", shred = "destroy files", unlink = "delete files",
        dd = "write straight onto disks", truncate = "empty files", wipefs = "erase disks",
        fdisk = "change the disks' partitions", parted = "change the disks' partitions",
        mount = "mount disks", umount = "unmount disks",
        sudo = "do things as the administrator", pkexec = "do things as the administrator",
        su = "do things as another user", doas = "do things as the administrator",
        chmod = "change who can open files", chown = "change who owns files", chattr = "change how files can be changed",
        systemctl = "start, stop and change system services", loginctl = "end sessions",
        shutdown = "turn the computer off", reboot = "restart the computer", poweroff = "turn the computer off", halt = "stop the computer",
        passwd = "change passwords", useradd = "create users", usermod = "change users", userdel = "delete users",
        crontab = "run things on its own at times", iptables = "change the firewall", nft = "change the firewall", ufw = "change the firewall",
        ssh = "connect to other computers", scp = "send files to other computers", rsync = "copy files elsewhere",
        nc = "open network connections", ncat = "open network connections", socat = "open network connections",
        pacman = "install or remove software", yay = "install or remove software", paru = "install or remove software",
        apt = "install or remove software", dnf = "install or remove software", flatpak = "install or remove software",
        mv = "move and replace files", cp = "copy over files", tee = "write files", install = "replace files",
        kill = "close programs", pkill = "close programs", killall = "close programs",
    }
    local INTERPRETERS = {
        sh = 1, bash = 1, zsh = 1, fish = 1, dash = 1, ksh = 1, busybox = 1, env = 1, xargs = 1, find = 1, awk = 1, sed = 1,
        python = 1, python3 = 1, perl = 1, ruby = 1, node = 1, lua = 1, luajit = 1, php = 1, osascript = 1,
    }
    --  Services pleamar brings: listening is harmless; acting on the system
    --  is asked; a few are not for something made in a chat.
    local SAFE_SERVICES = {
        clock = 1, ["clock.seconds"] = 1, audio = 1, media = 1, network = 1, battery = 1, brightness = 1,
        workspaces = 1, window = 1, apps = 1, tray = 1, notifications = 1, bluetooth = 1,
        files = 1, ["files.write"] = 1, ["files.remove"] = 1,
    }
    local ASK_SERVICES = {
        ["audio.*"] = "change the volume and the sound devices", ["audio.volume"] = "change the volume",
        ["media.*"] = "control the music that is playing", ["brightness.*"] = "change the screen's brightness",
        ["workspaces.*"] = "switch workspaces", ["workspaces.focus"] = "switch workspaces",
        ["window.*"] = "move and close your windows", ["apps.launch"] = "open programs",
        ["notifications.*"] = "answer and clear notifications", ["tray.*"] = "use the icons in the tray",
        ["network.*"] = "turn the network on and off, and connect to Wi-Fi",
        ["bluetooth.*"] = "connect and disconnect Bluetooth devices",
        clipboard = "read what you copy", ["clipboard.set"] = "put things in what you copy",
        env = "read the session's settings (environment)", ["session.*"] = "log out, restart or turn off the computer",
    }
    local DANGER_SERVICES = { auth = "check your password" }

    --  What a scene's permissions {} blocks ask for: programs and services.
    local function asks_of(content)
        local runs, services = {}, {}
        for block in tostring(content):gmatch("permissions%s*{(.-)}") do
            for part in (block .. ";"):gmatch("([^;]*);") do
                local key, values = part:match("^%s*(%a+)%s*:(.*)$")
                if key then
                    for v in values:gmatch('"([^"]*)"') do
                        if key == "run" then runs[#runs + 1] = v elseif key == "services" then services[#services + 1] = v end
                    end
                end
            end
        end
        return runs, services
    end
    local function has(list, v)
        for _, x in ipairs(list or {}) do if x == v then return true end end
        return false
    end
    --  Of what this content asks for, what is new: refused (a reason each),
    --  to ask (in plain words), and harmless.
    local function judge(content)
        local runs, services = asks_of(content)
        local approved = current.approved
        local refused, ask, fine = {}, {}, { run = {}, services = {} }
        for _, r in ipairs(runs) do
            if not has(approved.run, r) then
                local name = r:match("([^/]+)$") or r
                if DANGER_RUN[name] or name:match("^mkfs") then
                    refused[#refused + 1] = string.format(tr("run «%s», which can %s"), r, tr(DANGER_RUN[name] or "format disks"))
                --  By its whole path it may be anything with a known name:
                --  asked, never taken as harmless.
                elseif r:find("/", 1, true) then
                    ask[#ask + 1] = { run = r, words = string.format(tr("run «%s», a program Marea does not know"), r) }
                elseif SAFE_RUN[name] then
                    table.insert(fine.run, r)
                elseif INTERPRETERS[name] then
                    ask[#ask + 1] = { run = r, words = string.format(tr("run «%s»: a program that runs other programs. Through it, this creation could do anything on your computer"), r) }
                else
                    ask[#ask + 1] = { run = r, words = string.format(tr("run «%s», a program Marea does not know"), r) }
                end
            end
        end
        for _, s in ipairs(services) do
            if not has(approved.services, s) then
                if DANGER_SERVICES[s] then
                    refused[#refused + 1] = tr(DANGER_SERVICES[s])
                elseif SAFE_SERVICES[s] then
                    table.insert(fine.services, s)
                else
                    ask[#ask + 1] = { service = s, words = ASK_SERVICES[s] and tr(ASK_SERVICES[s]) or string.format(tr("use «%s» of the system"), s) }
                end
            end
        end
        return refused, ask, fine
    end
    local function approve(ask, fine)
        for _, r in ipairs(fine.run) do if not has(current.approved.run, r) then table.insert(current.approved.run, r) end end
        for _, s in ipairs(fine.services) do if not has(current.approved.services, s) then table.insert(current.approved.services, s) end end
        for _, a in ipairs(ask or {}) do
            if a.run and not has(current.approved.run, a.run) then table.insert(current.approved.run, a.run) end
            if a.service and not has(current.approved.services, a.service) then table.insert(current.approved.services, a.service) end
        end
    end

    -- ── looking around the computer, as a developer would ──
    --  To find where some data lives or how another app gets it. Reading is
    --  done at once; a program that is not a known reader is asked of you
    --  with its whole command; a dangerous one is refused; and files that may
    --  hold passwords or keys are asked even to read.
    local READERS = {
        ls = 1, cat = 1, head = 1, tail = 1, grep = 1, rg = 1, fd = 1, find = 1, which = 1, file = 1, stat = 1,
        wc = 1, du = 1, df = 1, ps = 1, uname = 1, date = 1, whoami = 1, free = 1, uptime = 1, lsblk = 1,
        lscpu = 1, tree = 1, jq = 1, realpath = 1, readlink = 1, basename = 1, dirname = 1, sort = 1, uniq = 1,
    }
    local FIND_ACTS = { ["-delete"] = 1, ["-exec"] = 1, ["-execdir"] = 1, ["-ok"] = 1, ["-okdir"] = 1, ["-fprint"] = 1, ["-fprintf"] = 1, ["-fls"] = 1 }
    local SECRET_WORDS = { "%.ssh", "%.gnupg", "password", "keyring", "auth%.json", "%.netrc", "credential", "%.env",
        "cookies", "logins%.json", "key4%.db", "login data", "token", "secret", "/etc/shadow", "%.pki", "wallet" }
    local function secretive(words)
        for _, w in ipairs(words) do
            local low = tostring(w):lower()
            for _, s in ipairs(SECRET_WORDS) do
                if low:find(s) then return true end
            end
        end
        return false
    end
    local function home_path(p)
        p = tostring(p or "")
        if p:sub(1, 2) == "~/" then return home_dir .. p:sub(2) end
        if p == "~" then return home_dir end
        return p
    end
    --  What to do with one: nil now, { ask, detail } or { refuse, note }.
    local function judge_system(tool, args)
        if tool == "system_read" then
            if secretive({ args.path }) then
                return { ask = string.format(tr("Marea wants to read «%s», a file that may hold passwords or keys."), tostring(args.path)) .. "\n" .. tostring(args.why or ""), detail = tr("Reading a private file") }
            end
            return nil
        end
        local program = tostring(args.program or "")
        local name = program:match("([^/]+)$") or program
        local list = type(args.args) == "table" and args.args or {}
        local command = program .. (#list > 0 and (" " .. table.concat(list, " ")) or "")
        if DANGER_RUN[name] or name:match("^mkfs") then
            return { refuse = "Refused: «" .. name .. "» can " .. (DANGER_RUN[name] or "format disks") .. ". Find it out another way.",
                      note = string.format(tr("Marea did not let it run «%s», which can %s."), name, tr(DANGER_RUN[name] or "format disks")) }
        end
        if secretive(list) then
            return { ask = tr("Marea wants to run on your computer, touching files that may hold passwords or keys:") .. "\n" .. command .. "\n" .. tostring(args.why or ""), detail = tr("A private file") }
        end
        local acts = false
        if name == "find" then for _, a in ipairs(list) do if FIND_ACTS[a] then acts = true end end end
        if READERS[name] and not acts then return nil end
        local warn = INTERPRETERS[name] and ("\n" .. tr("It is a program that runs other programs: it can do anything on your computer.")) or ""
        return { ask = tr("Marea wants to run on your computer:") .. "\n" .. command .. warn .. "\n" .. tostring(args.why or ""), detail = tr("Running a program") }
    end
    local function system_do(tool, args, done)
        if tool == "system_read" then
            run("sh", { "-c", 'head -c 65536 -- "$0"', home_path(args.path) }, function(out, code)
                done(code == 0, code == 0 and tostring(out) or ("Could not read it: " .. tostring(out)))
            end, { errors = true })
            return
        end
        local argv = { "-c", 'cd "$HOME" && timeout 20 "$0" "$@" 2>&1 | head -c 24576', home_path(args.program) }
        for _, a in ipairs(type(args.args) == "table" and args.args or {}) do argv[#argv + 1] = tostring(a) end
        run("sh", argv, function(out, code)
            done(true, "Exit " .. tostring(code) .. ":\n" .. tostring(out))
        end, { errors = true })
    end

    -- ── its scene, on the screen ──
    local function check(done)
        if not current then done(false, "Nothing is being built.") return end
        run("pleamar", { "--check", path_of(current.id, "scene.plm") }, function(out, code)
            done(code == 0, (tostring(out or ""):gsub("%s+$", "")) .. lately())
        end, { errors = true })
    end
    local function start_scene()
        if scene_id or not current then return end
        local ok, id = pcall(spawn, "pleamar", { "--scene", path_of(current.id, "scene.plm"), "--no-hud" }, function(line)
            log("build · " .. tostring(line))
            heard(line)
        end, function(_, code)
            log("build · its scene ended", code)
            scene_id = nil
        end, { errors = true })
        if ok then scene_id = id else log("build · its scene could not start: " .. tostring(id)) end
    end
    local function stop_scene()
        if scene_id then kill(scene_id, "term"); scene_id = nil end
    end

    -- ── where it was drawn ──
    --  The monitors as the compositor says them: name, place and size.
    local function monitors(done)
        local function parse(txt)
            local out = {}
            for block in (tostring(txt or "") .. "\n\n"):gmatch("(Monitor .-)\n\n") do
                local name = block:match("^Monitor (%S+)")
                local w, h, x, y = block:match("(%d+)x(%d+)@[%d%.]+ at (%-?%d+)x(%-?%d+)")
                local scale = tonumber(block:match("scale: ([%d%.]+)")) or 1
                if name and w then
                    out[#out + 1] = { name = name, x = tonumber(x), y = tonumber(y), w = math.floor(tonumber(w) / scale + 0.5), h = math.floor(tonumber(h) / scale + 0.5) }
                end
            end
            done(out)
        end
        if on_hyprland then run("hyprctl", { "monitors" }, parse) else run("pleamar-wm", { "hyprctl", "monitors" }, parse) end
    end
    --  What a drawing is, by its shape and place: a strip against the top or
    --  the bottom is a bar, low and centred a dock, anything else a widget.
    --  The surface block puts it there.
    local function shape(r)
        local x, y, w, h, mw, mh = r.x, r.y, r.w, r.h, r.mw, r.mh
        local screens = string.format('screens: "%s"', r.monitor)
        if w >= mw * 0.6 and y <= 16 then
            return "bar", string.format("surface { size: full, %d; anchor: top; reserve: %d; %s; keyboard: none }", h, h, screens), mw, h
        elseif w >= mw * 0.6 and y + h >= mh - 16 then
            return "bar", string.format("surface { size: full, %d; anchor: bottom; reserve: %d; %s; keyboard: none }", h, h, screens), mw, h
        elseif y + h >= mh - 60 and math.abs(x + w / 2 - mw / 2) < mw * 0.12 then
            return "dock", string.format("surface { size: %d, %d; anchor: bottom; margin: 0, 0, %d, 0; %s; keyboard: none }", w, h, math.max(0, mh - y - h), screens), w, h
        end
        return "widget", string.format("surface { size: %d, %d; anchor: top_left; margin: %d, 0, 0, %d; %s; keyboard: none }", w, h, y, x, screens), w, h
    end
    --  Where a scene's surface block puts it on its monitor: size, anchor,
    --  margin. nil if it cannot be told (a size from a fact).
    surface_box = function(content, r)
        local block = tostring(content or ""):match("surface%s*{(.-)}")
        if not block then return nil end
        local w, h = block:match("size:%s*([%w]+)%s*,%s*([%w]+)")
        w = w == "full" and r.mw or tonumber(w)
        h = h == "full" and r.mh or tonumber(h)
        if not (w and h) then return nil end
        local anchor = block:match("anchor:%s*([%a_]+)") or "center"
        local m = { 0, 0, 0, 0 }
        local ms = block:match("margin:%s*([%-%d%s,]+)")
        if ms then
            local list = {}
            for n in ms:gmatch("%-?%d+") do list[#list + 1] = tonumber(n) end
            if #list == 1 then m = { list[1], list[1], list[1], list[1] } elseif #list >= 4 then m = list end
        end
        local x, y = (r.mw - w) / 2, (r.mh - h) / 2
        if anchor:find("left") then x = m[4] elseif anchor:find("right") then x = r.mw - w - m[2] end
        if anchor:find("top") then y = m[1] elseif anchor:find("bottom") then y = r.mh - h - m[3] end
        return x, y, w, h
    end
    local function placeholder(name, surface, w, h)
        return string.format([[language 0.1
// Being made with Marea: «%s». She writes it again as it grows.
scene Creation {
    %s
    let w = %d
    let h = %d
    prop t = 0
    spin t by 0.35
    box { from: 0, 0; size: w, h; corner: min(h, w) * 0.3; color: #0c1c19; opacity: 75%% }
    box { from: 0, 0; size: w, h; corner: min(h, w) * 0.3; stroke: 2; color: #7fe0c4; opacity: 35%% + 25%% * sin(t * 360) }
    box { from: 0, 0; size: w * (0.5 + 0.5 * sin(t * 180)), h; corner: min(h, w) * 0.3; color: #7fe0c4; opacity: 10%% }
    text "%s" { at: w / 2, h / 2; anchor: center; size: 13; color: #cfeee4; opacity: 80%% }
}
]], name, surface, w, h, tr("Marea is making it…"))
    end

    -- ── beginning, and coming back to one ──
    local function context()
        if not current then return nil end
        local files = {}
        for _, f in ipairs({ "scene.plm", "scene.luau", "icon.svg" }) do
            if read(current.id, f) then files[#files + 1] = f end
        end
        --  Where the desktop's own code is, to read how it gets what it shows:
        --  Marea's folder (she runs from it) and pleamar's source, if it is here.
        local code = { Marea = sys.ask("env", "PWD") or "" }
        if source ~= "" then code["pleamar (its source, docs and examples)"] = source end
        return { name = current.name, kind = current.kind, region = current.region, files = files, skill = skill, desktop = desktop, code = code }
    end
    local function open(record)
        current = record
        fact["build.on"] = true
        text["build.name"] = record.name
        start_scene()
        if chat then chat.begin(record.history or {}, record.rows or {}) end
    end
    --  A drawing that falls mostly on a creation already there edits it.
    local function overlapping(r)
        for _, item in ipairs(index().list) do
            if not item.thrown and item.region and item.region.monitor == r.monitor then
                local o = item.region
                local ix = math.max(0, math.min(o.x + o.w, r.x + r.w) - math.max(o.x, r.x))
                local iy = math.max(0, math.min(o.y + o.h, r.y + r.h) - math.max(o.y, r.y))
                if ix * iy > 0.5 * math.min(o.w * o.h, r.w * r.h) then return item.id end
            end
        end
        return nil
    end
    local function load(id)
        local ok, t = pcall(sys.ask, "files.read", where(id) .. "/creation.json", "json")
        return (ok and type(t) == "table") and t or nil
    end
    local function stop_kept(id)
        if shared.kept and shared.kept[id] then kill(shared.kept[id], "term"); shared.kept[id] = nil end
    end
    local function create(r)
        local kind, surface, w, h = shape(r)
        local ix = index()
        local n = 1
        for _, item in ipairs(ix.list) do if item.kind == kind then n += 1 end end
        local names = { bar = tr("Bar"), dock = tr("Dock"), widget = tr("Widget") }
        local id = "c" .. os.date("%Y%m%d%H%M%S")
        local record = { id = id, name = names[kind] .. " " .. n, kind = kind, region = r, made = os.time(),
                         approved = { run = {}, services = {} }, versions = {}, history = {}, rows = {}, kept = false }
        current = record
        pcall(sys.call, "files.write", where(id) .. "/" .. disk(id, "scene.plm"), placeholder(record.name, surface, w, h))
        --  Its logic, from the start, even with nothing in it: pleamar decides
        --  when a scene starts whether it has logic, and one that started
        --  without it never got the services a later version asked for.
        pcall(sys.call, "files.write", where(id) .. "/" .. disk(id, "scene.luau"), "-- Its logic: Marea writes it here when it needs one.\n")
        record_save()
        table.insert(ix.list, { id = id, name = record.name, kind = kind, region = r })
        index_save(ix)
        log("build · new " .. kind .. " " .. id .. " on " .. r.monitor)
        open(record)
    end
    local function begin()
        if current then if chat then chat.show() end return end
        if not skill then
            run("pleamar", { "--docs", "skill" }, function(out, code)
                if code == 0 then skill = tostring(out) end
            end)
            run("pleamar", { "--docs", "desktop" }, function(out, code)
                if code == 0 then desktop = tostring(out) end
            end)
            --  Built from its source (two folders up from the program), or
            --  installed with it beside (pleamar-update keeps it there).
            run("sh", { "-c", 'd=$(dirname "$(readlink -f "$(command -v pleamar)")"); for c in "$d/../.." "$HOME/.local/share/pleamar/src/pleamar"; do [ -f "$c/Cargo.toml" ] && { readlink -f "$c"; exit 0; }; done' }, function(out)
                source = tostring(out or ""):gsub("%s+$", "")
            end)
        end
        --  A breather so whatever was open (the finder) is gone from the screen.
        after(250, function()
            run("slurp", {}, function(sel, code)
                local x, y, w, h = (sel or ""):match("(%-?%d+),(%-?%d+) (%d+)x(%d+)")
                if code ~= 0 or x == nil then return end
                x, y, w, h = tonumber(x), tonumber(y), tonumber(w), tonumber(h)
                if w < 8 or h < 8 then return end
                monitors(function(list)
                    local cx, cy = x + w / 2, y + h / 2
                    local m = list[1]
                    for _, s in ipairs(list) do
                        if cx >= s.x and cx < s.x + s.w and cy >= s.y and cy < s.y + s.h then m = s end
                    end
                    if not m then log("build · no monitor"); return end
                    local r = { monitor = m.name, mw = m.w, mh = m.h, x = x - m.x, y = y - m.y, w = w, h = h, gx = x, gy = y }
                    local again = overlapping(r)
                    if again then
                        local record = load(again)
                        if record then stop_kept(again); open(record); return end
                    end
                    create(r)
                end)
            end)
        end)
    end
    on("build_start", begin)
    hooks.build = begin

    -- ── the tools she has while building ──
    local OWN = { creation_read = 1, creation_write = 1, creation_check = 1, creation_look = 1, creation_poke = 1, pleamar_docs = 1, system_run = 1, system_read = 1 }
    local WORDS = {
        creation_read = "Reading %s", creation_write = "Writing %s", creation_check = "Checking it",
        creation_look = "Looking at it", pleamar_docs = "Reading pleamar's %s",
        system_run = "Running %s", system_read = "Reading %s", creation_poke = "Trying it: %s",
    }
    local api = {}
    function api.owns(tool) return OWN[tool] ~= nil end
    function api.active() return current ~= nil end
    function api.context() return context() end
    function api.said(tool, args)
        return string.format(tr(WORDS[tool] or tool), tostring(args.file or args.topic or args.program or args.path or args.order or ""))
    end
    --  Before it is done: nil to do it now, { ask = …, detail = … } for a card,
    --  { refuse = for the model, note = for you }.
    function api.propose(tool, args)
        if not current then return { refuse = "Nothing is being built now: tell the user to draw where it goes first (Build, in Marea's finder).", note = "" } end
        if tool == "system_run" or tool == "system_read" then return judge_system(tool, args) end
        if tool ~= "creation_write" then return nil end
        local file = tostring(args.file or "")
        if not file:match("%.plm$") then return nil end
        local refused, ask, fine = judge(args.content)
        if #refused > 0 then
            return {
                refuse = "Marea refused this version: it asks to " .. table.concat(refused, "; ") .. ". A creation made in a chat may not do that. Do it without it (a pleamar service, or leave that part out) and tell the user plainly.",
                note = tr("Marea did not let it ") .. table.concat(refused, "; ") .. ".",
            }
        end
        if #ask > 0 then
            local lines = {}
            for _, a in ipairs(ask) do lines[#lines + 1] = "· " .. a.words end
            args._ask = ask
            return { ask = string.format(tr("«%s» wants to:"), current.name) .. "\n" .. table.concat(lines, "\n") .. "\n" .. tostring(args.why or ""), detail = tr("New permissions") }
        end
        return nil
    end
    --  Doing it: `done(ok, words, extra)` answers the model.
    function api.perform(tool, args, done)
        if not current then done(false, "Nothing is being built.") return end
        local id = current.id
        if tool == "system_run" or tool == "system_read" then
            system_do(tool, args, done)
        elseif tool == "creation_poke" then
            --  What --say understands, and nothing else: it is the creation's own socket.
            local order = tostring(args.order or "")
            if not (order:match("^press [%w_]+$") or order:match("^fact [%w_.]+ %S+$") or order:match("^emit [%w_]+") or order:match("^get [%w_.]+$")) then
                done(false, "Not an order it understands: press ZONE, fact NAME VALUE, emit EVENT, get NAME.")
                return
            end
            run("pleamar", { "--say", id, order }, function(out, code)
                done(code == 0, tostring(out or ""))
            end, { errors = true })
        elseif tool == "creation_read" then
            local t = read(id, tostring(args.file or ""))
            done(true, t or "(there is no such file yet)")
        elseif tool == "creation_check" then
            check(done)
        elseif tool == "creation_write" then
            local file, content = tostring(args.file or ""), tostring(args.content or "")
            if not file:match("^[a-z0-9_-]+%.[a-z]+$") then done(false, "Not a file of the creation.") return end
            if file:match("%.plm$") then
                local _, ask, fine = judge(content)
                approve(args._ask or ask, fine)
            end
            --  The version before, kept: «Undo» puts it back.
            local n = #current.versions + 1
            pcall(sys.call, "files.write", where(id) .. "/versions/" .. n .. "-" .. file, content)
            table.insert(current.versions, { n = n, file = file, why = tostring(args.why or ""), at = os.time() })
            pcall(sys.call, "files.write", where(id) .. "/" .. disk(id, file), content)
            record_save()
            start_scene()
            if file:match("%.plm$") or file:match("%.luau$") then
                said = {}
                --  A moment for it to reload and its logic to run, so what that
                --  said is in the answer.
                after(1500, function()
                    check(function(ok, words)
                        done(true, (ok and "Written; it compiles, and it is on the screen now: " or "Written, but it does NOT compile (the screen keeps the last good version): ") .. words)
                    end)
                end)
            else
                done(true, "Written.")
            end
        elseif tool == "creation_look" then
            local r = current.region
            local m = 24
            --  The surface as the scene says it is now, with where it was
            --  drawn, and a margin: what grew past the drawing is seen too.
            local x0, y0, x1, y1 = r.x, r.y, r.x + r.w, r.y + r.h
            local sx, sy, sw, sh = surface_box(read(id, "scene.plm"), r)
            if sx then x0, y0, x1, y1 = math.min(x0, sx), math.min(y0, sy), math.max(x1, sx + sw), math.max(y1, sy + sh) end
            x0, y0 = math.max(0, x0 - m), math.max(0, y0 - m)
            x1, y1 = math.min(r.mw, x1 + m), math.min(r.mh, y1 + m)
            local ox, oy = r.gx - r.x, r.gy - r.y
            local dest = STATE .. "/build-look.png"
            run("grim", { "-g", string.format("%d,%d %dx%d", math.floor(ox + x0), math.floor(oy + y0), math.floor(x1 - x0), math.floor(y1 - y0)), dest }, function(out, code)
                if code == 0 then
                    done(true, string.format("The creation on the screen now, with %d px around it.", m), { image = { path = "/state/build-look.png" } })
                else
                    done(false, "Could not take the picture: " .. tostring(out))
                end
            end, { errors = true })
        elseif tool == "pleamar_docs" then
            local topic = tostring(args.topic or "reference")
            local argv = topic == "grammar" and { "--grammar" } or { "--docs", topic }
            run("pleamar", argv, function(out, code)
                if code ~= 0 then done(false, tostring(out)) return end
                local all = tostring(out)
                local find = tostring(args.find or ""):lower()
                if find == "" then
                    done(true, #all > 30000 and (all:sub(1, 30000) .. "\n[…cut: ask with `find` for the rest]") or all)
                    return
                end
                --  Only the paragraphs that mention it.
                local found, size = {}, 0
                for para in (all .. "\n\n"):gmatch("(.-)\n\n+") do
                    if para:lower():find(find, 1, true) then
                        if size + #para > 24000 then break end
                        found[#found + 1] = para
                        size += #para
                    end
                end
                done(true, #found > 0 and table.concat(found, "\n\n") or ("Nothing in «" .. topic .. "» mentions «" .. find .. "»."))
            end, { errors = true })
        else
            done(false, "Marea does not know that tool.")
        end
    end

    -- ── undo, keep, throw away ──
    on("build_undo", function()
        if not current or #current.versions == 0 then return end
        local last = table.remove(current.versions)
        local before = nil
        for k = #current.versions, 1, -1 do
            if current.versions[k].file == last.file then before = current.versions[k]; break end
        end
        local text_before = before and read(current.id, "versions/" .. before.n .. "-" .. last.file)
        if text_before then
            pcall(sys.call, "files.write", where(current.id) .. "/" .. disk(current.id, last.file), text_before)
        elseif last.file == "scene.plm" then
            local _, surface, w, h = shape(current.region)
            pcall(sys.call, "files.write", where(current.id) .. "/" .. disk(current.id, "scene.plm"), placeholder(current.name, surface, w, h))
        else
            pcall(sys.call, "files.remove", where(current.id) .. "/" .. disk(current.id, last.file))
        end
        record_save()
        if chat then chat.note(string.format(tr("Undone: %s"), last.why ~= "" and last.why or last.file)) end
    end)
    local function finish()
        if chat then
            local rows, history = chat.finish()
            current.rows, current.history = rows, history
        end
        record_save()
        current = nil
        fact["build.on"] = false
        text["build.name"] = ""
    end
    on("build_keep", function()
        if not current then return end
        current.kept = true
        --  It goes on running, now as one of hers: she starts it with her.
        if scene_id then
            shared.kept = shared.kept or {}
            shared.kept[current.id] = scene_id
            scene_id = nil
        end
        log("build · kept " .. current.id)
        finish()
    end)
    on("build_discard", function()
        if not current then return end
        stop_scene()
        current.kept = false
        current.thrown = true
        local ix = index()
        for _, item in ipairs(ix.list) do if item.id == current.id then item.thrown = true end end
        index_save(ix)
        log("build · thrown away " .. current.id)
        finish()
    end)
    --  Closing the chat in the middle leaves it as it is, not kept: the next
    --  «Build» over it carries on.
    on("build_leave", function()
        if not current then return end
        stop_scene()
        finish()
    end)

    --  The ones you kept run with her.
    shared.kept = {}
    for _, item in ipairs(index().list) do
        if not item.thrown then
            local record = load(item.id)
            if record and record.kept then
                local ok, id = pcall(spawn, "pleamar", { "--scene", path_of(item.id, "scene.plm"), "--no-hud" }, function(line)
                    log("build · " .. item.id .. " · " .. tostring(line))
                end, function() shared.kept[item.id] = nil end, { errors = true })
                if ok then shared.kept[item.id] = id end
            end
        end
    end

    --  The chat lends what it needs to hold the builder's conversation:
    --  begin(history, rows), finish() → rows, history, note(text), show().
    function api.attach(lent) chat = lent end
    shared.builder = api
    return api
end
