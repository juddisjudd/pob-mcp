-- Minimal, self-contained JSON encode/decode for the pob-mcp bridge.
-- Only handles what the bridge protocol needs: objects, arrays, strings,
-- numbers, booleans, and null. No external dependencies (LuaJIT 5.1 safe).

local json = {}

-- Sentinel used for JSON `null`, since Lua `nil` can't live inside a table.
json.null = setmetatable({}, { __tostring = function() return "null" end })

-- Wrap a table so encode() treats it as a JSON array even if empty or if it
-- has non-sequential-looking content. Use for "always an array" fields.
local arrayMeta = { __jsonarray = true }
function json.array(t)
	t = t or {}
	return setmetatable(t, { __jsonarray = true })
end

local function isArray(t)
	local mt = getmetatable(t)
	if mt and mt.__jsonarray then
		return true
	end
	if mt then
		return false
	end
	local n = 0
	for k in pairs(t) do
		if type(k) ~= "number" then
			return false
		end
		n = n + 1
	end
	for i = 1, n do
		if t[i] == nil then
			return false
		end
	end
	return true
end

local escapes = {
	['"'] = '\\"', ["\\"] = "\\\\", ["\n"] = "\\n", ["\r"] = "\\r",
	["\t"] = "\\t", ["\b"] = "\\b", ["\f"] = "\\f",
}

