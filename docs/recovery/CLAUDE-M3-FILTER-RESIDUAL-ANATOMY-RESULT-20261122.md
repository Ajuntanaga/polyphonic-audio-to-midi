# After the support filter, the false output that is left is mostly held-note overhang: result

Claude, 2026-11-22. Pre-registration: `CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-PREREGISTRATION-20261122.md` (commit `e84bc9d`, before the run). Descriptive, saved data (ordinary recording, emitted clock, D = 220 ms, the cropped-ONNX events); no audio, model run, job or native edit; nothing promoted. One section (the late-cue sensitivity) is post hoc and marked as such.

## Answer

**The cropped-adapted support filter leaves 9.35 M false samples (97.4 pitch-seconds). 62.7% of them are held-note tail (output after the last same-pitch label ended) and 31.6% are orphan notes (no same-pitch label overlaps the span). The filter removes 29.7% of CURRENT's orphan volume and 39.4% of its head volume but only 10.5% of its tail volume.** All 200 CURRENT tail spans survive, and the median tail barely changes (292.7 ms kept against 294.0 ms in CURRENT). By the reading rule I registered, the largest class names the lever, and it is a release cue for held-note overhang, not the support.

Voice samples at 96 kHz, ordinary, all pitches; precision = present / (present + false); pitch-seconds = samples / 96,000.

| | CURRENT | cropped unmodified | cropped adapted |
|---|---:|---:|---:|
| Present | 13,525,345 | 13,501,658 | 13,516,249 |
| False | 11,429,794 | 9,406,949 | 9,346,313 |
| Precision | 54.20% | 58.94% | 59.12% |
| Tail | 6,546,826 (57.3%) | 5,762,162 (61.3%) | 5,860,153 (62.7%) |
| Orphan | 4,204,480 (36.8%) | 3,115,477 (33.1%) | 2,956,850 (31.6%) |
| Head | 378,197 (3.3%) | 229,019 (2.4%) | 229,019 (2.5%) |
| Between | 300,291 (2.6%) | 300,291 (3.2%) | 300,291 (3.2%) |

Removal share of CURRENT's class volume (unmodified / adapted): orphan 25.9% / 29.7%, tail 12.0% / 10.5%, head 39.4% / 39.4%, between 0 / 0. The filter's whole present loss against CURRENT is 23,687 samples (247 ms) unmodified and 9,096 samples (95 ms) adapted.

## What the filter does to each class

- **Orphans:** 207 of 221 spans survive (6.3% removed entirely) and the median kept share of a surviving span is 1.0, so the filter removes an orphan whole or leaves it whole. The 31.6% that is left is false notes the model-plus-native support confirms, which is a detection-side question.
- **Tails:** every one of the 200 tail spans keeps some output. Lower band (pitch below 60): median 294.66 to 293.99 ms, p10 171.32 to 171.32 ms, p90 603.32 to 522.80 ms, so the filter trims only the longest tails. Tails are 63.88% of the lower band's remaining false output (unmodified 62.37%).
- **Upper band (60 and up):** 3.9% of the remaining false output, and the filter removes none of it (it loses 319 present samples). Its 6 tails are tightly grouped (median 212.99 ms, p10 191.32, p90 215.99), which looks like a fixed release hold of about 213 ms. That reading is my inference from six spans and I did not test it.
- **Where the remaining tail sits:** 3,283,141 samples (56.0%) under another label's annotated time and 2,577,012 (44.0%) in no label at all; the tail is 78.6% of the remaining gap output. Orphans are 86.0% under another label and 14.0% in no label.
- **Register:** tail share of the false output in each band below 60 is 56.8% (pitch 0 to 39), 58.1% (40 to 44), 66.4% (45 to 52), 81.2% (53 to 56) and 63.1% (57 to 59), so the overhang is broad, not one register. Per-pitch tail counts are 2 to 13 spans, too few to read pitch by pitch.

## Headroom (oracles use the labels; not implementable)

Precision after removing every tail, every orphan, or both. By construction no present sample is removed.

| | now | tail cut | orphan cut | both |
|---|---:|---:|---:|---:|
| CURRENT | 54.20 | 73.47 | 65.18 | 95.22 |
| cropped unmodified | 58.94 | 78.74 | 68.21 | 96.23 |
| cropped adapted | 59.12 | 79.50 | 67.90 | 96.23 |

The whole support filter earns +4.9 points over CURRENT (54.20 to 59.12). A perfect tail cut would add +20.4 more and a perfect orphan cut +8.8.

## Post hoc: how much of that survives a late cue

Not pre-registered; written after the registered result was seen. Cut every tail at (last label end + x): remaining false = false − tail volume + the output kept in the first x ms of each tail. x = 0 reproduces the registered tail cut and x beyond the longest tail reproduces the filter itself (both checked, or nothing is reported).

| x (ms) | 0 | 25 | 50 | 75 | 100 | 150 | 200 | 300 | 500 | filter |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Adapted precision (%) | 79.50 | 77.33 | 75.29 | 73.37 | 71.54 | 68.23 | 65.42 | 61.93 | 60.19 | 59.12 |
| Share of the +20.4 lift kept | 100% | 89% | 79% | 70% | 61% | 45% | 31% | 14% | 5% | 0 |
| CURRENT precision (%) | 73.47 | 71.62 | 69.87 | 68.21 | 66.63 | 63.75 | 61.29 | 58.21 | 56.29 | 54.20 |

