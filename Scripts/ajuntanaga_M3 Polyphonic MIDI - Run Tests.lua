local COMMAND = 100
local CASE_ID = 101
local STATE = 102
local ACTUAL_RATE = 103
local ONSET_SAMPLE = 104
local RELEASE_SAMPLE = 105
local NOTE_COUNT = 106
local NOTE_BASE = 107
local DETUNE_CENTS = 115
local MISSING_FUNDAMENTAL = 116
local NOISE_GAIN = 117
local DC_GAIN = 118
local HUM_50_GAIN = 119
local HUM_60_GAIN = 120
local CLIP = 121
local STAGGER_SAMPLES = 122
local SOURCE_ACK = 123
local SOURCE_INIT_COUNT = 124
local SOURCE_READY = 125
local SOURCE_HEARTBEAT = 126
local ACTUAL_BLOCK = 127
local SAMPLE_COUNTER = 128
local NOTE_GAIN_BASE = 160
local CAPTURE_COUNT = 256
local CAPTURE_OVERFLOW = 257
local CAPTURE_EVENT_BASE = 258
local CAPTURE_EVENT_WORDS = 5
local CAPTURE_MAX_EVENTS = 256
local DRY_ERROR = 2048
local DRY_COUNT = 2049
local SYNTH_OUTPUT_PEAK = 2100
local SYNTH_OUTPUT_COUNT = 2101

local STATE_ARMED = 1
local STATE_COMPLETE = 3
local STATE_FAULT = -1
local CASE_TIMEOUT_SECONDS = 10
local MATRIX_CASE_TIMEOUT_SECONDS = 20
local SOURCE_READY_TIMEOUT_SECONDS = 3
local TRANSPORT_STOP_TIMEOUT_SECONDS = 3
local RELEASE_SETTLE_SECONDS = 0.35
local PANIC_TRIALS_REQUIRED = 10
local PANIC_OFF_TIMEOUT_SECONDS = 0.500
local SAFE_BYPASS_TIMEOUT_SECONDS = 0.500

local resource = reaper.GetResourcePath()
local manifest_path = resource .. "/Data/m3_poly_midi/synthetic_cases.tsv"
local result_directory = resource .. "/test-results"
local events_path = result_directory .. "/events.tsv"
local summary_path = result_directory .. "/summary.tsv"
local safety_path = result_directory .. "/safety.tsv"
local phase_path = result_directory .. "/phase.log"
local safe_bypass_path = resource ..
  "/Scripts/ajuntanaga_M3 Polyphonic MIDI - Safe Bypass.lua"
local _, project_path = reaper.EnumProjects(-1, "")
local automated_project = project_path:match(
  "/build/host%-integration%.RPP$"
) ~= nil

