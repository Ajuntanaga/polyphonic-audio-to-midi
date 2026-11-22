# Independent check of the L/E/A callback screen, and what E and A bring back: pre-registration

Claude, 2026-11-22. Committed before `CLAUDE-M3-SUPPORT-EVENTS-CHECK-20261122.py --run`. Honest ordering: the script was written first and its `--selftest` (plumbing only: unit checks on synthetic callbacks, the pinned trace hashes and tick grids, and my L support against the saved native confirmation) runs before this commit; the real run, the comparison with Codex's saved numbers and every prediction below come after it. Any change to the script after this commit will be disclosed in the result.

Saved data only. No audio, model run, job, native edit or promotion. Nothing here changes Codex's frozen plan, its stop rule or the frozen label budget.

## Why

`CODEX-M3-SUPPORT-EVENTS-PLAN-20261122.md` froze three per-callback support arms and its result (`CODEX-M3-SUPPORT-EVENTS-20261122.json`) says: A clears labels 263 and 364 with zero loss but removes only 1.985% of CURRENT's wrong-pitch output; E clears 263 but not 364 (3,831 samples, 39.9 ms); L fails both. The next decision stands on those numbers, and they come from one derivation (Codex's script). Two things are missing:

1. A second derivation of the same numbers from the pinned trace, with code written from the plan's wording.
2. What E and A actually bring back. The screen reports aggregates (wrong pitch, gap, budget). It does not say whether the re-admitted false output is held-note tail, orphan notes or heads, nor how selective each added source is as a cue before the 220 ms hold spreads it.

## Independence caveat

I read Codex's `project`, `observed_support`, `evaluate` and `budget` code before designing this check, and the filter, scorer and event-span code are shared repository code (`ad`, `tools`). So this re-derivation can catch slips, mis-wired inputs and plan-versus-code mismatches. It cannot catch a misreading that Codex and I share, and it does not re-test the shared scorer. The label-budget function and the five added per-label fields (first-present delay, segment counts) follow the committed decision and the plan; I wrote them after reading Codex's.

## What will be run

- Inputs, all pinned: the two v5 traces (ordinary run 44835727027, extended-middle run 45062999189; raw sha256 in the plan), the adapted cropped event members of run 45034216124 (sha256 in the plan), Codex's saved span files and result JSON as the things to compare against.
- One streaming pass per trace, with the hash and the contiguous 64-sample tick grid checked.
- CPU only on this laptop, modest (about 170 thousand plus 35 thousand rows).

## Definitions (from the plan, as I read it)

- Decision grid: one decision per 64 samples. A decision at sample s (zero-based) can first affect output at `(s // 512 + 1) * 512`. Callbacks whose boundary is at or past the horizon are dropped; the last support span is clipped to the horizon.
- Per decision: skip candidates when `quiet != 0`. Direct note: `selector_pool_member == 1 and direct == 1`. Onset-cue note: `selector_pool_member == 1`, `active == 1`, `selection == 4`, `onset_observed == 1`, `onset > 0`. Flags must be 0 or 1 or the run stops.
- L = direct set of the last decision of the callback. E = union of the direct sets of every decision in the callback. A = E plus the onset-cue notes. Each positive note supplies one callback of support, `[boundary, boundary + 512)`.
- Filter: support = model spans (adapted cropped ONNX events, emitted clock) union the arm's native support, held forward 220 ms; filtered output = CURRENT intersect support; scored with the shared scorer against CURRENT.
- Label budget (frozen, `CLAUDE-M3-LABEL-RULE-DECISION-20261122.md`): per label, present-time and longest-hold loss at most 25 ms and at most 5% of that label's own CURRENT value; no newly missed label; no wrong-pitch or gap growth; no exact-set or all-expected loss.
- Classes (`CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.py`): CURRENT spans unioned per pitch; a false sample is orphan (no same-pitch label overlaps the span), head (before the first overlapping label), tail (after the last overlapping label end) or between. Each filtered sample takes the class of the CURRENT span it lies in. Ordinary only for classes (499 labels); extended-middle (6 labels, all MIDI 52) is safety only.
- Sources, per pitch: L-direct = callbacks in the L set; E_add = callbacks where the note was direct earlier in the callback but not at its last decision (E minus L); A_add = callbacks where the onset cue fired and the note was not direct anywhere in the callback (A minus E).
- Coverage and lift of a source: its callbacks (before the hold), clipped to CURRENT's spans; coverage of present = present volume covered over CURRENT's present volume; coverage of false likewise; lift = coverage of present over coverage of false. A lift of 1 means the source covers present and false output alike.

