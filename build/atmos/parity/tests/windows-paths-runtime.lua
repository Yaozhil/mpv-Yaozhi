local mp = require 'mp'
local utils = require 'mp.utils'
local input = assert(io.open(assert(os.getenv('YAOZHI_WINDOWS_TEST_INPUT')), 'rb'))
local payload = assert(utils.parse_json(input:read('*a')))
input:close()
local result = {checks = {}, loaded = {}, mode = payload.mode}
local function check(name, actual, expected)
    result.checks[#result.checks + 1] = {
        name = name, actual = actual, expected = expected,
        pass = actual == expected,
    }
end
local function write_result()
    local output = assert(io.open(assert(os.getenv('YAOZHI_WINDOWS_TEST_OUTPUT')), 'wb'))
    output:write(assert(utils.format_json(result)))
    output:close()
end
mp.register_event('shutdown', write_result)
if payload.mode == 'paths' then
    mp.add_timeout(0.05, function()
        check('stale-PWD-working-directory', mp.get_property('working-directory'), payload.cwd)
        for _, item in ipairs(payload.paths) do
            local actual, err = mp.command_native({'normalize-path', item.input})
            check(item.name, actual or ('ERROR:' .. tostring(err)), item.expected)
        end
        write_result()
        mp.commandv('quit', 0)
    end)
else
    mp.register_event('file-loaded', function()
        result.loaded[#result.loaded + 1] = {
            path = mp.get_property('path'),
        }
    end)
    mp.register_event('playback-restart', function()
        local entry = result.loaded[#result.loaded]
        if not entry then return end
        local params = mp.get_property_native('audio-params') or {}
        entry.channels = params['channel-count']
        entry.samplerate = params.samplerate
    end)
end
