# Adapted Basic Pitch events as the filter's support: result

Claude, 2026-11-22. Saved data only: Codex's four compact event files from run 45016827324 (collected by Codex through evidence-subset run 45022134487), scored with the committed script. No audio, model run, job or native edit; nothing promoted. The adaptation itself was rejected by Codex's frozen screen; this note only asks what its events are worth as the support of the existing CURRENT filter.

## Inputs (sizes and SHA256 equal the values pinned in Codex's report)

| file | bytes | sha256 (first 12) |
|---|---|---|
| unchanged TF, ordinary | 166,961 | ca4d2ce4553f |
| adapted TF, ordinary | 171,292 | c602b950c76d |
| unchanged TF, extended-middle | 4,383 | 6b0f30d48202 |
| adapted TF, extended-middle | 6,336 | 662f7c273ea6 |

Scripts and outputs (sha256 first 12): `CLAUDE-M3-ADAPTED-SUPPORT-20261122.py` d8dd73e78e71 (commit e5a5e17), its emitted-clock JSON c06838bb5a0a and availability-clock JSON 3869a9c2e66f, `CLAUDE-M3-ADAPTED-SUPPORT-CONTROL-20261122.py` da83a752bb94 and JSON cb7b807c006c. The plan and the eight predictions are in `CLAUDE-M3-ADAPTED-SUPPORT-PREREGISTRATION-20261122.md` (commit af50edc), written before any event existed. Support = model spans union the native confirmation, held forward D ms; filter = CURRENT intersect support; no lane, no persistence rule.

## 1. Pre-registered view: the measured emitted clock

Ordinary, D = 220 ms (CURRENT: coverage 39.9932%, 528 runs):

| support | coverage % | precision % | wrong removed | gap delta | labels losing | lost share of present |
|---|---|---|---|---|---|---|
| arm A (saved ONNX run) | 39.923 | 58.93 | 22.15% | -291,474 | 6 | 0.18% |
| unchanged TF | 39.785 | 59.56 | 25.23% | -323,439 | 9 | 0.52% |
| adapted TF | 39.787 | 59.41 | 24.97% | -285,422 | 8 | 0.52% |
| arm A union adapted | 39.938 | 58.38 | 20.22% | -221,623 | 5 | 0.14% |
| native confirmation only (control, post hoc) | 39.773 | 60.22 | 28.01% | -357,368 | 9 | 0.55% |

Extended-middle, D = 220: every support keeps coverage 97.4879% and 0 labels losing (precision 78.53 to 78.68%, wrong removed 26.0%). At D = 50 the unchanged TF loses 2 labels and the adapted 1 (coverage 96.49 and 97.07%); arm A and arm A union adapted lose none.

Predictions, as registered, on this clock: **5 pass, 3 fail.**

| | prediction | result |
|---|---|---|
| R0 | unchanged TF within a few labels of arm A (4 to 8 labels, removal 18 to 26%) | **FAIL**: 9 labels (removal 25.2% is inside the band) |
| R1 | adapted loses no more labels than unchanged | pass (8 vs 9) |
| R2 | adapted lost share <= unchanged | pass (0.0052 vs 0.0052; present -69,750 vs -70,600) |
| R3 | adapted removal >= unchanged | **FAIL**: 24.97% vs 25.23% |
| R4 | label 229 stays lost under both | pass (-14,591 samples under both, 79.7% of its present time) |
| R5 | extended-middle D = 220 both safe, 0 labels | pass |
| R6 | adapted precision >= unchanged | **FAIL**: 59.41% vs 59.56% |
| R7 | arm A union adapted loses fewer labels than arm A | pass (5 vs 6) |

