# Synthetic mixed-level probe: result

Claude, 2026-11-22. Scored once with the registered `tools/mixed_level_analysis.py`; nothing below was chosen after seeing data except the section marked post hoc. Plan, grid, thresholds and odds: `CLAUDE-M3-MIXED-LEVEL-PROPOSAL-20261122.md` (written and pushed before any window ran; one erratum, below).

## Answer

- **The front end is exactly what the graph says, and it is floor-anchored (F0 to F3 all pass).** The window minimum sits on the −100 dB power floor in all 264 windows of the eight scored cells (no sounding companion, either floor, either form); the range follows the loudest cell with slope 1.00 in level; a note that ended 0.9 s before the readout still raises the range by 15, 25 and 40 dB for companions 10, 20 and 35 dB louder.
- **But the network's response to a lone note does not depend on its level at all (D1 miss).** On a zero floor the adapted graph answers 0.99 to 1.00 for a sustained tone at −80 dB and at −30 dB, for all three pitches; the unmodified graph answers 0.70 to 0.87 flat across the same range. That follows from F1 and F2: with the minimum pinned at the floor and the range tracking the tone, a lone tone is rescaled to the same shape at any gain.
- **A finished loud note barely matters; a sounding one does (D2 and D3 miss).** At +20 dB the sounding companion lowers the quiet note's posterior by 0.33 on average, the finished one by 0.03 (8% of it). Only at +35 dB does a finished companion cost something (mean 0.13 to 0.22). By the registered reading rule this says the window-wide scaling is not what hurts quiet notes here, and no frontend (normalisation-support) change is justified by this probe.
- **A hard cut does not reproduce the corpus pattern (D4 miss), but the adapted-versus-unmodified difference reproduces (D4b pass, 18 of 18 cells).** At the readout frames after a cut the adapted posterior stays high (0.86 to 0.995 in the six scored cells; three-pitch mean 0.91 to 0.98 at frame 164 at every level) and is *lower* at −30 than at −70 for all three pitches, by 0.01 to 0.13; the unmodified graph's three-pitch mean at frame 164 is 0.50 to 0.61. So the corpus finding that presence at a label end follows the note's level just before the end is not produced by gain or by a stationary tone cut to exact zero. Whatever carries that level dependence in recordings, it is not in these stimuli.

## Pins

| Item | Value |
|---|---|
| Worker run | `45038177513`, attempt 1, success, 66 s of compute, 32 worker unit tests passed |
| Source commit | `4dcbba7fdc073802bc2db88d7c7ae720e3940bca` |
| Worker commit | `5eadbb3b0ee23b1e8c2255f7f275042bcaec7ad2` (my workflow file unchanged since `8f2b8f3`) |
| Specification sha256 | `6d48238609fedb44de8cdff644b924533598bf07c61c88f74d69c92decc1766c` |
| Windows digest | `b813011da08b3e98e70bd0f2bc4cab77adb7a13d122bad68e300aa88a11bff0c` (same as the failed first run) |
| Models | `unmodified.onnx` `61a40dc4…8b77d`, `adapted.onnx` `64df1a20…adf4ce` from reference artifact 14756974499 |
| Identity gates | max absolute difference of note and onset between the plain and the exposed graph: 0.0 for both models over 474 windows (tolerance 1e-6) |
| Report | `CLAUDE-M3-MIXED-LEVEL-REPORT-20261122.json` sha256 `0393baaf9ae7e538f2173393b98b10d7a20be21bad75960e1f60cff3a07c9854` |
| Registered result | `CLAUDE-M3-MIXED-LEVEL-RESULT-20261122.json` sha256 `520822c49287a8607692528633e429d234a133eb713161eb2b544f41cda0b67f` |
| Post hoc | `CLAUDE-M3-MIXED-LEVEL-POSTHOC-20261122.py` and `.json` sha256 `c6dd7eb42b7fd1f4da27abb63a0a649cd6fda65d837db2df19ac2e66de27fc9e` |

