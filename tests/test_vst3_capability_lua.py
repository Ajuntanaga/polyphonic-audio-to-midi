import ctypes
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CAPABILITY_SCRIPT = (
    ROOT / "Scripts/tests/ajuntanaga_M3 Native VST3 Capability.lua"
)


def lua_quote(value: pathlib.Path) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def run_lua(source: str) -> None:
    lua = ctypes.CDLL("liblua5.4.so.0")
    lua.luaL_newstate.restype = ctypes.c_void_p
    lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
    lua.luaL_loadbufferx.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.c_char_p,
        ctypes.c_char_p,
    ]
    lua.luaL_loadbufferx.restype = ctypes.c_int
    lua.lua_pcallk.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_ssize_t,
        ctypes.c_void_p,
    ]
    lua.lua_pcallk.restype = ctypes.c_int
    lua.lua_tolstring.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    lua.lua_tolstring.restype = ctypes.c_char_p
    lua.lua_close.argtypes = [ctypes.c_void_p]

    state = lua.luaL_newstate()
    if not state:
        raise RuntimeError("luaL_newstate failed")
    try:
        lua.luaL_openlibs(state)
        payload = source.encode("utf-8")
        status = lua.luaL_loadbufferx(
            state, payload, len(payload), b"@vst3-capability-test", None
        )
        if status == 0:
            status = lua.lua_pcallk(state, 0, -1, 0, 0, None)
        if status != 0:
            length = ctypes.c_size_t()
            message = lua.lua_tolstring(state, -1, ctypes.byref(length))
            detail = "unknown Lua error" if not message else message[: length.value].decode()
            raise AssertionError(detail)
    finally:
        lua.lua_close(state)


class Vst3CapabilityLuaTests(unittest.TestCase):
    def test_normalized_parameter_and_diagnostic_conversions_execute_in_lua(self):
        with tempfile.TemporaryDirectory() as temporary:
            resource = pathlib.Path(temporary) / "build/reaper-test"
            (resource / "test-results").mkdir(parents=True)
            run_lua(
                f"""
M3_VST3_CAPABILITY_UNIT_TEST = {{}}
reaper = {{
  GetResourcePath = function() return {lua_quote(resource)} end,
  RecursiveCreateDirectory = function() end,
  gmem_attach = function() end,
  gmem_write = function() end,
  gmem_read = function() return 0 end,
  CountTracks = function() return 1 end,
  InsertTrackAtIndex = function() end,
  GetTrack = function() return nil end,
  OnStopButton = function() end,
  GetSetProjectInfo = function() end,
  defer = function(callback) callback() end,
  Main_OnCommand = function() end,
}}
assert(loadfile({lua_quote(CAPABILITY_SCRIPT)}))()
local api = M3_VST3_CAPABILITY_UNIT_TEST
assert(type(api.plain_to_normalized) == "function", "missing normalized writer")
assert(type(api.normalized_to_plain) == "function", "missing normalized reader")
assert(type(api.diagnostic_to_plain) == "function", "missing diagnostic conversion")

local cases = {{
  {{"A4 reference", 432.1, 0.40125}},
  {{"Input trim", -3.2, 0.43333333333333335}},
  {{"Lowest MIDI note", 29, 5 / 84}},
  {{"Fixed velocity", 77, 76 / 126}},
  {{"MIDI channel", 4, 0.2}},
}}
for _, case in ipairs(cases) do
  local normalized = api.plain_to_normalized(case[1], case[2])
  assert(math.abs(normalized - case[3]) < 1e-12, case[1] .. " normalized")
  local plain = api.normalized_to_plain(case[1], case[3])
  assert(math.abs(plain - case[2]) < 1e-9, case[1] .. " plain")
end
assert(api.diagnostic_to_plain("Probe sample rate", 0.25) == 96000)
assert(api.diagnostic_to_plain("Probe maximum block", 0.03125) == 512)
assert(api.diagnostic_to_plain("Probe process", 1 / 1048576) == 1)
"""
            )

    def test_address_pattern_fails_before_audio_and_closes_disposable_instance(self):
        with tempfile.TemporaryDirectory() as temporary:
            resource = pathlib.Path(temporary) / "build/reaper-test"
            results = resource / "test-results"
            results.mkdir(parents=True)
            run_lua(
                f"""
closed = false
reaper = {{
  GetResourcePath = function() return {lua_quote(resource)} end,
  RecursiveCreateDirectory = function() end,
  gmem_attach = function() end,
  gmem_write = function() end,
  gmem_read = function(index) return index end,
  CountTracks = function() return 0 end,
  InsertTrackAtIndex = function() end,
  GetTrack = function() return {{}} end,
  TrackFX_AddByName = (function()
    local index = -1
    return function() index = index + 1 return index end
  end)(),
  TrackFX_SetEnabled = function() return true end,
  SetEditCurPos = function() end,
  OnPlayButton = function() end,
  OnStopButton = function() end,
  time_precise = function() return 0 end,
  GetSetProjectInfo = function() end,
  defer = function(callback) callback() end,
  Main_OnCommand = function(command) closed = command == 40004 end,
}}
assert(loadfile({lua_quote(CAPABILITY_SCRIPT)}))()
assert(closed, "failed capability run did not close")
"""
            )
            self.assertEqual(
                (results / "phase.log").read_text(encoding="utf-8").splitlines(),
                ["suite-start", "suite-fail"],
            )
            capability = (results / "capability.tsv").read_text(encoding="utf-8")
            self.assertIn("status\tfail", capability)
            self.assertIn("sample_rate\t-1", capability)
            self.assertIn("block_size\t-1", capability)
            self.assertIn("observer-magic", capability)
            self.assertNotIn("dry-mute", capability)

    def test_observer_protocol_rejects_address_values_and_waits_for_ack(self):
        with tempfile.TemporaryDirectory() as temporary:
            resource = pathlib.Path(temporary) / "build/reaper-test"
            (resource / "test-results").mkdir(parents=True)
            run_lua(
                f"""
M3_VST3_CAPABILITY_UNIT_TEST = {{}}
reaper = {{
  GetResourcePath = function() return {lua_quote(resource)} end,
  RecursiveCreateDirectory = function() end,
  gmem_attach = function() end,
  gmem_write = function() end,
  gmem_read = function() return 0 end,
  CountTracks = function() return 1 end,
  InsertTrackAtIndex = function() end,
  GetTrack = function() return nil end,
  OnStopButton = function() end,
  GetSetProjectInfo = function() end,
  defer = function(callback) callback() end,
  Main_OnCommand = function() end,
}}
assert(loadfile({lua_quote(CAPABILITY_SCRIPT)}))()
local api = M3_VST3_CAPABILITY_UNIT_TEST
assert(type(api.observer_status) == "function", "missing observer validator")
local status = api.observer_status(function(index) return index end, 1)
assert(status == "invalid", "address pattern advanced observer")

local value = {{
  [api.cells.magic] = api.magic,
  [api.cells.generation] = 7,
  [api.cells.ready] = 7,
  [api.cells.heartbeat] = 4,
  [api.cells.ack] = 0,
  [api.cells.active] = 1,
  [api.cells.fault] = 0,
  [api.cells.rate] = 96000,
  [api.cells.block] = 512,
}}
local function read(index) return value[index] or 0 end
assert(api.observer_status(read, 1) == "waiting", "missing ack did not wait")
value[api.cells.ack] = 1
assert(api.observer_status(read, 1) == "ready", "valid observer was rejected")
"""
            )


if __name__ == "__main__":
    unittest.main()
