on("clear_all", function()
    -- Snapshot before requesting deletion: a completion may change both lists.
    local pending, seen = {}, {}
    local function add(f)
        if f.id and not seen[f.id] and not finished[f.id] and not snoozed[f.id] and not f.done then
            seen[f.id] = true
            pending[#pending + 1] = f
        end
    end
    for _, f in ipairs(rows) do add(f) end
    for _, n in ipairs(live or {}) do add(row_of(n)) end
    for _, f in ipairs(pending) do
        dismiss_native(f.id, function() remember(f) end)
    end
end)
