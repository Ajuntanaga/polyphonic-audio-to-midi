#!/usr/bin/env python3
"""Stage a disposable, hardware-targeted REAPER profile for live M3 use."""

import argparse
import pathlib
import shutil


ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE_REAPER_PROFILE = (pathlib.Path.home() / ".config" / "REAPER").resolve()
DEFAULT_INPUT_DEVICE = "hw:R24,0"
DEFAULT_OUTPUT_DEVICE = "hw:R24,0"
DEFAULT_SAMPLE_RATE = 48000
DEFAULT_BLOCK_SIZE = 256
DEFAULT_INPUT_CHANNELS = 6
DEFAULT_OUTPUT_CHANNELS = 2
SETUP_SCRIPT_NAME = "ajuntanaga_M3 Live Guitar to MIDI.lua"


SETUP_SCRIPT = r'''local function add_fx(track, name)
  local fx = reaper.TrackFX_AddByName(track, name, false, 1)
  assert(fx >= 0, "required effect is unavailable: " .. name)
  return fx
end

reaper.Undo_BeginBlock2(0)
local index = reaper.CountTracks(0)
reaper.InsertTrackAtIndex(index, true)
local track = assert(reaper.GetTrack(0, index))
reaper.GetSetMediaTrackInfo_String(
  track,
  "P_NAME",
  "M3 8-String Guitar to MIDI (low range)",
  true
)
reaper.SetMediaTrackInfo_Value(track, "I_NCHAN", 2)
reaper.SetMediaTrackInfo_Value(track, "I_RECARM", 1)
reaper.SetMediaTrackInfo_Value(track, "I_RECINPUT", 0)
reaper.SetMediaTrackInfo_Value(track, "I_RECMON", 1)
reaper.SetMediaTrackInfo_Value(track, "D_VOL", 0.25)

local detector = add_fx(track, "JS: ajuntanaga_M3 Polyphonic Audio to MIDI")
reaper.TrackFX_SetParam(track, detector, 0, 0)
reaper.TrackFX_SetParam(track, detector, 1, 0)
reaper.TrackFX_SetParam(track, detector, 7, 48)
reaper.TrackFX_SetParam(track, detector, 8, 1)
reaper.TrackFX_SetParam(track, detector, 9, 12)
reaper.TrackFX_SetParam(track, detector, 14, 0)

local synth = reaper.TrackFX_AddByName(track, "VSTi: ReaSynth (Cockos)", false, 1)
if synth < 0 then
  synth = add_fx(track, "ReaSynth (Cockos)")
end

reaper.SetOnlyTrackSelected(track)
reaper.TrackList_AdjustWindows(false)
reaper.UpdateArrange()
reaper.Undo_EndBlock2(0, "Create M3 8-String Guitar to MIDI live chain", -1)
'''


def _overlaps_live_profile(output: pathlib.Path) -> bool:
    return (
        output == LIVE_REAPER_PROFILE
        or LIVE_REAPER_PROFILE in output.parents
        or output in LIVE_REAPER_PROFILE.parents
    )


def stage_live_profile(
    root: pathlib.Path,
    output: pathlib.Path,
    *,
    input_device: str = DEFAULT_INPUT_DEVICE,
    output_device: str = DEFAULT_OUTPUT_DEVICE,
) -> pathlib.Path:
    root = root.resolve()
    output = output.resolve()
    if _overlaps_live_profile(output):
        raise ValueError("refusing to stage into, below, or above live REAPER profile")
    effects = root / "Effects"
    if not effects.is_dir():
        raise ValueError(f"missing Effects tree: {effects}")

    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(effects, output / "Effects", dirs_exist_ok=True)
    (output / "Scripts").mkdir(parents=True, exist_ok=True)

    profile = (
        "[reaper]\n"
        "linux_audio_mode=1\n"
        f"alsa_indev={input_device}\n"
        f"alsa_outdev={output_device}\n"
        f"linux_audio_bsize={DEFAULT_BLOCK_SIZE}\n"
        "linux_audio_bufs=2\n"
        f"linux_audio_nch_in={DEFAULT_INPUT_CHANNELS}\n"
        f"linux_audio_nch_out={DEFAULT_OUTPUT_CHANNELS}\n"
        f"linux_audio_srate={DEFAULT_SAMPLE_RATE}\n"
        "newprojdo=0\n"
        "saveFlags=0\n"
        "warnmaxram64=0\n"
    )
    (output / "reaper.ini").write_text(profile, encoding="utf-8")
    (output / "Scripts" / SETUP_SCRIPT_NAME).write_text(
        SETUP_SCRIPT,
        encoding="utf-8",
    )
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="stage an isolated Revelator-backed M3 live-MIDI REAPER profile"
    )
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--input-device", default=DEFAULT_INPUT_DEVICE)
    parser.add_argument("--output-device", default=DEFAULT_OUTPUT_DEVICE)
    args = parser.parse_args(argv)
    output = stage_live_profile(
        ROOT,
        args.output,
        input_device=args.input_device,
        output_device=args.output_device,
    )
    print(f"staged M3 live MIDI profile: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
