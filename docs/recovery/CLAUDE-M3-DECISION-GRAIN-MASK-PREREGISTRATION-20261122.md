# Pre-registration: does the rapid-mute mask's verdict depend on its 512-sample grain?

Claude, 2026-11-22. Saved data only: the two pinned v5 traces and Codex's published rapid-mute JSON. No audio, model run, job, native edit or promotion. Script `CLAUDE-M3-DECISION-GRAIN-MASK-20261122.py` (sha256 prefix `c9fa7d51aae9`). This note and the script are committed and pushed before the one scored run; the run refuses to overwrite its output.
**POST HOC in motivation:** the check is prompted by the two labels that fail Codex's frozen screen (see "Why this check, and what it is not").

## Question

Codex's frozen screen (plan commit `bc72dc7`, result `CODEX-M3-RAPID-MUTE-RESULT-20261122.md`) reads quiet disposition 5 (`rapid_mute_ratio`) only from the last decision of each completed 512-sample callback and removes the whole following callback from CURRENT. The shipped VST3 stamps each note event at its own 64-sample decision frame. If the same existing cue is read at every decision and applied for the 64 samples that follow it, does the frozen per-label budget verdict change on either recording?

I expect the ordinary verdict **not** to change (label 70, see "Budget arithmetic"), so this is mostly a confirmation with a descriptive payload: whether the sixteen head losses are a grain artifact (P5), what new cuts the finer mask makes (P3, P4, P8), and whether extended-middle still passes (P9).

## Why this check, and what it is not

- **Native evidence.** `native/vst3/vst3_component.cpp:1127` sets `transition.sample_offset = frame;` and `native/vst3/vst3_event_sink.cpp:29-30` copies it to the VST3 event's `sampleOffset` (same lines in `HEAD` and in the working tree). A causal release can therefore act at a decision, at the earliest from the sample after the flagged decision (`s + 1`). The callback-grain mask is coarser than the output stage can express.
- **Motive.** My own anatomy of Codex's mask (`CLAUDE-M3-RAPID-MUTE-CHECK-RESULT-20261122.md`) found that sixteen of the seventeen labels that lose presence lose it only inside the first 1,024 samples after their annotated start (26 to 679 samples): the window clears on a 512-sample boundary a few samples after the new note's onset and takes its first samples. The seventeenth is label 70, where two windows start inside the label (15.7 and 31.7 ms after its annotated start). Part of the failure may therefore be an artifact of the grain. That is why this is post hoc.
- **It is not a rescue.** Codex wrote that "the two failures are not exemptions or parameters to fit". Nothing here exempts them: Codex's mask (M0 below) keeps failing on labels 31 and 70 whatever the finer mask does, and Codex's verdict on its frozen mask stands. Nothing here is a parameter either: 64 samples is the detector's own decision interval, not a value chosen from a label outcome, and exactly one finer mask is scored. Codex's frozen text lists "No dwell, extension, new threshold, pitch split or grid"; this check adds none of those (same cue, each mark lasts one decision, nothing is searched).
- **What each result is worth.** A failure closes the granularity route and shows the rejection holds at the native decision grain. A pass would be a lead about a mask Codex did not screen, on two design recordings, and nothing would be accepted.
- **Codex was told first.** The proposal went to Codex's queue (id `01a205f6`) with an invitation to object. No objection has arrived as of this commit; its newest note says Claude retains "the distinct callback/restart analysis", which I do not read as approval of this specific check.

## What I have seen and what I have not

Seen:

1. Every M0 number in Codex's result and JSON: CURRENT and masked totals, the per-label deltas, the budget verdict (ordinary fails on labels 31 and 70; extended-middle passes).
2. My own earlier anatomy of where M0 removes present output (the bullet above).
3. The counts-only geometry below: flagged-decision counts and mask sizes from the trace alone. It involves neither CURRENT nor labels.
4. One boolean per recording from running the scoring path on an **empty** mask (masked output equals CURRENT, so it removes nothing; true on both). It prints no volume and no label value.

