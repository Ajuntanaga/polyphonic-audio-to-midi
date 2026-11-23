# Native candidate temporal feasibility result — 2026-11-23

**REJECTED by the frozen gain gates.** The one GitHub CPU screen completed
successfully and passed its safety checks. On the later ordinary passages,
pitch presence rose **1,973,489 -> 2,011,632 / 4,328,055 samples**
(**45.5976 -> 46.4789%, +0.88130 percentage points**), below the required
1 point. Three labels gained, below the required five. No cutoff, feature,
training split or acceptance rule was changed after the result.

## What changed

| Ordinary test quantity | CURRENT | Candidate | Change |
| --- | ---: | ---: | ---: |
| Expected pitch-samples found | 1,973,489 | 2,011,632 | +38,143 |
| All expected pitches present, samples | 53,249 | 86,466 | +33,217 |
| Exact pitch set, samples | 53,249 | 65,732 | +12,483 |
| Extra pitch voice-samples over labels | 933,383 | 933,383 | 0 |
| Extra voice-samples in unlabeled gaps | 438,291 | 438,291 | 0 |
| Merged occupancy segments | 74 | 138 | +64 |

The gains were concentrated: label 451/note 65 gained 36,672 samples
(longest hold 0 -> 29,120), label 487/note 65 gained 1,408 (longest
0 -> 384), and label 496/note 41 gained 63. These are original corpus
label indices. Occupancy segments are not delivered MIDI attacks.

Calibration coverage and errors stayed unchanged. Extended-middle stayed
**2,021,510 / 2,073,600 = 97.4879%**, with no label, false-output or gap
regression. Both complete CURRENT scores and trace identity pins reproduced.
The classifier admitted no negative eligible rows in train, calibration,
ordinary test or extended-middle. Duration-weighted ranking AUC was 0.8983,
0.8846 and 0.8695 on the ordinary roles, and 0.5673 on extended-middle.
The calibration-only cutoff was 0.9584239909130117.

## Interpretation and disposition

Joint current/past native features found a small safe addition on these
recordings, but not the breadth of benefit required to justify implementation.
The added occupancy was fragmented. The fixed screen is closed: no retuning,
second dispatch, native integration or promotion. This does not establish
that every joint or temporal design is impossible.

These are pitch occupancy measurements, not labeled-frame string matches,
unison multiplicity, acoustic re-pluck preservation or delivered MIDI.
The split separates whole passages with purges, but reuses development
recordings and source takes; it is not independent-recording validation.
Classifier runtime, allocations, VST3 deadlines and feedback into native
selection were not measured. Installed output, defaults and scoreboard
remain unchanged. Claude's ordinary-58 acoustic work remains separate.

## Reproduction

- Plan: `CODEX-M3-NATIVE-CANDIDATE-TEMPORAL-PLAN-20261123.md`.
- Spec: `native-candidate-temporal-20261123.json`.
- Source: `6fa215986366e8e39b0c2d81f015efbd3287681b`.
- Worker: `f44967008517cddcb2ae7fb62afbebb1aacf0f7f`.
- Run: <https://github.com/Ajuntanaga/m3-offload/actions/runs/45225444392>.
- Source portable verification: `45224840872`, success.
- All 35 synthetic checks passed locally and on the worker.
- Small artifact `14843525468`, 115,898 bytes, collected once; SHA-256
  `8139db8b72e694c8745dc64e551feaae3d20d251821cc07a5b9a785caccaafdc`.
- Report:
  `build/github-results/native-candidate-temporal-45225444392/report/native-candidate-temporal-result/report/report.json`;
  SHA-256 `d7b5f5aa686f010afd008599320ce46e812e2f4de883f51a7efe7b52dba9fb2c`.
- Receipt: `build/github-results/native-candidate-temporal-45225444392/collection.json`.
- Bulk artifact `14842124759` (3,014,588 bytes) remains remote;
  SHA-256 `86ca09106bd7a647548b05d7fd1db6e6799ead6900b784a1191e5c5c1c0925a8`.

No completed job should be polled, downloaded again or rerun for this result.
