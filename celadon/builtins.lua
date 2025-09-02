function split(sep, target)
    local res = {}

    for _, word in ipairs(string.gmatch(str, "[^"..sep.."]+")) do
        table.insert(res, word)
    end

    return res
end

function join(sep, target)
    local converted = {}

    for _, v in ipairs(target) do
        table.insert(converted, tostring(v))
    end

    return table.concat(target, sep)
end

function table_keys(t)
    local result = {}

    for k, _ in pairs(t) do
        table.insert(result, k)
    end

    return result
end

function table_values(t)
    local result = {}

    for _, v in pairs(t) do
        table.insert(result, v)
    end

    return result
end

return {
    ipairs = ipairs,
    next = next,
    pairs = pairs,
    pcall = pcall,
    tonumber = tonumber,
    tostring = tostring,
    type = type,
    coroutine = {
        create = coroutine.create, resume = coroutine.resume,
        running = coroutine.running, status = coroutine.status,
        wrap = coroutine.wrap
    },
    string = {
        byte = string.byte, char = string.char, find = string.find,
        format = string.format, gmatch = string.gmatch, gsub = string.gsub,
        len = string.len, lower = string.lower, match = string.match,
        rep = string.rep, reverse = string.reverse, sub = string.sub,
        upper = string.upper
    },
    table = {
        insert = table.insert, maxn = table.maxn, remove = table.remove,
        sort = table.sort, unpack = table.unpack, concat = table.concat,
        keys = table_keys, values = table_values,
    },
    math = {
        abs = math.abs, acos = math.acos, asin = math.asin,
        atan = math.atan, atan2 = math.atan2, ceil = math.ceil, cos = math.cos,
        cosh = math.cosh, deg = math.deg, exp = math.exp, floor = math.floor,
        fmod = math.fmod, frexp = math.frexp, huge = math.huge,
        ldexp = math.ldexp, log = math.log, log10 = math.log10, max = math.max,
        min = math.min, modf = math.modf, pi = math.pi, pow = math.pow,
        rad = math.rad, random = math.random, sin = math.sin, sinh = math.sinh,
        sqrt = math.sqrt, tan = math.tan, tanh = math.tanh
    },
    os = {
        clock = os.clock, difftime = os.difftime, time = os.time
    },
    copy = copy, 
    setmetatable = setmetatable,
    print = print,
    error = error,
    debug = {
        getupvalue = debug.getupvalue, upvaluejoin = debug.upvaluejoin, getlocal = debug.getlocal
    },

    split = split,
    join = join,
}
