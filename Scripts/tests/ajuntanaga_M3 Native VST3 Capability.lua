local PERSISTENT_PARAMETER_COUNT = 14
local OBSERVER_MAGIC_VALUE = 0x4D335633
local COMMAND = 2210
local SOURCE_RESET = 2211
local PHASE_SAMPLE = 2212
local ACTIVE = 2201
local SOURCE_FAULT = 2202
local ACTUAL_RATE = 2203
local ACTUAL_BLOCK = 2204
local OBSERVER_MAGIC = 2205
local OBSERVER_GENERATION = 2206
local OBSERVER_READY = 2207
local OBSERVER_HEARTBEAT = 2208
local OBSERVER_ACK = 2209
local CAPTURE_COUNTER = 128
local CAPTURE_COUNT = 256
local CAPTURE_OVERFLOW = 257
local CAPTURE_EVENT_BASE = 258
local CAPTURE_EVENT_WORDS = 5
local DRY_ERROR = 2048
local DRY_COUNT = 2049
local OUTPUT_PEAK = 2050
local OUTPUT_NONFINITE = 2051
local SYNTH_OUTPUT_PEAK = 2100
local SYNTH_OUTPUT_COUNT = 2101
local TEST_TIMEOUT_SECONDS = 5
local OBSERVER_TIMEOUT_SECONDS = 3

local resource = reaper.GetResourcePath()
local result_directory = resource .. "/test-results"
local phase_path = result_directory .. "/phase.log"
local expected_result_root = "/build/reaper-test/test-results"

