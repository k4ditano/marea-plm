-- Windows applications own their menus. Keep every live icon reachable without
-- letting a long notification area overlap Marea's heading.
do
    local items, live, rows = {}, {}, {}
    local page, selected, pending = 1, nil, false
    local page_size = 6
    local function report(message) notice(tostring(message)) end
    local function send(name, key)
        if not live[key] then report("La aplicacion ya no esta en la bandeja."); return end
        if pending then return end
        pending = true
        local ok, error = pcall(sys.call_async, name, { key }, function(error, code)
            pending = false
            if code ~= 0 then report(error) end
        end)
        if not ok then pending = false; report(error) end
    end
    local function render()
        rows = {}
        if selected and live[selected] then
            text["systray.title"] = live[selected].title
            rows = {
                { label = "‹  Aplicaciones", action = "back" },
                { label = "Abrir", action = "activate", key = selected },
                { label = "Menu de la aplicacion", action = "context", key = selected },
            }
        else
            selected = nil
            local pages = math.max(1, math.ceil(#items / page_size))
            page = math.clamp(page, 1, pages)
            text["systray.title"] = "Aplicaciones · " .. page .. "/" .. pages
            if page > 1 then rows[#rows + 1] = { label = "‹  Anterior", action = "previous" } end
            for i = (page - 1) * page_size + 1, math.min(page * page_size, #items) do
                local item = items[i]
                rows[#rows + 1] = { label = item.title ~= "" and item.title or item.id, action = "select", key = item.key }
            end
            if page < pages then rows[#rows + 1] = { label = "Siguiente  ›", action = "next" } end
        end
        model.options = rows
    end
    local function open_list()
        selected, page = nil, 1
        fact.page = "systray"
        render()
    end
    local function index(list, i)
        if type(i) ~= "number" or i < 0 or i % 1 ~= 0 then return nil end
        return list[i + 1]
    end
    assert(sys.watch("tray", function(list)
        items, live = list, {}
        for _, item in ipairs(items) do live[item.key] = item end
        local visible = {}
        local count = #items > 4 and 3 or #items
        for i = 1, count do visible[#visible + 1] = items[i] end
        if #items > 4 then
            -- A local navigation control, never passed to the native service
            -- as an application or a pretend tray identifier.
            visible[#visible + 1] = { more = true, title = "Todas las aplicaciones", icon = "" }
        end
        model.icons = visible
        if fact.page == "systray" then render() end
    end))
    on("systray_activate", function(i)
        local item = index(model.icons, i)
        if not item then return end
        if item.more then open_list() else send("tray.activate", item.key) end
    end)
    on("systray_menu", function(i)
        local item = index(model.icons, i)
        if not item then return end
        if item.more then open_list() else fact.page = "none"; send("tray.context", item.key) end
    end)
    on("systray_pick", function(i)
        local row = index(rows, i)
        if not row then return end
        if row.action == "next" then page += 1
        elseif row.action == "previous" then page -= 1
        elseif row.action == "back" then selected = nil
        elseif row.action == "select" then selected = row.key
        else fact.page = "none"; send("tray." .. row.action, row.key); return end
        render()
    end)
end