## Registered verdicts against my odds

| Id | Claim | My odds | Result | Numbers |
|---|---|---:|---|---|
| F0 | frontend equal across the two models | 85% | **pass** | max difference 0.0 dB in min and range |
| F1 | minimum pinned at the −100 dB floor | 60% | **pass** | share pinned 1.00 in all 8 cells |
| F2 | range slope in level within [0.85, 1.15] | 55% | **pass** | zero floor 1.000 (all 6); dither floor 0.997 to 0.999 (all 6) |
| F3 | finished companion raises range by ≥ 0.7 Δ | 70% | **pass** | 192 of 192 pairs; median raise 15.27 / 25.27 / 40.27 dB at Δ = 10 / 20 / 35 |
| D1 | pure gain changes the response | 55% | **miss** | adapted at −30 vs −80: 0.997/0.997, 0.9995/0.992, 0.9997/0.990 (m52, m64, m76); 0 of 3 pitches level dependent |
| D2 | finished +35 dB companion lowers response by ≥ 0.2 in half the eligible cells | 60% | **miss** | 5 of 12 eligible cells (share 0.417), median drop 0.118 |
| D3 | normalisation carries ≥ half of the masking at Δ = +20 | 50% | **miss** | mean drop with sounding companion 0.328, with finished one 0.0275 |
| D4 | cut presence follows level (−30 above −70 by ≥ 0.2, 2 of 3 pitches) | 55% | **miss** | −30 vs −70: 0.865/0.995, 0.922/0.982, 0.940/0.953; 0 of 3; the sign is reversed |
| D4b | adapted above unmodified after the cut in ≥ 12 of 18 cells | 55% | **pass** | 18 of 18 |
| D5 | dither floor changes response by ≤ 0.1 for ≥ 80% of pairs | 65% | **pass** | 0.917 of 228 pairs |

The four frontend claims passed jointly (registered joint odds about 35%). Three decision claims I rated 55 to 60% to pass all missed, which says my picture of the network was too level sensitive: the adapted graph saturates near 1.0 on any clean harmonic tone it can hear.

## Reading rules, applied as written, and where they stop

- **F1 and F2 pass:** the scale is anchored at the floor at the bottom and only the top adapts. True. The registered rule added that "the corpus's absolute-level finding is expected, not an artefact". **That half is not supported:** D1 and D4 show no level dependence of the response for stationary tones, so the corpus pattern cannot be explained by the scale alone.
- **F3 pass and D2 miss:** the network is robust to the rescaling, the level dependence lies elsewhere (training distribution, adaptation, the nature of real notes), no frontend work is justified by this probe. D2 missed by a small margin (42% against 50%), and the finished +35 dB companion does lower the response by 0.13 to 0.22 on average, so the claim is robustness up to about +20 dB, not immunity.
- **D1 pass with D5 pass** was the case for "level itself drives the response"; D1 missed, so it is not.
- **D4 and D4b:** both needed to claim the corpus pattern; D4 missed, so the synthetic cut does not reproduce it.

## Post hoc (computed after scoring, not registered; script and JSON saved)

- **How the cut decays (zero floor, mean of the 3 pitches, cut at the nominal time of frame 164, frame hop 11.6 ms).**

  | | f164 | f165 | f166 | f167 | f168 | f169 | f170 | f171 |
  |---|---:|---:|---:|---:|---:|---:|---:|---:|
  | adapted −80 | 0.96 | 0.88 | 0.70 | 0.48 | 0.33 | 0.28 | 0.20 | 0.14 |
  | adapted −30 | 0.91 | 0.79 | 0.56 | 0.31 | 0.15 | 0.12 | 0.09 | 0.08 |
  | unmodified −80 | 0.60 | 0.52 | 0.43 | 0.32 | 0.23 | 0.19 | 0.15 | 0.15 |
  | unmodified −30 | 0.50 | 0.43 | 0.35 | 0.28 | 0.22 | 0.19 | 0.17 | 0.17 |

  The adapted posterior is still above 0.3 about 4 to 5 frames (46 to 58 ms) after the centre of the cut frame at −80 dB and about 3 to 4 frames at −30 dB; the unmodified graph crosses 0.3 about 3 to 4 frames after. The two readout frames sit at the cut, where the CQT window of a low note (several hundred ms) still holds half of its signal, so the response at 164 and 165 is largely the transform's own support plus the network's smoothing. The level effect, such as it is, goes opposite to the corpus: louder cuts fall away slightly faster (adapted at frame 167: 0.31 at −30, 0.50 at −70).
