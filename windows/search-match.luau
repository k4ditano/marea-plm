-- Matching is bounded to names. No browser data or document contents are read.
local from = {"Á","À","Â","Ä","Ã","Å","á","à","â","ä","ã","å","É","È","Ê","Ë","é","è","ê","ë","Í","Ì","Î","Ï","í","ì","î","ï","Ó","Ò","Ô","Ö","Õ","ó","ò","ô","ö","õ","Ú","Ù","Û","Ü","ú","ù","û","ü","Ñ","ñ","Ç","ç"}
local to = "aaaaaaaaaaaaeeeeeeeeiiiiiiiioooooooooouuuuuuuunncc"
local function fold(value)
    value = tostring(value or "")
    for i, c in ipairs(from) do value = value:gsub(c, to:sub(i, i)) end
    local characters = {}
    for _, code in utf8.codes(value) do
        if code < 0x300 or code > 0x36f then characters[#characters + 1] = utf8.char(code) end
    end
    return table.concat(characters):lower()
end
local function near(a, b)
    -- Fuzzy edits apply to ASCII words after accent folding, never UTF-8 bytes.
    if a:find("[^%w]") or b:find("[^%w]") or #a < 4 or math.abs(#a - #b) > 1 then return false end
    local i, j, edits = 1, 1, 0
    while i <= #a and j <= #b do
        if a:sub(i, i) == b:sub(j, j) then i += 1; j += 1
        else
            edits += 1
            if edits > 1 then return false end
            if #a == #b then i += 1; j += 1 elseif #a > #b then i += 1 else j += 1 end
        end
    end
    return edits + ((i <= #a or j <= #b) and 1 or 0) <= 1
end
local function score(name, query)
    name, query = fold(name), fold(query):match("^%s*(.-)%s*$")
    if query == "" then return 0 end
    if name == query then return 1000 end
    if name:sub(1, #query) == query then return 900 end
    if name:find(query, 1, true) then return 800 end
    local words, initials = {}, ""
    for word in name:gmatch("[%w\128-\255]+") do words[#words + 1] = word; initials ..= word:sub(1, 1) end
    if #query >= 2 and initials == query then return 750 end
    local total, count = 0, 0
    for token in query:gmatch("%S+") do
        local best = name:find(token, 1, true) and 600 or nil
        for _, word in ipairs(words) do
            if word:sub(1, #token) == token then best = 700; break end
            if not best and near(token, word) then best = 400 end
        end
        if not best then return nil end
        total += best; count += 1
    end
    return total / math.max(1, count)
end
return { fold = fold, score = score }
