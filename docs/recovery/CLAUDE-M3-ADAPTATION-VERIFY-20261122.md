# Independent check of Codex's adaptation numbers (run 45016827324)

Claude, 2026-11-22. Saved data only, no audio, model run or job; nothing promoted. A handoff number is worth more once a second code path has reproduced it, so this rebuilds the paired unchanged-TF versus adapted-TF comparison from Codex's four saved event files and compares every figure with the report.

## Result: all 14 compared fields match in all four corpus-and-clock blocks

Path: the events pinned in Codex's collection receipt (sha256 first 12: ordinary unchanged `ca4d2ce4553f`, adapted `c602b950c76d`; extended-middle unchanged `6b0f30d48202`, adapted `662f7c273ea6`), turned into pitch spans with `tools.basic_pitch_streaming.emission_spans`, scored with `tools.pitch_detector_comparison.score` and `compare` at the full recording length the report used (spec sample counts 10,689,600 and 2,241,600, not the consensus common horizon), against `report.json` (sha256 first 12 `c34627e27329`). Script `CLAUDE-M3-ADAPTATION-VERIFY-20261122.py` (`1e25df923b63`), JSON `CLAUDE-M3-ADAPTATION-VERIFY-20261122.json` (`703b24e83a53`).

Fields compared: both arms' coverage and exact-set percentages, the present / all-expected / exact-set / extra-voice / gap-voice sample deltas, labels losing present time and labels losing longest hold, labels changed either way, labels losing present time per register band, and the no-pitch-safety-regression flag.

| corpus, clock | coverage unchanged → adapted | exact set | labels losing present / longest | labels changed | safety flag |
|---|---|---|---|---|---|
| ordinary, measured completion | 6.43 → 8.09% | 0 → 0% | 21 / 21 | 58 | False |
| ordinary, availability | 55.81 → 71.88% | 9.98 → 37.59% | 120 / 122 | 352 | False |
| extended-middle, measured completion | 96.20 → 97.06% | 95.84 → 77.05% | 1 / 2 | 4 | False |
| extended-middle, availability | 98.29 → 98.16% | 85.65 → 66.28% | 1 / 1 | 1 | False |

Ordinary availability per band, labels losing present time: below 48: 21, 48 to 59: 33, 60 to 71: 45, 72 and above: 21 (total 120), as reported.

## What differed on my first run, and why it was not a disagreement

My first run printed differences in three fields, all naming or denominator choices on my side, found by arithmetic before anything was changed: (1) `extra_gap_pitch_samples_delta` in the report is the unlabeled gap-voice delta alone (my gap delta, 1,811,058 on ordinary availability, equals the report's figure exactly, and my extra-voice delta −713,262 equals its extra-voice delta), not extra plus gap; (2) the exact-set percentage divides by annotated samples, not expected pitch samples (the ratio 3.79 between the two readings is the chord multiplicity); (3) the per-band lost-label count counts labels that lose present time, not present-or-longest (122 vs 120 labels, which is why my band counts were 22 / 33 / 46 / 21). I changed those three definitions to the report's meaning and recorded the first-run mismatches here; nothing else changed between the runs.

## Scope

This confirms that Codex's reported scoring follows from its saved events and that the REJECTED verdict rests on correct arithmetic (120 labels lose presence, 122 lose longest hold, 21 + 33 + 45 + 21 by band, extended-middle presence down 0.12 pp on the availability clock). It does not reproduce the training, the TensorFlow model run or the event capture itself, and it re-scores Codex's own saved outputs rather than raw audio. Event counts at the recording end differ by one from the report (my audit 370 and 420 against its 369 and 419), which is a boundary-counting difference with no effect on these scores.
