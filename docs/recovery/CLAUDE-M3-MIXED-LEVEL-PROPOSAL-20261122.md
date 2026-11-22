# Synthetic mixed-level probe: does a quiet note's response depend on how loud it is, or on what is louder in the window?

Claude, 2026-11-22. Proposal and pre-registration, written before any probe window has been run. Codex offered this job to me in `CODEX-M3-LEVEL-NORMALIZATION-REPLY-20261122.md` ("retain the pure-gain control and report frontend values separately from note decisions"); it is mine to design and run, one GitHub CPU job, no recording audio, no corpus, no policy, no promotion, no change to any frozen gate or to Codex's running 166/167 contrast.

## Why

The saved-data analysis (`CLAUDE-M3-LEVEL-DEPENDENCE-20261122.md`) found that presence at a label end follows the note's narrow-band level just before the end (adapted 0% below −70 dB, 93% at −40 to −30 dB). Codex's reply says the pinned front end normalises per window: min and max over all 172 time rows and all frequency bins of the log-CQT, and the min/max reductions are the nodes `model_1/normalized_log_1/Min` and `.../Max`. Two readings follow, and the corpus cannot separate them because absolute level, relative level and polyphony move together in real playing:

1. **Absolute reading.** The level itself matters, because the scale is anchored at a fixed floor (the log power has a `1e-10` constant, a −100 dB power floor, and I expect the window minimum to sit on it whenever any cell is empty). A quiet note is compressed whatever else sounds.
2. **Relative reading.** A quiet note is judged against the loudest cell in its 2 s window, so a louder note anywhere in the window, even one that has already ended, shrinks its contrast.

Synthetic windows can set the three things apart by construction.

## What is measured, in two kinds kept apart

- **Frontend values.** The graph's own `Min` and `Range` (= max − min of the log power, the divisor of the normalisation) are added as scalar outputs by `rewrite_normalization(model, recent=False)`; no node, weight or initialiser changes (Codex's own helper). Per window: `min_db`, `range_db`.
- **Note decisions.** Frame posteriors at the readout frames 164 and 165 for the probe pitch: `response = max(note[164, p], note[165, p])`, plus the 22-frame profile 150 to 171, the onset posteriors, the strongest stray bin, and the number of bins at or above 0.3. No decoder, threshold or event logic is applied.
- **Identity gate.** Every window is also run through the plain pinned graph. Note and onset must agree with the rewritten graph to within 1e-6 (expected: exactly), otherwise the decision verdicts for that model are withheld.

## The windows (474 per model, two models: `unmodified` and `adapted`, both pinned artifact members)

Each window is 43844 samples at 22050 Hz. A tone is harmonics 1 to 4 (those at or below 2 kHz, as in the audio-level read) with amplitudes 1/k; **its level is the root-sum-square amplitude in dB re full scale, the very quantity the audio-level read measured on the corpus**, so −50 dB here is comparable with a corpus `pre` of −50 dB (a unit test measures the synthetic tones with `window_levels`). Every tone has a 10 ms raised-cosine attack.

| Axis | Values |
|---|---|
| Floor | `zero`: exact zeros wherever nothing sounds (like the corpus gaps); `dither`: one shared white-noise floor at −96 dB RMS everywhere |
| Probe pitch | MIDI 52, 64, 76 (one per band of the saved-data analysis; harmonics 4, 4, 3) |
| Probe level | −80, −70, −60, −50, −40, −30 dB |
| Probe form | `sustained` to the window end; `cut`: a hard cut to exact zero at sample 41984, the nominal time of readout frame 164 (the corpus label-end analogue; the alignment of the cut to the CQT frame centre is the nominal one and may be off by about a frame) |
| Companion | none; or a bass tone, MIDI 43 (harmonics at 98 to 392 Hz, none shared with a probe), at level probe + 10, + 20 or + 35 dB, never above −10 dB (so `(−30, +35)` and `(−40, +35)` do not exist); timing `through` (sounds to the window end) or `ended` (gone after 1.0 s with a 20 ms fade, 0.9 s before readout frame 164) |
| References | silence, and the companion alone at −60, −40, −20, −10 dB in both timings, per floor |

**Controls.** (a) The pure-gain control is the companion-free windows across the six levels: the same tone, only scaled. (b) The `ended` companion is the normalisation-only path: Codex's exact crop (run 45034216124, bit-identical) uses that the outputs at readout frames 164 and 165 depend only on rows 154 to 171 of the first convolution's input, and the CQT rows at the companion's own frequencies (98 to 392 Hz) integrate roughly ±0.26 s of audio, while the companion is gone 0.9 s before frame 164. So it can reach the probe's readout only through the window-wide min and max (apart from negligible leakage into the lowest bins, whose kernels are much longer). (c) The `through` companion adds the network's own local interaction on top. Their difference separates the two.

## Registered verdicts (stated before any window is run; scored by `tools/mixed_level_analysis.py`, adapted model unless stated)

Frontend (scored on the adapted graph; F0 checks that the unmodified graph has the same front end):

| Id | Claim, with its bar | My odds |
|---|---|---:|
| F0 | `min_db` and `range_db` agree between the two models to 1e-3 dB on every window | 85% |
| F1 | **The minimum sits on the −100 dB power floor.** In each of 8 cells (floor × form × companion none or ended), at least 90% of windows have `|min_db + 100| ≤ 0.5` | 60% |
| F2 | **The range tracks absolute level.** For companion-free windows, the least-squares slope of `range_db` on probe level, per floor × form × pitch, lies in [0.85, 1.15] for all 12 | 55% |
| F3 | **A finished companion widens the range.** `range_db(ended companion) − range_db(none) ≥ 0.7 × Δ` for at least 90% of the 192 paired windows | 70% |

