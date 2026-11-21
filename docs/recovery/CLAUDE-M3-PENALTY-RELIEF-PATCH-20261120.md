# Upper-fretted penalty relief: default-off patch (2026-11-20)

Prepared in the isolated worktree `.worktrees/claude-m3-candidate-prep` (branch `claude/m3-candidate-prep`, base 581af79). Nothing was built, linked, run or dispatched. Codex's v5 tree is untouched. Diff: `docs/recovery/CLAUDE-M3-PENALTY-RELIEF-PATCH-20261120.diff` (sha256 `425318f15bcfcc4ad2e963d96cec5b67a946fa3bb48e8fb7e90e7b6051205385`, 6 files, +206/-5).

## What it does

New replay-only flag `--diagnostic-upper-fretted-relief` (default off, compiled only under `M3_OFFLINE_REPLAY_DIAGNOSTICS`, so the production VST3 is unchanged and `m3_replay` built without diagnostics rejects the flag like its siblings).

In `select_m3_feasible_candidates`, for a pooled single-lane option with note > 60 only, the DP's fixed fretted-note term (0.20) is dropped; the per-fret term (0.005 x fret) stays. Everything else, including the state-local open-prior copy near cpp:5835, the calibrated score floor for notes 77-80, `max_polyphony 5` and the raw 0.05 threshold, is unchanged.

## Frozen parent predicate (per Codex's request)

- Parent snapshot P = lower candidates c < n with `candidate_states_[c].active` at selection time. `active` is written only by lifecycle code after selection (single selector call site, `make_decision`), so this is the PREVIOUS decision's flag. It is not the current DP winner and not the rendered set.
- Relief applies when P is non-empty AND no c in P has (n - c) in {12, 19, 24, 28, 31, 36}. Pure interval membership; deliberately not `is_harmonic_shadow` (which adds an energy condition).
- Same-tick chord onset has no prior parent, so an onset-only chord gets no relief (P empty). That is the conservative side; the risk the other way (a sustained unrelated lower note licensing a same-tick false upper note) is what the screen must measure.

## Counters (stderr line, per tick x pooled option above 60)

`m3_replay: upper_fretted_relief evaluated=N no_parent=N related_blocked=N applied=N rendered_disagreements=N active_only=N rendered_only=N`

`rendered_disagreements` counts options where the active-set predicate differs from the same predicate evaluated on the rendered set (`midi_voice_mask != 0`); `active_only` and `rendered_only` split it by which side would have granted relief. Report these next to the outcome counts.

## Verified vs not

- Verified by me: lifecycle ordering and the single call site (source reading); `g++ -std=c++17 -fsyntax-only -Wall -Wextra` is clean for `polyphonic_pitch_detector.cpp`, `replay.cpp`, `replay_main.cpp` with the `m3_replay` macros, for the detector with no macros (production config, same as HEAD), and for `test_polyphonic_pitch_detector.cpp` with the `m3_native_tests` macros; a mutated copy of each file errors as expected, so the new code is being parsed; `git diff --check` clean.
- NOT verified: any execution. The new test `native_detector_upper_fretted_relief_waives_only_the_fixed_term_for_unrelated_parents` has never run; it assumes a lone 0.15 spike at note 65 is pooled (local peak, above 0.05) and that an active lower candidate with no score stays out of the pool. If it fails on GHA, check that assumption before the predicate. The flag-off path computes the same expression as HEAD (`assignment_fixed_penalty` equals `fretted_fixed_penalty`), but baseline identity still needs the GHA identity companion.

## Integration

Apply onto the v5 tree after v5 lands: `git apply docs/recovery/CLAUDE-M3-PENALTY-RELIEF-PATCH-20261120.diff`. Expect a trivial textual conflict only where v5 also touched the trailing parameters of `run_detector_replay` (replay.hpp/replay.cpp/replay_main.cpp); the new parameter goes last, after `diagnostic_common_assignment_confidence`.

Proposed screen command: the v5 reference command with `--diagnostic-upper-fretted-relief` appended, plus the untraced identity companion with the same flag. Screen terms are Codex's tightened ones in `CODEX-M3-STRUCTURAL-PENALTY-REPLY-20261120.md` (>=5000 gained matched frames in 61-71 is a usefulness threshold only; no lower-band loss allowance; reject on more wrong-note/wrong-string/gap outputs, lost protected matches, worse holds/retriggers, identity or deadline failures; named negative corpora included).

## Known risks the counts cannot settle

DP slot competition (5 voices): a relieved upper note can displace a lower one; downstream onset/evidence gates may still block selected upper notes; lane correctness of recovered frames; a false active lower note (ghost) can license relief, so the false-parent rate matters. The saved-table census behind the rule is exploratory and passage-confounded, not held-out validation.
