-- The native service keeps window identities and capture coordinates together.
-- Approval stays in shared chat logic; this adapter only executes its decision.
return function(native_sys)
    local generation = 0
    local epoch = nil
    local actions = {
        desktop_focus = {"focus"}, desktop_to_monitor = {"send", "monitor"},
        desktop_type = {"type", "text"}, desktop_key = {"key", "key"},
        desktop_type_secret = {"type_secret", "name"},
        desktop_hotkey = {"hotkey", "keys"},
        desktop_click = {"click", "x", "y", "button", "count"},
        desktop_scroll = {"scroll", "x", "y", "direction", "steps"},
        desktop_drag = {"drag", "x1", "y1", "x2", "y2"},
    }
    local defaults = {button="left", count=1, direction="down", steps=3}
    local function box(value)
        value = value or {}
        return string.format("%sx%s at %s,%s", tostring(value.width), tostring(value.height), tostring(value.x), tostring(value.y))
    end
    return function(tool, args, complete)
        if tool == "cancel" or tool == "done" then
            generation += 1
            epoch = nil
            if tool == "cancel" then
                -- This is a constant-time native invalidation, not queued
                -- behind captures or input already waiting on the worker.
                local ok, error = pcall(native_sys.call, "desktop.cancel")
                if not ok then complete(false, tostring(error)) end
            end
            pcall(native_sys.call_async, "desktop.done", {}, function() end)
            return true
        end
        local current = generation
        local function answer(ok, words, extra)
            if current == generation then complete(ok, words, extra) end
        end
        if tool == "desktop_windows" then
            local ok, error = pcall(native_sys.ask_async, "desktop.windows", {}, function(state, error)
                if current ~= generation then return end
                if error then answer(false, tostring(error)); return end
                if type(state) ~= "table" or type(state.windows) ~= "table" then answer(false, "Invalid native window catalog."); return end
                if type(state.epoch) ~= "number" then answer(false, "The native window catalog has no cancellation token."); return end
                epoch = state.epoch
                local programs = {}
                local lines = {"Windows uses the shared foreground keyboard and pointer. Window ids below are opaque catalog ids, not OS process ids."}
                for _, window in ipairs(state.windows) do
                    programs[tostring(window.id)] = tostring(window.program)
                    lines[#lines+1] = string.format("%s %s «%s» %s on %s%s%s%s", tostring(window.id), tostring(window.program), tostring(window.title),
                        box(window.box), tostring(window.monitor), window.focused and " user keyboard" or "", window.minimized and " minimized" or "",
                        window.dialogof ~= "" and (" dialog of " .. tostring(window.dialogof)) or "")
                end
                lines[#lines+1] = "Monitors:"
                for _, monitor in ipairs(state.monitors or {}) do
                    lines[#lines+1] = string.format("%s %s %s%s", tostring(monitor.id), tostring(monitor.name), box(monitor.box), monitor.primary and " primary" or "")
                end
                answer(true, table.concat(lines, "\n"), {programs=programs})
            end)
            if not ok then answer(false, tostring(error)) end
            return true
        end
        if tool == "desktop_look" then
            if epoch == nil then answer(false, "List windows before looking at them."); return true end
            local ok, error = pcall(native_sys.ask_async, "desktop.look", {args.pid}, function(image, error)
                if error then answer(false, tostring(error)); return end
                if type(image) ~= "table" or type(image.data) ~= "string" then answer(false, "The native capture returned no image."); return end
                answer(true, string.format("Window %s: %sx%s physical pixels. Look again after each action.", tostring(args.pid), tostring(image.width), tostring(image.height)),
                    {image={data=image.data}})
            end)
            if not ok then answer(false, tostring(error)) end
            return true
        end
        local action = actions[tool]
        if not action then return false end
        if epoch == nil then answer(false, "List windows before acting on them."); return true end
        local values = {epoch, args.pid}
        for i=2,#action do
            local value = args[action[i]]
            if value == nil then value = defaults[action[i]] end
            if value == nil then answer(false, "Missing desktop argument: " .. action[i]); return true end
            values[#values+1] = value
        end
        local ok, error = pcall(native_sys.call_async, "desktop." .. action[1], values, function(error, code)
            answer(code == 0, code == 0 and "Windows accepted the action. Use desktop_look to verify the result." or tostring(error))
        end)
        if not ok then answer(false, tostring(error)) end
        return true
    end
end
