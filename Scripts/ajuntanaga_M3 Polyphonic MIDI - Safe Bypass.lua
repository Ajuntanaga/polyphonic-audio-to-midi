-- @description M3 Polyphonic MIDI - Safe Bypass
-- @version 0.2.0
-- @author ajuntanaga
-- @about Sends Panic, waits for MIDI cleanup, then disables the detector.

local DETECTOR_NAME = "M3 Polyphonic Audio to MIDI"
local SAFE_BYPASS_MIN_DELAY_SECONDS = 0.100
local SAFE_BYPASS_PROCESS_BLOCKS = 4

local function report_failure(message)
  reaper.ShowMessageBox(
    message,
    "M3 Polyphonic MIDI - Safe Bypass",
    0
  )
end

local function audio_number(name, fallback)
  local ok, text = reaper.GetAudioDeviceInfo(name)
  local value = ok and tonumber(text) or nil
  if not value or value ~= value or value <= 0 then
    return fallback
  end
  return value
end

local sample_rate = audio_number("SRATE", 48000)
local block_size = audio_number("BSIZE", 512)
local safe_bypass_delay_seconds = math.max(
  SAFE_BYPASS_MIN_DELAY_SECONDS,
  SAFE_BYPASS_PROCESS_BLOCKS * block_size / sample_rate
)

local track = reaper.GetSelectedTrack(0, 0)
if not track then
  report_failure("Select the track containing the M3 detector first.")
  return
end

local detector_fx = -1
local match_count = 0
for fx = 0, reaper.TrackFX_GetCount(track) - 1 do
  local _, name = reaper.TrackFX_GetFXName(track, fx, "")
  if name and name:find(DETECTOR_NAME, 1, true) then
    detector_fx = fx
    match_count = match_count + 1
  end
end

if match_count ~= 1 then
  report_failure(
    match_count == 0 and
      "No M3 Polyphonic Audio to MIDI detector was found on the selected track." or
      "More than one M3 detector is on the selected track; bypass them individually."
  )
  return
end

if not reaper.TrackFX_GetEnabled(track, detector_fx) then
  report_failure("The M3 detector is already disabled.")
  return
end

local detector_guid = reaper.TrackFX_GetFXGUID(track, detector_fx)
if not detector_guid or detector_guid == "" then
  report_failure("The M3 detector could not be identified safely.")
  return
end

local original_sensitivity = reaper.TrackFX_GetParam(track, detector_fx, 4)
local sensitivity_muted = reaper.TrackFX_SetParam(track, detector_fx, 4, 0)
if sensitivity_muted == false then
  report_failure("Sensitivity could not be muted; Panic was not sent.")
  return
end
local panic_set = reaper.TrackFX_SetParam(track, detector_fx, 13, 1)
if panic_set == false then
  reaper.TrackFX_SetParam(track, detector_fx, 4, original_sensitivity)
  report_failure("Panic could not be sent; the detector was not disabled.")
  return
end

local started = reaper.time_precise()

local function find_detector_by_guid()
  if not reaper.ValidatePtr2(0, track, "MediaTrack*") then
    return -1
  end
  for fx = 0, reaper.TrackFX_GetCount(track) - 1 do
    if reaper.TrackFX_GetFXGUID(track, fx) == detector_guid then
      return fx
    end
  end
  return -1
end

local function disable_detector()
  if reaper.time_precise() - started < safe_bypass_delay_seconds then
    reaper.defer(disable_detector)
    return
  end

  local current_fx = find_detector_by_guid()
  if current_fx < 0 then
    report_failure("The M3 detector moved or was removed before bypass completed.")
    return
  end

  reaper.TrackFX_SetEnabled(track, current_fx, false)
  reaper.TrackFX_SetParam(track, current_fx, 13, 0)
  local sensitivity_restored = reaper.TrackFX_SetParam(
    track, current_fx, 4, original_sensitivity
  )
  if reaper.TrackFX_GetEnabled(track, current_fx) then
    report_failure("The M3 detector did not disable; Panic was still sent.")
    return
  end
  if sensitivity_restored == false then
    report_failure(
      "The M3 detector disabled, but its sensitivity could not be restored."
    )
    return
  end
  reaper.UpdateArrange()
end

reaper.defer(disable_detector)
