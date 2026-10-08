-- Windows owns delivery; callbacks are consumed only from our native scene queue.
local task_notice, pending_notices, polling_notices = 0, {}, false
local function notice_error()
    text["tasks.status"] = tr("Windows could not show the task notification.")
end
local function poll_notices()
    if polling_notices or next(pending_notices) == nil then return end
    polling_notices = true
    after(500, function()
        local function complete(events, code)
            polling_notices = false
            for tag, entry in pairs(pending_notices) do
                if os.time() >= entry.expires then
                    pending_notices[tag] = nil
                    pcall(native_sys.call_async, "notifications.cancel", {tag}, function() end)
                end
            end
            if code == 0 and type(events) == "table" then
                for _, event in ipairs(events) do
                    local entry = type(event) == "table" and pending_notices[event.tag]
                    if entry and event.action == "dismissed" then
                        pending_notices[event.tag] = nil
                    elseif entry and entry.allowed[event.action] then
                        pending_notices[event.tag] = nil
                        -- A task callback re-resolves its current task before acting.
                        local ok = pcall(entry.callback, event.action)
                        if not ok then notice_error() end
                    end
                end
            end
            poll_notices()
        end
        local ok = pcall(native_sys.ask_async, "notifications.actions", {}, complete)
        if not ok then complete(nil, -1) end
    end)
end
local function notice(title, body, actions, then_)
    task_notice += 1
    local tag = string.format("task%08x%04x", bit32.band(os.time(), 0xffffffff), task_notice % 65536)
    local args = {title, body, tag}
    if then_ and actions and #actions > 0 then
        local count = 0
        for _ in pairs(pending_notices) do count += 1 end
        if count >= 64 then notice_error(); return end
        local allowed = {default = true}
        for _, action in ipairs(actions) do allowed[action[1]] = true end
        pending_notices[tag] = {callback = then_, allowed = allowed, expires = os.time() + 21600}
        args[4] = actions
    end
    local function complete(_, code)
        if code ~= 0 then pending_notices[tag] = nil; notice_error() end
        poll_notices()
    end
    local ok = pcall(native_sys.call_async, "notifications.publish", args, complete)
    if not ok then complete(nil, -1) end
end
