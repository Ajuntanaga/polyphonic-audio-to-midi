# Codex's rapid-mute screen reproduces exactly; the cue is selective and complements the support filter, and its value hangs on restarting re-struck notes: result

Claude, 2026-11-22. Pre-registration: `CLAUDE-M3-RAPID-MUTE-CHECK-PREREGISTRATION-20261122.md` (commit `2fbefb6`, before the run). Saved data only (the two pinned v5 traces, the adapted cropped ONNX events for the stacked support arms, Codex's saved JSON); no audio, model run, job, native edit or promotion. The check script did not change after the pre-registration commit (sha256 prefix `19eb96cb045b` before and after). The section "Where the cut's present loss sits" is post hoc and says so.

## Answer

1. **The screen reproduces.** My derivation of the cue from the plan's wording gives Codex's marked intervals list for list, its mask totals, its full scorer comparison with every per-label delta, its budget verdicts and its occupancy run counts, on both recordings. The `[B, B + 512)` wiring was right. Codex's reading stands: the bare mask fails ordinary labels 31 and 70 on the 5% clause only.
2. **What the mask removes.** 1,550,017 false samples for 4,350 present (356 to 1), 73.7% of it tail output. That is 17.4% of CURRENT's tail volume and 13.6% of its false output. It is nearly disjoint from what the L support filter removes: stacked over L it still takes 1,409,464 of those false samples (90.9%) for 4,103 present and lifts precision from L's 59.1% to 63.0%. No arm plus mask passes the budget: A+mask fails the same labels 31 and 70, and L+mask and E+mask add them to the arm's own failures.
3. **The bare mask is a small bite of a large pool.** The windows are short (median 58.7 ms) and the old span resumes after them. Cutting each CURRENT span at the first window that starts inside it (a bound, not a policy) removes 6,766,181 false samples, 59.2% of CURRENT's false output and 79.8% of its tail volume, and moves precision from 54.2% to 72.7%, at the price of 1,077,990 present samples (8.0%) and 23 labels over budget, 18 of them missed entirely. I registered 30% odds that it would lose under 50,000 present samples; it lost about 22 times that.
4. **All of that present loss is one mechanism (post hoc).** In each of the 23 labels the CURRENT span containing the label began before the window that cuts it, so the new note has no span of its own. Eighteen sit in spans that hold two or three same-pitch labels (the tracker kept the pitch through the mute pause and into the re-strike); five are single-label spans whose pitch output starts 0.5 to 1.1 s before the annotated note. With a perfect label-timed restart the same cut keeps every present sample, removes the same 59.2% of false output, reaches 74.4% precision and passes the frozen budget. The cue is not the limit; telling a re-struck note from the old span continuing is.
5. **Here the cue follows the recording protocol.** It fires in the pause between chords: 125 of 127 runs start outside any annotated note, 125 of the 130 gaps between annotated blocks hold a run start (median 42.7 ms after the gap opens), and the last run ends at the next annotated onset (median 0.41 ms after it). Whether free playing leaves those pauses is not measured.

## Identity: the screen reproduces

All of the following hold on both recordings (ordinary 499 labels, extended-middle 6):

- Trace audit equal (ordinary 167,025 rows, quiet counts per code `[150917, 62, 4783, 0, 0, 10949, 0, 314]`; extended-middle 35,025 rows), horizon and rate equal; raw trace hashes and the 64-sample tick grid checked, completed callbacks contiguous.
- Marked intervals equal list for list: ordinary 127 runs, 695,808 samples; extended-middle 6 runs, 53,478 samples.
- CURRENT and masked totals equal; the overlap (ordinary present 4,350, wrong-pitch 30,980, gap 1,519,037; extended-middle gap 79,078) equals Codex's and equals the geometry intersection of CURRENT with the marked intervals.
- My full `compare` output of the mask against CURRENT equals Codex's stored comparison, every per-label delta included; the budget verdicts and occupancy run counts (ordinary 528 to 806, extended-middle 14 to 22) are equal.
- The mask lies inside CURRENT and the cut inside the mask, per pitch; on the ordinary recording my per-label lost present by geometry equals the scorer's present delta for all 499 labels.

The limit is the one I registered: the scorer, filter, class and budget code are shared repository code, so this catches slips, mis-wired inputs and plan-versus-code mismatches, not a misreading Codex and I share.

## What the mask removes (ordinary, all pitches, voice samples)

| | Removed by the mask | Share of what it removes | Share of CURRENT's class volume |
|---|---:|---:|---:|
| Tail | 1,141,760 | 73.7% | 17.4% of 6,546,826 |
| Orphan | 263,168 | 17.0% | 6.3% of 4,204,480 |
| Between | 112,416 | 7.3% | 37.4% of 300,291 |
| Head | 32,673 | 2.1% | 8.6% of 378,197 |
| False total | 1,550,017 | 100% | 13.6% of 11,429,794 |
| Present | 4,350 | | 0.03% of 13,525,345 |

Precision 54.20% to 57.78%. In the upper band (pitch 60 and up) it removes 47,846 false and 282 present samples, 13.2% of that band's false output, so the cue does not reach where the support filter also fails.

## How it stacks on the support arms (ordinary)

| | Present | False | Precision | Occupancy runs | Budget fails |
|---|---:|---:|---:|---:|---|
| CURRENT | 13,525,345 | 11,429,794 | 54.20% | 528 | none |
| mask | 13,520,995 | 9,879,777 | 57.78% | 806 | 31, 70 |
| L | 13,516,249 | 9,346,313 | 59.12% | 521 | 263, 364 |
| L + mask | 13,512,146 | 7,936,849 | 63.00% | 774 | 31, 70, 263, 364 |
| E | 13,521,113 | 9,519,387 | 58.68% | 530 | 364 |
| E + mask | 13,517,010 | 8,109,923 | 62.50% | 783 | 31, 70, 364 |
| A | 13,525,345 | 11,274,378 | 54.54% | 526 | none |
| A + mask | 13,520,995 | 9,724,361 | 58.17% | 804 | 31, 70 |

Over L the mask removes tail 1,101,312, orphan 178,688, between 112,416 and head 17,048: 343.5 false samples per present sample, and 18.8% of the tail volume L leaves (5,860,153). The filter leaves the tail and the cue takes part of it. Extended-middle is safety only: the mask removes 79,078 gap samples (43.2% of its gap output) with no present loss and passes the budget alone and stacked on every arm.

## Where the mask's present loss sits

Seventeen labels lose present output under the mask; none is newly missed. Sixteen lose it only within the first 1,024 samples of their annotated start (26 to 679 samples, 0.3 to 7.1 ms): the window clears on a 512-sample callback boundary a few samples after the new note's onset and takes its first samples. The 17th is label 70, where two windows start inside the label (15.7 and 31.7 ms after its annotated start, the only two runs that start inside an annotated note) and take 959 of the 3,494 samples CURRENT gives it. Labels 31 (679 of 9,510, 7.1%) and 70 are the two over budget, on the 5% clause only: CURRENT detects 9,510 and 3,494 of their 71,783 annotated samples, so 5% is 475 and 175 samples; the absolute losses are 7.07 and 9.99 ms.

## The cue and the recording protocol

| | Ordinary | Extended-middle |
|---|---:|---:|
| Marked runs / starting outside annotated notes | 127 / 125 | 6 / 6 |
| Annotated blocks / interior gaps / gaps holding a run start | 131 / 130 / 125 | 6 / 5 / 5 |
| Median gap, median run | 102.3 ms, 58.7 ms | 250.0 ms, 93.3 ms |
| Median run start after the gap opens | 42.7 ms | 54.7 ms |
| Last run ends relative to the gap end | 0.41 ms after it | 104.7 ms before it |

The flag is raised by the pause the player leaves after each chord and, on the ordinary recording, clears at the next onset. That is why it is so selective here (99.7% false overlap) and why the generalisation is untested.

## Mask, cut and a perfect restart

| Ordinary | Mask (instant restart) | Cut (no restart) | Cut + oracle restart |
|---|---:|---:|---:|
| Present lost | 4,350 (0.03%) | 1,077,990 (8.0%) | 0 |
| False removed | 1,550,017 (13.6%) | 6,766,181 (59.2%) | 6,766,181 (59.2%) |
| Precision | 57.78% | 72.75% | 74.36% |
| Occupancy runs | 806 | 528 (245 spans shortened, none removed) | 551 |
| Budget | fails 31, 70 | fails 23 labels | passes |

The cut removes tail 5,226,179 (79.8% of CURRENT's tail volume), orphan 1,215,061 (28.9%), between 215,869 (71.9%) and head 109,072 (28.8%). Stacked on L it removes 5,666,152 false for 1,069,472 present (L+cut precision 77.2%). The oracle restart adds back every CURRENT sample that lies inside a same-pitch annotated label (that is all of the present output and nothing false); it uses labels a tracker does not have, so it is a ceiling for any restart rule, not a design. Extended-middle: the cut removes 136,990 gap samples (74.9% of its gap output), loses no present and passes the budget; no restart problem shows up on that recording (six labels of one pitch, gaps of about 250 ms).

## Where the cut's present loss sits (post hoc)

Written and run after the pre-registered result, descriptive, no predictions (`CLAUDE-M3-RAPID-MUTE-CUT-ANATOMY-20261122.py`; the per-label losses sum to the aggregate 1,077,990).

- All 23 labels lose present output the same way: the CURRENT span containing the label began before the first window that starts inside it, so the cut removes the label from that window on. 18 labels lose all of their present output; the other five lose 4.4% to 81.8%.
- Cut point against the label's annotated start: 50 to 74 ms before it for 19 labels (the pre-note window), about 0.91 s before for four (labels 70, 178, 245, 263: an earlier window in a long span).
- 18 labels sit in a span that holds two or three same-pitch labels (19, 31, 70, 91, 128, 159, 174, 178, 200, 225, 239, 245, 302, 349, 355, 456, 459, 470). For 15 of them the chord that ended within 200 ms before the label holds the same pitch. This is a re-strike that CURRENT never released between.
- Five labels (42, 123, 263, 306, 364) are single-label spans whose pitch output begins 0.48 to 1.07 s before the annotated start: sustained detector output ahead of the true onset (the preceding chord holds an octave or semitone neighbour for 123 and 364, nothing within 200 ms for 42, 263 and 306).
- Labels 31 and 70, the two the mask fails, are among the 23 and lose all of their present output under the cut.
- The five labels that lose only part of their present output (91, 128, 178, 225, 263) are exactly the five whose present output lies in two CURRENT spans: the cut takes the first span's share and the second span, which starts later inside the label, survives. The other 18 lie in one span each and lose everything.
- Limit of this anatomy: for those five labels the script treats the union range of the two spans as one span. The cut point it reports is the first span's, but "span end after label" and the count of same-pitch labels in the span describe the union. For 91, 128, 178 and 225 the previous-chord check (a same-pitch label that ended within 200 ms before) confirms the re-strike independently of that count; label 263 has no such label and a single same-pitch label in the union. The per-label lost samples come straight from geometry and are exact (they sum to the aggregate and match the scorer for every label).

## Reading

- Codex's screen stands and its rejection of the bare mask stands under its own frozen rule. Nothing here changes a gate, a default or the frozen label budget (the user's "Leave it as is", `2bf0e2a`). I did not shift, shorten or condition any window.
- The cue and the support filter act on different output: the filter leaves the tail and the mask takes 18.8% of it over L. But a mask that lets the old span resume understates what a release can remove by a factor of about 4.4 (13.6% against 59.2% of CURRENT's false output).
- What gates that 59.2% is restarting a re-struck pitch: 23 of 499 labels (4.6%) here. A release design driven by this cue lies between the mask and the oracle ceiling, and where it lies depends only on how well a new note of the same pitch is told from the old span continuing.
- After the run I read Codex's joint release latch (`CODEX-M3-JOINT-RELEASE-RESULT-20261122.md`): it is the cut with a neural-presence veto and a latch, and it loses seven labels completely (19, 42, 70, 123, 200, 306, 364). All seven are among my 23, so the veto does not remove the restart problem and the latch inherits it. That is the question Codex announced as its next item (a sustained detector pitch versus a new physical note).
- Not run, and not claimed: which saved per-pitch signals after a window (native direct and onset observations, model NoteOn events) mark the 23 restarts but not the roughly 220 other truncated spans, which hold no lost present output. That evidence census would need its own pre-registration; it overlaps Codex's note-identity work, so Codex hears about it before I start.

## Predictions, scored

| Id | Claim | Odds | Measured | Result |
|---|---|---:|---|---|
| I0-I3 | All identity checks pass | 90% | all pass, both recordings | hit |
| P1 | Largest class of the false output the mask removes is tail | 70% | tail 1,141,760 (73.7%); orphan 17.0% | hit |
| P2 | Mask removes under 25% of CURRENT tail volume | 75% | 17.4% | hit |
| P3 | Mask adds at least 75% of its false volume over L | 70% | 90.9% (1,409,464 of 1,550,017) | hit |
| P4 | Cut removes at least 3 times the mask's false volume | 60% | 4.37 times | hit |
| P5 | Cut loses under 50,000 present samples | 30% | 1,077,990 | **miss** |
| P6 | At least 80% of runs start where no label is annotated | 65% | 125 of 127 (98.4%) | hit |
| P7 | At least 12 of the lossy labels lose only within their first 1,024 samples | 70% | 16 of 17 | hit |

Six of seven against 4.4 expected, plus the identity checks. P5 was the one I said I expected to miss, and I misjudged the size: I reasoned that merged old-tail plus re-strike spans exist ("between" is 300,291 samples) but did not expect them to take 23 labels with them (18 of them entirely). The arithmetic items in the pre-registration (356 false per present, 13.6%, 57.78%) reproduced and were not scored.

## Provenance

- `CLAUDE-M3-RAPID-MUTE-CHECK-20261122.py` (sha256 prefix `19eb96cb045b`, committed in `2fbefb6` before the run; selftest passed first), output `CLAUDE-M3-RAPID-MUTE-CHECK-20261122.json` (`185f1db63edc`), run 2026-11-22 21:37:50 to 21:38:09 UTC, CPU only. Compared against `CODEX-M3-RAPID-MUTE-20261122.json` (sha256 `c2008b895622…`, the hash Codex's joint-release plan also pins).
- Post hoc: `CLAUDE-M3-RAPID-MUTE-CUT-ANATOMY-20261122.py` (`22d070dca798`) and its output (`fb219633382e`).
- Inputs pinned as in the plan: ordinary trace run 44835727027 (raw sha256 `b664c7ff0ce8`), extended-middle trace run 45062999189 (`78929974b9cc`), adapted cropped events of run 45034216124 (`4e0601c42dbd`, `1eea72fdc62b`). Classes and tally code: `CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.py` (`047242e96fc6`); support arms: `CLAUDE-M3-SUPPORT-EVENTS-CHECK-20261122.py` (`fea9de35dff4`).

## What cannot be concluded

- Two recordings with a mute after nearly every chord; a cue that fires at every pause here may fire rarely or differently in free playing. Both are design recordings already examined, and the cut anatomy was found on the ordinary one.
- The quiet disposition is a whole-signal tracker state, so a marked window blanks every pitch; nothing here says which voices a real note-off should release.
- Emitted-clock saved spans, occupancy only: no audio, no native run, no MIDI lifecycle (NoteOn and NoteOff counts, retriggers, stuck notes), no lane, string or unison claim, nothing about live latency. The mask, the cut and the oracle are bounds on occupancy, not implementations.
- The oracle restart uses the annotated labels. It says what a perfect restart would buy on this recording, not that a restart rule exists or what it would cost in false output.
- Labels are annotated note times; audible ring after an annotated end scores as false and sits in the tail class.
- Nothing is promoted; no gate, default, native file or label budget changes.