A cue that fires 100 ms after the annotated end still keeps 61% of the oracle lift (+12.4 points, about 2.5 times what the whole support filter earns); at 200 ms it keeps 31%, and at 300 ms, about the length of the median tail, 14%. So the opportunity is large and it is time-critical: a cue has to fire within about 100 ms of the note's end to be worth most of it.

## Where this sits against the earlier tail notes

This sizes the opportunity. It does not add a lever, because every implementable cue tried so far is exchange-limited:

- `CLAUDE-M3-TAIL-CLIP-GRACE-CURVE-20261122.md`: a clip driven by Arm A's note-offs with a grace gave about 3 false samples removed per present sample lost, and no grace passed the strict gate; the overhang that is left sits in the installed tracker's own release logic (release hold 50 to 220 ms, the unison hold), which is native code.
- `CLAUDE-M3-LOWREG-ENERGY-RELEASE-20261122.md`: voice-energy-decay features separate tails, but no single feature removed more than about 5% of false output at near-zero label loss.
- `CLAUDE-M3-LOWREG-TAIL-CODES-20261122.md` (supersedes the tail-state note): lower tails by disposition code are 35% selected, 45% coasting and 19% quiet-tick holds.
- `RESUME.md`: the release-hold trial remains unclaimed, and reopening it needs a note-off cue that separates on held-out data.

What is new here is the size of the prize on the filter's own output (+20.4 points at the oracle, +12.4 with a 100 ms-late cue) and where it sits, mostly the lower band and 44% of it in time when no note is annotated at all, which an audio-level gate could address in principle (not testable on saved spans). The 56% under another label needs a cue that is specific to the pitch.

## What cannot be concluded

- One recording (ordinary only); extended-middle (six labels, all MIDI 52) was not used.
- Label ends are annotated note ends. A string can ring acoustically after the annotated end, and the scorer calls that output false. From saved spans I cannot tell how much of the tail, and in particular of the 44% in no label, is audible ring and how much is tracker overhang, so the oracle is the scorer's ceiling and not proof that the output is wrong to a listener.
- Emitted-clock saved spans; no audio; no lane, string, unison or MIDI-lifecycle claim.
- The late-cue table is post hoc and assumes a cue that fires exactly x ms after the label end on every tail and removes the rest; it is not a measurement of any real cue.
- Nothing is promoted and no gate, default or native file changes. The frozen label budget is unchanged (the user's "Leave it as is", commit `2bf0e2a`), and the support filter still cannot pass it on labels 263 and 364.

## Predictions, scored

| Id | Claim | Odds | Measured | Result |
|---|---|---:|---|---|
| R0 | All identity checks pass | 97% | all three pass | hit |
| R1 | Orphan removal share above tail removal share (all) | 75% | 29.67% against 10.49% | hit |
| R2 | Tail removal under 15% (all) | 65% | 10.49% | hit |
| R3 | Orphan removal between 25% and 50% (all) | 55% | 29.67% | hit |
| R4 | Lower band: tails over 50% of remaining false output | 70% | 63.88% | hit |
| R5 | Lower band: median kept tail extent at least 200 ms | 60% | 293.99 ms | hit |
| R6 | Tail-cut oracle lifts precision at least 10 points | 70% | +20.38 | hit |
| R7 | Lower band: unmodified and adapted tail share within 3 points | 80% | 62.37% and 63.88% (1.51) | hit |
| R8 | Orphan-cut lift below tail-cut lift | 80% | +8.78 against +20.38 | hit |

Nine of nine against about 6.5 expected from my odds, so I was under-confident on this set. The claims share one fact (the tail dominates and survives), so they are correlated and this is closer to one confirmation than nine; R2 and R3 hit with thin margins (10.5% against a 15% ceiling, 29.7% against a 25% floor) and the rest by wide ones. I had already seen CURRENT's class split when I registered, so the new information was how the filter treats each class.

## Provenance

- `CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.py` (sha256 `047242e96fc6`, committed in `e84bc9d` before the run), output `CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.json`. The selftest and the three identity checks (CURRENT reproduces the committed anatomy, class sums equal the scorer's extra and gap, the two D = 220 filter rows and event hashes equal the committed ONNX-support result) passed before anything was reported. No change to the script after the pre-registration commit.
- `CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-FOLLOWUP-20261122.py` (sha256 `d188c9363f7a`, post hoc), output `CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-FOLLOWUP-20261122.json` (late-cue sensitivity, tail by register, tail split, tail by pitch).
- Event members (hash-verified, from run 45034216124, the same as the earlier results): `unmodified_cropped__ordinary-events.json` sha256 `c1c48293b6c9b8e10d2ae5c51ae565b50b6987ac0bc9de54180f6de837ab3c32`, `adapted_cropped__ordinary-events.json` sha256 `4e0601c42dbdccffe32c245a74ce80a9ae24be825f0b21e010b37f33f8ac9e92`.
