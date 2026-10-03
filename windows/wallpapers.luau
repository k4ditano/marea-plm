-- Runs in the generated profile's settings scope, after save_settings exists.
local wall_list, wall_offset, wall_busy, wall_selected = {}, 0, false, nil
-- A reload discards the selection/callbacks that own a transition. Hide its
-- retained scene surface immediately; its final event cannot commit a choice.
fact["tide.on"] = false
local function ask_wallpaper(name, args, callback)
    local ok, error = pcall(native_sys.ask_async, name, args, callback)
    if not ok then callback(nil, tostring(error)) end
end
local function same_wall(a, b)
    return tostring(a):gsub("\\", "/"):lower() == tostring(b):gsub("\\", "/"):lower()
end
local function wall_now()
    local name = tostring(WALLPAPER):match("([^/\\]+)$") or ""
    model.wallnow = WALLPAPER ~= "" and { { name = name, thumb = WALLPAPER, ready = true } } or {}
end
local function show_walls()
    local cards = {}
    for k = wall_offset + 1, math.min(wall_offset + 9, #wall_list) do
        local item = wall_list[k]
        cards[#cards + 1] = { name = item.name, thumb = item.path, ready = true, current = same_wall(item.path, WALLPAPER) }
    end
    model.walls = cards
end
local function wallpaper_error(error)
    fact.open = true
    fact.page = "walls"
    notice(tostring(error))
end
local function refresh_wallpaper()
    ask_wallpaper("wallpaper.state", {}, function(value, error)
        if error then log("wallpaper:", error); return end
        WALLPAPER = value.current or ""
        wall_now()
        show_walls()
    end)
end
refresh_wallpaper()
on("customize", refresh_wallpaper)
on("walls_open", function()
    ask_wallpaper("wallpaper.list", {}, function(value, error)
        if error then wallpaper_error(error); return end
        WALLPAPER = value.current or ""
        wall_list = value.items or {}
        wall_offset = 0
        wall_now()
        show_walls()
        if #wall_list == 0 then notice("No hay fondos en Imagenes, Wallpapers ni en los fondos de Windows.") end
    end)
end)
on("walls_scroll", function(wheel)
    wall_offset = math.clamp(wall_offset + ((wheel or 0) > 0 and -3 or 3), 0, math.max(#wall_list - 3, 0))
    wall_offset -= wall_offset % 3
    show_walls()
end)
on("wall_pick", function(index)
    local item = wall_list[wall_offset + index + 1]
    if not item or wall_busy or same_wall(item.path, WALLPAPER) then return end
    wall_busy = true
    local home = fact["hosts.1"] and 1 or 0
    local count = math.min(tonumber(fact["screens.count"]) or 0, 2)
    local sizes, pictures = {}, {}
    for k = 0, count - 1 do
        local w, h = fact["windows_tide_width." .. k], fact["windows_tide_height." .. k]
        if type(w) ~= "number" or type(h) ~= "number" or w <= 0 or h <= 0 then
            wall_busy = false; wallpaper_error("Las pantallas aún no están listas para la transición."); return
        end
        sizes[k + 1] = {w, h, text["screen." .. k .. ".name"]}
    end
    if count == 0 then wall_busy = false; wallpaper_error("No hay pantallas disponibles."); return end
    local function prepare(index)
        if index > count then
            -- A hotplug/DPI change during preparation invalidates the crops.
            if math.min(tonumber(fact["screens.count"]) or 0, 2) ~= count then
                wall_busy = false; wallpaper_error("Las pantallas han cambiado. Vuelve a elegir el fondo."); return
            end
            for k, size in ipairs(sizes) do
                if fact["windows_tide_width." .. (k - 1)] ~= size[1]
                    or fact["windows_tide_height." .. (k - 1)] ~= size[2]
                    or text["screen." .. (k - 1) .. ".name"] ~= size[3] then
                    wall_busy = false; wallpaper_error("Las pantallas han cambiado. Vuelve a elegir el fondo."); return
                end
            end
            wall_selected = item.path
            model.tidepics = pictures
            fact["tide.home"] = math.min(home, count - 1)
            emit("tide_start")
            return
        end
        local size = sizes[index]
        ask_wallpaper("wallpaper.preview", { item.path, size[1], size[2] }, function(preview, error)
            if error or type(preview) ~= "string" or preview == "" then
                wall_busy = false; wallpaper_error(error or "No se pudo preparar el fondo."); return
            end
            pictures[index] = {pic = preview}
            prepare(index + 1)
        end)
    end
    prepare(1)
end)
on("tide_done", function()
    local selected = wall_selected
    if not selected then return end
    wall_selected = nil
    local function finished(error)
        emit("tide_away")
        wall_busy = false
        if error then wallpaper_error(error) end
    end
    local ok, queue_error = pcall(native_sys.call_async, "wallpaper.set", { selected }, function(error, code)
        if code ~= 0 then finished(error); return end
        ask_wallpaper("wallpaper.state", {}, function(state, read_error)
            if read_error then finished(read_error); return end
            if not same_wall(state.current, selected) then finished("Windows no ha confirmado el nuevo fondo."); return end
            WALLPAPER = state.current
            save_settings()
            wall_now()
            show_walls()
            finished()
        end)
    end)
    if not ok then finished(tostring(queue_error)) end
end)
