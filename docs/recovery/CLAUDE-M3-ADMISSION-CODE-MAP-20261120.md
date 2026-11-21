# M3 admission / selection code map (read-only, 2026-11-20)

Source: `native/src/polyphonic_pitch_detector.cpp` at 581af79 (worktree `claude-m3-candidate-prep`). Nothing built or run. "V" = I read the cited lines myself; "S" = reported by a read-only subagent, not re-read by me.

## Why notes above 60 are structurally disadvantaged (V)

- `kM3FrettedNotePenalty = 0.20`, `kM3FretPenalty = 0.005` (lines 156-157).
- Selection DP assignment penalty (lines 5712-5718): `(open_candidate_count >= kM3OpenChordMinimum(2) || note > kM3OpenNotes.back()) && fret > 0 ? 0.20 + 0.005*fret : 0`; net = `option.score - penalty` (5725). `option.score` is `scores[c] / fast_energy_` (5207, `normalized_score`).
- So a pooled note above 60 (always fretted) needs `score/fast_energy_` above about 0.205-0.32 to have a positive net option. Raw admission needs only 0.05 (`kCandidateCoherenceRatio`, line 141; threshold at about 12690 S).
- The calibrated direct path raises the score to `calibrated_floor = fixed + per_fret*max_fret + 0.01` (5213-5217 V), but it applies only to notes `{60, 77..80}` at `max_fret 24` (S) and only with a calibration bank.
- Replay-only diagnostics `--diagnostic-fretted-fixed-penalty` / `--diagnostic-fretted-per-fret-penalty` (2841-2846 V) can only lower these.

## Other pitch-dependent stages (S)

- `harmonic_limit(note)` (341-343): 6 harmonics up to 52, 4 for 53-75, 3 for 76+. Used for cells at 1551 and guard cells at 1577. Effect size unknown.
- Harmonic-shadow pass (5304-5395): a new candidate at an interval of {12,19,24,28,31} from a stronger one is demoted unless its own fundamental is at least 0.85 of the stronger one's (or retained / calibrated direct).
- `has_calibrated_direct_support` (4617-4690) returns false below note 60; band rescue (5119-5170) only for strings 7 and 8.
- Lifecycle `energy_blocks_onset = fast_energy_ < slow_energy_ * 0.95` (about 13251) blocks every new onset while total energy decays.
- Front end (window 40 ms EMA, 64-sample decision quantum, fixed cell frequencies) is pitch-independent.

## Replay configuration facts (V, from report.json of run 44752010601)

- `--calibration corpus/calibration.m3cb` and `--spectral-shadow-templates` are passed, so the calibrated paths are active in the saved traces.
- `--max-polyphony 5 --max-fret 24`: this is why no trace tick renders more than 5 voices (DP `voice_count >= max_polyphony`, line 5736).
- `current-on` adds only `--diagnostic-spectral-lane-collision`.

## Saved-trace evidence for the penalty gate (exploratory, current-on 44752010601)

- Annotated notes 61-71 absent from the render with a trace row: for pooled rows essentially all have non-positive `selector_best_adjusted_score` (note 61: 4819 of 4821; 62: 2621/2621; 65: 4895/4895; 71: 4174/4174). Note 60 (open string, no penalty): 0 of 89.
- Killed pooled rows above 60: 26,038 annotated-genuine, 2,004 not annotated. Extended-middle (no annotated note above 60): 3,760 rows, all false.
- Share harmonically related (12,19,24,28,31,36) to a rendered lower note: extended-middle ghosts 100%, ordinary false at labelled ticks 94%, ordinary genuine 47.7%, ordinary gap-tick false 17%.
- Earlier uniform half-strength screen (RESUME.md:3213-3215, `build/modal/fretted-penalty-half-outcomes.json`): label frames gained/lost by band 61-71 +8815/-34, 48-60 +354/-1255, <48 +3218/-2929. Per-note split of its false additions is not saved.

## Where a default-off experiment goes (S, idiom of `diagnostic_fundamental_admission`)

Header setter under `M3_OFFLINE_REPLAY_DIAGNOSTICS` (hpp 774-776, member near 1892), use site wrapped in the same macro in `select_m3_feasible_candidates` around 5712, plumbing through `replay_main.cpp`, `replay.hpp` and `replay.cpp` (defaulted trailing parameter and a non-diagnostics reject-list entry). The macro is defined only for `m3_native_tests`, `m3_vst3_corpus_replay` and `m3_replay`.

## Still unknown

Whether the DP penalty or the later onset/evidence gates dominate once a pooled candidate is selected; per-note split of the half-penalty false additions; lane correctness of recovered frames; DP competition effects on lower notes.