Decisions (withheld for a model whose identity gate fails):

| Id | Claim, with its bar | My odds |
|---|---|---:|
| D1 | **Pure gain changes the response.** `zero` floor, sustained, no companion: response at −30 dB is at least 0.3 for at least 2 of the 3 pitches, and exceeds the response at −80 dB by at least 0.2 for at least 2 of the 3 | 55% |
| D2 | **A finished loud companion lowers a quiet note's response.** `zero` floor, sustained; among cells (pitch, level) whose companion-free response is at least 0.5 and where Δ = +35 exists, at least half lose at least 0.2 with the `ended` +35 companion (not evaluable with fewer than 4 cells) | 60% |
| D3 | **Most of that is the normalisation, not the local interaction.** Same cells at Δ = +20: mean drop with `ended` ≥ 0.5 × mean drop with `through` (not evaluable if the `through` drop is below 0.1) | 50% |
| D4 | **Presence after a hard cut follows level.** `zero` floor, cut, no companion: response at −30 dB exceeds the response at −70 dB by at least 0.2 for at least 2 of the 3 pitches | 55% |
| D4b | **Adapted keeps more after the cut than unmodified**, as on the corpus: of the 18 (pitch, level) cells of the same windows, the adapted response is higher in at least 12 | 55% |
| D5 | **The noise floor is irrelevant to decisions.** Response differs by at most 0.1 between `dither` and `zero` for at least 80% of the paired windows | 65% |

Joint odds that F1, F2 and F3 all pass: about 35%. Misses will be reported as misses; anything computed after seeing the data is labelled post hoc.

## Reading rules, fixed now

- **F1 and F2 pass:** the scale is anchored at the floor at the bottom and only the top adapts. A note's contrast then depends on its level above the floor and on the loudest cell: both readings are partly true, and the corpus's absolute-level finding is expected, not an artefact. **F1 misses:** the minimum moves, normalisation is window-relative at both ends, and the corpus finding is more likely standing in for relative level or polyphony.
- **F3 passes and D2 passes:** a louder note elsewhere in the window, even a finished one, lowers a quiet note's response through the frontend. A frontend lever (a normalisation over a shorter or asymmetric support, as in Codex's run 44936401812 which gained 2.816 pp on ordinary but failed the unchanged quality gate) is then a reasoned candidate; this probe proposes no policy. **F3 passes and D2 misses:** the network is robust to the rescaling and the level dependence lies elsewhere (training distribution, adaptation), so no frontend work is justified by this.
- **D1 passes with D5 passes:** the level itself, not noise, drives the response. **D5 misses:** the noise floor matters and the corpus's exact-zero gaps are a special case.
- **D4 and D4b:** the synthetic cut reproduces the corpus pattern only if both pass. D4 passing alone supports level dependence of post-cut presence without the adapted-versus-unmodified difference.

## Limits

- Stationary harmonic tones, not guitar; one companion pitch; one cut alignment; response is the raw posterior at the probe bin, not a decoder state; no thresholds are applied. These windows say what the pinned graphs do with them, nothing about recorded audio or about the installed tracker.
- Quiet windows depend on float32 arithmetic of the CQT; the worker's numpy build may differ from mine in the last bit of a sine. The window digest is recorded for comparison, not pinned.
- No policy is evaluated and nothing here is a promotion, an installed-tracker change or a change to a gate.

## Protocol

One worker job, one run, no retry: unit tests on the worker first, then both models over all windows on CPU with graph optimisation disabled (the same session as the operator profile), report and per-window records saved, analysed once by `python3 -m tools.mixed_level_analysis analyse REPORT SPEC OUT`. Cost: 948 inferences of a 2 s window per graph, a few minutes.

## Erratum, 2026-11-22, after the first dispatch failed and before any window was scored

The first dispatch (worker run 45037221708, source `728dc65f4f9443533af3bc3a1cb4255e83ba35c9`, worker commit `8f2b8f3`) **failed in 5 seconds at the exposure step, before any model ran a single window**. All 28 worker unit tests passed and all 474 windows were built (digest `b813011d…bff0c`), but the report's state is `failed` with `ValueError: Both normalization reductions are required` and no window record exists. Cause, my error: I called Codex's `rewrite_normalization`, which looks for the node names `model_1/normalized_log_1/Min;…` of the TFLite-derived graph, while the pinned artifact members `unmodified.onnx` and `adapted.onnx` are tf2onnx exports whose reductions are named `StatefulPartitionedCall/StatefulPartitionedCall/StatefulPartitionedCall/StatefulPartitionedCall/normalized_log_1/PartitionedCall/Min` and `…/Max` (same names in both members).

Fix: `expose_normalization` in `tools/portable_mixed_level_probe.py`, strict like Codex's helper (exact node names, op types, input tensors, `axes=[1,2]`, `keepdims=0`; refuses if already exposed; no node, weight or initialiser changes; ONNX checker). Codex's helper is untouched. The two exposed tensors are the outputs of the `ReduceMin` over the log power and the `ReduceMax` over (log power − minimum), exactly the quantities the registered `min_db` and `range_db` name.

Read from the two pinned graphs while fixing this, with no window run: the log-power scale constant is 4.342944… = 10/ln 10 and the additive floor is 1e-10, so `min_db` and `range_db` are dB of power and the −100 dB floor in F1 is the right constant. Both members also contain a `flat_guard` (if the window's CQT power is constant over all cells, the graph outputs zeros), which affects only windows that are exactly flat, i.e. the silence references; it is the same in both members and does not touch any registered verdict, grid, threshold or odds.

Nothing registered above changed: grid, spec, thresholds, verdict definitions, odds and reading rules are as written before the first dispatch. The rerun is the second and last planned dispatch of the same frozen specification; the failed run saw no data, so no choice below was informed by results.
