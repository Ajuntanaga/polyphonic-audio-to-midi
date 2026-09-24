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
SUPPORTED_SAMPLE_RATES = (44100, 48000, 88200, 96000)
DEFAULT_BLOCK_SIZE = 256
SUPPORTED_BLOCK_SIZES = (32, 64, 128, 256, 512, 1024)
DEFAULT_INPUT_CHANNELS = 6
DEFAULT_OUTPUT_CHANNELS = 2
SETUP_SCRIPT_NAME = "ajuntanaga_M3 Live Guitar to MIDI.lua"
DEFAULT_NATIVE_BUNDLE = (
    ROOT / "build/vst3/release/VST3/M3_Polyphonic_Audio_to_MIDI.vst3"
)


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


NATIVE_SETUP_SCRIPT = r'''local function add_fx(track, name)
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
  "M3 Native 8-String Guitar to MIDI",
  true
)
reaper.SetMediaTrackInfo_Value(track, "I_NCHAN", 2)
reaper.SetMediaTrackInfo_Value(track, "I_RECARM", 1)
reaper.SetMediaTrackInfo_Value(track, "I_RECINPUT", 0)
reaper.SetMediaTrackInfo_Value(track, "I_RECMON", 1)
reaper.SetMediaTrackInfo_Value(track, "D_VOL", 0.25)

local detector = add_fx(track, "VST3: M3 Polyphonic Audio to MIDI")
reaper.TrackFX_SetParamNormalized(track, detector, 0, 0.0)
reaper.TrackFX_SetParamNormalized(track, detector, 1, 0.0)
reaper.TrackFX_SetParamNormalized(track, detector, 4, 0.75)
reaper.TrackFX_SetParamNormalized(track, detector, 6, 0.095238095238)
reaper.TrackFX_SetParamNormalized(track, detector, 7, 0.714285714286)
reaper.TrackFX_SetParamNormalized(track, detector, 8, 1.0)
reaper.TrackFX_SetParamNormalized(track, detector, 9, 0.333333333333)
reaper.TrackFX_SetParamNormalized(track, detector, 14, 0.0)

local synth = reaper.TrackFX_AddByName(track, "VSTi: ReaSynth (Cockos)", false, 1)
if synth < 0 then
  synth = add_fx(track, "ReaSynth (Cockos)")
end

reaper.SetOnlyTrackSelected(track)
reaper.TrackList_AdjustWindows(false)
reaper.TrackFX_Show(track, detector, 3)
reaper.UpdateArrange()
reaper.Undo_EndBlock2(0, "Create M3 native 8-string guitar-to-MIDI live chain", -1)
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
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    block_size: int = DEFAULT_BLOCK_SIZE,
    input_channels: int = DEFAULT_INPUT_CHANNELS,
    output_channels: int = DEFAULT_OUTPUT_CHANNELS,
    detector: str = "jsfx",
    native_bundle: pathlib.Path | None = None,
) -> pathlib.Path:
    root = root.resolve()
    output = output.resolve()
    if _overlaps_live_profile(output):
        raise ValueError("refusing to stage into, below, or above live REAPER profile")
    effects = root / "Effects"
    if not effects.is_dir():
        raise ValueError(f"missing Effects tree: {effects}")
    if detector not in {"jsfx", "native"}:
        raise ValueError("detector must be 'jsfx' or 'native'")
    if type(sample_rate) is not int or sample_rate not in SUPPORTED_SAMPLE_RATES:
        raise ValueError("sample rate must be one of the supported live rates")
    if type(block_size) is not int or block_size not in SUPPORTED_BLOCK_SIZES:
        raise ValueError("block size must be one of the supported live sizes")
    if type(input_channels) is not int or not 1 <= input_channels <= 64:
        raise ValueError("input channels must be an integer between 1 and 64")
    if type(output_channels) is not int or not 1 <= output_channels <= 64:
        raise ValueError("output channels must be an integer between 1 and 64")

    resolved_native_bundle: pathlib.Path | None = None
    if detector == "native":
        resolved_native_bundle = (native_bundle or DEFAULT_NATIVE_BUNDLE).resolve()
        if not resolved_native_bundle.is_dir():
            raise ValueError(f"missing native VST3 bundle: {resolved_native_bundle}")
        if resolved_native_bundle.name != "M3_Polyphonic_Audio_to_MIDI.vst3":
            raise ValueError("native bundle must be M3_Polyphonic_Audio_to_MIDI.vst3")
        native_module = (
            resolved_native_bundle
            / "Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI.so"
        )
        if not native_module.is_file():
            raise ValueError(f"missing native VST3 module: {native_module}")

    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(effects, output / "Effects", dirs_exist_ok=True)
    (output / "Scripts").mkdir(parents=True, exist_ok=True)

    if resolved_native_bundle is not None:
        native_output = output / "VST3" / resolved_native_bundle.name
        shutil.copytree(resolved_native_bundle, native_output, dirs_exist_ok=True)

    profile = (
        "[reaper]\n"
        "linux_audio_mode=1\n"
        f"alsa_indev={input_device}\n"
        f"alsa_outdev={output_device}\n"
        f"linux_audio_bsize={block_size}\n"
        "linux_audio_bufs=2\n"
        f"linux_audio_nch_in={input_channels}\n"
        f"linux_audio_nch_out={output_channels}\n"
        f"linux_audio_srate={sample_rate}\n"
        "newprojdo=0\n"
        "saveFlags=0\n"
        "warnmaxram64=0\n"
    )
    if resolved_native_bundle is not None:
        profile += f"vstpath={output / 'VST3'}\n"
    (output / "reaper.ini").write_text(profile, encoding="utf-8")
    (output / "Scripts" / SETUP_SCRIPT_NAME).write_text(
        NATIVE_SETUP_SCRIPT if resolved_native_bundle is not None else SETUP_SCRIPT,
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
    parser.add_argument(
        "--sample-rate",
        type=int,
        choices=SUPPORTED_SAMPLE_RATES,
        default=DEFAULT_SAMPLE_RATE,
    )
    parser.add_argument(
        "--block-size",
        type=int,
        choices=SUPPORTED_BLOCK_SIZES,
        default=DEFAULT_BLOCK_SIZE,
    )
    parser.add_argument("--input-channels", type=int, default=DEFAULT_INPUT_CHANNELS)
    parser.add_argument("--output-channels", type=int, default=DEFAULT_OUTPUT_CHANNELS)
    parser.add_argument("--detector", choices=("jsfx", "native"), default="jsfx")
    parser.add_argument("--native-bundle", type=pathlib.Path)
    args = parser.parse_args(argv)
    output = stage_live_profile(
        ROOT,
        args.output,
        input_device=args.input_device,
        output_device=args.output_device,
        sample_rate=args.sample_rate,
        block_size=args.block_size,
        input_channels=args.input_channels,
        output_channels=args.output_channels,
        detector=args.detector,
        native_bundle=args.native_bundle,
    )
    print(f"staged M3 live MIDI profile: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