local function split(text, separator)
  local fields = {}
  local pattern = "(.-)" .. separator
  for field in (text .. separator):gmatch(pattern) do
    fields[#fields + 1] = field
  end
  return fields
end

local function parse_number_list(text)
  local values = {}
  if not text or text == "" or text == "-" then
    return values
  end
  for _, token in ipairs(split(text, ",")) do
    values[#values + 1] = assert(tonumber(token), "invalid numeric list")
  end
  return values
end

local function db_to_gain(text)
  local value = tonumber(text) or -120
  return 10 ^ (value / 20)
end

local function read_cases(path)
  local handle = assert(io.open(path, "r"))
  local header_line = assert(handle:read("*l"), "empty case manifest")
  local headers = split(header_line, "\t")
  local host_mode = false
  for _, header in ipairs(headers) do
    if header == "sensitivity" then
      host_mode = true
      break
    end
  end
  local cases = {}
  for line in handle:lines() do
    if line ~= "" and line:sub(1, 1) ~= "#" then
      local fields = split(line, "\t")
      local case = {}
      for index, header in ipairs(headers) do
        case[header] = fields[index] or ""
      end
      case.case_id = assert(tonumber(case.case_id), "case_id is required")
      case.sample_rate = assert(
        tonumber(case.sample_rate),
        "sample_rate is required"
      )
      case.block_size = assert(
        tonumber(case.block_size),
        "block_size is required"
      )
      case.notes_list = parse_number_list(case.notes)
      case.expected_list = parse_number_list(case.expected)
      cases[#cases + 1] = case
    end
  end
  handle:close()
  assert(#cases > 0, "case manifest contains no cases")
  return cases, host_mode
end

local function atomic_write(path, lines)
  local temporary = path .. ".tmp"
  os.remove(temporary)
  local handle = assert(io.open(temporary, "w"))
  for _, line in ipairs(lines) do
    handle:write(line, "\n")
  end
  handle:close()
  os.remove(path)
  assert(os.rename(temporary, path))
end

local function write_phase(phase)
  local handle = assert(io.open(phase_path, "a"))
  handle:write(phase, "\n")
  handle:close()
end

local function expected_text(case)
  local notes = {}
  for _, note in ipairs(case.expected_list) do
    notes[#notes + 1] = tostring(math.floor(note + 0.5))
  end
  if #notes == 0 then
    return "-"
  end
  return table.concat(notes, ",")
end

local function append_panic_trials(cases)
  local eight_case
  for _, case in ipairs(cases) do
    if case.case_id == 3 then
      eight_case = case
      break
    end
  end
  assert(eight_case, "eight-note safety source case is missing")
  for trial = 1, PANIC_TRIALS_REQUIRED do
    local panic_case = {}
    for key, value in pairs(eight_case) do
      panic_case[key] = value
    end
    panic_case.case_id = 300 + trial
    panic_case.panic_trial = trial
    panic_case.synth_only = true
    cases[#cases + 1] = panic_case
  end
end

local function configure_case(
  case,
  generation,
  case_track,
  case_detector_fx,
  host_mode
)
  local gains = parse_number_list(case.gains_db)
  local mode = case.mode or ""
  local general_mode = mode == "general" or mode == "release" or
                       mode == "silence" or mode == "noise" or
                       mode == "hum50" or mode == "hum60" or mode == "dc" or
                       mode:match("^general:poly=%d+$") ~= nil
  assert(general_mode or mode == "m3", "unsupported case mode: " .. mode)
  local maximum_polyphony = tonumber(mode:match("^general:poly=(%d+)$")) or 8
  assert(
    maximum_polyphony >= 1 and maximum_polyphony <= 8,
    "maximum polyphony must be between 1 and 8"
  )
  local noise_gain = db_to_gain(case.noise_db)
  local dc_gain = 0
  local hum_50_gain = db_to_gain(case.hum_db)
  local hum_60_gain = hum_50_gain
  if not host_mode then
    hum_50_gain = 0
    hum_60_gain = 0
    if mode == "silence" then
      noise_gain = 0
    elseif mode == "noise" then
      -- noise_gain already carries the requested level
    elseif mode == "hum50" then
      noise_gain = 0
      hum_50_gain = db_to_gain(case.hum_db)
    elseif mode == "hum60" then
      noise_gain = 0
      hum_60_gain = db_to_gain(case.hum_db)
    elseif mode == "dc" then
      dc_gain = noise_gain
      noise_gain = 0
    end
  end
  reaper.gmem_write(CASE_ID, case.case_id)
  reaper.gmem_write(NOTE_COUNT, #case.notes_list)
  for index = 0, 7 do
    local note = case.notes_list[index + 1] or 0
    local gain_db = gains[index + 1] or gains[1] or 0
    reaper.gmem_write(NOTE_BASE + index, note)
    reaper.gmem_write(NOTE_GAIN_BASE + index, 10 ^ (gain_db / 20))
  end
  reaper.gmem_write(DETUNE_CENTS, tonumber(case.detune_cents) or 0)
  reaper.gmem_write(
    MISSING_FUNDAMENTAL,
    tonumber(case.missing_fundamental) or 0
  )
  reaper.gmem_write(NOISE_GAIN, noise_gain)
  reaper.gmem_write(DC_GAIN, dc_gain)
  reaper.gmem_write(HUM_50_GAIN, hum_50_gain)
  reaper.gmem_write(HUM_60_GAIN, hum_60_gain)
  reaper.gmem_write(CLIP, tonumber(case.clip) or 0)
  reaper.gmem_write(
    STAGGER_SAMPLES,
    math.floor(
      (tonumber(case.stagger_ms) or 0) * case.sample_rate / 1000 + 0.5
    )
  )
  reaper.gmem_write(CAPTURE_COUNT, 0)
  reaper.gmem_write(CAPTURE_OVERFLOW, 0)
  reaper.gmem_write(DRY_ERROR, 0)
  reaper.gmem_write(DRY_COUNT, 0)
  reaper.gmem_write(SYNTH_OUTPUT_PEAK, 0)
  reaper.gmem_write(SYNTH_OUTPUT_COUNT, 0)
  reaper.gmem_write(SOURCE_ACK, 0)
  reaper.TrackFX_SetParam(
    case_track,
    case_detector_fx,
    1,
    general_mode and 1 or 0
  )
  reaper.TrackFX_SetParam(
    case_track,
    case_detector_fx,
    4,
    tonumber(case.sensitivity) or 80
  )
  reaper.TrackFX_SetParam(
    case_track,
    case_detector_fx,
    5,
    0
  )
  reaper.TrackFX_SetParam(case_track, case_detector_fx, 6, host_mode and 32 or 24)
  reaper.TrackFX_SetParam(case_track, case_detector_fx, 7, host_mode and 84 or 108)
  reaper.TrackFX_SetParam(
    case_track,
    case_detector_fx,
    8,
    maximum_polyphony
  )
  reaper.TrackFX_SetParam(
    case_track,
    case_detector_fx,
    14,
    case.synth_only and 0 or 1
  )
  reaper.gmem_write(STATE, STATE_ARMED)
  reaper.gmem_write(COMMAND, generation)
end

local cases, host_mode = read_cases(manifest_path)
if host_mode then
  append_panic_trials(cases)
end
local event_lines = {
  "case_id\tabsolute_sample\toffset\tstatus\tnote\tvelocity",
}
local summary_lines = {
  "case_id\tstatus\treason\tactual_rate\tactual_block\tsensitivity" ..
  "\tonset_sample\trelease_sample" ..
  "\texpected\tevent_count\toverflow\tdry_max_error\tdry_samples" ..
  "\tsynth_peak\tsynth_samples",
}
local safety_lines = {
  "trial\tstatus\treason\tpanic_sample\tlast_off_sample" ..
  "\toff_latency_ms\tdetector_disabled\tdetector_deleted" ..
  "\tsynth_present",
}
local failures = {}
local track
local source_fx
local detector_fx
local capture_fx
local synth_fx
local probe_fx
local case_index = 0
local command_generation = 0
local case_started = 0
local source_ready_started = 0
local source_completed = nil
local case_init_count = 0
local stop_started = 0
local undo_open = false
local finished = false
local panic_started_at
local panic_sample = 0
local panic_event_index = 0
local panic_trials_passed = 0
local safe_delete_passed = false
local case_forced_reason
local stop_finish_suite = false
local safe_bypass_started_at
local safe_bypass_snapshot

local function record_case(case, forced_reason)
  local count = math.min(
    CAPTURE_MAX_EVENTS,
    math.max(0, math.floor(reaper.gmem_read(CAPTURE_COUNT) or 0))
  )
  local overflow = math.floor(reaper.gmem_read(CAPTURE_OVERFLOW) or 0)
  local dry_error = reaper.gmem_read(DRY_ERROR) or 0
  local dry_samples = math.floor(reaper.gmem_read(DRY_COUNT) or 0)
  local synth_peak = reaper.gmem_read(SYNTH_OUTPUT_PEAK) or 0
  local synth_samples = math.floor(reaper.gmem_read(SYNTH_OUTPUT_COUNT) or 0)
  local active = {}
  local observed_on = {}
  local observed_off = {}
  local on_counts = {}
  local off_counts = {}
  for index = 0, count - 1 do
    local cell = CAPTURE_EVENT_BASE + index * CAPTURE_EVENT_WORDS
    local absolute_sample = math.floor(reaper.gmem_read(cell) or 0)
    local offset = math.floor(reaper.gmem_read(cell + 1) or 0)
    local status = math.floor(reaper.gmem_read(cell + 2) or 0)
    local note = math.floor(reaper.gmem_read(cell + 3) or 0)
    local velocity = math.floor(reaper.gmem_read(cell + 4) or 0)
    event_lines[#event_lines + 1] = table.concat({
      case.case_id,
      absolute_sample,
      offset,
      status,
      note,
      velocity,
    }, "\t")
    local kind = status & 0xF0
    if kind == 0x90 and velocity > 0 then
      observed_on[note] = true
      on_counts[note] = (on_counts[note] or 0) + 1
      active[note] = true
    elseif kind == 0x80 or (kind == 0x90 and velocity == 0) then
      observed_off[note] = true
      off_counts[note] = (off_counts[note] or 0) + 1
      active[note] = nil
    end
  end

  local reasons = {}
  if forced_reason then
    reasons[#reasons + 1] = forced_reason
  end
  if overflow ~= 0 then
    reasons[#reasons + 1] = "capture-overflow"
  end
  if case.synth_only then
    if synth_samples <= 0 then
      reasons[#reasons + 1] = "no-synth-samples"
    end
    if synth_peak <= 0.000001 then
      reasons[#reasons + 1] = "no-synth-output"
    end
  else
    if dry_samples <= 0 then
      reasons[#reasons + 1] = "no-dry-samples"
    end
    if dry_error > 0.000000000001 then
      reasons[#reasons + 1] = "dry-error"
    end
  end
  local actual_rate = math.floor(reaper.gmem_read(ACTUAL_RATE) or 0)
  if actual_rate ~= case.sample_rate then
    reasons[#reasons + 1] = "sample-rate-" .. actual_rate
  end
  local actual_block = math.floor(reaper.gmem_read(ACTUAL_BLOCK) or 0)
  if actual_block ~= case.block_size then
    reasons[#reasons + 1] = "block-size-" .. actual_block
  end
  local expected = {}
  for _, raw_note in ipairs(case.expected_list) do
    local note = math.floor(raw_note + 0.5)
    expected[note] = true
    if not observed_on[note] then
      reasons[#reasons + 1] = "missing-on-" .. note
    end
    if not observed_off[note] then
      reasons[#reasons + 1] = "missing-off-" .. note
    end
    if (on_counts[note] or 0) > 1 then
      reasons[#reasons + 1] = "duplicate-on-" .. note
    end
    if (off_counts[note] or 0) > 1 then
      reasons[#reasons + 1] = "duplicate-off-" .. note
    end
  end
  for note in pairs(observed_on) do
    if not expected[note] then
      reasons[#reasons + 1] = "unexpected-on-" .. note
    end
  end
  for note in pairs(active) do
    reasons[#reasons + 1] = "hanging-" .. note
  end

  local status = #reasons == 0 and "pass" or "fail"
  local reason = #reasons == 0 and "ok" or table.concat(reasons, ",")
  summary_lines[#summary_lines + 1] = table.concat({
    case.case_id,
    status,
    reason,
    actual_rate,
    actual_block,
    tonumber(case.sensitivity) or 80,
    math.floor(reaper.gmem_read(ONSET_SAMPLE) or 0),
    math.floor(reaper.gmem_read(RELEASE_SAMPLE) or 0),
    expected_text(case),
    count,
    overflow,
    string.format("%.17g", dry_error),
    dry_samples,
    string.format("%.17g", synth_peak),
    synth_samples,
  }, "\t")
  if status ~= "pass" then
    failures[#failures + 1] = "case " .. case.case_id .. ": " .. reason
  end
end

local function capture_snapshot(case)
  local expected = {}
  for _, raw_note in ipairs(case.expected_list) do
    expected[math.floor(raw_note + 0.5)] = true
  end
  local active = {}
  local observed_on = {}
  local observed_off_after_panic = {}
  local post_panic_ons = 0
  local last_off_sample = panic_sample
  local count = math.min(
    CAPTURE_MAX_EVENTS,
    math.max(0, math.floor(reaper.gmem_read(CAPTURE_COUNT) or 0))
  )
  for index = 0, count - 1 do
    local cell = CAPTURE_EVENT_BASE + index * CAPTURE_EVENT_WORDS
    local absolute_sample = math.floor(reaper.gmem_read(cell) or 0)
    local status = math.floor(reaper.gmem_read(cell + 2) or 0)
    local note = math.floor(reaper.gmem_read(cell + 3) or 0)
    local velocity = math.floor(reaper.gmem_read(cell + 4) or 0)
    local kind = status & 0xF0
    if expected[note] and kind == 0x90 and velocity > 0 then
      observed_on[note] = true
      active[note] = true
      if panic_started_at and index >= panic_event_index then
        post_panic_ons = post_panic_ons + 1
      end
    elseif expected[note] and (
      kind == 0x80 or (kind == 0x90 and velocity == 0)
    ) then
      active[note] = nil
      if panic_started_at and index >= panic_event_index then
        observed_off_after_panic[note] = true
        last_off_sample = math.max(last_off_sample, absolute_sample)
      end
    end
  end

  local all_expected_active = true
  local all_expected_off_after_panic = panic_started_at ~= nil
  for note in pairs(expected) do
    if not observed_on[note] or not active[note] then
      all_expected_active = false
    end
    if not observed_off_after_panic[note] or active[note] then
      all_expected_off_after_panic = false
    end
  end
  return {
    count = count,
    all_expected_active = all_expected_active,
    all_expected_off_after_panic = all_expected_off_after_panic,
    post_panic_ons = post_panic_ons,
    last_off_sample = last_off_sample,
  }
end

local function capture_request_sample(case)
  local current_sample = math.floor(
    reaper.gmem_read(SAMPLE_COUNTER) or 0
  )
  local block_size = math.max(1, math.floor(case.block_size))
  return math.max(0, current_sample - block_size)
end

local function find_track_fx(fragment)
  if not track or not reaper.ValidatePtr2(0, track, "MediaTrack*") then
    return -1
  end
  for fx = 0, reaper.TrackFX_GetCount(track) - 1 do
    local _, name = reaper.TrackFX_GetFXName(track, fx, "")
    if name and name:find(fragment, 1, true) then
      return fx
    end
  end
  return -1
end

local function prime_detector_for_case()
  assert(track and reaper.ValidatePtr2(0, track, "MediaTrack*"))
  assert(detector_fx and detector_fx >= 0)
  if not reaper.TrackFX_GetEnabled(track, detector_fx) then
    reaper.TrackFX_SetEnabled(track, detector_fx, true)
  end
  assert(reaper.TrackFX_GetEnabled(track, detector_fx))
  reaper.TrackFX_SetParam(track, detector_fx, 4, 0)
  reaper.TrackFX_SetParam(track, detector_fx, 13, 1)
end

local function delete_disabled_detector()
  local disabled = false
  local deleted = false
  if detector_fx and detector_fx >= 0 then
    disabled = not reaper.TrackFX_GetEnabled(track, detector_fx)
    if disabled then
      local count_before = reaper.TrackFX_GetCount(track)
      reaper.TrackFX_Delete(track, detector_fx)
      deleted = reaper.TrackFX_GetCount(track) == count_before - 1
      if deleted then
        detector_fx = -1
      end
    end
  end
  synth_fx = find_track_fx("ReaSynth (Cockos)")
  probe_fx = find_track_fx("Synth Output Probe")
  local synth_present = synth_fx >= 0 and probe_fx >= 0 and
                        reaper.TrackFX_GetEnabled(track, synth_fx)
  safe_delete_passed = disabled and deleted and synth_present
  return disabled, deleted, synth_present
end

local function finish_panic_trial(case, snapshot, forced_reason)
  local reasons = {}
  if forced_reason then
    reasons[#reasons + 1] = forced_reason
  end
  local expected_events = 2 * #case.expected_list
  if snapshot.count ~= expected_events then
    reasons[#reasons + 1] = "event-count-" .. snapshot.count
  end
  if snapshot.post_panic_ons ~= 0 then
    reasons[#reasons + 1] = "post-panic-on"
  end
  local elapsed_samples = snapshot.last_off_sample - panic_sample
  local maximum_samples = math.floor(
    PANIC_OFF_TIMEOUT_SECONDS * case.sample_rate + 0.5
  )
  if elapsed_samples < 0 or elapsed_samples > maximum_samples then
    reasons[#reasons + 1] = "panic-off-latency"
  end
  if not snapshot.all_expected_off_after_panic then
    reasons[#reasons + 1] = "missing-panic-off"
  end

  local disabled = false
  local deleted = false
  local synth_present = find_track_fx("ReaSynth (Cockos)") >= 0
  if #reasons == 0 then
    panic_trials_passed = panic_trials_passed + 1
    if case.panic_trial == PANIC_TRIALS_REQUIRED and
       panic_trials_passed == PANIC_TRIALS_REQUIRED and
       #failures == 0 then
      disabled, deleted, synth_present = delete_disabled_detector()
      if not disabled then
        reasons[#reasons + 1] = "detector-disable-failed"
      end
      if not deleted then
        reasons[#reasons + 1] = "detector-delete-failed"
      end
      if not synth_present then
        reasons[#reasons + 1] = "synth-missing-after-delete"
      end
    end
  end

  local status = #reasons == 0 and "pass" or "fail"
  local reason = #reasons == 0 and "ok" or table.concat(reasons, ",")
  safety_lines[#safety_lines + 1] = table.concat({
    case.panic_trial,
    status,
    reason,
    panic_sample,
    snapshot.last_off_sample,
    string.format("%.3f", 1000 * elapsed_samples / case.sample_rate),
    disabled and 1 or 0,
    deleted and 1 or 0,
    synth_present and 1 or 0,
  }, "\t")
  if status == "pass" then
    case_forced_reason = nil
  else
    case_forced_reason = reason
  end
  stop_finish_suite = status ~= "pass"
end

local function clean_track()
  if track and reaper.ValidatePtr2(0, track, "MediaTrack*") then
    reaper.DeleteTrack(track)
  end
  track = nil
end

local function finish_suite()
  if finished then
    return
  end
  finished = true
  reaper.OnStopButton()
  if host_mode then
    if panic_trials_passed ~= PANIC_TRIALS_REQUIRED then
      failures[#failures + 1] = string.format(
        "panic trials %d/%d",
        panic_trials_passed,
        PANIC_TRIALS_REQUIRED
      )
    end
    if not safe_delete_passed then
      failures[#failures + 1] = "safe detector delete gate not reached"
    end
  end
  clean_track()
  if undo_open then
    reaper.Undo_EndBlock2(0, "M3 Polyphonic MIDI disposable integration", -1)
    undo_open = false
  end
  atomic_write(events_path, event_lines)
  atomic_write(summary_path, summary_lines)
  atomic_write(safety_path, safety_lines)
  if #failures == 0 then
    reaper.ShowConsoleMsg("M3 integration suite: PASS\n")
  else
    reaper.ShowConsoleMsg(
      "M3 integration suite: FAIL\n" .. table.concat(failures, "\n") .. "\n"
    )
  end
  if automated_project then
    reaper.GetSetProjectInfo(0, "DIRTY", 0, true)
  end
  write_phase("suite-finish")
  if automated_project then
    reaper.defer(function()
      reaper.Main_OnCommand(40004, 0)
    end)
  end
end

local poll_case
local poll_source_ready
local complete_case_after_stop
local start_next_case
local poll_safe_bypass

start_next_case = function()
  case_index = case_index + 1
  if case_index > #cases then
    finish_suite()
    return
  end
  command_generation = command_generation + 1
  local case = cases[case_index]
  if case.panic_trial and #failures > 0 then
    finish_suite()
    return
  end
  source_completed = nil
  panic_started_at = nil
  panic_sample = 0
  panic_event_index = 0
  safe_bypass_started_at = nil
  safe_bypass_snapshot = nil
  case_forced_reason = nil
  stop_finish_suite = false
  reaper.gmem_write(STATE, 0)
  reaper.gmem_write(SOURCE_ACK, 0)
  reaper.gmem_write(SOURCE_READY, 0)
  reaper.SetEditCurPos(0, false, false)
  write_phase("case-" .. case.case_id .. "-prime-start")
  prime_detector_for_case()
  reaper.OnPlayButton()
  source_ready_started = reaper.time_precise()
  reaper.defer(poll_source_ready)
end

poll_source_ready = function()
  if finished then
    return
  end
  local case = cases[case_index]
  local now = reaper.time_precise()
  local init_count = math.floor(
    reaper.gmem_read(SOURCE_INIT_COUNT) or 0
  )
  local ready = math.floor(reaper.gmem_read(SOURCE_READY) or 0)
  local heartbeat = math.floor(reaper.gmem_read(SOURCE_HEARTBEAT) or 0)
  local playing = (reaper.GetPlayState() & 1) ~= 0
  if playing and init_count > 0 and ready == init_count and heartbeat >= 4 then
    case_init_count = init_count
    configure_case(
      case,
      command_generation,
      track,
      detector_fx,
      host_mode
    )
    write_phase(string.format(
      "case-%d-source-ready init=%d heartbeat=%d",
      case.case_id,
      init_count,
      heartbeat
    ))
    write_phase("case-" .. case.case_id .. "-play-start")
    case_started = now
    reaper.defer(poll_case)
    return
  end
  if now - source_ready_started >= SOURCE_READY_TIMEOUT_SECONDS then
    reaper.OnStopButton()
    record_case(case, "source-not-ready")
    finish_suite()
    return
  end
  reaper.defer(poll_source_ready)
end

complete_case_after_stop = function()
  if finished then
    return
  end
  local case = cases[case_index]
  if (reaper.GetPlayState() & 1) == 0 then
    record_case(case, case_forced_reason)
    reaper.gmem_write(STATE, 0)
    if stop_finish_suite then
      finish_suite()
    else
      reaper.defer(start_next_case)
    end
    return
  end
  if reaper.time_precise() - stop_started >= TRANSPORT_STOP_TIMEOUT_SECONDS then
    record_case(case, "transport-stop-timeout")
    finish_suite()
    return
  end
  reaper.defer(complete_case_after_stop)
end

poll_safe_bypass = function()
  if finished then
    return
  end
  local case = cases[case_index]
  local now = reaper.time_precise()
  if detector_fx and detector_fx >= 0 and
     not reaper.TrackFX_GetEnabled(track, detector_fx) then
    finish_panic_trial(case, safe_bypass_snapshot)
    reaper.OnStopButton()
    write_phase("panic-trial-" .. case.panic_trial .. "-complete")
    stop_started = now
    reaper.defer(complete_case_after_stop)
    return
  end
  if now - safe_bypass_started_at >= SAFE_BYPASS_TIMEOUT_SECONDS then
    finish_panic_trial(
      case,
      safe_bypass_snapshot,
      "safe-bypass-disable-timeout"
    )
    reaper.OnStopButton()
    write_phase("panic-trial-" .. case.panic_trial .. "-failed")
    stop_started = now
    reaper.defer(complete_case_after_stop)
    return
  end
  reaper.defer(poll_safe_bypass)
end

poll_case = function()
  if finished then
    return
  end
  local case = cases[case_index]
  local state = math.floor(reaper.gmem_read(STATE) or 0)
  local ack = math.floor(reaper.gmem_read(SOURCE_ACK) or 0)
  local init_count = math.floor(
    reaper.gmem_read(SOURCE_INIT_COUNT) or 0
  )
  local now = reaper.time_precise()
  local case_timeout_seconds = host_mode and CASE_TIMEOUT_SECONDS or
                               MATRIX_CASE_TIMEOUT_SECONDS
  if state == STATE_FAULT then
    reaper.OnStopButton()
    record_case(case, "source-fault")
    finish_suite()
    return
  end
  if reaper.gmem_read(CAPTURE_OVERFLOW) ~= 0 then
    reaper.OnStopButton()
    record_case(case, "capture-overflow")
    finish_suite()
    return
  end
  if init_count ~= case_init_count then
    reaper.OnStopButton()
    record_case(case, "source-reinitialized")
    finish_suite()
    return
  end
  if ack ~= command_generation then
    if now - case_started >= case_timeout_seconds then
      reaper.OnStopButton()
      record_case(case, "source-not-acknowledged")
      finish_suite()
      return
    end
    reaper.defer(poll_case)
    return
  end
  if case.panic_trial then
    local snapshot = capture_snapshot(case)
    if not panic_started_at and snapshot.all_expected_active then
      panic_sample = capture_request_sample(case)
      panic_event_index = snapshot.count
      reaper.TrackFX_SetParam(track, detector_fx, 4, 0)
      reaper.TrackFX_SetParam(track, detector_fx, 13, 1)
      panic_started_at = now
      write_phase(string.format(
        "panic-trial-%d-start sample=%d",
        case.panic_trial,
        panic_sample
      ))
      reaper.defer(poll_case)
      return
    end
    if panic_started_at then
      if snapshot.all_expected_off_after_panic then
        if case.panic_trial == PANIC_TRIALS_REQUIRED then
          safe_bypass_snapshot = snapshot
          safe_bypass_started_at = now
          reaper.SetOnlyTrackSelected(track)
          local loaded = pcall(dofile, safe_bypass_path)
          if loaded then
            write_phase("safe-bypass-inline-start")
            reaper.defer(poll_safe_bypass)
          else
            finish_panic_trial(
              case,
              snapshot,
              "safe-bypass-script-error"
            )
            reaper.OnStopButton()
            write_phase("panic-trial-" .. case.panic_trial .. "-failed")
            stop_started = now
            reaper.defer(complete_case_after_stop)
          end
        else
          finish_panic_trial(case, snapshot)
          reaper.OnStopButton()
          write_phase("panic-trial-" .. case.panic_trial .. "-complete")
          stop_started = now
          reaper.defer(complete_case_after_stop)
        end
        return
      end
      if now - panic_started_at >= PANIC_OFF_TIMEOUT_SECONDS then
        finish_panic_trial(case, snapshot, "panic-off-timeout")
        reaper.OnStopButton()
        write_phase("panic-trial-" .. case.panic_trial .. "-failed")
        stop_started = now
        reaper.defer(complete_case_after_stop)
        return
      end
    end
  end
  if state == STATE_COMPLETE and not panic_started_at then
    source_completed = source_completed or now
    if now - source_completed >= RELEASE_SETTLE_SECONDS then
      reaper.OnStopButton()
      write_phase("case-" .. case.case_id .. "-play-complete")
      stop_started = now
      reaper.defer(complete_case_after_stop)
      return
    end
  end
  if now - case_started >= case_timeout_seconds then
    reaper.OnStopButton()
    record_case(case, "timeout")
    finish_suite()
    return
  end
  reaper.defer(poll_case)
end

reaper.RecursiveCreateDirectory(result_directory, 0)
os.remove(phase_path)
write_phase("script-start")
reaper.gmem_attach("m3_poly_midi_tests_v1")
reaper.Undo_BeginBlock2(0)
undo_open = true
local index = reaper.CountTracks(0)
reaper.InsertTrackAtIndex(index, false)
track = assert(reaper.GetTrack(0, index))
reaper.GetSetMediaTrackInfo_String(
  track,
  "P_NAME",
  "M3 disposable integration",
  true
)
reaper.SetMediaTrackInfo_Value(track, "I_NCHAN", 2)
assert(reaper.CreateNewMIDIItemInProj(track, 0, 2, false))
source_fx = reaper.TrackFX_AddByName(
  track,
  "JS: tests/ajuntanaga_M3 Polyphonic MIDI - Signal Source",
  false,
  1
)
detector_fx = reaper.TrackFX_AddByName(
  track,
  "JS: ajuntanaga_M3 Polyphonic Audio to MIDI",
  false,
  1
)
capture_fx = reaper.TrackFX_AddByName(
  track,
  "JS: tests/ajuntanaga_M3 Polyphonic MIDI - MIDI Capture",
  false,
  1
)
synth_fx = reaper.TrackFX_AddByName(
  track,
  "VSTi: ReaSynth (Cockos)",
  false,
  1
)
if synth_fx < 0 then
  synth_fx = reaper.TrackFX_AddByName(
    track,
    "ReaSynth (Cockos)",
    false,
    1
  )
end
probe_fx = reaper.TrackFX_AddByName(
  track,
  "JS: tests/ajuntanaga_M3 Polyphonic MIDI - Synth Output Probe",
  false,
  1
)
assert(
  source_fx >= 0 and detector_fx >= 0 and capture_fx >= 0 and
  synth_fx >= 0 and probe_fx >= 0
)
assert(
  source_fx == 0 and detector_fx == 1 and capture_fx == 2 and
  synth_fx == 3 and probe_fx == 4
)
assert(reaper.TrackFX_GetEnabled(track, synth_fx))
reaper.TrackFX_SetParam(track, detector_fx, 1, 0)
reaper.TrackFX_SetParam(track, detector_fx, 5, 0)
reaper.TrackFX_SetParam(track, detector_fx, 14, 1)
write_phase("chain-ready")
reaper.defer(start_next_case)
