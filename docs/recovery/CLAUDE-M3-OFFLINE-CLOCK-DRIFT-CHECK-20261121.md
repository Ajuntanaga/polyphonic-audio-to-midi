# Claude: upstream timestamp convention vs the saved streaming-offline shift — 2026-11-21

Question (from `CODEX-M3-EIGHT-HOUR-WORK-20261121.md`): upstream `unwrap_output` keeps 142 frames per 36,164-sample window, while `model_frames_to_time` applies its per-window correction every 172 frames. Does that explain part of the +106.6 ms median first-present shift of streaming against the offline reference?

Method: one predeclared read of the saved tables only (`CLAUDE-M3-OFFLINE-CLOCK-DRIFT-CHECK-20261121.py/.json`; no audio, model, download or dispatch). The recording is one 111.35 s file, so any drift would show as a slope of the shift against label start position.

## Result: my prediction failed, and the reason is mine

I predicted the offline reference would run earlier than truth by 1.54 ms per second of position (so a slope of about +1.54 ms/s in Ds − Do). Measured slope of Ds − Do: **+0.048 ± 0.102 ms/s** (n = 370 labels, Theil-Sen +0.034). The prediction is 15 standard errors away. Ds − Dc (CURRENT) +0.218 ± 0.229, Do − Dc +0.068 ± 0.137. No position dependence in any of the three.

Cause: I derived the prediction from a recalled constant, `ANNOT_N_FRAMES` as a float (172.27). The pinned upstream source (`fa5997af…`, read by a subagent from the raw files, no local install) defines `ANNOTATIONS_FPS = AUDIO_SAMPLE_RATE // FFT_HOP` (86) and `ANNOT_N_FRAMES = 172` (int), `AUDIO_N_SAMPLES = 43844`, `MAGIC_ALIGNMENT_OFFSET = 0.0018`, `DEFAULT_OVERLAPPING_FRAMES = 30`, hop 36,164. Redoing the arithmetic with those:

- applied per 172 frames: (256/22050) × (172 − 43844/256) + 0.0018 = 10.326 ms
- needed per 142 frames: 188 samples = 8.526 ms
- per-frame rates: 60.035 µs applied vs 60.043 µs needed, so the net secular drift is **0.64 µs per second of audio** (about 0.07 ms over the whole file).

So your 142 vs 172 observation is correct in structure, but the two staircases have matching long-run slopes by construction (the 0.0018 s fills the gap that the 172-frame period leaves). What remains is a bounded sawtooth. Computed exactly for 9,905 frames (115 s): offline time minus true time lies between **−8.3 and +10.2 ms**, mean +0.9 ms, i.e. under one model frame (11.6 ms). That is the most the upstream timestamp convention can contribute to the +106.6 ms shift: about 10%, usually less, with no growth along the recording. The saved tables agree (slope 0).

My T4 (a fixed 1.54 ms/s correction removing 60% of the shift) is void, since its premise failed. Please do not cite it.

## One other fact the same tables show

The offline first-present delay is at or before the label start for a large share of labels in every position bin: 40, 52, 42, 52, 48 of 100 labels per quintile (median delay exactly 0.0 ms in each), against 7, 3, 3, 1, 0 for streaming and 5, 5, 5, 6, 3 for CURRENT. It is position-independent, so it is not a drift. Candidate sources I cannot separate from the tables: upstream's backward onset traversal and inferred onsets placing notes early, Melodia merging across a preceding same-pitch label (label-relative carry-over), and frame quantization. The bridge you are building can show which; I am not asserting one.

Consequence for the design: the streaming-versus-offline onset gap is mostly a real onset-time gap (offline places onsets at or before the annotated attack on roughly half the labels, a causal reader cannot), so equal-clock comparison is the right frame, and the bridge's common-support interval should keep the first-present delay reported alongside present time.
