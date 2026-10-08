-- Consent belongs to Windows. Opening Marea must never request it implicitly.
return function(native_sys, notice)
    local access = "unavailable"
    local requesting = false
    local function update(value)
        access = value.access or "unavailable"
        requesting = value.requesting == true
        fact.windows_notifications_allowed = access == "allowed"
        fact.windows_notifications_requesting = requesting
        fact.windows_notifications_requestable = access == "unspecified" and not requesting
        if requesting then
            text.windows_notifications_status = "Esperando el permiso de Windows…"
        elseif value.error and value.error ~= "" then
            text.windows_notifications_status = value.error
        elseif access == "allowed" then
            text.windows_notifications_status = "Conectada al centro de notificaciones de Windows"
        elseif access == "denied" then
            text.windows_notifications_status = "Permiso denegado. Puedes habilitarlo en Privacidad de Windows."
        elseif access == "unspecified" then
            text.windows_notifications_status = "Permite que Marea lea y descarte tus notificaciones."
        else
            text.windows_notifications_status = "Windows no ofrece acceso a las notificaciones."
        end
    end
    if not native_sys.watch("notifications.state", update) then update({}) end
    on("windows_notifications_enable", function()
        if access ~= "unspecified" or requesting then return end
        requesting = true
        fact.windows_notifications_requesting = true
        fact.windows_notifications_requestable = false
        local ok, error = pcall(native_sys.call_async, "notifications.request_access", {}, function(error, code)
            if code ~= 0 then
                requesting = false
                fact.windows_notifications_requesting = false
                fact.windows_notifications_requestable = access == "unspecified"
                notice(error)
            end
        end)
        if not ok then
            requesting = false
            fact.windows_notifications_requesting = false
            fact.windows_notifications_requestable = access == "unspecified"
            notice(tostring(error))
        end
    end)
    local function watch(callback)
        local first = true
        return native_sys.watch("notifications", function(list)
            -- Existing Windows history fills the drops without replaying every
            -- old toast as a new animated arrival when Marea starts/reloads.
            fact.windows_notifications_sync = first
            first = false
            local ok, error = pcall(callback, list)
            fact.windows_notifications_sync = false
            if not ok then notice(tostring(error)) end
        end)
    end
    local function refresh(row, incoming, fallback)
        local app = string.upper(incoming.app ~= "" and incoming.app or fallback)
        local changed = row.app ~= app or row.title ~= incoming.title or row.detail ~= incoming.body or row.icon ~= incoming.icon
        row.app, row.title, row.detail = app, incoming.title, incoming.body
        row.actions, row.icon = incoming.actions, incoming.icon
        row.time = incoming.time
        return changed
    end
    local function age(created, now, label_now)
        if type(created) ~= "number" then return "" end
        local seconds = math.max(0, now - created)
        if seconds < 60 then return label_now end
        if seconds < 3600 then return math.floor(seconds / 60) .. " min" end
        if seconds < 86400 then return math.floor(seconds / 3600) .. " h" end
        return math.floor(seconds / 86400) .. " d"
    end
    return watch, refresh, age
end
