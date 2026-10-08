-- A head slot can hold a hat or headphones. Glasses and the cup are independent.
local head_slot = { hat = "phones", phones = "hat" }
local changing = false
local saved = type(settings.wears) == "table" and settings.wears or {}
for _, piece in ipairs(PIECES) do fact["wears." .. piece] = saved[piece] == true end
-- Deterministically repair settings written by versions that allowed overlap.
if fact["wears.hat"] and fact["wears.phones"] then fact["wears.hat"] = false end
for _, piece in ipairs(PIECES) do
    on("fact:wears." .. piece, function(value)
        if changing then return end
        changing = true
        local other = head_slot[piece]
        if value and other then fact["wears." .. other] = false end
        save_settings()
        changing = false
    end)
end
fact.windows_shelf_folded = settings.shelf_folded == true
on("fact:windows_shelf_folded", save_settings)