assert(
  result_directory:sub(-#expected_result_root) == expected_result_root,
  "native VST3 capability results escaped the disposable test directory"
)
reaper.RecursiveCreateDirectory(result_directory, 0)
reaper.gmem_attach("m3_poly_midi_tests_v1")

local phase_lines = {}
local failures = {}
local event_lines = {
  "phase\tindex\tabsolute_sample\toffset\ttype\tchannel\tpitch\tvelocity\tnote_id"
}
local state_lines = {
  "index\tstable_id\tname\tdefault\tmutated\trestored"
}
local diagnostic_values = {}
local track
local source_fx = -1
local probe_fx = -1
local capture_fx = -1
local synth_fx = -1
local synth_probe_fx = -1
local reporter_fx = -1
local finished = false
local finish_suite
local reset_nonce = 0
local verified_dry_error = math.huge
local verified_synth_peak = 0

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
  return actual == actual and expected == expected and
         math.abs(actual - expected) <= tolerance
end

local function finite(value)
  return value == value and value > -math.huge and value < math.huge
end

local function integer_in_range(value, minimum, maximum)
  return finite(value) and value == math.floor(value) and
         value >= minimum and value <= maximum
end

local function observer_status(read, expected_ack)
  local magic = read(OBSERVER_MAGIC)
  local generation = read(OBSERVER_GENERATION)
  local ready = read(OBSERVER_READY)
  local heartbeat = read(OBSERVER_HEARTBEAT)
  local ack = read(OBSERVER_ACK)
  if magic == 0 and generation == 0 and ready == 0 and heartbeat == 0 then
    return "waiting", "init"
  end
  if magic ~= OBSERVER_MAGIC_VALUE then
    return "invalid", "magic"
  end
  if not integer_in_range(generation, 1, 1048576) or
     not integer_in_range(ready, 0, 1048576) or
     not integer_in_range(heartbeat, 0, 1048576) or
     not integer_in_range(ack, 0, 1048576) then
    return "invalid", "protocol-range"
  end
  if ready == 0 or heartbeat < 4 then
    return "waiting", "ready"
  end
  if ready ~= generation then
    return "invalid", "generation"
  end
  if ack ~= expected_ack then
    return "waiting", "ack"
  end
  if read(ACTIVE) ~= 1 or read(SOURCE_FAULT) ~= 0 or
     not integer_in_range(read(ACTUAL_RATE), 1, 384000) or
     not integer_in_range(read(ACTUAL_BLOCK), 1, 512) then
    return "invalid", "source-range"
  end
  return "ready", "-"
end

local observer_metric_contract = {
  {CAPTURE_COUNTER, 0, 1048576, true, "capture-counter"},
  {CAPTURE_COUNT, 0, 256, true, "capture-count"},
  {CAPTURE_OVERFLOW, 0, 1, true, "capture-overflow"},
  {DRY_ERROR, 0, 2, false, "dry-error"},
  {DRY_COUNT, 0, 1048576, true, "dry-count"},
  {OUTPUT_PEAK, 0, 1, false, "output-peak"},
  {OUTPUT_NONFINITE, 0, 1, true, "output-nonfinite"},
  {SYNTH_OUTPUT_PEAK, 0, 1000, false, "synth-peak"},
  {SYNTH_OUTPUT_COUNT, 0, 1048576, true, "synth-count"},
  {PHASE_SAMPLE, 0, 1048576, true, "phase-sample"},
}

local function observer_metrics_valid(read)
  for _, contract in ipairs(observer_metric_contract) do
    local value = read(contract[1])
    local valid = finite(value) and value >= contract[2] and
                  value <= contract[3]
    if contract[4] then
      valid = valid and value == math.floor(value)
    end
    if not valid then
      return false, contract[5]
    end
  end
  return true, "-"
end

local observer_transport_cells = {
  ACTIVE, SOURCE_FAULT, ACTUAL_RATE, ACTUAL_BLOCK, OBSERVER_MAGIC,
  OBSERVER_GENERATION, OBSERVER_READY, OBSERVER_HEARTBEAT, OBSERVER_ACK,
  COMMAND, SOURCE_RESET, PHASE_SAMPLE,
}

local function clear_observer_transport()
  for _, cell in ipairs(observer_transport_cells) do
    reaper.gmem_write(cell, 0)
  end
end

local parameter_contract = {
  {"Detector input", 0, 2, 1, 0, false},
  {"Mode", 0, 1, 1, 0, true},
  {"A4 reference", 400, 480, 0.1, 440, false},
  {"Input trim", -24, 24, 0.1, 0, false},
  {"Sensitivity", 0, 100, 1, 50, false},
  {"Response", 0, 100, 1, 25, false},
  {"Lowest MIDI note", 24, 108, 1, 32, false},
  {"Highest MIDI note", 24, 108, 1, 84, false},
  {"Maximum polyphony", 1, 8, 1, 8, false},
  {"M3 maximum fret", 0, 36, 1, 24, false},
  {"Velocity mode", 0, 1, 1, 1, true},
  {"Fixed velocity", 1, 127, 1, 100, false},
  {"MIDI channel", 1, 16, 1, 1, false},
  {"Panic", 0, 1, 1, 0, true},
  {"Dry audio", 0, 1, 1, 1, true},
  {"Status", 0, 5, 1, 0, false},
}

local parameter_contract_by_name = {}
for _, contract in ipairs(parameter_contract) do
  parameter_contract_by_name[contract[1]] = contract
end

local function canonical_plain(contract, value)
  if contract == nil or not finite(value) then
    return nil
  end
  local bounded = math.max(contract[2], math.min(contract[3], value))
  local steps = math.floor((bounded - contract[2]) / contract[4] + 0.5)
  return math.max(contract[2], math.min(
    contract[3], contract[2] + steps * contract[4]
  ))
end

local function plain_to_normalized(name, value)
  local contract = parameter_contract_by_name[name]
  local plain = canonical_plain(contract, value)
  if plain == nil then
    return nil
  end
  return (plain - contract[2]) / (contract[3] - contract[2])
end

local function normalized_to_plain(name, value)
  local contract = parameter_contract_by_name[name]
  if contract == nil or not finite(value) or value < 0 or value > 1 then
    return nil
  end
  return canonical_plain(
    contract, contract[2] + value * (contract[3] - contract[2])
  )
end

local persistent_names = {
  "Detector input", "Mode", "A4 reference", "Input trim",
  "Sensitivity", "Response", "Lowest MIDI note", "Highest MIDI note",
  "Maximum polyphony", "M3 maximum fret", "Velocity mode",
  "Fixed velocity", "MIDI channel", "Dry audio",
}
local persistent_mutations = {
  2, 1, 432.1, -3.2, 73, 61, 29, 91, 5, 19, 0, 77, 4, 0,
}

local parameter_indices = {}
local parameter_idents = {}

local function map_parameters()
  parameter_indices = {}
  parameter_idents = {}
  local names_seen = {}
  local parameter_count = reaper.TrackFX_GetNumParams(track, probe_fx)
  expect(parameter_count >= #parameter_contract, "parameter-count-too-small")
  for index = 0, parameter_count - 1 do
    local name_ok, name = reaper.TrackFX_GetParamName(track, probe_fx, index, "")
    if name_ok and name ~= "" then
      if names_seen[name] then
        fail("duplicate-parameter-name-" .. name)
      else
        names_seen[name] = true
        parameter_indices[name] = index
      end
    end
  end
  local identifiers_seen = {}
  for _, contract in ipairs(parameter_contract) do
    local name = contract[1]
    local index = parameter_indices[name]
    if expect(index ~= nil, "missing-parameter-" .. name) then
      local ident_ok, ident = reaper.TrackFX_GetParamIdent(
        track, probe_fx, index
      )
      expect(ident_ok and ident ~= "", "parameter-ident-" .. name)
      if ident_ok and ident ~= "" then
        expect(not identifiers_seen[ident], "duplicate-parameter-ident-" .. name)
        identifiers_seen[ident] = true
        parameter_idents[name] = ident
        expect(
          reaper.TrackFX_GetParamFromIdent(track, probe_fx, ident) == index,
          "parameter-ident-round-trip-" .. name
        )
      end
    end
  end
end

local function parameter_value(name)
  local index = parameter_indices[name]
  if index == nil then
    return math.huge
  end
  local value = normalized_to_plain(
    name, reaper.TrackFX_GetParamNormalized(track, probe_fx, index)
  )
  if value == nil then
    fail("parameter-normalized-range-" .. name)
    return math.huge
  end
  return value
end

local function set_parameter(name, value)
  local index = parameter_indices[name]
  if index == nil then
    fail("set-missing-parameter-" .. name)
    return math.huge
  end
  local normalized = plain_to_normalized(name, value)
  if normalized == nil then
    fail("parameter-plain-range-" .. name)
    return math.huge
  end
  expect(
    reaper.TrackFX_SetParamNormalized(track, probe_fx, index, normalized),
    "parameter-write-rejected-" .. name
  )
  return parameter_value(name)
end

local function inspect_parameter_surface()
  map_parameters()
  for _, contract in ipairs(parameter_contract) do
    local name = contract[1]
    local index = parameter_indices[name]
    if index ~= nil then
      local raw_value, minimum, maximum = reaper.TrackFX_GetParamEx(
        track, probe_fx, index
      )
      local normalized = reaper.TrackFX_GetParamNormalized(
        track, probe_fx, index
      )
      expect(near(minimum, 0, 1e-12), "parameter-min-" .. name)
      expect(near(maximum, 1, 1e-12), "parameter-max-" .. name)
      expect(near(raw_value, normalized, 1e-12), "parameter-raw-" .. name)
      expect(near(parameter_value(name), contract[5], 1e-9),
             "parameter-default-" .. name)

      local step_ok, step, small_step, large_step, is_toggle =
        reaper.TrackFX_GetParameterStepSizes(track, probe_fx, index)
      expect(step_ok, "parameter-step-api-" .. name)
      if step_ok then
        local normalized_step = contract[4] / (contract[3] - contract[2])
        expect(
          near(step, contract[4], 1e-9) or
          near(step, normalized_step, 1e-9),
          "parameter-step-" .. name
        )
        expect(finite(small_step) and finite(large_step),
               "parameter-step-finite-" .. name)
        expect(is_toggle == contract[6], "parameter-toggle-" .. name)
      end

      local formatted_ok, formatted = reaper.TrackFX_GetFormattedParamValue(
        track, probe_fx, index, ""
      )
      local normalized_format_ok, normalized_format =
        reaper.TrackFX_FormatParamValueNormalized(
          track, probe_fx, index, normalized, ""
        )
      expect(formatted_ok and formatted ~= "" and normalized_format_ok and
             formatted == normalized_format, "parameter-format-" .. name)
    end
  end

  local status_before = parameter_value("Status")
  local status_index = parameter_indices["Status"]
  if status_index ~= nil then
    reaper.TrackFX_SetParamNormalized(track, probe_fx, status_index, 1)
    expect(near(parameter_value("Status"), status_before, 1e-9),
           "status-read-only")
  end
  set_parameter("Panic", 1)
  expect(near(parameter_value("Panic"), 0, 1e-9), "panic-not-momentary")
end

local function state_round_trip()
  for _, name in ipairs(persistent_names) do
    if parameter_indices[name] == nil or parameter_idents[name] == nil then
      fail("state-mapping-incomplete-" .. name)
      return false
    end
  end
  local mutated = {}
  local saved_idents = {}
  for position, name in ipairs(persistent_names) do
    mutated[position] = set_parameter(name, persistent_mutations[position])
    expect(near(mutated[position], persistent_mutations[position], 1e-6),
           "parameter-not-writable-" .. name)
    saved_idents[position] = parameter_idents[name]
  end
  local chunk_ok, saved_chunk = reaper.GetTrackStateChunk(track, "", false)
  expect(chunk_ok and #saved_chunk > 0, "state-chunk-save")

  for _, contract in ipairs(parameter_contract) do
    local name = contract[1]
    if name ~= "Panic" and name ~= "Status" then
      set_parameter(name, contract[5])
    end
  end
  local restore_ok = reaper.SetTrackStateChunk(track, saved_chunk, false)
  expect(restore_ok, "state-chunk-restore")
  reaper.TrackFX_SetEnabled(track, reporter_fx, false)
  expect(not reaper.TrackFX_GetEnabled(track, reporter_fx),
         "state-reporter-enabled")
  map_parameters()

  for position, name in ipairs(persistent_names) do
    local restored = parameter_value(name)
    expect(near(restored, mutated[position], 1e-6), "state-value-" .. name)
    expect(parameter_idents[name] == saved_idents[position],
           "state-ident-" .. name)
    local contract
    for _, candidate in ipairs(parameter_contract) do
      if candidate[1] == name then
        contract = candidate
        break
      end
    end
    state_lines[#state_lines + 1] = table.concat({
      parameter_indices[name], parameter_idents[name], name,
      contract[5], mutated[position], restored,
    }, "\t")
  end
  expect(#persistent_names == PERSISTENT_PARAMETER_COUNT, "persistent-count")
  expect(near(parameter_value("Panic"), 0, 1e-9), "panic-state-persisted")
  expect(near(parameter_value("Status"), 0, 1e-9), "status-state-persisted")

  for _, contract in ipairs(parameter_contract) do
    local name = contract[1]
    if name ~= "Panic" and name ~= "Status" then
      set_parameter(name, contract[5])
    end
  end
  return true
end

local observer_reset_cells = {
  CAPTURE_COUNTER, CAPTURE_COUNT, CAPTURE_OVERFLOW, DRY_ERROR, DRY_COUNT,
  OUTPUT_PEAK, OUTPUT_NONFINITE, SYNTH_OUTPUT_PEAK, SYNTH_OUTPUT_COUNT,
}

local function reset_observers()
  for _, cell in ipairs(observer_reset_cells) do
    reaper.gmem_write(cell, 0)
  end
  for _, cell in ipairs(observer_reset_cells) do
    if reaper.gmem_read(cell) ~= 0 then
      return false, cell
    end
  end
  return true, nil
end

local function select_source_phase(command)
  reset_nonce = reset_nonce + 1
  reaper.gmem_write(COMMAND, command)
  reaper.gmem_write(SOURCE_RESET, reset_nonce)
  reaper.gmem_write(PHASE_SAMPLE, 0)
end

local function prepare_playback(command)
  reaper.OnStopButton()
  local reset_ok = reset_observers()
  if not reset_ok then
    fail("observer-reset-readback")
    finish_suite()
    return false
  end
  select_source_phase(command)
  reaper.SetEditCurPos(0, false, false)
  return true
end

local function begin_playback(command)
  if not prepare_playback(command) then
    return false
  end
  reaper.OnPlayButton()
  return true
end

local function captured_note_events()
  local raw_count = reaper.gmem_read(CAPTURE_COUNT)
  if not integer_in_range(raw_count, 0, 256) then
    fail("capture-count-out-of-range")
    finish_suite()
    return nil
  end
  local events = {}
  for index = 0, raw_count - 1 do
    local cell = CAPTURE_EVENT_BASE + index * CAPTURE_EVENT_WORDS
    local absolute_sample = reaper.gmem_read(cell)
    local offset = reaper.gmem_read(cell + 1)
    local status = reaper.gmem_read(cell + 2)
    local pitch = reaper.gmem_read(cell + 3)
    local velocity = reaper.gmem_read(cell + 4)
    if not integer_in_range(absolute_sample, 0, 1048576) or
       not integer_in_range(offset, 0, 511) or
       not integer_in_range(status, 0, 255) or
       not integer_in_range(pitch, 0, 127) or
       not integer_in_range(velocity, 0, 127) then
      fail("capture-event-out-of-range")
      finish_suite()
      return nil
    end
    local kind = status & 0xF0
    if kind ~= 0x80 and kind ~= 0x90 then
      fail("capture-event-type-out-of-range")
      finish_suite()
      return nil
    end
    events[#events + 1] = {
      absolute_sample = absolute_sample,
      offset = offset,
      type = kind == 0x90 and velocity > 0 and "on" or "off",
      channel = (status & 0x0F) + 1,
      pitch = pitch,
      velocity = velocity,
      note_id = -1000 - pitch,
    }
  end
  return events
end

local function record_events(phase, events)
  for index, event in ipairs(events) do
    event_lines[#event_lines + 1] = table.concat({
      phase, index - 1, event.absolute_sample, event.offset, event.type,
      event.channel, event.pitch, event.velocity, event.note_id,
    }, "\t")
  end
end

local function expect_event(event, event_type, pitch, velocity, absolute_sample)
  if not expect(event ~= nil, "event-missing-" .. event_type .. "-" .. pitch) then
    return
  end
  expect(event.type == event_type, "event-type-" .. pitch)
  expect(event.channel == 1, "event-channel-" .. pitch)
  expect(event.pitch == pitch, "event-pitch-" .. pitch)
  expect(event.velocity == velocity, "event-velocity-" .. pitch)
  expect(event.note_id == -1000 - pitch, "event-note-id-" .. pitch)
  if absolute_sample ~= nil then
    expect(event.absolute_sample == absolute_sample,
           "event-absolute-sample-" .. pitch)
    local actual_block = math.floor(reaper.gmem_read(ACTUAL_BLOCK) + 0.5)
    if actual_block > 0 then
      expect(event.offset == absolute_sample % actual_block,
             "event-offset-" .. pitch)
    end
  end
end

local function first_event_index(events, event_type, pitch)
  for index, event in ipairs(events) do
    if event.type == event_type and event.pitch == pitch then
      return index
    end
  end
  return nil
end

local function setup_track()
  if not expect(reaper.CountTracks(0) == 0, "project-not-blank") then
    return false
  end
  reaper.InsertTrackAtIndex(0, true)
  track = reaper.GetTrack(0, 0)
  if not expect(track ~= nil, "track-creation") then
    return false
  end
  source_fx = reaper.TrackFX_AddByName(
    track, "JS: ajuntanaga/M3 Native VST3 Capability Source", false, -1
  )
  probe_fx = reaper.TrackFX_AddByName(track, "VST3: M3 Polyphonic Audio to MIDI Probe", false, -1)
  capture_fx = reaper.TrackFX_AddByName(
    track, "JS: ajuntanaga/M3 Polyphonic MIDI - MIDI Capture", false, -1
  )
  synth_fx = reaper.TrackFX_AddByName(
    track, "VSTi: ReaSynth (Cockos)", false, -1
  )
  synth_probe_fx = reaper.TrackFX_AddByName(
    track, "JS: ajuntanaga/M3 Polyphonic MIDI - Synth Output Probe", false, -1
  )
  reporter_fx = reaper.TrackFX_AddByName(track, "VST3: M3 Polyphonic Audio to MIDI Probe", false, -1)
  if reporter_fx >= 0 then
    reaper.TrackFX_SetEnabled(track, reporter_fx, false)
  end
  return expect(source_fx == 0, "source-discovery")
end

local function inspect_track_surface()
  expect(source_fx == 0, "source-discovery")
  expect(probe_fx == 1, "probe-discovery")
  expect(capture_fx == 2, "capture-discovery")
  expect(synth_fx == 3, "reasynth-discovery")
  expect(synth_probe_fx == 4, "synth-probe-discovery")
  expect(reporter_fx == 5, "diagnostic-reporter-reserve")
  if reporter_fx >= 0 then
    expect(not reaper.TrackFX_GetEnabled(track, reporter_fx),
           "diagnostic-reporter-reserve-enabled")
  end
  if probe_fx ~= 1 or reporter_fx ~= 5 then
    return false
  end

  local name_ok, name = reaper.TrackFX_GetFXName(track, probe_fx, "")
  expect(name_ok and name:find("M3 Polyphonic Audio to MIDI Probe", 1, true),
         "probe-exact-name")
  local type_ok, fx_type = reaper.TrackFX_GetNamedConfigParm(track, probe_fx, "fx_type")
  expect(type_ok and fx_type == "VST3", "probe-format")
  local instrument_ok, is_instrument = reaper.TrackFX_GetNamedConfigParm(track, probe_fx, "is_instrument")
  expect(instrument_ok and is_instrument == "0", "probe-is-instrument")
  local pdc_ok, pdc = reaper.TrackFX_GetNamedConfigParm(track, probe_fx, "pdc")
  expect(pdc_ok and tonumber(pdc) == 0, "nonzero-pdc")
  return true
end

local function diagnostic_parameter(name)
  local count = reaper.TrackFX_GetNumParams(track, probe_fx)
  for index = 0, count - 1 do
    local ok, candidate = reaper.TrackFX_GetParamName(track, probe_fx, index, "")
    if ok and candidate == name then
      return index
    end
  end
  return nil
end

local diagnostic_contract = {
  {"create", "Probe create"},
  {"initialize", "Probe initialize"},
  {"setup", "Probe setup"},
  {"activate", "Probe activate"},
  {"start", "Probe start"},
  {"process", "Probe process"},
  {"stop", "Probe stop"},
  {"deactivate", "Probe deactivate"},
  {"terminate", "Probe terminate"},
  {"destroy", "Probe destroy"},
  {"reset", "Probe reset"},
  {"float32_seen", "Probe float32"},
  {"float64_seen", "Probe float64"},
  {"alias_seen", "Probe alias"},
  {"separate_seen", "Probe separate"},
  {"sample_rate_diagnostic", "Probe sample rate", 384000},
  {"block_size_diagnostic", "Probe maximum block", 16384},
  {"trigger_one", "Probe trigger one"},
  {"trigger_two", "Probe trigger two"},
  {"trigger_overflow", "Probe trigger overflow"},
  {"trigger_fault", "Probe trigger fault"},
}

local diagnostic_maximum = {}
for _, contract in ipairs(diagnostic_contract) do
  diagnostic_maximum[contract[2]] = contract[3] or 1048576
end

local function diagnostic_to_plain(name, normalized)
  local maximum = diagnostic_maximum[name]
  if maximum == nil or not finite(normalized) or
     normalized < 0 or normalized > 1 then
    return nil
  end
  return normalized * maximum
end

local function read_diagnostic(name)
  local index = diagnostic_parameter(name)
  if index == nil then
    return nil
  end
  return diagnostic_to_plain(
    name, reaper.TrackFX_GetParamNormalized(track, probe_fx, index)
  )
end

local function capture_diagnostics()
  diagnostic_values = {}
  for _, contract in ipairs(diagnostic_contract) do
    local value = read_diagnostic(contract[2])
    expect(value ~= nil and finite(value), "diagnostic-" .. contract[1])
    diagnostic_values[contract[1]] = value or -1
  end
  for _, name in ipairs({
    "create", "initialize", "setup", "activate", "start", "process",
    "stop", "deactivate", "terminate", "destroy", "reset",
  }) do
    expect(diagnostic_values[name] >= 1, "lifecycle-" .. name)
  end
  expect(
    diagnostic_values.float32_seen + diagnostic_values.float64_seen >= 1,
    "host-sample-format"
  )
  expect(diagnostic_values.alias_seen + diagnostic_values.separate_seen >= 1,
         "host-buffer-layout")
  expect(near(diagnostic_values.sample_rate_diagnostic,
              reaper.gmem_read(ACTUAL_RATE), 0.5),
         "diagnostic-sample-rate")
  expect(near(diagnostic_values.block_size_diagnostic,
              reaper.gmem_read(ACTUAL_BLOCK), 0.5),
         "diagnostic-block-size")
  expect(diagnostic_values.trigger_one >= 1, "trigger-one-count")
  expect(diagnostic_values.trigger_two >= 3, "trigger-two-count")
  expect(near(diagnostic_values.trigger_overflow, 0, 1e-9),
         "trigger-overflow")
  expect(near(diagnostic_values.trigger_fault, 0, 1e-9), "trigger-fault")
end

local function write_results()
  local observer_ok = observer_status(reaper.gmem_read, reset_nonce) == "ready"
  local actual_rate = observer_ok and
    math.floor(reaper.gmem_read(ACTUAL_RATE) + 0.5) or -1
  local actual_block = observer_ok and
    math.floor(reaper.gmem_read(ACTUAL_BLOCK) + 0.5) or -1
  local status = #failures == 0 and "pass" or "fail"
  atomic_write(result_directory .. "/capability.tsv", {
    "metric\tvalue",
    "status\t" .. status,
    "sample_rate\t" .. actual_rate,
    "block_size\t" .. actual_block,
    "dry_error\t" .. string.format(
      "%.17g", finite(verified_dry_error) and verified_dry_error or -1
    ),
    "synth_peak\t" .. string.format("%.17g", verified_synth_peak),
    "source_fault\t" .. (observer_ok and
      math.floor(reaper.gmem_read(SOURCE_FAULT)) or -1),
    "capture_overflow\t" .. (observer_ok and
      math.floor(reaper.gmem_read(CAPTURE_OVERFLOW)) or -1),
    "output_nonfinite\t" .. (observer_ok and
      math.floor(reaper.gmem_read(OUTPUT_NONFINITE)) or -1),
    "failure_count\t" .. #failures,
    "failures\t" .. (#failures == 0 and "-" or table.concat(failures, ",")),
  })
  atomic_write(result_directory .. "/events.tsv", event_lines)
  atomic_write(result_directory .. "/state.tsv", state_lines)

  local report = {
    "metric\tvalue",
    "schema\t1",
    "sample_rate\t" .. actual_rate,
    "block_size\t" .. actual_block,
  }
  for _, contract in ipairs(diagnostic_contract) do
    report[#report + 1] = contract[1] .. "\t" ..
      string.format("%.17g", diagnostic_values[contract[1]] or -1)
  end
  report[#report + 1] = "failure_count\t" .. #failures
  atomic_write(result_directory .. "/probe-vst3.tsv", report)
end

finish_suite = function()
  if finished then
    return
  end
  finished = true
  reaper.OnStopButton()
  write_results()
  write_phase(#failures == 0 and "suite-finish" or "suite-fail")
  reaper.GetSetProjectInfo(0, "DIRTY", 0, true)
  reaper.defer(function()
    reaper.Main_OnCommand(40004, 0)
  end)
end

local function fail_timeout(label)
  fail(label .. "-timeout")
  finish_suite()
end

local function observer_gate(deadline, label, poll)
  if finished then
    return false
  end
  local status, reason = observer_status(reaper.gmem_read, reset_nonce)
  if status == "invalid" then
    fail("observer-" .. reason)
    finish_suite()
    return false
  end
  if status == "waiting" then
    if reaper.time_precise() >= deadline then
      fail_timeout(label .. "-observer-" .. reason)
    else
      reaper.defer(poll)
    end
    return false
  end
  local valid, metric = observer_metrics_valid(reaper.gmem_read)
  if not valid then
    fail("observer-" .. metric .. "-range")
    finish_suite()
    return false
  end
  return true
end

local begin_trigger_one
local begin_trigger_two
local begin_bypass_hold
local begin_delete_hold
local begin_reporter

local mute_deadline
local function poll_mute()
  if not observer_gate(mute_deadline, "dry-mute", poll_mute) then
    return
  end
  if reaper.gmem_read(DRY_COUNT) >= 320 then
    expect(reaper.gmem_read(OUTPUT_PEAK) == 0, "dry-mute-output")
    expect(reaper.gmem_read(DRY_ERROR) > 0, "dry-mute-no-input-reference")
    expect(reaper.gmem_read(OUTPUT_NONFINITE) == 0, "dry-mute-nonfinite")
    local events = captured_note_events()
    if events == nil then
      return
    end
    expect(#events == 0, "dry-mute-note-output")
    reaper.OnStopButton()
    set_parameter("Dry audio", 1)
    begin_trigger_one()
    return
  end
  if reaper.time_precise() >= mute_deadline then
    fail_timeout("dry-mute")
    return
  end
  reaper.defer(poll_mute)
end

local trigger_one_deadline
local function poll_trigger_one()
  if not observer_gate(
    trigger_one_deadline, "trigger-one", poll_trigger_one
  ) then
    return
  end
  local events = captured_note_events()
  if events == nil then
    return
  end
  if #events >= 2 and reaper.gmem_read(DRY_COUNT) >= 320 then
    expect(#events == 2, "trigger-one-event-count")
    expect_event(events[1], "on", 60, 101, 256)
    expect_event(events[2], "off", 60, 0, 320)
    record_events("trigger-one", events)
    verified_dry_error = reaper.gmem_read(DRY_ERROR)
    verified_synth_peak = math.max(
      verified_synth_peak, reaper.gmem_read(SYNTH_OUTPUT_PEAK)
    )
    expect(verified_dry_error == 0, "dry-pass-not-bit-exact")
    expect(reaper.gmem_read(OUTPUT_NONFINITE) == 0, "dry-pass-nonfinite")
    expect(reaper.gmem_read(SOURCE_FAULT) == 0, "source-fault")
    expect(reaper.gmem_read(CAPTURE_OVERFLOW) == 0, "capture-overflow")
    expect(verified_synth_peak > 0, "trigger-one-synth-silent")
    reaper.OnStopButton()
    begin_trigger_two()
    return
  end
  if reaper.time_precise() >= trigger_one_deadline then
    fail_timeout("trigger-one")
    return
  end
  reaper.defer(poll_trigger_one)
end

local recovery_deadline
local function poll_stop_recovery()
  if not observer_gate(
    recovery_deadline, "stop-restart", poll_stop_recovery
  ) then
    return
  end
  local events = captured_note_events()
  if events == nil then
    return
  end
  if #events >= 1 then
    local off_index = first_event_index(events, "off", 64)
    local on_index = first_event_index(events, "on", 64)
    expect(off_index ~= nil, "stop-restart-off")
    expect(on_index == nil or (off_index ~= nil and off_index < on_index),
           "stop-restart-order")
    expect_event(events[off_index], "off", 64, 0, 0)
    record_events("stop-restart", events)
    reaper.OnStopButton()
    begin_bypass_hold()
    return
  end
  if reaper.time_precise() >= recovery_deadline then
    fail_timeout("stop-restart")
    return
  end
  reaper.defer(poll_stop_recovery)
end

local trigger_two_deadline
local function poll_trigger_two()
  if not observer_gate(
    trigger_two_deadline, "trigger-two", poll_trigger_two
  ) then
    return
  end
  local events = captured_note_events()
  if events == nil then
    return
  end
  if #events >= 1 and reaper.gmem_read(SYNTH_OUTPUT_PEAK) > 0 then
    expect(#events == 1, "trigger-two-event-count")
    expect_event(events[1], "on", 64, 111, 256)
    record_events("trigger-two-held", events)
    verified_synth_peak = math.max(
      verified_synth_peak, reaper.gmem_read(SYNTH_OUTPUT_PEAK)
    )
    if begin_playback(3) then
      recovery_deadline = reaper.time_precise() + TEST_TIMEOUT_SECONDS
      reaper.defer(poll_stop_recovery)
    end
    return
  end
  if reaper.time_precise() >= trigger_two_deadline then
    fail_timeout("trigger-two")
    return
  end
  reaper.defer(poll_trigger_two)
end

local bypass_cleanup_deadline
local function poll_bypass_cleanup()
  if not observer_gate(
    bypass_cleanup_deadline, "bypass-cleanup", poll_bypass_cleanup
  ) then
    return
  end
  local events = captured_note_events()
  if events == nil then
    return
  end
  local off_index = first_event_index(events, "off", 64)
  if off_index ~= nil then
    local on_index = first_event_index(events, "on", 64)
    expect(on_index == nil or off_index < on_index, "bypass-cleanup-order")
    expect_event(events[off_index], "off", 64, 0, nil)
    record_events("bypass-cleanup", events)
    reaper.OnStopButton()
    begin_delete_hold()
    return
  end
  if reaper.time_precise() >= bypass_cleanup_deadline then
    fail_timeout("bypass-cleanup")
    return
  end
  reaper.defer(poll_bypass_cleanup)
end

local function enable_after_bypass()
  reaper.TrackFX_SetEnabled(track, probe_fx, true)
  expect(reaper.TrackFX_GetEnabled(track, probe_fx), "bypass-enable")
  bypass_cleanup_deadline = reaper.time_precise() + TEST_TIMEOUT_SECONDS
  reaper.defer(poll_bypass_cleanup)
end

local bypass_hold_deadline
local function poll_bypass_hold()
  if not observer_gate(
    bypass_hold_deadline, "bypass-held", poll_bypass_hold
  ) then
    return
  end
  local events = captured_note_events()
  if events == nil then
    return
  end
  if first_event_index(events, "on", 64) ~= nil then
    expect_event(events[first_event_index(events, "on", 64)],
                 "on", 64, 111, 256)
    record_events("bypass-held", events)
    if not prepare_playback(3) then
      return
    end
    reaper.TrackFX_SetEnabled(track, probe_fx, false)
    expect(not reaper.TrackFX_GetEnabled(track, probe_fx), "bypass-disable")
    reaper.OnPlayButton()
    reaper.defer(enable_after_bypass)
    return
  end
  if reaper.time_precise() >= bypass_hold_deadline then
    fail_timeout("bypass-held")
    return
  end
  reaper.defer(poll_bypass_hold)
end

local delete_quiet_reset_time
local delete_quiet_deadline
local delete_quiet_reset = false
local function poll_delete_quiet()
  if not observer_gate(
    delete_quiet_deadline, "probe-delete-silence", poll_delete_quiet
  ) then
    return
  end
  if not delete_quiet_reset and
     reaper.time_precise() >= delete_quiet_reset_time then
    delete_quiet_reset = true
    reaper.gmem_write(SYNTH_OUTPUT_PEAK, 0)
    reaper.gmem_write(SYNTH_OUTPUT_COUNT, 0)
  end
  if delete_quiet_reset and reaper.gmem_read(SYNTH_OUTPUT_COUNT) >= 320 then
    expect(reaper.gmem_read(SYNTH_OUTPUT_PEAK) <= 1e-12,
           "probe-delete-downstream-audio")
    local events = captured_note_events()
    if events == nil then
      return
    end
    record_events("probe-delete", events)
    begin_reporter()
    return
  end
  if reaper.time_precise() >= delete_quiet_deadline then
    fail_timeout("probe-delete-silence")
    return
  end
  reaper.defer(poll_delete_quiet)
end

local delete_hold_deadline
local function poll_delete_hold()
  if not observer_gate(
    delete_hold_deadline, "delete-held", poll_delete_hold
  ) then
    return
  end
  local events = captured_note_events()
  if events == nil then
    return
  end
  if first_event_index(events, "on", 64) ~= nil and
     reaper.gmem_read(SYNTH_OUTPUT_PEAK) > 0 then
    expect_event(events[first_event_index(events, "on", 64)],
                 "on", 64, 111, 256)
    record_events("delete-held", events)
    if not prepare_playback(3) then
      return
    end
    reaper.TrackFX_Delete(track, probe_fx)
    probe_fx = -1
    reporter_fx = 4
    expect(reaper.TrackFX_GetCount(track) == 5, "probe-delete-count")
    delete_quiet_reset = false
    delete_quiet_reset_time = reaper.time_precise() + 0.35
    delete_quiet_deadline = reaper.time_precise() + TEST_TIMEOUT_SECONDS
    reaper.OnPlayButton()
    reaper.defer(poll_delete_quiet)
    return
  end
  if reaper.time_precise() >= delete_hold_deadline then
    fail_timeout("delete-held")
    return
  end
  reaper.defer(poll_delete_hold)
end

local reporter_deadline
local function poll_reporter()
  if not observer_gate(
    reporter_deadline, "diagnostic-reporter", poll_reporter
  ) then
    return
  end
  local process_count = read_diagnostic("Probe process") or 0
  local destroy_count = read_diagnostic("Probe destroy") or 0
  if process_count >= 1 and destroy_count >= 1 then
    capture_diagnostics()
    reaper.OnStopButton()
    reaper.TrackFX_Delete(track, probe_fx)
    probe_fx = -1
    reporter_fx = -1
    expect(reaper.TrackFX_GetCount(track) == 4, "reporter-delete-count")
    finish_suite()
    return
  end
  if reaper.time_precise() >= reporter_deadline then
    fail_timeout("diagnostic-reporter")
    return
  end
  reaper.defer(poll_reporter)
end

begin_reporter = function()
  write_phase("lifecycle-report")
  probe_fx = reporter_fx
  expect(probe_fx == 4, "diagnostic-reporter-discovery")
  if probe_fx ~= 4 then
    finish_suite()
    return
  end
  local type_ok, fx_type = reaper.TrackFX_GetNamedConfigParm(
    track, probe_fx, "fx_type"
  )
  local instrument_ok, is_instrument = reaper.TrackFX_GetNamedConfigParm(
    track, probe_fx, "is_instrument"
  )
  expect(type_ok and fx_type == "VST3", "diagnostic-reporter-format")
  expect(instrument_ok and is_instrument == "0",
         "diagnostic-reporter-instrument")
  reaper.TrackFX_SetEnabled(track, probe_fx, true)
  expect(reaper.TrackFX_GetEnabled(track, probe_fx),
         "diagnostic-reporter-enable")
  if begin_playback(3) then
    reporter_deadline = reaper.time_precise() + TEST_TIMEOUT_SECONDS
    reaper.defer(poll_reporter)
  end
end

begin_delete_hold = function()
  write_phase("delete-held")
  if begin_playback(2) then
    delete_hold_deadline = reaper.time_precise() + TEST_TIMEOUT_SECONDS
    reaper.defer(poll_delete_hold)
  end
end

begin_bypass_hold = function()
  write_phase("bypass-held")
  if begin_playback(2) then
    bypass_hold_deadline = reaper.time_precise() + TEST_TIMEOUT_SECONDS
    reaper.defer(poll_bypass_hold)
  end
end

begin_trigger_two = function()
  write_phase("trigger-two-held")
  if begin_playback(2) then
    trigger_two_deadline = reaper.time_precise() + TEST_TIMEOUT_SECONDS
    reaper.defer(poll_trigger_two)
  end
end

begin_trigger_one = function()
  write_phase("trigger-one")
  if begin_playback(1) then
    trigger_one_deadline = reaper.time_precise() + TEST_TIMEOUT_SECONDS
    reaper.defer(poll_trigger_one)
  end
end

local function begin_capability_assertions()
  reaper.OnStopButton()
  if not reset_observers() then
    fail("observer-reset-readback")
    finish_suite()
    return
  end
  write_phase("observer-ready")
  if not inspect_track_surface() then
    finish_suite()
    return
  end
  inspect_parameter_surface()
  if #failures > 0 or not state_round_trip() then
    finish_suite()
    return
  end
  write_phase("dry-mute")
  set_parameter("Dry audio", 0)
  if begin_playback(0) then
    mute_deadline = reaper.time_precise() + TEST_TIMEOUT_SECONDS
    reaper.defer(poll_mute)
  end
end

local observer_boot_deadline
local function poll_observer_boot()
  if observer_gate(
    observer_boot_deadline, "observer-ready", poll_observer_boot
  ) then
    begin_capability_assertions()
  end
end

local function begin_observer_boot()
  select_source_phase(0)
  reaper.SetEditCurPos(0, false, false)
  reaper.OnPlayButton()
  observer_boot_deadline = reaper.time_precise() + OBSERVER_TIMEOUT_SECONDS
  reaper.defer(poll_observer_boot)
end

if type(M3_VST3_CAPABILITY_UNIT_TEST) == "table" then
  M3_VST3_CAPABILITY_UNIT_TEST.plain_to_normalized = plain_to_normalized
  M3_VST3_CAPABILITY_UNIT_TEST.normalized_to_plain = normalized_to_plain
  M3_VST3_CAPABILITY_UNIT_TEST.diagnostic_to_plain = diagnostic_to_plain
  M3_VST3_CAPABILITY_UNIT_TEST.observer_status = observer_status
  M3_VST3_CAPABILITY_UNIT_TEST.magic = OBSERVER_MAGIC_VALUE
  M3_VST3_CAPABILITY_UNIT_TEST.cells = {
    magic = OBSERVER_MAGIC,
    generation = OBSERVER_GENERATION,
    ready = OBSERVER_READY,
    heartbeat = OBSERVER_HEARTBEAT,
    ack = OBSERVER_ACK,
    active = ACTIVE,
    fault = SOURCE_FAULT,
    rate = ACTUAL_RATE,
    block = ACTUAL_BLOCK,
  }
  return
end

write_phase("suite-start")
clear_observer_transport()
if not setup_track() then
  finish_suite()
else
  begin_observer_boot()
end
