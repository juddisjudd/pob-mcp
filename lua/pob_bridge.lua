-- pob-mcp Lua bridge
--
-- Drives Path of Building headlessly over a newline-delimited JSON-RPC
-- protocol on stdin/stdout, so the pob-mcp Python MCP server can load,
-- inspect, and mutate a build using PoB's own calculation engine.
--
-- Run as:  luajit <this-file's-absolute-path>  (with CWD set to <pob-install>/src)
--
-- Forked from src/HeadlessWrapper.lua (MIT-licensed, see LICENSE.md in the
-- PathOfBuilding-PoE2 repo) rather than depending on it, since release
-- installs exclude that file (manifest.cfg's [program] exclude-files).
-- Differences from the original:
--   * stdout is reserved for JSON-RPC frames; ConPrintf/print go to stderr.
--   * Deflate/Inflate are real (LuaJIT FFI + zlib, raw deflate/wbits=-15)
--     instead of no-op stubs -- Timeless Jewel data and build import/export
--     codes both depend on them.
--   * continuousIntegrationMode is left off, so ModCache.lua loads normally
--     (the original skips it for mod-parsing test isolation).
--   * Adds the JSON-RPC request loop and RPC method table at the bottom.

-- Resolve our own directory so we can dofile() our sibling json.lua
-- regardless of the process's current working directory (which must be
-- <pob-install>/src for Launch.lua's own relative dofile()s to resolve).
local scriptPath = (arg and arg[0]) or "pob_bridge.lua"
local scriptDir = scriptPath:match("^(.*)[/\\][^/\\]*$") or "."
local json = dofile(scriptDir .. "/json.lua")

-- ===========================================================================
-- Protocol-safe output: keep stdout exclusively for JSON-RPC frames.
-- ===========================================================================

local function stderrPrint(...)
	local n = select("#", ...)
	local parts = {}
	for i = 1, n do
		parts[i] = tostring((select(i, ...)))
	end
	io.stderr:write(table.concat(parts, "\t"), "\n")
end
_G.print = stderrPrint

local function writeFrame(obj)
	io.stdout:write(json.encode(obj), "\n")
	io.stdout:flush()
end

-- ===========================================================================
-- Callbacks (identical to HeadlessWrapper.lua)
-- ===========================================================================

local callbackTable = { }
local mainObject
function runCallback(name, ...)
	if callbackTable[name] then
		return callbackTable[name](...)
	elseif mainObject and mainObject[name] then
		return mainObject[name](mainObject, ...)
	end
end
function SetCallback(name, func)
	callbackTable[name] = func
end
function GetCallback(name)
	return callbackTable[name]
end
function SetMainObject(obj)
	mainObject = obj
end

-- ===========================================================================
-- Image handles (identical to HeadlessWrapper.lua)
-- ===========================================================================

local imageHandleClass = { }
imageHandleClass.__index = imageHandleClass
function NewImageHandle()
	return setmetatable({ }, imageHandleClass)
end
function imageHandleClass:Load(fileName, ...)
	self.valid = true
end
function imageHandleClass:Unload()
	self.valid = false
end
function imageHandleClass:IsValid()
	return self.valid
end
function imageHandleClass:SetLoadingPriority(pri) end
function imageHandleClass:ImageSize()
	return 1, 1
end

-- ===========================================================================
-- Rendering / input / misc host stubs (identical to HeadlessWrapper.lua)
-- ===========================================================================

function RenderInit(flag, ...) end
function GetScreenSize()
	return 1920, 1080
end
function GetScreenScale()
	return 1
end
function GetVirtualScreenSize()
	return GetScreenSize()
end
function GetDPIScaleOverridePercent()
	return 1
end
function SetDPIScaleOverridePercent(scale) end
function SetClearColor(r, g, b, a) end
function SetDrawLayer(layer, subLayer) end
function SetViewport(x, y, width, height) end
function SetDrawColor(r, g, b, a) end
function GetDrawColor(r, g, b, a) end
function DrawImage(imgHandle, left, top, width, height, tcLeft, tcTop, tcRight, tcBottom) end
function DrawImageQuad(imageHandle, x1, y1, x2, y2, x3, y3, x4, y4, s1, t1, s2, t2, s3, t3, s4, t4) end
function DrawString(left, top, align, height, font, text) end
function DrawStringWidth(height, font, text)
	return 1
end
function DrawStringCursorIndex(height, font, text, cursorX, cursorY)
	return 0
end
function StripEscapes(text)
	return text:gsub("%^%d",""):gsub("%^x%x%x%x%x%x%x","")
end
function GetAsyncCount()
	return 0
end
function NewFileSearch() end
function SetWindowTitle(title) end
function GetCursorPos()
	return 0, 0
end
function SetCursorPos(x, y) end
function ShowCursor(doShow) end
function IsKeyDown(keyName) end
function Copy(text) end
function Paste() end
function GetTime()
	return 0
end
function GetScriptPath()
	return ""
end
function GetRuntimePath()
	return ""
end
function GetUserPath()
	return ""
end
function MakeDir(path) end
function RemoveDir(path) end
function SetWorkDir(path) end
function GetWorkDir()
	return ""
end
function LaunchSubScript(scriptText, funcList, subList, ...) end
function AbortSubScript(ssID) end
function IsSubScriptRunning(ssID) end
function LoadModule(fileName, ...)
	if not fileName:match("%.lua") then
		fileName = fileName .. ".lua"
	end
	local func, err = loadfile(fileName)
	if func then
		return func(...)
	else
		error("LoadModule() error loading '"..fileName.."': "..err)
	end
end
function PLoadModule(fileName, ...)
	if not fileName:match("%.lua") then
		fileName = fileName .. ".lua"
	end
	local func, err = loadfile(fileName)
	if func then
		return PCall(func, ...)
	else
		error("PLoadModule() error loading '"..fileName.."': "..err)
	end
end
function PCall(func, ...)
	local ret = { pcall(func, ...) }
	if ret[1] then
		table.remove(ret, 1)
		return nil, unpack(ret)
	else
		return ret[2]
	end
end
function ConPrintf(fmt, ...)
	stderrPrint(string.format(fmt, ...))
end
function ConPrintTable(tbl, noRecurse) end
function ConExecute(cmd) end
function ConClear() end
function SpawnProcess(cmdName, args) end
function OpenURL(url) end
function SetProfiling(isEnabled) end
function Restart() end
function Exit() end
function TakeScreenshot() end

---@return string? provider
---@return string? version
---@return number? status
function GetCloudProvider(fullPath)
	return nil, nil, nil
end

local l_require = require
function require(name)
	-- Hack to stop it looking for lcurl, which we don't really need
	if name == "lcurl.safe" then
		return
	end
	return l_require(name)
end

-- ===========================================================================
-- Real Deflate/Inflate via LuaJIT FFI + zlib (raw deflate, wbits=-15).
--
-- Needed for: build import/export codes (paste-code and share-code flows)
-- and Timeless Jewel lookup tables (src/Modules/DataLegionLookUpTableHelper.lua),
-- both of which use the host Deflate/Inflate functions PoB expects the native
-- runtime to provide. Falls back to a no-op ("") on failure, same as the
-- stubbed original, so startup never crashes if zlib can't be found --
-- callers that need it (load_build_code/save_build_code) check for an empty
-- result and raise a clear RPC error instead.
-- ===========================================================================

local ffiOk, ffi = pcall(require, "ffi")
local zlib

if ffiOk then
	ffi.cdef[[
	typedef struct pob_mcp_z_stream {
		const uint8_t *next_in;
		unsigned int  avail_in;
		unsigned long total_in;
		uint8_t       *next_out;
		unsigned int  avail_out;
		unsigned long total_out;
		const char    *msg;
		void          *state;
		void          *zalloc;
		void          *zfree;
		void          *opaque;
		int            data_type;
		unsigned long  adler;
		unsigned long  reserved;
	} pob_mcp_z_stream;

	int deflateInit2_(pob_mcp_z_stream *strm, int level, int method, int windowBits, int memLevel, int strategy, const char *version, int stream_size);
	int deflate(pob_mcp_z_stream *strm, int flush);
	int deflateEnd(pob_mcp_z_stream *strm);
	int inflateInit2_(pob_mcp_z_stream *strm, int windowBits, const char *version, int stream_size);
	int inflate(pob_mcp_z_stream *strm, int flush);
	int inflateEnd(pob_mcp_z_stream *strm);
	]]

	local function loadZlib()
		local candidates = { }
		local explicit = os.getenv("POB_MCP_ZLIB_PATH")
		if explicit then
			candidates[#candidates + 1] = explicit
		end
		-- Bundled with every Windows PoB install/checkout, relative to CWD == <pob-install>/src
		candidates[#candidates + 1] = "../runtime/zlib1.dll"
		candidates[#candidates + 1] = "zlib1"
		candidates[#candidates + 1] = "z"
		candidates[#candidates + 1] = "libz.so.1"
		candidates[#candidates + 1] = "libz.dylib"
		for _, name in ipairs(candidates) do
			local ok, lib = pcall(ffi.load, name)
			if ok and lib then
				return lib
			end
		end
		return nil
	end
	zlib = loadZlib()
end

local Z_OK, Z_STREAM_END, Z_NO_FLUSH, Z_FINISH, Z_DEFLATED = 0, 1, 0, 4, 8
local ZLIB_VERSION = "1.2.11" -- only the major digit is actually checked by zlib

local function ffiDeflate(data)
	if not zlib then error("zlib is not available on this system", 0) end
	local strm = ffi.new("pob_mcp_z_stream")
	local ret = zlib.deflateInit2_(strm, 9, Z_DEFLATED, -15, 8, 0, ZLIB_VERSION, ffi.sizeof(strm))
	if ret ~= Z_OK then error("deflateInit2_ failed: code " .. ret, 0) end
	local inBuf = ffi.new("uint8_t[?]", #data, data)
	strm.next_in = inBuf
	strm.avail_in = #data
	local bufSize = 65536
	local outBuf = ffi.new("uint8_t[?]", bufSize)
	local chunks = { }
	repeat
		strm.next_out = outBuf
		strm.avail_out = bufSize
		ret = zlib.deflate(strm, Z_FINISH)
		if ret < Z_OK then
			zlib.deflateEnd(strm)
			error("deflate failed: code " .. ret, 0)
		end
		local have = bufSize - strm.avail_out
		if have > 0 then
			chunks[#chunks + 1] = ffi.string(outBuf, have)
		end
	until ret == Z_STREAM_END
	zlib.deflateEnd(strm)
	return table.concat(chunks)
end

local function ffiInflate(data)
	if not zlib then error("zlib is not available on this system", 0) end
	local strm = ffi.new("pob_mcp_z_stream")
	local ret = zlib.inflateInit2_(strm, -15, ZLIB_VERSION, ffi.sizeof(strm))
	if ret ~= Z_OK then error("inflateInit2_ failed: code " .. ret, 0) end
	local inBuf = ffi.new("uint8_t[?]", #data, data)
	strm.next_in = inBuf
	strm.avail_in = #data
	local bufSize = 65536
	local outBuf = ffi.new("uint8_t[?]", bufSize)
	local chunks = { }
	local have = 0
	local iterations = 0
	repeat
		strm.next_out = outBuf
		strm.avail_out = bufSize
		ret = zlib.inflate(strm, Z_NO_FLUSH)
		if ret ~= Z_OK and ret ~= Z_STREAM_END then
			zlib.inflateEnd(strm)
			error("inflate failed: code " .. ret, 0)
		end
		have = bufSize - strm.avail_out
		if have > 0 then
			chunks[#chunks + 1] = ffi.string(outBuf, have)
		end
		iterations = iterations + 1
		if iterations > 100000 then
			zlib.inflateEnd(strm)
			error("inflate: too many iterations, aborting (likely corrupt input)", 0)
		end
	until ret == Z_STREAM_END or (strm.avail_in == 0 and have == 0)
	zlib.inflateEnd(strm)
	return table.concat(chunks)
end

function Deflate(data)
	local ok, result = pcall(ffiDeflate, data)
	if ok then
		return result
	end
	stderrPrint("[pob-mcp] Deflate unavailable: " .. tostring(result))
	return ""
end
function Inflate(data)
	local ok, result = pcall(ffiInflate, data)
	if ok then
		return result
	end
	stderrPrint("[pob-mcp] Inflate unavailable: " .. tostring(result))
	return ""
end

-- ===========================================================================
-- Boot Path of Building
-- ===========================================================================

local bootOk, bootErr = pcall(function()
	dofile("Launch.lua")
	-- Deliberately NOT setting mainObject.continuousIntegrationMode: we want
	-- ModCache.lua to load normally for fast, accurate mod data, unlike the
	-- test harness which skips it to isolate mod-parsing changes.
	runCallback("OnInit")
	runCallback("OnFrame") -- need at least one frame for everything to initialise
	if mainObject.promptMsg then
		error("PoB reported a startup problem: " .. tostring(mainObject.promptMsg), 0)
	end
end)

if not bootOk then
	writeFrame({ id = json.null, error = { message = "bridge init failed: " .. tostring(bootErr) } })
	os.exit(1)
end

-- The build module; once a build is loaded, all the good stuff is in here.
local build = mainObject.main.modes["BUILD"]

-- ===========================================================================
-- Helpers
-- ===========================================================================

local function refreshBuild()
	build.buildFlag = true
	runCallback("OnFrame")
end

local function ensureBuildLoaded()
	if not build or not build.calcsTab or not build.calcsTab.mainOutput then
		error("no build is loaded; call load_build_xml/load_build_code/new_build first", 0)
	end
end

local function scalarOrNull(v)
	local t = type(v)
	if t == "number" or t == "string" or t == "boolean" then
		return v
	end
	return json.null
end

local function isScalar(v)
	local t = type(v)
	return t == "number" or t == "string" or t == "boolean"
end

-- ===========================================================================
-- RPC methods
-- ===========================================================================

local methods = { }

methods.list_gems = function(params)
	params = params or { }
	local query = params.query and tostring(params.query):lower() or nil
	local onlySupports = params.onlySupports
	local limit = tonumber(params.limit) or 50
	local out = json.array({ })
	local total = 0
	for gemId, gemData in pairs(data.gems) do
		local isSupport = (gemData.grantedEffect and gemData.grantedEffect.support) and true or false
		local include = true
		if onlySupports ~= nil then
			include = (isSupport == onlySupports)
		end
		if include and query then
			local nameMatches = gemData.name and gemData.name:lower():find(query, 1, true)
			include = gemId:lower():find(query, 1, true) ~= nil or nameMatches ~= nil
		end
		if include then
			total = total + 1
			if #out < limit then
				out[#out + 1] = { gemId = gemId, name = gemData.name or gemId, isSupport = isSupport }
			end
		end
	end
	table.sort(out, function(a, b) return (a.name or "") < (b.name or "") end)
	return { gems = out, total = total, truncated = (total > #out) }
end

methods.ping = function()
	return { ok = true, buildLoaded = (build ~= nil and build.calcsTab ~= nil and build.calcsTab.mainOutput ~= nil) }
end

methods.new_build = function(params)
	mainObject.main:SetMode("BUILD", false, (params and params.name) or "New Build")
	runCallback("OnFrame")
	build = mainObject.main.modes["BUILD"]
	return { ok = true }
end

methods.load_build_xml = function(params)
	if not params or not params.xml or params.xml == "" then
		error("params.xml is required", 0)
	end
	mainObject.main:SetMode("BUILD", false, params.name or "", params.xml)
	runCallback("OnFrame")
	build = mainObject.main.modes["BUILD"]
	ensureBuildLoaded()
	return { ok = true }
end

methods.load_build_code = function(params)
	if not params or not params.code or params.code == "" then
		error("params.code is required", 0)
	end
	local code = params.code:gsub("%s+", ""):gsub("-", "+"):gsub("_", "/")
	local ok, decoded = pcall(common.base64.decode, code)
	if not ok or not decoded then
		error("failed to base64-decode build code: " .. tostring(decoded), 0)
	end
	local xmlText = Inflate(decoded)
	if not xmlText or xmlText == "" then
		error("failed to decode build code: zlib inflate produced no output (see stderr for the underlying zlib error, or pass raw XML via load_build_xml instead)", 0)
	end
	return methods.load_build_xml({ xml = xmlText, name = params.name })
end

methods.save_build_xml = function()
	ensureBuildLoaded()
	return { xml = build:SaveDB("code") }
end

methods.save_build_code = function()
	ensureBuildLoaded()
	local xmlText = build:SaveDB("code")
	local deflated = Deflate(xmlText)
	if not deflated or deflated == "" then
		error("zlib is not available: cannot produce a share code; use save_build_xml instead", 0)
	end
	local code = common.base64.encode(deflated):gsub("+", "-"):gsub("/", "_")
	return { code = code }
end

methods.get_stats = function(params)
	ensureBuildLoaded()
	local output = build.calcsTab.mainOutput
	local stats = { }
	if params and params.fields then
		for _, key in ipairs(params.fields) do
			stats[key] = scalarOrNull(output[key])
		end
	else
		for key, value in pairs(output) do
			if isScalar(value) then
				stats[key] = value
			end
		end
	end
	return { stats = stats }
end

methods.list_stat_keys = function()
	ensureBuildLoaded()
	local keys = json.array({ })
	for key, value in pairs(build.calcsTab.mainOutput) do
		if isScalar(value) then
			keys[#keys + 1] = key
		end
	end
	table.sort(keys)
	return { keys = keys }
end

methods.get_character = function()
	ensureBuildLoaded()
	local spec = build.spec
	local result = {
		level = build.characterLevel,
		classId = spec.curClassId,
		ascendClassId = spec.curAscendClassId,
		secondaryAscendClassId = spec.curSecondaryAscendClassId,
		mainSocketGroup = build.mainSocketGroup,
	}
	pcall(function()
		result.className = spec.tree.classes[spec.curClassId].name
	end)
	pcall(function()
		local classData = spec.tree.classes[spec.curClassId]
		if spec.curAscendClassId and spec.curAscendClassId ~= 0 then
			result.ascendClassName = classData.classes[spec.curAscendClassId].name
		end
	end)
	return result
end

methods.get_tree_state = function()
	ensureBuildLoaded()
	local allocIds = json.array({ })
	for id, node in pairs(build.spec.nodes) do
		if node.alloc then
			allocIds[#allocIds + 1] = id
		end
	end
	table.sort(allocIds)
	return {
		classId = build.spec.curClassId,
		ascendClassId = build.spec.curAscendClassId,
		-- #allocIds (not CountAllocNodes(), which excludes the automatic class-start
		-- node) so this always agrees with the length of allocatedNodes below.
		allocatedNodeCount = #allocIds,
		allocatedNodes = allocIds,
	}
end

methods.node_info = function(params)
	ensureBuildLoaded()
	local id = tonumber(params and params.id)
	if not id then error("params.id (node id) is required", 0) end
	local node = build.spec.nodes[id] or build.spec.tree.nodes[id]
	if not node then error("unknown node id " .. tostring(params.id), 0) end
	return {
		id = node.id,
		name = node.dn or node.name,
		type = node.type,
		stats = json.array(node.sd or { }),
		allocated = node.alloc == true,
		pathCost = node.path and #node.path or json.null,
		ascendancyName = node.ascendancyName or json.null,
	}
end

methods.search_tree = function(params)
	ensureBuildLoaded()
	params = params or { }
	local query = params.query and tostring(params.query):lower() or nil
	local wantType = params.type
	local ascendFilter = params.ascendancyName -- nil = no filter; false/"" = main tree only; a name = just that ascendancy
	local limit = tonumber(params.limit) or 200
	local results = json.array({ })
	for id, node in pairs(build.spec.nodes) do
		local include = true
		if wantType and node.type ~= wantType then
			include = false
		end
		if include and ascendFilter ~= nil then
			if ascendFilter == false or ascendFilter == "" then
				include = node.ascendancyName == nil
			else
				include = node.ascendancyName == ascendFilter
			end
		end
		if include and query then
			local haystack = (node.dn or node.name or ""):lower()
			if not haystack:find(query, 1, true) then
				local foundInStats = false
				if node.sd then
					for _, line in ipairs(node.sd) do
						if line:lower():find(query, 1, true) then
							foundInStats = true
							break
						end
					end
				end
				include = foundInStats
			end
		end
		if include then
			results[#results + 1] = {
				id = id,
				name = node.dn or node.name,
				type = node.type,
				stats = json.array(node.sd or { }),
				allocated = node.alloc == true,
				ascendancyName = node.ascendancyName or json.null,
				pathCost = node.path and #node.path or json.null,
			}
			if #results >= limit then
				break
			end
		end
	end
	table.sort(results, function(a, b) return a.id < b.id end)
	return { nodes = results, truncated = (#results >= limit) }
end

methods.alloc_node = function(params)
	ensureBuildLoaded()
	local id = tonumber(params and params.id)
	if not id then error("params.id (node id) is required", 0) end
	local node = build.spec.nodes[id]
	if not node then error("unknown node id " .. tostring(params.id), 0) end
	build.spec:AllocNode(node)
	refreshBuild()
	return { ok = true }
end

methods.dealloc_node = function(params)
	ensureBuildLoaded()
	local id = tonumber(params and params.id)
	if not id then error("params.id (node id) is required", 0) end
	local node = build.spec.nodes[id]
	if not node then error("unknown node id " .. tostring(params.id), 0) end
	build.spec:DeallocNode(node)
	refreshBuild()
	return { ok = true }
end

methods.node_path_cost = function(params)
	ensureBuildLoaded()
	local id = tonumber(params and params.id)
	if not id then error("params.id (node id) is required", 0) end
	local node = build.spec.nodes[id]
	if not node then error("unknown node id " .. tostring(params.id), 0) end
	return {
		cost = node.path and #node.path or json.null,
		alreadyAllocated = node.alloc == true,
	}
end

methods.list_classes = function()
	ensureBuildLoaded()
	local classes = json.array({ })
	for classId, classData in pairs(build.spec.tree.classes) do
		local ascendancies = json.array({ })
		if classData.classes then
			for ascendId, ascendData in pairs(classData.classes) do
				if ascendId ~= 0 then
					ascendancies[#ascendancies + 1] = { id = ascendId, name = ascendData.name }
				end
			end
			table.sort(ascendancies, function(a, b) return a.id < b.id end)
		end
		classes[#classes + 1] = { id = classId, name = classData.name, ascendancies = ascendancies }
	end
	table.sort(classes, function(a, b) return a.id < b.id end)
	return { classes = classes }
end

methods.select_class = function(params)
	ensureBuildLoaded()
	if not params then error("params.classId is required", 0) end
	-- PoB's own SelectClass/SelectAscendClass mutate spec state before fully
	-- validating an id (e.g. an invalid classId leaves curClassId set to the
	-- bad value and then errors deeper in), so this snapshots first and rolls
	-- back through the same tested load_build_xml path on any failure --
	-- callers should never see a partially-applied class change.
	local snapshot = build:SaveDB("select_class_snapshot")
	local ok, err = pcall(function()
		if params.classId ~= nil then
			build.spec:SelectClass(tonumber(params.classId))
		end
		if params.ascendClassId ~= nil then
			build.spec:SelectAscendClass(tonumber(params.ascendClassId))
		end
		if params.secondaryAscendClassId ~= nil then
			build.spec:SelectSecondaryAscendClass(tonumber(params.secondaryAscendClassId))
		end
	end)
	if not ok then
		methods.load_build_xml({ xml = snapshot, name = "select_class_rollback" })
		error("select_class failed and was rolled back: " .. tostring(err) .. " (use list_classes for valid ids)", 0)
	end
	refreshBuild()
	return { ok = true }
end

methods.list_slots = function()
	ensureBuildLoaded()
	local slots = json.array({ })
	for _, slot in ipairs(build.itemsTab.orderedSlots) do
		local itemName = json.null
		if slot.selItemId and slot.selItemId ~= 0 and build.itemsTab.items[slot.selItemId] then
			itemName = build.itemsTab.items[slot.selItemId].name
		end
		slots[#slots + 1] = {
			slot = slot.slotName,
			itemId = slot.selItemId or 0,
			itemName = itemName,
		}
	end
	return { slots = slots }
end

methods.equip_item_raw = function(params)
	ensureBuildLoaded()
	if not params or not params.text then error("params.text (raw item text) is required", 0) end
	local item = new("Item", params.text)
	item:BuildAndParseRaw()
	if not item.base then
		error("could not parse item text (unrecognised base type or format)", 0)
	end
	build.itemsTab:AddItem(item, true)
	local slotName = params.slot
	if not slotName then
		for _, slot in ipairs(build.itemsTab.orderedSlots) do
			if build.itemsTab:IsItemValidForSlot(item, slot.slotName) then
				slotName = slot.slotName
				break
			end
		end
	end
	if not slotName or not build.itemsTab.slots[slotName] then
		error("no compatible slot found for this item; pass params.slot explicitly", 0)
	end
	build.itemsTab.slots[slotName]:SetSelItemId(item.id)
	refreshBuild()
	return { ok = true, itemId = item.id, slot = slotName, itemName = item.name }
end

methods.unequip_item = function(params)
	ensureBuildLoaded()
	if not params or not params.slot then error("params.slot is required", 0) end
	local slot = build.itemsTab.slots[params.slot]
	if not slot then error("unknown slot " .. tostring(params.slot), 0) end
	slot:SetSelItemId(0)
	refreshBuild()
	return { ok = true }
end

methods.get_skills = function()
	ensureBuildLoaded()
	local groups = json.array({ })
	for i, group in ipairs(build.skillsTab.socketGroupList) do
		local gems = json.array({ })
		for gi, gem in ipairs(group.gemList) do
			gems[#gems + 1] = {
				index = gi,
				nameSpec = gem.nameSpec or json.null,
				gemId = gem.gemId or json.null,
				skillId = gem.skillId or json.null,
				level = gem.level or json.null,
				quality = gem.quality or json.null,
				enabled = gem.enabled ~= false,
			}
		end
		groups[#groups + 1] = {
			index = i,
			label = group.label or json.null,
			enabled = group.enabled ~= false,
			slot = group.slot or json.null,
			gems = gems,
			isMainSkill = (build.mainSocketGroup == i),
		}
	end
	return { socketGroups = groups, mainSocketGroup = build.mainSocketGroup or json.null }
end

methods.add_socket_group = function(params)
	ensureBuildLoaded()
	local newGroup = {
		label = (params and params.label) or "",
		enabled = true,
		gemList = { },
	}
	if params and params.slot then
		newGroup.slot = params.slot
	end
	table.insert(build.skillsTab.socketGroupList, newGroup)
	if not build.mainSocketGroup or build.mainSocketGroup == 0 then
		build.mainSocketGroup = #build.skillsTab.socketGroupList
	end
	refreshBuild()
	return { ok = true, groupIndex = #build.skillsTab.socketGroupList }
end

methods.set_main_skill = function(params)
	ensureBuildLoaded()
	local index = tonumber(params and params.index)
	if not index then error("params.index is required", 0) end
	build.mainSocketGroup = index
	refreshBuild()
	return { ok = true }
end

local function requireGroup(groupIndex)
	local group = build.skillsTab.socketGroupList[tonumber(groupIndex)]
	if not group then error("unknown socket group index " .. tostring(groupIndex), 0) end
	return group
end

methods.set_gem = function(params)
	ensureBuildLoaded()
	if not params or not params.groupIndex or not params.gemIndex then
		error("params.groupIndex and params.gemIndex are required", 0)
	end
	local group = requireGroup(params.groupIndex)
	local gem = group.gemList[tonumber(params.gemIndex)]
	if not gem then error("unknown gem index " .. tostring(params.gemIndex), 0) end
	if params.level ~= nil then gem.level = tonumber(params.level) end
	if params.quality ~= nil then gem.quality = tonumber(params.quality) end
	if params.enabled ~= nil then gem.enabled = params.enabled end
	build.skillsTab:ProcessSocketGroup(group)
	refreshBuild()
	return { ok = true }
end

methods.add_gem = function(params)
	ensureBuildLoaded()
	if not params or not params.groupIndex or not (params.gemId or params.skillId) then
		error("params.groupIndex and params.gemId (or params.skillId) are required", 0)
	end
	local group = requireGroup(params.groupIndex)
	local gemInstance = {
		nameSpec = params.nameSpec or "",
		gemId = params.gemId,
		skillId = params.skillId,
		level = tonumber(params.level) or 1,
		quality = tonumber(params.quality) or 0,
		enabled = true,
	}
	table.insert(group.gemList, gemInstance)
	build.skillsTab:ProcessSocketGroup(group)
	refreshBuild()
	return { ok = true, gemIndex = #group.gemList }
end

methods.remove_gem = function(params)
	ensureBuildLoaded()
	if not params or not params.groupIndex or not params.gemIndex then
		error("params.groupIndex and params.gemIndex are required", 0)
	end
	local group = requireGroup(params.groupIndex)
	if not group.gemList[tonumber(params.gemIndex)] then
		error("unknown gem index " .. tostring(params.gemIndex), 0)
	end
	table.remove(group.gemList, tonumber(params.gemIndex))
	build.skillsTab:ProcessSocketGroup(group)
	refreshBuild()
	return { ok = true }
end

methods.list_valid_supports = function(params)
	ensureBuildLoaded()
	if not params or not params.groupIndex then
		error("params.groupIndex is required", 0)
	end
	local group = requireGroup(params.groupIndex)
	local activeSkill = group.displaySkillList and group.displaySkillList[group.mainActiveSkill or 1]
	local results = json.array({ })
	if not activeSkill then
		return { supports = results, note = "could not resolve an active skill for this group" }
	end
	for gemId, gemData in pairs(build.data.gems) do
		if gemData.grantedEffect and gemData.grantedEffect.support then
			local ok, supports = pcall(calcLib.canGrantedEffectSupportActiveSkill, gemData.grantedEffect, activeSkill)
			if ok and supports then
				results[#results + 1] = { gemId = gemId, name = gemData.name or gemId }
			end
		end
	end
	return { supports = results }
end

-- Cache of slot -> matching bundled unique items, built lazily on first
-- request per slot (data.uniques doesn't change during a session, and
-- parsing every raw unique's item text is comparatively expensive).
local uniqueSlotCache = { }
local function getUniquesForSlot(slotName)
	if uniqueSlotCache[slotName] then
		return uniqueSlotCache[slotName]
	end
	local matches = { }
	for _, list in pairs(data.uniques) do
		for _, raw in ipairs(list) do
			local ok = pcall(function()
				local item = new("Item", raw)
				item:BuildAndParseRaw()
				if item.base then
					local ok2, primarySlot = pcall(function() return item:GetPrimarySlot() end)
					if ok2 and primarySlot == slotName then
						matches[#matches + 1] = { name = item.name, raw = raw }
					end
				end
			end)
		end
	end
	uniqueSlotCache[slotName] = matches
	return matches
end

methods.list_uniques_for_slot = function(params)
	ensureBuildLoaded()
	if not params or not params.slot then error("params.slot is required", 0) end
	local matches = getUniquesForSlot(params.slot)
	local limit = tonumber(params.limit) or 60
	local out = json.array({ })
	for i = 1, math.min(limit, #matches) do
		out[i] = { name = matches[i].name, raw = matches[i].raw }
	end
	return { items = out, total = #matches }
end

methods.list_config_options = function()
	local varList = LoadModule("Modules/ConfigOptions")
	local options = json.array({ })
	for _, opt in ipairs(varList) do
		if opt.var then -- skip section-header entries, which carry no var/label/type
			local entry = { var = opt.var, label = opt.label, type = opt.type }
			if opt.list then
				local list = json.array({ })
				for _, e in ipairs(opt.list) do
					list[#list + 1] = { val = tostring(e.val), label = e.label }
				end
				entry.list = list
			end
			options[#options + 1] = entry
		end
	end
	return { options = options }
end

methods.get_config = function()
	ensureBuildLoaded()
	local configTab = build.configTab
	local input = configTab.configSets[configTab.activeConfigSetId].input
	local config = { }
	for key, value in pairs(input) do
		if isScalar(value) then
			config[key] = value
		end
	end
	return { config = config }
end

methods.set_config = function(params)
	ensureBuildLoaded()
	if not params or not params.var then error("params.var is required", 0) end
	local configTab = build.configTab
	local input = configTab.configSets[configTab.activeConfigSetId].input
	if params.value == nil or params.value == json.null then
		input[params.var] = nil
	else
		input[params.var] = params.value
	end
	configTab:BuildModList()
	refreshBuild()
	return { ok = true }
end

methods.sanity_check = function()
	ensureBuildLoaded()
	local output = build.calcsTab.mainOutput
	local warnings = json.array({ })
	local function warn(fmt, ...)
		warnings[#warnings + 1] = string.format(fmt, ...)
	end
	for _, res in ipairs({ "FireResist", "ColdResist", "LightningResist" }) do
		if output[res] and output[res] < 75 then
			warn("%s is %.0f%%, below the 75%% cap", res, output[res])
		end
	end
	if output.ChaosResist and output.ChaosResist < 0 then
		warn("ChaosResist is %.0f%%, negative", output.ChaosResist)
	end
	if output.Life and (build.characterLevel or 1) >= 30 and output.Life < 500 then
		warn("Life is %.0f, which looks very low for character level %d", output.Life, build.characterLevel or 0)
	end
	if output.EnergyShield and output.EnergyShield > 0 and output.Life and output.Life < 200 and not output.ChaosInoculation then
		warn("Low-life/CI-style build detected without full Chaos Inoculation coverage; verify chaos damage handling")
	end
	return { warnings = warnings }
end

-- ===========================================================================
-- JSON-RPC stdio loop
-- ===========================================================================

pcall(function() io.stdout:setvbuf("no") end)

while true do
	local line = io.read("*l")
	if line == nil then
		break
	end
	if line ~= "" then
		local decodeOk, request = pcall(json.decode, line)
		if not decodeOk or type(request) ~= "table" then
			writeFrame({ id = json.null, error = { message = "invalid JSON-RPC request: " .. tostring(request) } })
		else
			local id = request.id
			if id == nil then id = json.null end
			local method = methods[request.method]
			if not method then
				writeFrame({ id = id, error = { message = "unknown method: " .. tostring(request.method) } })
			else
				local callOk, result = pcall(method, request.params)
				if callOk then
					writeFrame({ id = id, result = result })
				else
					writeFrame({ id = id, error = { message = tostring(result) } })
				end
			end
		end
	end
end
