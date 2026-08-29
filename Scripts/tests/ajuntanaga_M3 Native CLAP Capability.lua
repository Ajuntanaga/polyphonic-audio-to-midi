local EXPECTED_PARAMETER_COUNT = 16
local PERSISTENT_PARAMETER_COUNT = 14
local COMMAND = 2200
local ACTIVE = 2201
local SOURCE_FAULT = 2202
local ACTUAL_RATE = 2203
local ACTUAL_BLOCK = 2204
local CAPTURE_COUNT = 256
local CAPTURE_OVERFLOW = 257
local CAPTURE_EVENT_BASE = 258
local CAPTURE_EVENT_WORDS = 5
local DRY_ERROR = 2048
local DRY_COUNT = 2049
local SYNTH_OUTPUT_PEAK = 2100
local SYNTH_OUTPUT_COUNT = 2101
local TEST_TIMEOUT_SECONDS = 4

local resource = reaper.GetResourcePath()
local result_directory = resource .. "/test-results"
local phase_path = result_directory .. "/phase.log"
local probe_report_path = result_directory .. "/probe-native.tsv"
local expected_result_root = "/build/reaper-test/test-results"

assert(
  result_directory:sub(-#expected_result_root) == expected_result_root,
  "native capability results escaped the disposable test directory"
)
reaper.RecursiveCreateDirectory(result_directory, 0)
reaper.gmem_attach("m3_poly_midi_tests_v1")

local phase_lines = {}
local failures = {}
local event_lines = {
  "phase\tindex\tabsolute_sample\toffset\tstatus\tdata1\tdata2"
}
local state_lines = {
  "index\tname\tminimum\tmaximum\tdefault\tmutated\trestored"
}
local track
local source_fx = -1
local probe_fx = -1
local capture_fx = -1
local synth_fx = -1
local synth_probe_fx = -1
local finished = false
local verified_dry_error = math.huge

local function atomic_write(path, lines)
  assert(path:sub(1, #result_directory) == result_directory)
  local temporary = path .. ".tmp"
  os.remove(temporary)
  local handle = assert(io.open(temporary, "w"))
  for _, line in ipairs(lines) do
    handle:write(line, "\n")
  end
  handle:flush()
  handle:close()
  os.remove(path)
  assert(os.rename(temporary, path))
end

local function write_phase(phase)
  phase_lines[#phase_lines + 1] = phase
  atomic_write(phase_path, phase_lines)
end

local function fail(message)
  failures[#failures + 1] = message
end

local function expect(condition, message)
  if not condition then
    fail(message)
  end
  return condition
end

local function near(actual, expected, tolerance)
  return math.abs(actual - expected) <= tolerance
end

local parameter_contract = {
  {"Detector input", 0, 2, 0},
  {"Mode", 0, 1, 0},
  {"A4 reference", 400, 480, 440},
  {"Input trim", -24, 24, 0},
  {"Sensitivity", 0, 100, 50},
  {"Response", 0, 100, 25},
  {"Lowest MIDI note", 24, 108, 32},
  {"Highest MIDI note", 24, 108, 84},
  {"Maximum polyphony", 1, 8, 8},
  {"M3 maximum fret", 0, 36, 24},
  {"Velocity mode", 0, 1, 1},
  {"Fixed velocity", 1, 127, 100},
  {"MIDI channel", 1, 16, 1},
  {"Panic", 0, 1, 0},
  {"Dry audio", 0, 1, 1},
  {"Status", 0, 5, 0},
}

local persistent_indices = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14}
local persistent_mutations = {2, 1, 432.1, -3.2, 73, 61, 29, 91, 5, 19, 0, 77, 4, 0}

local function parameter_value(index)
  local value = reaper.TrackFX_GetParam(track, probe_fx, index)
  return value
end

local function set_parameter(index, value)
  reaper.TrackFX_SetParam(track, probe_fx, index, value)
  return parameter_value(index)
end

local function inspect_parameter_surface()
  expect(
    reaper.TrackFX_GetNumParams(track, probe_fx) == EXPECTED_PARAMETER_COUNT,
    "parameter-count"
  )
  for index, contract in ipairs(parameter_contract) do
    local parameter_index = index - 1
    local name_ok, name = reaper.TrackFX_GetParamName(
      track, probe_fx, parameter_index, ""
    )
    local value, minimum, maximum = reaper.TrackFX_GetParamEx(
      track, probe_fx, parameter_index
    )
    expect(name_ok and name == contract[1], "parameter-name-" .. parameter_index)
    expect(near(minimum, contract[2], 1e-9), "parameter-min-" .. parameter_index)
    expect(near(maximum, contract[3], 1e-9), "parameter-max-" .. parameter_index)
    expect(near(value, contract[4], 1e-9), "parameter-default-" .. parameter_index)
  end

  local initial_status = parameter_value(15)
  reaper.TrackFX_SetParam(track, probe_fx, 15, 5)
  expect(near(parameter_value(15), initial_status, 1e-9), "status-read-only")
  reaper.TrackFX_SetParam(track, probe_fx, 13, 1)
  expect(near(parameter_value(13), 0, 1e-9), "panic-not-momentary")
end

local function state_round_trip()
  local mutated = {}
  for position, parameter_index in ipairs(persistent_indices) do
    mutated[position] = set_parameter(
      parameter_index, persistent_mutations[position]
    )
    expect(
      near(mutated[position], persistent_mutations[position], 1e-6),
      "parameter-not-writable-" .. parameter_index
    )
  end
  local chunk_ok, saved_chunk = reaper.GetTrackStateChunk(track, "", false)
  expect(chunk_ok and #saved_chunk > 0, "state-chunk-save")

  for position, parameter_index in ipairs(persistent_indices) do
    set_parameter(parameter_index, parameter_contract[parameter_index + 1][4])
  end
  local restore_ok = reaper.SetTrackStateChunk(track, saved_chunk, false)
  expect(restore_ok, "state-chunk-restore")

  for position, parameter_index in ipairs(persistent_indices) do
    local restored = parameter_value(parameter_index)
    expect(near(restored, mutated[position], 1e-6), "state-value-" .. parameter_index)
    state_lines[#state_lines + 1] = table.concat({
      parameter_index,
      parameter_contract[parameter_index + 1][1],
      parameter_contract[parameter_index + 1][2],
      parameter_contract[parameter_index + 1][3],
      parameter_contract[parameter_index + 1][4],
      mutated[position],
      restored,
    }, "\t")
  end
  expect(near(parameter_value(13), 0, 1e-9), "panic-state-persisted")
  expect(near(parameter_value(15), 0, 1e-9), "status-state-persisted")

  for _, parameter_index in ipairs(persistent_indices) do
    set_parameter(parameter_index, parameter_contract[parameter_index + 1][4])
  end
  expect(#persistent_indices == PERSISTENT_PARAMETER_COUNT, "persistent-count")
end

local function captured_events(phase, record)
  local count = math.floor(reaper.gmem_read(CAPTURE_COUNT))
  local events = {}
  for index = 0, count - 1 do
    local cell = CAPTURE_EVENT_BASE + index * CAPTURE_EVENT_WORDS
    local event = {
      math.floor(reaper.gmem_read(cell)),
      math.floor(reaper.gmem_read(cell + 1)),
      math.floor(reaper.gmem_read(cell + 2)),
      math.floor(reaper.gmem_read(cell + 3)),
      math.floor(reaper.gmem_read(cell + 4)),
    }
    events[#events + 1] = event
    if record then
      event_lines[#event_lines + 1] = table.concat({
        phase, index, event[1], event[2], event[3], event[4], event[5]
      }, "\t")
    end
  end
  return events
end

local function expect_event(events, index, offset, status, data1, data2)
  local event = events[index]
  if not expect(event ~= nil, "event-missing-" .. index) then
    return
  end
  expect(event[2] == offset, "event-offset-" .. index)
  expect(event[3] == status, "event-status-" .. index)
  expect(event[4] == data1, "event-data1-" .. index)
  expect(event[5] == data2, "event-data2-" .. index)
end

local function setup_track()
  expect(reaper.CountTracks(0) == 0, "project-not-blank")
  reaper.InsertTrackAtIndex(0, true)
  track = assert(reaper.GetTrack(0, 0), "track creation failed")
  source_fx = reaper.TrackFX_AddByName(
    track, "JS: ajuntanaga/M3 Native CLAP Capability Source", false, -1
  )
  probe_fx = reaper.TrackFX_AddByName(track, "CLAP: M3 Polyphonic Audio to MIDI Probe", false, -1)
  capture_fx = reaper.TrackFX_AddByName(
    track, "JS: ajuntanaga/M3 Polyphonic MIDI - MIDI Capture", false, -1
  )
  synth_fx = reaper.TrackFX_AddByName(track, "VSTi: ReaSynth (Cockos)", false, -1)
  synth_probe_fx = reaper.TrackFX_AddByName(
    track, "JS: ajuntanaga/M3 Polyphonic MIDI - Synth Output Probe", false, -1
  )
  expect(source_fx == 0, "source-discovery")
  expect(probe_fx == 1, "probe-discovery")
  expect(capture_fx == 2, "capture-discovery")
  expect(synth_fx == 3, "reasynth-discovery")
  expect(synth_probe_fx == 4, "synth-probe-discovery")

  local fx_name_ok, fx_name = reaper.TrackFX_GetFXName(track, probe_fx, "")
  expect(fx_name_ok and fx_name:find("M3 Polyphonic Audio to MIDI Probe", 1, true),
         "probe-exact-name")
  local type_ok, fx_type = reaper.TrackFX_GetNamedConfigParm(
    track, probe_fx, "fx_type"
  )
  expect(type_ok and fx_type == "CLAP", "probe-format")
  local pdc_ok, pdc = reaper.TrackFX_GetNamedConfigParm(track, probe_fx, "pdc")
  expect(pdc_ok and tonumber(pdc) == 0, "nonzero-pdc")
end

local function reset_capture()
  reaper.gmem_write(CAPTURE_COUNT, 0)
  reaper.gmem_write(CAPTURE_OVERFLOW, 0)
end

local function finish_after_report()
  if finished then
    return
  end
  local report = io.open(probe_report_path, "r")
  if not report then
    return false
  end
  local report_values = {}
  for line in report:lines() do
    local key, value = line:match("^([^\t]+)\t([^\t]+)$")
    if key and key ~= "metric" then
      report_values[key] = tonumber(value)
    end
  end
  report:close()
  expect(report_values.schema == 1, "probe-report-schema")
  for _, name in ipairs({
    "create", "init", "activate", "start", "reset", "stop", "deactivate", "destroy"
  }) do
    expect((report_values[name] or 0) >= 1, "lifecycle-" .. name)
  end
  expect((report_values.float32_seen or 0) + (report_values.float64_seen or 0) >= 1,
         "no-host-sample-format")
  expect(report_values.self_test_alias_passed == 1, "alias-self-test")
  expect(report_values.self_test_separate_passed == 1, "separate-self-test")
  expect(report_values.CC119_trigger_one == 1, "trigger-one-count")
  expect(report_values.CC119_trigger_two == 1, "trigger-two-count")
  expect(report_values.trigger_overflow == 0, "probe-trigger-overflow")

  local status = #failures == 0 and "pass" or "fail"
  local actual_rate = math.floor(reaper.gmem_read(ACTUAL_RATE) + 0.5)
  local actual_block = math.floor(reaper.gmem_read(ACTUAL_BLOCK) + 0.5)
  atomic_write(result_directory .. "/capability.tsv", {
    "metric\tvalue",
    "status\t" .. status,
    "sample_rate\t" .. actual_rate,
    "block_size\t" .. actual_block,
    "dry_error\t" .. string.format("%.17g", verified_dry_error),
    "synth_peak\t" .. string.format("%.17g", reaper.gmem_read(SYNTH_OUTPUT_PEAK)),
    "source_fault\t" .. math.floor(reaper.gmem_read(SOURCE_FAULT)),
    "capture_overflow\t" .. math.floor(reaper.gmem_read(CAPTURE_OVERFLOW)),
    "failure_count\t" .. #failures,
    "failures\t" .. (#failures == 0 and "-" or table.concat(failures, ",")),
  })
  atomic_write(result_directory .. "/events.tsv", event_lines)
  atomic_write(result_directory .. "/state.tsv", state_lines)
  write_phase("suite-finish")
  finished = true
  reaper.GetSetProjectInfo(0, "DIRTY", 0, true)
  reaper.defer(function()
    reaper.Main_OnCommand(40004, 0)
  end)
  return true
end

local report_deadline
local function poll_report()
  if finish_after_report() then
    return
  end
  if reaper.time_precise() >= report_deadline then
    fail("probe-report-timeout")
    local status = "fail"
    atomic_write(result_directory .. "/capability.tsv", {
      "metric\tvalue", "status\t" .. status,
      "sample_rate\t" .. math.floor(reaper.gmem_read(ACTUAL_RATE) + 0.5),
      "block_size\t" .. math.floor(reaper.gmem_read(ACTUAL_BLOCK) + 0.5),
      "failure_count\t" .. #failures,
      "failures\t" .. table.concat(failures, ","),
    })
    atomic_write(result_directory .. "/events.tsv", event_lines)
    atomic_write(result_directory .. "/state.tsv", state_lines)
    write_phase("suite-finish")
    finished = true
    reaper.defer(function() reaper.Main_OnCommand(40004, 0) end)
    return
  end
  reaper.defer(poll_report)
end

local panic_deadline
local panic_status_seen = false
local panic_quiet_requested = false
local function poll_panic()
  local events = captured_events("panic", false)
  local note_off_seen = false
  local active_notes = {}
  for _, event in ipairs(events) do
    local kind = event[3] & 0xF0
    if kind == 0x90 and event[5] > 0 then
      active_notes[event[4]] = true
    elseif kind == 0x80 or (kind == 0x90 and event[5] == 0) then
      active_notes[event[4]] = nil
      if event[4] == 61 then
        note_off_seen = true
      end
    end
  end
  local status = parameter_value(15)
  panic_status_seen = panic_status_seen or status ~= 0
  if note_off_seen and panic_status_seen and not panic_quiet_requested then
    panic_quiet_requested = true
    reaper.gmem_write(COMMAND, 3)
  end
  if note_off_seen and panic_status_seen and panic_quiet_requested and status == 0 then
    captured_events("panic", true)
    expect(next(active_notes) == nil, "active-note-after-panic")
    reaper.OnStopButton()
    write_phase("probe-delete")
    reaper.TrackFX_Delete(track, probe_fx)
    report_deadline = reaper.time_precise() + TEST_TIMEOUT_SECONDS
    reaper.defer(poll_report)
    return
  end
  if reaper.time_precise() >= panic_deadline then
    fail("panic-release-timeout")
    reaper.OnStopButton()
    reaper.TrackFX_Delete(track, probe_fx)
    report_deadline = reaper.time_precise() + TEST_TIMEOUT_SECONDS
    reaper.defer(poll_report)
    return
  end
  reaper.defer(poll_panic)
end

local held_deadline
local function poll_held_note()
  local events = captured_events("held", false)
  local held_seen = false
  for _, event in ipairs(events) do
    if event[2] == 9 and event[3] == 0x90 and event[4] == 61 and event[5] == 100 then
      held_seen = true
    end
  end
  if held_seen and reaper.gmem_read(SYNTH_OUTPUT_PEAK) > 0 then
    expect(reaper.gmem_read(SYNTH_OUTPUT_PEAK) > 0, "reasynth-held-note-silent")
    captured_events("held", true)
    write_phase("panic")
    reaper.TrackFX_SetParam(track, probe_fx, 13, 1)
    panic_deadline = reaper.time_precise() + TEST_TIMEOUT_SECONDS
    reaper.defer(poll_panic)
    return
  end
  if reaper.time_precise() >= held_deadline then
    fail("held-note-timeout")
    reaper.OnStopButton()
    reaper.TrackFX_Delete(track, probe_fx)
    report_deadline = reaper.time_precise() + TEST_TIMEOUT_SECONDS
    reaper.defer(poll_report)
    return
  end
  reaper.defer(poll_held_note)
end

local scripted_deadline
local function poll_scripted_phase()
  local count = math.floor(reaper.gmem_read(CAPTURE_COUNT))
  if count >= 8 and reaper.gmem_read(DRY_COUNT) >= 32 and
     reaper.gmem_read(SYNTH_OUTPUT_COUNT) >= 32 then
    local events = captured_events("scripted", true)
    expect(#events == 8, "scripted-event-count")
    expect_event(events, 1, 4, 0x90, 67, 101)
    expect_event(events, 2, 8, 0xB0, 119, 1)
    expect_event(events, 3, 9, 0x90, 65, 99)
    expect_event(events, 4, 9, 0x90, 60, 100)
    expect_event(events, 5, 11, 0x80, 60, 0)
    expect_event(events, 6, 11, 0xB0, 1, 64)
    expect_event(events, 7, 20, 0x80, 67, 0)
    expect_event(events, 8, 21, 0x80, 65, 0)
    verified_dry_error = reaper.gmem_read(DRY_ERROR)
    expect(verified_dry_error == 0, "dry-audio-not-bit-exact")
    expect(reaper.gmem_read(SOURCE_FAULT) == 0, "source-overflow")
    expect(reaper.gmem_read(CAPTURE_OVERFLOW) == 0, "capture-overflow")
    expect(reaper.gmem_read(SYNTH_OUTPUT_PEAK) > 0, "reasynth-output-silent")

    set_parameter(14, 0)
    reset_capture()
    reaper.gmem_write(SYNTH_OUTPUT_PEAK, 0)
    reaper.gmem_write(SYNTH_OUTPUT_COUNT, 0)
    reaper.gmem_write(COMMAND, 2)
    write_phase("held-note")
    held_deadline = reaper.time_precise() + TEST_TIMEOUT_SECONDS
    reaper.defer(poll_held_note)
    return
  end
  if reaper.time_precise() >= scripted_deadline then
    fail("scripted-phase-timeout")
    reaper.OnStopButton()
    reaper.TrackFX_Delete(track, probe_fx)
    report_deadline = reaper.time_precise() + TEST_TIMEOUT_SECONDS
    reaper.defer(poll_report)
    return
  end
  reaper.defer(poll_scripted_phase)
end

write_phase("suite-start")
reaper.gmem_write(COMMAND, 0)
reaper.gmem_write(ACTIVE, 0)
reaper.gmem_write(SOURCE_FAULT, 0)
reset_capture()
reaper.gmem_write(DRY_ERROR, 0)
reaper.gmem_write(DRY_COUNT, 0)
reaper.gmem_write(SYNTH_OUTPUT_PEAK, 0)
reaper.gmem_write(SYNTH_OUTPUT_COUNT, 0)

setup_track()
inspect_parameter_surface()
state_round_trip()
write_phase("scripted-midi")
reaper.SetEditCurPos(0, false, false)
reaper.gmem_write(COMMAND, 1)
reaper.OnPlayButton()
scripted_deadline = reaper.time_precise() + TEST_TIMEOUT_SECONDS
reaper.defer(poll_scripted_phase)