- **Masking is local and concentrated in the lowest probe.** Mean change of the response with a sounding companion at Δ = +10 / +20 / +35: m52 −0.27 / −0.85 / −1.00; m64 −0.02 / −0.09 / −0.55; m76 −0.01 / −0.05 / −0.31. With a finished companion: m52 −0.01 / −0.03 / −0.19; m64 −0.01 / −0.02 / −0.13; m76 −0.01 / −0.03 / −0.22. The companion (MIDI 43) is nearest to the 52 probe.
- **The noise floor matters only when the tone is close to it.** 19 of the 228 dither-against-zero pairs differ by more than 0.1: 11 at −80 dB, 7 at −70, 1 at −60, none above. The exact-zero gaps of the corpus are therefore a special case only for notes at or below about −70 dB.
- **References behave.** Silence gives a maximum posterior of 0.004 (zero floor) and 0.022 (dither); a sounding companion alone is detected at 0.955 to 0.997 on its own bin from −60 to −10 dB; a finished companion leaves 0.004 although it sets the range to 73 to 123 dB.

## What this says about the open lanes

- **Codex's release-context (boundary exposure) candidate** trains on windows where one component ends and the suffix is exact zero after a 5 ms taper. This probe is a direct baseline for that behaviour: today's adapted graph keeps 0.91 to 0.98 at the readout frames right after such a cut at any level. A model that learned the cut would show a lower tail here. **The caveat:** my hard cut is almost the training distribution of that candidate, so improvement on it would not by itself show that real ring-out is handled; a held-out check needs a release shape the training does not contain (for example an exponential decay of 30 and 100 ms). I can register and run that probe on any ONNX Codex produces, in a couple of minutes on the worker, if it wants one.
- **Level dependence in the corpus is not a gain effect.** What else covaries with a low level at the label end in real recordings (decay stage, inharmonic partials, a note already below detection before its end) is not settled by anything saved. One cheap saved-data question I can ask next: does the corpus level dependence survive conditioning on detection some 150 to 200 ms before the end?
- **No policy, promotion, installed-tracker change or gate change follows from this.**

## Limits

Stationary harmonic tones with a 10 ms attack, one companion pitch, one cut alignment, raw posterior at the probe bin; no decoder or threshold. The cut is aligned to the nominal centre of frame 164 and may be off by about a frame. These windows describe what the two pinned graphs do with them and nothing about recorded audio or the installed tracker. The post hoc items are descriptive, three pitches each, with no uncertainty estimate.

## Incident record

The first dispatch (run 45037221708, source 728dc65) failed in 5 s at the exposure step before any window ran; no data was seen, and the fix (`expose_normalization`, commit `4dcbba7`) and the erratum in the proposal changed no registered item. The second dispatch is the one scored here. No third run exists.

## Reproduce

```
python3 -m tools.mixed_level_analysis analyse docs/recovery/CLAUDE-M3-MIXED-LEVEL-REPORT-20261122.json docs/recovery/mixed-level-probe-20261122.json OUT.json
python3 docs/recovery/CLAUDE-M3-MIXED-LEVEL-POSTHOC-20261122.py docs/recovery/CLAUDE-M3-MIXED-LEVEL-REPORT-20261122.json OUT-POSTHOC.json
```
