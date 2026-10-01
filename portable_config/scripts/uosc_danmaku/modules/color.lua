-- Hash once per source; repaint only when colour settings change.
local M = {}
local floor = math.floor
local WHITE = 0xFFFFFF
-- Pink/blue/cyan accents softened to sit beside authored colours and white.
-- Shared opacity and outlines still come from the existing renderer.
local palette = {0xA8D8F5, 0x9BDDDD, 0xB4DFC5, 0xF2CCB0, 0xF1BCD1, 0xCFC4EF}

local function valid(value)
    return type(value) == 'number' and value == value and value >= 0
        and value <= WHITE and value == floor(value)
end

-- Explicit formats avoid confusing a decimal colour with a six-digit hex.
-- ASS is BGR; its optional alpha byte must not override global opacity.
function M.normalize(value, format)
    if type(value) == 'number' then return valid(value) and value or nil end
    if type(value) ~= 'string' then return nil end
    local s = value:match('^%s*(.-)%s*$')
    local ass = s:match('^&[hH](%x+)&?$')
    if ass then
        if #ass ~= 6 and #ass ~= 8 then return nil end
        ass = ass:sub(-6)
        return tonumber(ass:sub(5, 6)..ass:sub(3, 4)..ass:sub(1, 2), 16)
    end
    local hex = s:match('^#(%x+)$') or s:match('^0[xX](%x+)$')
    if hex then
        if #hex == 3 and s:sub(1, 1) == '#' then
            hex = hex:gsub('.', '%0%0')
        end
        return #hex == 6 and tonumber(hex, 16) or nil
    end
    local r, g, b = s:lower():match('^rgb%(%s*(%d+)%s*,%s*(%d+)%s*,%s*(%d+)%s*%)$')
    if r then
        r, g, b = tonumber(r), tonumber(g), tonumber(b)
        if r > 255 or g > 255 or b > 255 then return nil end
        return r * 65536 + g * 256 + b
    end
    if format == 'hex' or s:find('[a-fA-F]') then
        return s:match('^%x%x%x%x%x%x$') and tonumber(s, 16) or nil
    end
    local n = s:match('^%d+$') and tonumber(s)
    return valid(n) and n or nil
end

function M.csv(value)
    local fields = {}
    for field in (value .. ','):gmatch('(.-),') do fields[#fields + 1] = field end
    return fields
end

-- Byte hash stays exact in Lua numbers and stable across platforms/reloads.
-- Rank preserves the original 25% membership and colours while allowing a
-- monotonic percentage: increasing coverage never recolours existing accents.
local function supplement(comment)
    local key = tostring(comment.color_key or comment.text or '')
    local h = 5381
    for i = 1, #key do h = (h * 33 + key:byte(i)) % 2147483647 end
    comment._supplement_rank = (h % 4) * 25 + floor(h / 24) % 25
    comment._supplement_color = palette[floor(h / 4) % #palette + 1]
end

function M.percentage(value)
    local n = tonumber(value)
    if not n or n ~= n or n == math.huge or n == -math.huge then return 25 end
    return math.max(0, math.min(100, floor(n)))
end

function M.resolve(comment, enabled, percentage, force_white)
    if force_white then return WHITE end
    local original = M.normalize(comment.color)
    if original ~= nil and original ~= WHITE then return original end
    if not enabled then return original or WHITE end
    if comment._supplement_color == nil or comment._supplement_rank == nil then
        supplement(comment)
    end
    return comment._supplement_rank < M.percentage(percentage) and comment._supplement_color or WHITE
end

function M.tag(color)
    local r = floor(color / 65536)
    local g = floor(color / 256) % 256
    local b = color % 256
    return string.format('{\\c&H%02X%02X%02X&}', b, g, r)
end

-- Only replace our generated primary-colour tag. Position, timing, alpha,
-- borders and the escaped source text stay byte-for-byte intact.
function M.apply(event, enabled, percentage, force_white)
    if not event.color_source then return false end
    local color = M.resolve(event.color_source, enabled, percentage, force_white)
    if color == event.render_color then return false end
    event.text = event.text:gsub('{\\c&H%x%x%x%x%x%x&}', M.tag(color), 1)
    event.render_color = color
    event._overlay_text = nil
    event._overlay_static_prefix = nil
    event._overlay_static_ass = nil
    return true
end

function M.recolor(events, enabled, percentage, force_white)
    for _, event in ipairs(events or {}) do M.apply(event, enabled, percentage, force_white) end
end

return M
