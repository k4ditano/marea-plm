-- What was chosen goes out on the output, where Marea reads it
-- (logic/builder.luau), with this monitor's name, which she gave it.
local old = {}
do
    local list = sys.ask("env", "BUILD_OLD") or ""
    for item in list:gmatch("[^;]+") do
        local id, x, y, w, h, name = item:match("^([^|]*)|(%-?%d+)|(%-?%d+)|(%d+)|(%d+)|(.*)$")
        if id then old[#old + 1] = { id = id, x = tonumber(x), y = tonumber(y), w = tonumber(w), h = tonumber(h), name = name } end
    end
    local rows = {}
    for k, o in ipairs(old) do rows[k] = { x = o.x, y = o.y, w = o.w, h = o.h, name = o.name } end
    model.old = rows
end
on("picked", function()
    local x, y = math.min(fact.x0, fact.x1), math.min(fact.y0, fact.y1)
    log(string.format("BUILD pick %d %d %d %d", x, y, math.abs(fact.x1 - fact.x0), math.abs(fact.y1 - fact.y0)))
end)
on("edit", function(i)
    local o = old[(tonumber(i) or -1) + 1]
    if o then log("BUILD edit " .. o.id) end
end)
on("cancel", function() log("BUILD cancel") end)