The three failures are margins of one label, 0.26 pp and 0.15 pp. The more important reading is the control row: on ordinary this clock gives the model almost no say. The measured FIFO backlog (Codex: about 72 s) pushes 370 of 1,192 unchanged and 420 of 1,223 adapted events (counted at the recording end by my audit; Codex's report counts 369 and 419) past the end of the recording, and the surviving model spans are late. The unchanged-TF and adapted-TF rows (9 and 8 labels, coverage 39.78 and 39.79%, 59.6 and 59.4% precision) sit within a label or two of the native-only control (9 labels, 39.77%, 60.2%); at D = 50 they lose 38 labels against the control's 39. So the emitted-clock comparison on ordinary compares the runtime bottleneck, not the models' content. Extended-middle is different: the control collapses there (coverage 73.3% at D = 220, 57.5% at D = 50), so the early surviving model events still carry that corpus.

## 2. Post-hoc view: the availability clock (what the content gives if the model kept up)

Declared before any event was read (commit e5a5e17); not part of the predictions; the zero-compute availability clock is a diagnostic, not measured live output.

Ordinary:

| support | D | coverage % | precision % | wrong removed | gap delta | labels losing | lost share |
|---|---|---|---|---|---|---|---|
| arm A | 220 | 39.923 | 58.93 | 22.15% | -291,474 | 6 | 0.18% |
| unchanged TF | 220 | 39.923 | 58.99 | 22.40% | -292,630 | 6 | 0.18% |
| adapted TF | 220 | 39.966 | 59.19 | 22.65% | -344,176 | 5 | 0.07% |
| arm A | 50 | 39.586 | 67.45 | 56.14% | -586,065 | 28 | 1.02% |
| unchanged TF | 50 | 39.584 | 67.86 | 57.44% | -605,292 | 28 | 1.02% |
| adapted TF | 50 | 39.793 | 66.16 | 52.02% | -484,276 | 20 | 0.50% |

- The unchanged TF events on this clock reproduce arm A (596 runs each, the same six D = 220 losers), so the TF/ONNX backend difference does not matter for this use.
- The adapted events as support lose fewer labels (D = 220: 5 vs 6, label 229, pitch 42, is restored and the other five losers, labels 42, 263, 364, 389, 398 at pitches 60, 33, 42, 33, 34, are lost under all three; D = 50: 20 vs 28, 11 labels fixed (19, 91, 174, 229, 239, 349, 355, 459, 470, 472, 477) and 3 new (179, 200, 202)) and less genuine presence (0.07% vs 0.18%; 0.50% vs 1.02%), and clean a little less (D = 50: 52.0% vs 57.4% of wrong-pitch output).
- Extended-middle, D = 220: all supports keep 0 labels and 26.0% wrong removed; the adapted support removes less gap voice (-6,013 vs -21,374, precision 78.07 vs 78.53%). At D = 50 the adapted support removes less wrong-pitch output (29.5% vs 32.2%).
- The same R0 to R7 checks on this clock: R4 fails (label 229 is restored); the other seven pass. Post hoc, not scored as predictions.

## What this means

- As a support the adapted model behaves like a higher-recall, slightly less selective copy of the original: fewer lost labels and less lost presence, a little more false output left in. That matches Codex's finding that the adapted model recovers presence but adds extra events (1,223 vs 1,192 events; 611 vs 596 runs).
- It does not change the gate picture. At D = 220 five labels still lose present or longest hold even with the adapted support, five lower-register or hard labels that neither model nor native confirmation supports; the strict label clause is still not met, and the filter's cleanup on ordinary is still about 22 to 25% of wrong-pitch output. The lower-register gap remains the limiting factor.
- On the measured clock neither TF model is usable as a live support; any real use would need a faster runtime. Codex dispatched the exact-weight TF to ONNX conversion and paired causal screen as run 45022754580 (12:31Z, spec `basic-pitch-onnx-export-20261122.json`). If that screen produces events at real-time pace, the same script scores them unchanged with `--clock emitted_ns` and its pre-registered checks; I will not claim any file in that run and will not poll it.

## Caveats

One recording per corpus, both used in earlier design; extended-middle has 6 labels and 14 to 21 runs, so its differences are a handful of notes. The adapted model failed Codex's own screen (120 labels lose presence against unchanged TF in its scoring), and this note does not reverse that: it scores a different use (a veto-only support for a filter whose own spans are CURRENT's). Zero-compute availability is not measured output. The 370 vs 369 and 420 vs 419 event counts at the recording end differ by one from Codex's report because of how the boundary is counted; the report's figures are Codex's. No lane, unison, string, callback or live-host claim; not a built output; nothing promoted.