local function encodeString(s)
	local out = { '"' }
	for i = 1, #s do
		local c = s:sub(i, i)
		local esc = escapes[c]
		if esc then
			out[#out + 1] = esc
		elseif c:byte() < 0x20 then
			out[#out + 1] = string.format("\\u%04x", c:byte())
		else
			out[#out + 1] = c
		end
	end
	out[#out + 1] = '"'
	return table.concat(out)
end

local encodeValue

local function encodeArray(t, seen)
	local parts = {}
	local n = 0
	for i in pairs(t) do
		if type(i) == "number" and i > n then
			n = i
		end
	end
	for i = 1, n do
		parts[i] = encodeValue(t[i], seen)
	end
	return "[" .. table.concat(parts, ",") .. "]"
end

local function encodeObject(t, seen)
	local parts = {}
	for k, v in pairs(t) do
		if type(k) == "string" then
			parts[#parts + 1] = encodeString(k) .. ":" .. encodeValue(v, seen)
		end
	end
	return "{" .. table.concat(parts, ",") .. "}"
end

encodeValue = function(v, seen)
	local t = type(v)
	if v == json.null then
		return "null"
	elseif t == "nil" then
		return "null"
	elseif t == "boolean" then
		return v and "true" or "false"
	elseif t == "number" then
		if v ~= v or v == math.huge or v == -math.huge then
			return "null" -- NaN/Inf aren't valid JSON; avoid emitting a broken frame
		end
		if v == math.floor(v) and math.abs(v) < 1e15 then
			return string.format("%d", v)
		end
		return string.format("%.17g", v)
	elseif t == "string" then
		return encodeString(v)
	elseif t == "table" then
		seen = seen or {}
		if seen[v] then
			error("json.encode: cannot encode a table that contains itself")
		end
		seen[v] = true
		local result
		if next(v) == nil then
			result = getmetatable(v) and getmetatable(v).__jsonarray and "[]" or "{}"
		elseif isArray(v) then
			result = encodeArray(v, seen)
		else
			result = encodeObject(v, seen)
		end
		seen[v] = nil
		return result
	else
		error("json.encode: cannot encode a value of type " .. t)
	end
end

function json.encode(value)
	return encodeValue(value, nil)
end

-- Decoder: a small recursive-descent parser.

local function decodeError(str, pos, msg)
	local line = 1
	for i = 1, pos - 1 do
		if str:sub(i, i) == "\n" then
			line = line + 1
		end
	end
	error(string.format("json.decode: %s at position %d (line %d)", msg, pos, line))
end

local function skipWhitespace(str, pos)
	local _, stop = str:find("^[ \t\r\n]*", pos)
	return stop + 1
end

local decodeValue

local function decodeString(str, pos)
	-- pos points at the opening quote
	local out = {}
	local i = pos + 1
	local len = #str
	while true do
		if i > len then
			decodeError(str, pos, "unterminated string")
		end
		local c = str:sub(i, i)
		if c == '"' then
			return table.concat(out), i + 1
		elseif c == "\\" then
			local nc = str:sub(i + 1, i + 1)
			if nc == "u" then
				local hex = str:sub(i + 2, i + 5)
				local code = tonumber(hex, 16)
				if not code then
					decodeError(str, i, "invalid \\u escape")
				end
				if code < 0x80 then
					out[#out + 1] = string.char(code)
				elseif code < 0x800 then
					out[#out + 1] = string.char(0xC0 + math.floor(code / 0x40), 0x80 + code % 0x40)
				else
					out[#out + 1] = string.char(
						0xE0 + math.floor(code / 0x1000),
						0x80 + math.floor(code / 0x40) % 0x40,
						0x80 + code % 0x40
					)
				end
				i = i + 6
			else
				local map = { ['"'] = '"', ["\\"] = "\\", ["/"] = "/", n = "\n", r = "\r", t = "\t", b = "\b", f = "\f" }
				local rep = map[nc]
				if not rep then
					decodeError(str, i, "invalid escape \\" .. tostring(nc))
				end
				out[#out + 1] = rep
				i = i + 2
			end
		else
			out[#out + 1] = c
			i = i + 1
		end
	end
end

local function decodeNumber(str, pos)
	local s, e, numStr = str:find("^(-?%d+%.?%d*[eE]?[+-]?%d*)", pos)
	if not numStr then
		decodeError(str, pos, "invalid number")
	end
	return tonumber(numStr), e + 1
end

local function decodeArray(str, pos)
	local result = json.array({})
	pos = skipWhitespace(str, pos + 1)
	if str:sub(pos, pos) == "]" then
		return result, pos + 1
	end
	local i = 1
	while true do
		local value
		value, pos = decodeValue(str, pos)
		result[i] = value
		i = i + 1
		pos = skipWhitespace(str, pos)
		local c = str:sub(pos, pos)
		if c == "," then
			pos = skipWhitespace(str, pos + 1)
		elseif c == "]" then
			return result, pos + 1
		else
			decodeError(str, pos, "expected ',' or ']' in array")
		end
	end
end

local function decodeObject(str, pos)
	local result = {}
	pos = skipWhitespace(str, pos + 1)
	if str:sub(pos, pos) == "}" then
		return result, pos + 1
	end
	while true do
		if str:sub(pos, pos) ~= '"' then
			decodeError(str, pos, "expected string key")
		end
		local key
		key, pos = decodeString(str, pos)
		pos = skipWhitespace(str, pos)
		if str:sub(pos, pos) ~= ":" then
			decodeError(str, pos, "expected ':' after key")
		end
		pos = skipWhitespace(str, pos + 1)
		local value
		value, pos = decodeValue(str, pos)
		result[key] = value
		pos = skipWhitespace(str, pos)
		local c = str:sub(pos, pos)
		if c == "," then
			pos = skipWhitespace(str, pos + 1)
		elseif c == "}" then
			return result, pos + 1
		else
			decodeError(str, pos, "expected ',' or '}' in object")
		end
	end
end

decodeValue = function(str, pos)
	pos = skipWhitespace(str, pos)
	local c = str:sub(pos, pos)
	if c == '"' then
		return decodeString(str, pos)
	elseif c == "{" then
		return decodeObject(str, pos)
	elseif c == "[" then
		return decodeArray(str, pos)
	elseif c == "t" and str:sub(pos, pos + 3) == "true" then
		return true, pos + 4
	elseif c == "f" and str:sub(pos, pos + 4) == "false" then
		return false, pos + 5
	elseif c == "n" and str:sub(pos, pos + 3) == "null" then
		return json.null, pos + 4
	elseif c == "-" or c:match("%d") then
		return decodeNumber(str, pos)
	else
		decodeError(str, pos, "unexpected character '" .. tostring(c) .. "'")
	end
end

function json.decode(str)
	if str == nil or str == "" then
		return nil
	end
	local pos = skipWhitespace(str, 1)
	if pos > #str then
		return nil
	end
	local value = decodeValue(str, pos)
	return value
end

return json
