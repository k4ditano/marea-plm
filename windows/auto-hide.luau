return function(settings, storage, notice)
    fact.hidden = settings.auto_hide ~= false
    on("windows_toggle_autohide", function()
        local enabled = fact.hidden ~= true
        local candidate = table.clone(settings)
        candidate.auto_hide = enabled
        -- Keep the visible choice and other preferences intact on a failed write.
        local ok, problem = pcall(storage.call, "files.write", "settings.json", candidate)
        if not ok then
            log("auto-hide · " .. tostring(problem))
            notice(tr("Could not save auto-hide preference"))
            return
        end
        settings.auto_hide = enabled
        fact.hidden = enabled
    end)
end
