# Independent check of the rapid-mute cue screen, what its mask removes, how it stacks on the support filters, and a cut-at-first-flag bound: pre-registration

Claude, 2026-11-22. Committed before `CLAUDE-M3-RAPID-MUTE-CHECK-20261122.py --run`. Honest ordering: the script was written first and its `--selftest` (plumbing only: unit checks on synthetic intervals, the pinned trace hashes and tick grids, callback completeness, and CURRENT's span volume against the scorer) passes before this commit, script sha256 prefix `19eb96cb045b`. The real run, the comparison with Codex's saved numbers and every prediction below come after it. Any change to the script after this commit will be disclosed in the result.

Saved data only. No audio, model run, job, native edit or promotion. Nothing here changes Codex's frozen plan, its reading rule ("any label-budget or aggregate safety failure on either recording rejects this predicate alone as a global shortening cue; do not tune it here") or the frozen label budget.

## What I had already seen (disclosure)

- From `CODEX-M3-RAPID-MUTE-20261122.json` (schema `m3_rapid_mute_overlap_v1`), before writing the script: the headline numbers (ordinary: 127 marked runs, 695,808 marked samples; the marked callbacks overlap CURRENT's present 4,350, wrong-pitch 30,980 and gap 1,519,037 samples; extended-middle: 6 runs, 53,478 samples, 79,078 gap samples and no present), the budget verdict (ordinary fails labels 31 and 70 on the 5% clause only; extended-middle passes), occupancy runs (CURRENT 528 to masked 806; extended-middle 14 to 22), the list of the 17 labels whose present time changes with their sizes, and the first few marked intervals.
- I read the plan (`CODEX-M3-RAPID-MUTE-PLAN-20261122.md`) in full and wrote the cue and mask from its wording. **I have not read Codex's script (`CODEX-M3-RAPID-MUTE-20261122.py`)** and will not before the real run; I read it only to diagnose a mismatch.
- Reading the 17-label list, I noticed that for labels 19, 31 and 42 the present loss equals a marked window's end minus the label's annotated start (48, 679 and 282 samples). So the "window end straddles the next onset" explanation is partly known to me; P7 asks whether it holds for most of the 17.

## Why

Codex's screen asks whether the existing rapid-mute predicate overlaps false output selectively enough to warrant a causal release design. The saved result says yes on selectivity (99.72% of the overlap is false) and rejects the cue alone on the label budget (two labels, 5% clause). Four things are missing and are in my lane (independent verification; saved-data analysis):

1. A second derivation of the marked intervals, mask, comparison and budget from the plan's wording.
2. What the mask removes by class (orphan, tail, head, between), since tail is 62.7% of what the support filter leaves behind.
3. How the cue stacks on the L, E and A support arms (is its removal complementary or already taken by the filter?).
4. A bound on what a real note-off from this cue could remove and lose. Codex's mask resumes a span when the flag clears, which is an optimistic occupancy diagnostic for the present cost (instant restart) and understates what a note-off would remove from the rest of each tail. The cut bound below is the opposite extreme.

Also, the first marked windows in the saved list repeat about every 80,000 to 83,000 samples, which looks like a once-per-note-slot mute in the recording. If so, the cue's selectivity may be a recording-protocol effect; I measure it, I do not assume it.

## Independence caveat

The marking and mask are written from the plan's wording alone. The scorer, filter, class code and budget function are shared repository code (`ad`, `fr`, and my earlier L/E/A check, which reproduced Codex's L/E/A screen exactly), so this re-derivation can catch slips, mis-wired inputs and plan-versus-code mismatches. It cannot catch a misreading Codex and I share, and it does not re-test the shared scorer. One reading choice is mine: the "following callback interval" is `[B, B + 512)`, the same wiring as the L/E/A plan; if Codex used `[B - 512, B)` the saved intervals would be shifted by 512 and I would report that as the discrepancy.

## What will be run

- Inputs, all pinned: the two v5 traces (ordinary run 44835727027, raw sha256 `b664c7ff0ce8`; extended-middle run 45062999189, `78929974b9cc`), the adapted cropped event members of run 45034216124 for the stacked support arms (hash-verified), and Codex's saved rapid-mute JSON as the thing to compare against.
- One streaming pass per trace for the cue (quiet disposition of each completed callback's last decision) and one for the L/E/A support derivation of my earlier check, hashes and the 64-sample tick grid checked. CPU only, laptop, a few minutes.

## Definitions

- **Cue.** A completed callback is one whose last decision is at a zero-based post-sample `s` with `(s + 1) % 512 == 0`; its boundary is `B = s + 1 = ceil((s + 1) / 512) * 512`. Mark `[B, B + 512)` when that decision's quiet disposition is 5 (rapid_mute_ratio). Clip to the common horizon; merge touching intervals into runs. Nothing is marked before the first completed callback.
- **Mask** (Codex's diagnostic): CURRENT minus the marked intervals, all pitches alike.
- **Cut variant** (mine; a bound, not a policy): each CURRENT span (merged per pitch) is truncated at the first marked interval that starts inside it. A span that begins inside a marked interval is blanked until that interval ends (as the mask does) and is then truncated at the next marked interval that starts inside it. Nothing is resumed after a truncation, so a CURRENT span that merges an old note's tail with a re-struck note of the same pitch loses the new note too. The mask is therefore the optimistic extreme for present loss (instant restart) and the cut is the pessimistic one (no restart inside a span); a real note-off design sits between them. The cut never keeps anything the mask removes.
- **Stacks:** each support arm's filtered output (L, E, A: the cropped-adapted ONNX events plus the arm's native support, held 220 ms, intersected with CURRENT, as in my L/E/A check) with the marked intervals removed (`arm+mask`) or intersected with the cut output (`arm+cut`).
- **Classes** (`CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.py`): CURRENT spans unioned per pitch; a false sample is orphan (no same-pitch label overlaps the span), head (before the first overlapping label), tail (after the last overlapping label end) or between; each output sample takes the class of the CURRENT span it lies in. Ordinary only for classes (499 labels); extended-middle (six labels, all MIDI 52) is identity and safety only.
- **Label budget** (frozen, `CLAUDE-M3-LABEL-RULE-DECISION-20261122.md`): per label, present-time and longest-hold loss at most 25 ms and at most 5% of that label's own CURRENT value; no newly missed label; no wrong-pitch or gap growth; no exact-set or all-expected loss. Reported for every variant for information; verdicts about policies stay Codex's.
- **Label anatomy:** for each label, the part of CURRENT's same-pitch output inside the label that falls in a marked interval, as offsets from the annotated start. `head` means all of it lies within the first 1,024 samples of the label; `end` within the last 1,024; otherwise `other`. Checked against the scorer's per-label present delta for every label.
- **Protocol:** the annotated timeline is the union of all labels; its interior gaps are the stretches between consecutive merged blocks. A run "starts outside labels" if its first sample is not annotated. I report how many interior gaps contain a run start and the median offsets.

## Identity checks (all must pass for the class and stack results to count as a confirmation of Codex's screen; a mismatch becomes the result and is diagnosed before anything else is claimed)

- **I0** My trace audit (rows, quiet counts per code, raw hash, last sample), horizon and rate, marked intervals (list equality), marked runs and marked samples equal Codex's, both corpora.
- **I1** My CURRENT and masked present, wrong-pitch and gap totals, and the overlap (present, wrong-pitch, gap, total) equal Codex's; the overlap computed by geometry (CURRENT intersect marked) equals the scorer's difference.
- **I2** My full `compare` output of the mask against CURRENT equals Codex's stored comparison; my budget verdict equals Codex's; the occupancy run counts (CURRENT, masked) equal Codex's.
- **I3** The mask lies inside CURRENT and the cut inside the mask, per pitch; my per-label lost present (by geometry) equals the scorer's present delta for every label (no mismatches), ordinary.

## Predictions (odds committed here; ordinary, all pitches, voice samples unless noted)

| Id | Claim | Odds |
|---|---|---:|
| P1 | The largest class of the false output the mask removes is tail (alternative: orphan; head and between are small) | 70% |
| P2 | The mask removes under 25% of CURRENT's tail volume | 75% |
| P3 | The L filter already removes under 25% of the mask overlap's false volume, i.e. the mask adds at least 75% of it over L | 70% |
| P4 | The cut variant removes at least 3 times the mask's false volume | 60% |
| P5 | The cut variant loses under 50,000 present samples (the mask loses 4,350) | 30% |
| P6 | At least 80% of the marked runs start where no label is annotated | 65% |
| P7 | At least 12 of the labels that lose present output under the mask lose it only within the first 1,024 samples of their annotated start | 70% |
| I0-I3 | All identity checks pass | 90% |

Expected hits from the odds on P1 to P7: 4.4 of 7. P5 is the one I expect to miss: where CURRENT merges an old note's tail with a re-struck note of the same pitch (the "between" class is 300,291 samples, so such merges exist), the cut removes the new note's present output as well. P4 is near the middle of my estimate: tails (median 294 ms) usually outlast the cue's 62 ms windows several times over, but not every note slot may have a window.

## Arithmetic that Codex's saved aggregates already fix (reproduced, not predicted, not scored)

Ordinary, voice samples. The mask removes 4,350 present, 30,980 wrong-pitch and 1,519,037 gap samples (1,554,367 in all; 1,550,017 false, 99.72%); CURRENT precision 54.20% (13,525,345 present, 11,429,794 false); masked present 13,520,995 and masked false 9,879,777, so masked precision 57.78%. So the mask's exchange is about 356 false samples per present sample and it removes 13.6% of CURRENT's false output. Present loss is 0.032% of CURRENT's present.

## What will be reported without a prediction

Class volumes and removal shares for CURRENT, mask, cut, the three arms and the six stacks (and by band, below and from pitch 60); per-class removal of the mask and the cut; the false and present volume each cue adds over L, E and A; budget verdicts and failing labels for every variant; span counts (fragmentation) per variant and how many spans the cut shortens or removes; per-label anatomy of all labels with present loss; protocol counts (blocks, interior gaps, gaps with a run start, run length and offset medians, offsets of runs that start inside a label).

## Reading rule

- If an identity check fails, the result is the discrepancy: where my marked intervals, mask, comparison or budget differ from Codex's, by how much, and which plan wording or code line explains it (this is the one point where I read Codex's script). No class, stack or cut result is then called a confirmation.
- If all four pass, Codex's rapid-mute screen is independently reproduced on the saved data, and Codex's rejection of the cue alone stands under its own frozen reading. The rest is descriptive: what the cue removes, how it stacks, where its present loss sits, and the bracket (mask versus cut) a causal release design would fall in. A large present loss under the cut (P5 missing) would mean the mask understates the cost of a real note-off; a small one would mean it does not. Neither accepts or rejects a design.
- No tuning: I will not shift, shorten or condition the windows to fit the two failing labels here. Any such variant would need its own pre-registration and a recording that was not used to find the problem; neither recording is newly held out.

## What cannot be concluded

- Two recordings that seem to share a once-per-slot mute protocol (that is what P6 and the protocol counts examine); a cue that fires at every mute in these recordings may fire rarely or differently in free playing.
- The quiet disposition is a whole-signal state of the tracker, so a marked window blanks every pitch; nothing here says which voices a real note-off should release.
- Emitted-clock saved spans, occupancy only: no audio, no native run, no MIDI lifecycle (NoteOn/NoteOff counts, retriggers, stuck notes), no lane, string or unison claim, nothing about live latency. The mask and the cut are bounds on occupancy, not implementations.
- Labels are annotated note times; audible ring after an annotated end scores as false and sits in the tail class.
- Nothing is promoted; no gate, default, native file or label budget changes.
