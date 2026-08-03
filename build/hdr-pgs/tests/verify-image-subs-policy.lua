local state = {
    gamma = 'pq',
    tracks = {
        {type = 'video', selected = true, ['demux-w'] = 3840, ['demux-h'] = 2160},
        {type = 'sub', selected = true, codec = 'hdmv_pgs_subtitle', external = false},
    },
    properties = {
        ['image-subs-colorspace'] = 'video',
    },
    messages = {},
}

package.preload['mp.msg'] = function()
    return setmetatable({}, {__index = function() return function() end end})
end

package.preload['mp.options'] = function()
    return {read_options = function() end}
end

mp = {}

function mp.command_native()
    return '.codex-build/test-image-subs-brightness.conf'
end

function mp.get_property(name, default)
    if name == 'video-params/gamma' then return state.gamma end
    local value = state.properties[name]
    if value == nil then return default end
    return tostring(value)
end

function mp.get_property_native(name, default)
    if name == 'track-list' then return state.tracks end
    if name == 'video-params/w' then return 3840 end
    if name == 'video-params/h' then return 2160 end
    local value = state.properties[name]
    if value == nil then return default end
    return value
end

function mp.set_property(name, value)
    state.properties[name] = value
end

function mp.set_property_number(name, value)
    state.properties[name] = value
end

function mp.register_script_message(name, callback)
    state.messages[name] = callback
end

function mp.observe_property() end
function mp.register_event() end
function mp.osd_message() end

function mp.add_timeout(_, callback)
    callback()
    return {kill = function() end, resume = callback}
end

package.preload['mp'] = function() return mp end

assert(loadfile('portable_config/scripts/image-subs-brightness.lua'))()

local function expect(name, property, expected)
    local actual = state.properties[property]
    assert(actual == expected,
        string.format('%s: expected %s=%s, got %s',
            name, property, tostring(expected), tostring(actual)))
    print(string.format('PASS %-38s %s=%s', name, property, tostring(actual)))
end

expect('auto UHD HDR PGS colorspace', 'image-subs-colorspace', 'video')
expect('auto UHD HDR PGS peak', 'image-subs-hdr-peak', 'video')
expect('published native peak', 'user-data/image-subs-brightness/effective-peak', 'video')

state.messages['set-mode']('sdr')
expect('manual SDR colorspace', 'image-subs-colorspace', 'sdr')
expect('manual SDR peak', 'image-subs-hdr-peak', '203')
expect('published SDR peak', 'user-data/image-subs-brightness/effective-peak', '203')

state.tracks[2].external = true
state.messages['set-mode']('auto')
expect('auto external PGS colorspace', 'image-subs-colorspace', 'sdr')
expect('auto external PGS peak', 'image-subs-hdr-peak', '203')

state.messages['set-mode']('video')
expect('manual video colorspace', 'image-subs-colorspace', 'video')
expect('manual video preserves metadata', 'image-subs-hdr-peak', 'video')

os.remove('.codex-build/test-image-subs-brightness.conf')
print('all image subtitle policy tests passed')