Not seen: any M1 occupancy, per-label loss or budget result, the region breakdown, the label table, or any score of M0 from my own code (the scored identity gate runs only inside `--run`; the plumbing compares M0's intervals, not its scores).

## Design

Two masks, nothing searched, nothing tuned. Both are CURRENT minus the marked intervals, per pitch, clipped to the horizon:

| Mask | Rule |
| --- | --- |
| **M0** (Codex's frozen mask) | Per completed 512-sample callback take only its last decision. If the disposition is 5, mark the following callback `[B, B + 512)` with `B = s + 1`. Merge. |
| **M1** (decision grain) | For every decision at zero-based sample `s` whose disposition is 5, mark `[s + 1, s + 65)`. Merge. |

The decision grid is `s = 64 * tick - 1` (checked for every tick, contiguous). Both masks are an optimistic occupancy diagnostic: when a flag clears, CURRENT's old span resumes. Neither is a NoteOff/NoteOn implementation.

Scoring is the machinery of `CLAUDE-M3-RAPID-MUTE-CHECK-20261122.py` (`19eb96cb045b`, committed unchanged), which loads `CLAUDE-M3-SUPPORT-EVENTS-CHECK-20261122.py` (`fea9de35dff4`): the same scorer, trace pins, strict and aggregate checks, and the frozen per-label budget (loss at most 25 ms **and** at most 5% of that label's own CURRENT value).

**Identity gate (P1).** On both recordings M0 must reproduce Codex's JSON (`c2008b895622`) exactly: CURRENT totals, masked totals, per-label comparison, budget block and run counts. The plumbing step additionally requires the per-tick reader to reproduce the callback reader's dictionary, the trace audit to equal Codex's, and M0's intervals to equal Codex's marked intervals. Any failure stops the run before a score is written.

## Budget arithmetic (CURRENT only, ordinary)

| Label | CURRENT presence | Allowance, 5% (25 ms cap not reached) | Loss under M0 |
| ---: | ---: | ---: | ---: |
| 31 (pitch 55) | 9,510 | 475.5 samples (4.95 ms) | 679 (7.14%) |
| 70 (pitch 48) | 3,494 | 174.7 samples (1.82 ms) | 959 presence (27.4%); longest hold 1,983 (56.8%) |

So label 31 needs its total loss cut by about 30% and label 70 by about 82%. Across the 234 ordinary labels with CURRENT presence the allowance is below 512 samples for 5, below 256 for 2, and below 128 and below 64 samples for 1 (minimum 60.8 samples: one flagged decision overlapping that label would already exceed it). Extended-middle: all six labels have the full 25 ms (2,400 samples) allowance.

**The budget covers the longest hold as well as the presence** (`budget()` in `CLAUDE-M3-SUPPORT-EVENTS-CHECK-20261122.py`: for both quantities the loss must be at most 25 ms and at most 5% of the label's own CURRENT value). A mark in the interior of a label's dominant present run splits it, and the longest hold then falls by roughly half the run, however short the mark is. Only marks within about 5% of a run's ends, or outside CURRENT's presence, are harmless.

**Label 70 (a structural expectation from already-seen M0 numbers).** Its CURRENT longest hold equals its presence (3,494 samples: one contiguous run), and M0 leaves a longest piece of 1,511 samples (hold loss 1,983). M0's two windows start inside that run, each triggered by a flagged decision at `s = B - 1`. M1 marks `[s + 1, s + 65)` after that same decision, so it also lands inside the run, splits it, and loses far more than 174.7 samples of longest hold. Label 70 therefore stays over budget unless CURRENT is absent over the 64 samples after each trigger, which is unlikely given that M0 removes 959 present samples across the two windows. This is why P6 and P7 are at 1%, and why I expect CLOSED. The same reasoning raises P8: M1 adds 519 flagged decisions that are not M0 triggers (646 outside every M0 run, of which about 127 are the decisions just before an M0 run), including 19 isolated single-decision runs, and any of them that lands inside a label's run breaks that label's hold budget.

## Counts-only geometry (second `--dry`, before this note)

| | Ordinary | Extended-middle |
| --- | ---: | ---: |
| Decision ticks | 167,025 | 35,025 |
| Flagged (disposition 5) decisions | 10,949 | 888 |
| ...of which inside an M0 run | 10,303 | 808 |
| ...of which outside every M0 run (M1 newly marks them) | 646 | 80 |
| Unflagged decisions inside an M0 run (M1 unmarks them) | 569 | 27 |
| M0 runs / samples | 127 / 695,808 | 6 / 53,478 |
| M1 runs / samples | 149 / 696,640 | 6 / 53,606 |
| Samples only in M0 / only in M1 | 28,288 / 29,120 | 1,408 / 1,536 |
| M1 runs of one decision / longest M1 run (samples) | 19 / 6,976 | 0 / 11,136 |

M1 is not simply a shorter M0: the two masks have almost the same total size and differ by about 28 to 29 thousand samples each way on the ordinary recording, so M1 is a shifted mask. Against an M0 run, an M1 run can start earlier or end earlier by up to seven decisions (448 samples). The 646 flagged decisions outside every M0 run include the decision just before each M0 run (that is where an M0 window is triggered, `s = B - 1`, one sample before the run); M1 marks all of them.

## Predictions (odds fixed before the commit and before any M0 or M1 outcome; P6, P7 and P8 were revised once, see below)

| # | Odds | Statement |
| ---: | ---: | --- |
| P1 | 97% | Identity gate: M0 reproduces every Codex number on both recordings |
| P2 | 50% | Ordinary: M1 removes at least as large a share of CURRENT gap extra as M0 (41.945%) |
| P3 | 55% | Ordinary: M1 loses fewer present samples than M0 (4,350) |
| P4 | 60% | Ordinary: at least 17 labels lose presence under M1 (M0: 17) |
| P5 | 35% | Ordinary: label 31 is within the frozen budget under M1 |
| P6 | 1% | Ordinary: label 70 is within the frozen budget under M1 |
| P7 | 1% | Ordinary: M1 passes the frozen budget (no label over, none newly missed, aggregate pitch safety) |
| P8 | 60% | Ordinary: at least one label within budget under M0 is over budget under M1 |
| P9 | 85% | Extended-middle: M1 passes the frozen budget |
| P10 | 70% | Ordinary: at least 99% of the CURRENT output M1 affects is false |

**Revision of P6, P7, P8 (before the commit).** They were written as 6%, 4% and 30%. After comparing the allowance with the head and interior structure (the two paragraphs under "Budget arithmetic") I moved them to 1%, 1% and 60%. That came from the budget definition and from M0 numbers I had already seen; no M0 or M1 outcome had been computed. The other seven odds are as first written. P5 stays at 35%: label 31 passes only if the flagged run after its onset is short (its M0 loss of 679 samples implies at least two consecutive flagged callback ends, so M1 loses between 2 and about 9 decisions of it, 128 to 576 samples, against an allowance of 475.5).

The Brier sum over the ten is reported with the result (a flat 50% scores 2.50). Misses are reported as misses.

## Reading rule (fixed now)

1. **P1 false: VOID.** M0 does not reproduce Codex's numbers, so no M1 number is interpreted; the plumbing fault is diagnosed and disclosed before anything is rerun.
2. **M1 fails the frozen budget on either recording** (a label over its allowance, a label newly missed, or aggregate pitch safety): **CLOSED.** The callback-grain rejection holds at the detector's own decision grain. No other grain and no other variant is run.
3. **M1 passes on both recordings: LEAD ONLY.** Passing the budget under an optimistic occupancy subtraction is necessary and nowhere near sufficient. Nothing is accepted. Whether a NoteOff/NoteOn mechanism could realize M1, and what it would do to the re-struck notes after a mute (the scalar restart routes are closed on three measurements), is Codex's call.

The strict gate (no label loses any present sample) is reported through the count of labels losing presence, but it is not the reading rule: Codex's frozen text rejects on a label-budget or aggregate-safety failure, and M0 fails both gates.

## What this cannot show

- Both recordings are already-seen design data; there is no held-out recording.
- M1 is an occupancy diagnostic with the old span resuming when the flag clears. It is not a release implementation, a latency test, a host test, or a measurement of delivered MIDI.
- It reads the cue at the earliest possible causal moment (`s + 1`). A real path through the detector's lifecycle (the cue clears selection and starts the 50 to 220 ms coasting hold; it does not end MIDI immediately) would act later.
- Pitch-voice samples include overlaps; they are not unique audio duration or string-correct tuner frames.
- A pass says nothing about what replaces the removed output when a note is re-struck after the mute.

## Exclusions

No native change, job, promotion or default change. No change to Codex's frozen screen, its verdict, the label budget or the gates. No second grain, no dwell, extension, threshold or pitch split. No download. Codex's files are not edited.

## How it runs

```
cd docs/recovery
python3 -P -E CLAUDE-M3-DECISION-GRAIN-MASK-20261122.py --selftest   # plumbing only
python3 -P -E CLAUDE-M3-DECISION-GRAIN-MASK-20261122.py --dry        # plus the counts above
python3 -P -E CLAUDE-M3-DECISION-GRAIN-MASK-20261122.py --run        # the one scored run; refuses to overwrite its JSON
```

The run repeats the plumbing, stops if it fails, and writes `CLAUDE-M3-DECISION-GRAIN-MASK-20261122.json` with both masks' totals, the per-label table for labels that lose anything under either mask, the removed volume by region (in both masks, only M0, only M1), the predictions with their outcomes and Brier scores, and the reading.

## Provenance and script history

Inputs: the pinned v5 traces (ordinary run 44835727027, raw sha256 prefix `b664c7ff0ce8`; extended-middle run 45062999189, `78929974b9cc`) and Codex's JSON (`c2008b895622`).
Script changes after the first draft, all made before any M0 or M1 outcome was computed: (1) the first `--dry` failed on two faults in my own test code (an expectation in the geometry unit check, and the tick-grid relation, which is `s = 64 * tick - 1`); (2) before this commit I added the empty-mask scoring-path check and the VOID clause in the reading rule; (3) P6, P7 and P8 were revised as described under the predictions table (a comment in the script records it). No other odds changed.
