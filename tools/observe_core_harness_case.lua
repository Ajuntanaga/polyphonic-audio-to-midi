local expected_magic = 0x4D335431
local started = reaper.time_precise()

local _, script_path = reaper.get_action_context()
local root = script_path:match("^(.*)/tools/[^/]+$")
if not root then
  reaper.ShowConsoleMsg("core harness observer could not resolve the repository root\n")
  reaper.Main_OnCommand(40004, 0)
  return
end

local _, project_path = reaper.EnumProjects(-1, "")
local disposable_prefix = root .. "/build/core-harness-cases/"
local project_name = project_path:match("([^/]+)$") or ""
local rate_text, case_text = project_name:match(
  "^core%-harness%-(%d+)%-case%-(%d+)%.RPP$"
)
local expected_rate = tonumber(rate_text)
local expected_case = tonumber(case_text)
local valid_rate = expected_rate == 44100 or expected_rate == 48000 or expected_rate == 96000
local valid_case = expected_case and (
  (expected_case >= 4101 and expected_case <= 4106) or
  (expected_case >= 5101 and expected_case <= 5106) or
  (expected_case >= 6101 and expected_case <= 6106)
)

if project_path:sub(1, #disposable_prefix) ~= disposable_prefix or
   not valid_rate or not valid_case then
  reaper.ShowConsoleMsg(
    "core harness observer refused non-disposable or malformed project: " ..
    tostring(project_path) .. "\n"
  )
  reaper.Main_OnCommand(40004, 0)
  return
end

local task_number = math.floor(expected_case / 1000)
local result_path = root .. "/build/evidence/task-0" .. task_number .. "-results/" ..
                    expected_rate .. "-case-" .. expected_case .. ".txt"
local temporary_result_path = result_path .. ".tmp"
os.remove(result_path)
os.remove(temporary_result_path)

local function rounded_gmem(index)
  return math.floor((reaper.gmem_read(index) or 0) + 0.5)
end

local function write_result(status, detail)
  local handle, open_error = io.open(temporary_result_path, "w")
  if not handle then
    reaper.ShowConsoleMsg(
      "unable to write core harness observation: " .. tostring(open_error) .. "\n"
    )
    return false
  end

  handle:write("status=", status, "\n")
  handle:write("detail=", detail, "\n")
  handle:write("project=", project_path, "\n")
  handle:write("expected_rate=", expected_rate, "\n")
  handle:write("expected_case=", expected_case, "\n")
  for index = 0, 31 do
    handle:write("gmem_", index, "=", tostring(reaper.gmem_read(index) or 0), "\n")
  end
  handle:write(
    "elapsed_seconds=",
    string.format("%.6f", reaper.time_precise() - started),
    "\n"
  )
  handle:close()
  local renamed, rename_error = os.rename(temporary_result_path, result_path)
  if not renamed then
    os.remove(temporary_result_path)
    reaper.ShowConsoleMsg(
      "unable to publish core harness observation: " ..
      tostring(rename_error) .. "\n"
    )
    return false
  end
  return true
end

local function finish(status, detail)
  write_result(status, detail)
  reaper.defer(function()
    reaper.Main_OnCommand(40004, 0)
  end)
end

local function poll()
  local magic = rounded_gmem(0)
  local state = rounded_gmem(1)
  local assertions = rounded_gmem(2)
  local failed_id = rounded_gmem(3)
  local actual_rate = rounded_gmem(6)
  local actual_case = rounded_gmem(15)
  local expected_assertions = expected_case == 4101 and 19 or 3

  if magic == expected_magic and state == -1 and
     actual_rate == expected_rate and actual_case == expected_case then
    finish("fail", "core JSFX assertion " .. failed_id .. " failed")
    return
  end

  if magic == expected_magic and state == 2 and
     actual_rate == expected_rate and actual_case == expected_case then
    if failed_id == 0 and assertions == expected_assertions then
      finish("pass", "all bounded assertions passed")
    else
      finish(
        "fail",
        "unexpected result: assertions=" .. assertions .. ", failed_id=" .. failed_id
      )
    end
    return
  end

  if reaper.time_precise() - started >= 10 then
    finish(
      "error",
      "timed out waiting for matching rate/case result"
    )
    return
  end

  reaper.defer(poll)
end

reaper.gmem_attach("m3_poly_midi_tests_v1")
reaper.defer(poll)