## Identity checks (all four must pass for the class results to count as a confirmation; a mismatch becomes the result and is diagnosed before anything else is claimed)

- **I0** Trace audit (rows, candidate rows, quiet rows, first and last sample and tick, raw hash) equals Codex's. My L support equals the saved native confirmation. My L, E and A support spans equal Codex's saved spans, both corpora (compared after merging touching spans; raw equality also reported).
- **I1** My filtered spans equal Codex's saved filtered spans for L, E and A, both corpora, and my L filter equals the committed cropped-adapted filter of the residual-anatomy script.
- **I2** My budget verdict (over-budget labels with their violations, newly missed labels, aggregate pitch safety, pass flag) equals Codex's for L, E and A, both corpora, and my per-label deltas (present, longest, first-present delay) and sample deltas equal Codex's. The full `compare` output equality is reported separately.
- **I3** Class volumes (present, extra, gap) equal the scorer's totals for CURRENT, L, E and A on ordinary, and the three filtered outputs nest per pitch (L inside E inside A).

## Predictions (odds committed here)

Calibrated after seeing Codex's published aggregates and projection counts (ordinary: 20,863 observed callbacks; positive note-callbacks L 39,303, E 46,500, A 51,073; E adds 7,197 note-callbacks in 5,361 callbacks; A adds 4,573 more in 4,164), so I name what I had already seen.

| Id | Claim (ordinary, all pitches) | Odds |
|---|---|---:|
| P1 | The largest class of the false output that E re-admits over L is tail (alternatives: orphan 42%, head 18%; between is 0 by construction) | 40% |
| P2 | A re-admits at least as large a share of the L-removed orphan pool as of the L-removed tail pool | 70% |
| P3 | Lift of the L-direct source is at least 2.0 | 60% |
| P4 | Lift of the onset-only source (A_add) is under 1.5 | 70% |
| P5 | Lift of E_add is below the lift of the L-direct source | 75% |
| I0-I3 | All identity checks pass | 90% |

Expected hits from the odds on P1 to P5: 3.15 of 5. P1 is close to a coin flip on purpose; I have no strong prior on where the extra mid-callback direct observations sit.

## Arithmetic that Codex's published aggregates already fix (reproduced, not predicted, not scored)

Ordinary, voice samples. L, E and A false output (wrong plus gap) are 9,346,313, 9,519,387 and 11,274,378; present 13,516,249, 13,521,113 and 13,525,345; CURRENT false is 11,429,794 and present 13,525,345.

- E over L re-admits 173,074 false samples with 4,864 present (35.6 false per present). A over E re-admits 1,754,991 false with 4,232 present (414.7 per present). A over L re-admits 1,928,065 false with 9,096 present.
- The pool L removed from CURRENT is 2,083,481 false samples: orphan 1,247,630, tail 686,673, head 149,178, between 0. A takes back 92.5% of it. So the class split of A over L is bounded by that pool: orphan at least 1,092,214 (87.5% of its pool) and tail at least 531,257 (77.4% of its pool). Orphan is therefore the largest class of A over L whatever the data show, and I do not count it as a prediction.
- A removes 155,416 false samples from CURRENT (1.4%), so A's removal share of CURRENT's tail volume is at most 2.4%.

## What will be reported without a prediction

Per-class volumes and removal shares for CURRENT, L, E and A; per-class re-admission for E over L, A over E and A over L (with false per present); the share of each class's L-removed pool that E and A re-admit; the callback counts and per-class coverage of each source and its lift; my own budget verdicts per arm and corpus.

## Reading rule

- If an identity check fails, the result is the discrepancy: where my support, filtered output, budget or label deltas differ from Codex's, by how much, and which plan wording or code line explains it. No class split is then called a confirmation.
- If all four pass, Codex's L/E/A screen is independently reproduced on the saved data. The class and lift results are then descriptive: they say what E and A bring back and how selective each source is as a cue. They do not reopen the frozen stop rule (if A fails, do not tune onset strength, hold, pitch range or individual labels) and do not change the budget or any gate.
- A lift near 1 for a source means it cannot separate present from false output on its own.

## What cannot be concluded

- One recording for classes (ordinary). Extended-middle is six labels on one pitch.
- Emitted-clock saved spans; no audio, no native run, no lane, string, unison or MIDI-lifecycle claim; nothing about live latency (the screen assumes per-callback observability from a trace of the current native build).
- Labels are annotated note times; the classes inherit the earlier caveat that audible ring after an annotated end scores as false.
- Pre-hold coverage lifts describe the cue, not the final filter: the hold and the model support change which callbacks matter.
- Nothing is promoted and no default, gate or native file changes.
