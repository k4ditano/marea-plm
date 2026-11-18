-- Marea's logic, in pieces: her sky: the weather where you are.
-- marea.luau loads it, and hands it what it uses of its own.
return function(shared)
    local hooks, PIECES, save_settings, settings = shared.hooks, shared.PIECES, shared.save_settings, shared.settings
    -- ── her sky: the weather where you are ─────────────────────────────
    --  The city is chosen in the calendar (its strip at the top) and kept in her
    --  settings; without one, she guesses it from the time zone (Europe/Madrid:
    --  Madrid). Open-Meteo is asked every quarter of an hour —no account, no
    --  key— and the scene draws it on the time card.
    local WX_WORDS = { [0] = "Clear sky", [1] = "Mostly clear", [2] = "Partly cloudy", [3] = "Overcast",
        [45] = "Fog", [48] = "Fog", [51] = "Drizzle", [53] = "Drizzle", [55] = "Drizzle", [56] = "Drizzle", [57] = "Drizzle",
        [61] = "Rain", [63] = "Rain", [65] = "Heavy rain", [66] = "Rain", [67] = "Rain",
        [71] = "Snow", [73] = "Snow", [75] = "Heavy snow", [77] = "Snow",
        [80] = "Showers", [81] = "Showers", [82] = "Heavy showers", [85] = "Snow showers", [86] = "Snow showers",
        [95] = "Thunderstorm", [96] = "Thunderstorm", [99] = "Thunderstorm" }
    local WX_RAIN = { [51] = 0.3, [53] = 0.4, [55] = 0.5, [56] = 0.4, [57] = 0.5, [61] = 0.5, [63] = 0.75, [65] = 1,
        [66] = 0.6, [67] = 0.9, [80] = 0.6, [81] = 0.8, [82] = 1, [95] = 0.9, [96] = 1, [99] = 1 }
    local WX_SNOW = { [71] = 0.4, [73] = 0.7, [75] = 1, [77] = 0.3, [85] = 0.6, [86] = 1 }
    local sky_place = nil
    local sky_code = nil
    local function sky_words()
        text["wx.summary"] = sky_code ~= nil and tr(WX_WORDS[sky_code] or "Clear sky") or ""
    end
    local function url_encode(s)
        return (tostring(s):gsub("[^%w%-_%.~]", function(c) return string.format("%%%02X", string.byte(c)) end))
    end
    local function sky_fetch()
        if sky_place == nil then return end
        local url = string.format("https://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f&current=temperature_2m,weather_code,cloud_cover&daily=temperature_2m_max,temperature_2m_min&forecast_days=1&timezone=auto", sky_place.lat, sky_place.lon)
        run("curl", { "-s", "--max-time", "10", url }, function(out)
            local ok, v = pcall(json.decode, tostring(out or ""))
            if not ok or type(v) ~= "table" or type(v.current) ~= "table" then return end
            local c = v.current
            sky_code = tonumber(c.weather_code) or 0
            local rain, snow = WX_RAIN[sky_code] or 0, WX_SNOW[sky_code] or 0
            local cloud = (tonumber(c.cloud_cover) or 0) / 100
            if rain > 0 or snow > 0 then cloud = math.max(cloud, 0.8) end
            fact["wx.temp"] = tonumber(c.temperature_2m) or 0
            fact["wx.cloud"] = cloud
            fact["wx.rain"] = rain
            fact["wx.snow"] = snow
            fact["wx.fog"] = (sky_code == 45 or sky_code == 48) and 1 or 0
            fact["wx.storm"] = sky_code >= 95 and 1 or 0
            if type(v.daily) == "table" then
                fact["wx.hi"] = tonumber((v.daily.temperature_2m_max or {})[1]) or fact["wx.temp"]
                fact["wx.lo"] = tonumber((v.daily.temperature_2m_min or {})[1]) or fact["wx.temp"]
            end
            fact["wx.ok"] = true
            sky_words()
        end)
    end
    local function sky_find(name)
        local q = tostring(name or ""):match("^%s*(.-)%s*$")
        if q == "" then return end
        local lang = fact.locale == "es" and "es" or fact.locale == "pt_br" and "pt" or "en"
        run("curl", { "-s", "--max-time", "10", "https://geocoding-api.open-meteo.com/v1/search?count=1&format=json&language=" .. lang .. "&name=" .. url_encode(q) }, function(out)
            local ok, v = pcall(json.decode, tostring(out or ""))
            local r = ok and type(v) == "table" and type(v.results) == "table" and v.results[1] or nil
            if r == nil or r.latitude == nil then
                log("her sky · no city called", q)
                return
            end
            sky_place = { name = tostring(r.name), lat = tonumber(r.latitude), lon = tonumber(r.longitude) }
            settings.city = sky_place
            text["wx.place"] = sky_place.name
            save_settings()
            log("her sky ·", sky_place.name)
            sky_fetch()
        end)
    end
    if type(settings.city) == "table" and tonumber(settings.city.lat) ~= nil then
        sky_place = { name = tostring(settings.city.name or ""), lat = tonumber(settings.city.lat), lon = tonumber(settings.city.lon) }
        text["wx.place"] = sky_place.name
        sky_fetch()
    else
        run("timedatectl", { "show", "-p", "Timezone", "--value" }, function(out)
            local city = tostring(out or ""):match("([^/%s]+)%s*$")
            if city then sky_find((city:gsub("_", " "))) end
        end)
    end
    every(15 * 60 * 1000, sky_fetch)
    on("submit:city_q", function(value)
        sky_find(value)
        text.city_q = ""
    end)
    table.insert(hooks.language, sky_words)

    --  And what she had on, as it was left: each piece that is not there, off.
    if type(settings.wears) == "table" then
        for _, piece in ipairs(PIECES) do
            if settings.wears[piece] == true then fact["wears." .. piece] = true end
        end
    end
    for _, piece in ipairs(PIECES) do
        on("fact:wears." .. piece, function() save_settings() end)
    end
end
