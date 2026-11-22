# Callback support events: no arm passes the frozen screen

2026-11-22. Plan and implementation committed in `50b6566` before the one saved-data pass. Result: `CODEX-M3-SUPPORT-EVENTS-20261122.json`; run 20:59:57–21:00:13 UTC. No audio, model inference, native execution or new GitHub job. Installed output and all acceptance gates are unchanged.

Keeping any direct-support observation inside a 512-sample callback recovers most of the two onset losses, but label 364 still exceeds the frozen 25 ms AND 5% budget. Adding an observed positive onset from an active selected candidate preserves every label, but gives back almost all cleanup. No candidate is selected for native implementation; no threshold or hold tuning follows this screen.

## Frozen comparison

All arms use the same cropped adapted ONNX events on the measured `emitted_ns` clock, support held forward 220 ms, no onset grace, and the same CURRENT pitch spans. Native evidence becomes available only at the end of its callback.

- L: the last decision in each callback is non-quiet, pooled and direct-fundamental supported. This reproduces the earlier support-filter result.
- E: any decision in the callback meets that same predicate.
- A: E or a non-quiet pooled, active, selected candidate with an observed positive onset value. This value is causal detector evidence, not a verified physical attack.

Labels and rendered voices do not enter these predicates. The label budget requires present-time and longest-hold loss each at most 25 ms AND 5% of that metric's CURRENT value, with no new completely missed label. Wrong-pitch and gap growth remain prohibited on each corpus. The pre-fixed usefulness floor is at least 20% ordinary wrong-pitch removal, gap reduction at least 250,000 samples, coverage loss at most 0.10 percentage points, and extended-middle strict safety.

## Ordinary result

Units below are pitch-presence/voice-samples at 96 kHz. They are not string-assigned tuner frames, unique duration, MIDI retriggers or live-host measurements. CURRENT has 13,525,345 / 33,819,101 expected pitch-samples present (39.9932%), 7,808,309 wrong-pitch and 3,621,485 gap voice-samples. Gap output means extra notes during unlabeled gaps.

| Arm | Present | Coverage | Wrong-pitch change | Removal | Gap change | Labels losing | Over budget |
|---|---:|---:|---:|---:|---:|---:|---|
| L | 13,516,249 | 39.9663% | -1,739,305 | 22.2751% | -344,176 | 5 | 263, 364 |
| E | 13,521,113 | 39.9807% | -1,578,391 | 20.2142% | -332,016 | 2 | 364 |
| A | 13,525,345 | 39.9932% | -154,969 | 1.9847% | -447 | 0 | none |

E reduces label 263's present loss from 3,344 samples (34.833 ms, 10.183%) to 401 (4.177 ms, 1.221%); its longest hold is unchanged. Label 364's present and longest-hold losses fall from 4,855 (50.573 ms, 6.756%) to 3,831 (39.906 ms, 5.331%), which still fails both limits. First-present delay accounts for these remaining losses and is reported separately. A passes the strict saved pitch-safety comparison but fails usefulness. Exact-set and all-expected pitch-samples remain 53,249 in all arms. Span runs are CURRENT 528, L 521, E 530, A 526; these are not raw MIDI NoteOn counts.

## Extended-middle and identity

All arms preserve all six labels and CURRENT's 2,021,510 / 2,073,600 present samples (97.4879%), with 14 span runs. L/E/A remove 137,344 / 136,832 / 65 wrong-pitch samples; gap changes are -4,014 / -4,014 / 0. All three pass strict saved pitch safety on this corpus. A therefore fails usefulness, not the measured safety clauses.

Input hashes, contiguous 64-sample trace ticks, reconstructed CURRENT identity, the L native-support projection and the prior L filter score all pass. The pure synthetic check covers callback causality, validity/selection, control projection and the exact budget boundary. Ordinary events include one at/after EOF and two pitches still open at the scoring horizon; they are clipped to that horizon, not diagnosed as stuck MIDI. Full pins, per-label results and mechanism counts are in the JSON. Compressed resulting spans are retained beside it.

The mechanism is observable: E adds 7,197 ordinary positive note-callbacks over L; A adds another 4,573. The extra positive-onset evidence renews support for false output as well as genuine notes. These are design recordings; even a passing screen would need held-out, native lifecycle/allocation/deadline and host checks. The separate installed tracker scoreboard remains unchanged.

## Next

Use this rejection and Claude's independently completed residual-anatomy result (`bc5ff5e`) to select a distinct causal release or note-identity mechanism. The residual census sizes held-note overhang but does not itself demonstrate a deployable cue. Neither result authorizes a new cutoff, re-run or promotion. The broader project remains open; no overall-completion percentage is measured.
