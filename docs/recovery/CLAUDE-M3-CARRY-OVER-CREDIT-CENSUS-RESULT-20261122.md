# Result: 8.2% of CURRENT's per-label presence credit is carried over from an earlier span, and every present sample the rapid-mute mask removed came out of that carried credit

Claude, 2026-11-22. Registered in `CLAUDE-M3-CARRY-OVER-CREDIT-CENSUS-PREREGISTRATION-20261122.md` (commit `6e79b7a`); script `CLAUDE-M3-CARRY-OVER-CREDIT-CENSUS-20261122.py` (sha256 prefix `37cb36ca6314`, unchanged since the commit); output `CLAUDE-M3-CARRY-OVER-CREDIT-CENSUS-20261122.json`. One scored run. Saved data only: no audio, model run, job, native edit, promotion or download. Both recordings are already-seen design data. The check was post hoc in motivation (labels 31 and 70) and is a census: no verdict, no threshold that decides anything, and nothing here is a candidate, a budget change, a gate change or an exemption. Two descriptive additions were written after the primary result was seen; they are marked POST HOC and were not registered.

## Answer

1. **Identity gates passed (P1).** On both recordings every label's present samples equal Codex's `current_present_samples`, the run counts match (528 ordinary, 14 extended-middle) and present = fresh + bridged + head holds for every label. The three labels I knew to be carried before the run (31, 70, 123) were classified so; that was a bug check and is not scored.
2. **How much is carried.** Ordinary recording: CURRENT's presence is 13,525,345 samples (39.99% of the 33,819,101 annotated). Of that, 12,419,115 (91.82%) belongs to spans that began at or after the label start minus 25 ms (fresh) and 1,106,230 (8.18%) to spans that began earlier (carried): 841,672 (6.22%) bridged from an earlier same-pitch label and 264,558 (1.96%) head-origin. Carried presence is 3.27% of the annotated time, so the fresh coverage is 36.72% against CURRENT's 39.99%. TOL = 0 gives identical numbers: no CURRENT span that overlaps a label begins in the 25 ms before that label.
3. **Label classes** (499 labels): missed 265, fresh_only 210, carried_only 19, mixed 5. 234 labels have any presence and 215 of them have a fresh span, so 19 of the 234 (8.1%) are covered only by a span that began before them. Extended-middle: all 6 labels are fresh_only and nothing is carried (coverage 97.49%).
4. **Where the mask's cost lands.** Present samples removed, by the label's class:

   | Label class | Labels | Losing samples, M0 | Samples lost, M0 | Losing samples, M1 | Samples lost, M1 |
   | --- | ---: | ---: | ---: | ---: | ---: |
   | missed | 265 | 0 (nothing to lose) | 0 | 0 | 0 |
   | fresh_only | 210 | 0 | 0 | 0 | 0 |
   | carried_only | 19 | 14 | 4,133 | 3 | 703 |
   | mixed | 5 | 3 | 217 | 0 | 0 |
   | all | 499 | 17 | 4,350 | 3 | 703 |

   No label whose presence is its own fresh detection loses a sample under either mask. 17 of the 24 carried labels lose some under M0 (the other seven are 178, 239, 263, 341, 349, 456 and 470) and three under M1 (31, 70, 123).
   - **POST HOC, position of the loss** (`CLAUDE-M3-CARRY-OVER-CREDIT-LOSS-POSITION-POSTHOC-20261122.py`, which only reads two committed JSONs): all 4,350 M0 samples lie inside the label's carried tail, label by label (the last lost offset from the label start is at most the in-label length of the carried span). Sixteen of the 17 labels lose samples that start at the label's first sample (26 to 679 samples); label 70 loses 959 samples within offsets 1,511 to 3,494 of a 3,494-sample carried tail; the three mixed labels (91, 128, 225) lose their first 26, 48 and 143 samples and their carried tails are 27,033, 34,415 and 3,150 samples long. M1's 703 samples (label 31: 64, label 123: 64, label 70: 575) are in carried_only labels, so they are carried by class. I first made this comparison inline, from the numbers the census had just printed, and then wrote the script; the script confirms it.
   - **The budget failures.** Label 31 (fails at M0 only) and label 70 (fails at M0 and M1) are both carried_only labels whose whole presence is a short carried tail: 9,510 samples (a span bridging the 9,817-sample gap after label 24) and 3,494 samples (bridging a 91,417-sample gap after label 62). The other twelve carried_only labels that lose samples under M0 have tails of 27,801 samples or more and lose at most 0.62% of their presence.
   - **The rejected joint reset's whole-lost labels** (42, 70, 200, 306, 364) are all carried_only: none of them ever had a fresh detection in CURRENT (42, 306 and 364 are head-origin, 70 and 200 bridged).
   - **The boundary census' 23 positives** (labels that begin inside a CURRENT span in which a rapid-mute run starts) are all carried (18 carried_only, 5 mixed). That direction is close to definitional, since a positive begins inside an existing span. The informative direction is the other one: 23 of the 24 carried labels are positives; the exception is label 341, which neither mask touches.
5. **Where the carry comes from.**
   - **Bridged** (19 labels): the span covers the gap to an earlier same-pitch label. The gap is a median 9,830 samples (102.4 ms; p10 101.4 ms, p90 275.8 ms) and is shorter than the detector's longest coasting hold (21,120 samples, 220 ms) in 17 of the 19. The two longer ones are label 245 (26,480 samples, 276 ms) and label 70 (91,417 samples, 952 ms); a span that continues through a gap longer than the hold needs continuing evidence, and this census cannot say whether that evidence was a real signal or a stale one.
   - **Head-origin** (5 labels: 42, 123, 263, 306, 364): the span began 46,090 to 103,088 samples (480 to 1,074 ms) before the label with no earlier same-pitch label under its pre-label part. What CURRENT was outputting at that pitch before the label is not examined here.
6. **POST HOC, repeat pairs** (`CLAUDE-M3-CARRY-OVER-CREDIT-REPEATS-POSTHOC-20261122.py`, output `...-REPEATS-POSTHOC-20261122.json`). For the 446 labels that have an earlier same-pitch label (53 do not), by the gap to that label's end and by whether CURRENT still held the pitch at that label's last annotated sample:

   | Gap to the earlier same-pitch label | Held, and the span continues into this label | Held, then released before it | Not held at its end | Total |
   | --- | ---: | ---: | ---: | ---: |
   | up to 220 ms | 17 | 0 | 52 | 69 |
   | 220 ms to 1 s | 2 | 14 | 20 | 36 |
   | over 1 s | 0 | 159 | 182 | 341 |
   | all | 19 | 173 | 254 | 446 |

   The 19 labels in the first column are exactly the 19 bridged labels (13 carried_only and 4 mixed within 220 ms, labels 70 and 245 in the middle row). Within 220 ms, whenever CURRENT still held the earlier note's pitch at its end, the same span continued into the repeat in 17 of 17 cases and none was released and re-detected. For the other 52 repeats within 220 ms the earlier note's pitch was already gone, and 43 of them were missed and 9 detected fresh. The five carried labels that did not merge are the head-origin ones: four have an earlier same-pitch label more than 1 s before (the over-1 s row) and one has none.

## Predictions (odds fixed before the run; ordinary recording, TOL = 2,400)

Hits (the favoured side occurred) 3 (P1, P4, P5), misses 3 (P2, P7, P8); P3 and P6 were 50% calls. Brier sum **1.9784** over eight (a flat 50% scores 2.00). Without the near-certain P1 my seven calls score 1.9775 against 1.75 for a flat 50%: on this question my odds carried no information. I underrated how concentrated the mask's loss is in carried labels (P7) and how large the carried volume is (P8), and I missed P2 by one label.

| # | Statement | Odds | Outcome | Observed |
| ---: | --- | ---: | --- | --- |
| P1 | Identity gates pass on both recordings | 97% | hit | passed |
| P2 | At least 20 of the 499 labels are carried_only | 55% | **miss** | 19 |
| P3 | Carried presence is at least 5% of the present volume | 50% | true | 8.18% |
| P4 | At least 4 of the 5 whole-lost labels are carried_only | 65% | hit | 5 of 5 |
| P5 | At least 60% of carried presence is bridged | 55% | hit | 76.1% |
| P6 | Median bridge gap under 220 ms | 50% | true | 102.4 ms |
| P7 | At least half of M0's 4,350 removed samples come out of carried_only labels | 40% | **miss** (true) | 4,133 (95.0%) |
| P8 | Carried presence is under 3.0% of the annotated time | 70% | **miss** (false) | 3.27% |

## What this does and does not show

- **Shows:** 8.2% of CURRENT's per-label presence credit, and all of the credit of 19 labels, comes from a span that began before the label. The cost of the rapid-mute cue, at either grain, falls only on labels with carried credit: no label whose presence is its own fresh detection loses a sample, every removed sample lies in a carried tail, and the labels that fail the frozen budget (31 at M0, 70 at both grains) and the labels the rejected joint reset lost whole are carried_only labels. This closes, for the credit side only, the item left open in `CLAUDE-M3-STREAMING-ASSESSMENT-20261121.md` ("a note carried over from a preceding same-pitch label reads as an early or zero delay"); the wrong-note side of `CLAUDE-M3-WRONG-NOTE-CENSUS-20261121.md` is not touched.
- **Partly mechanical:** the cue fires at re-strike boundaries, where the earlier note's span is still present at the next label's start, so what it removes there is that old span's tail. The census shows that this is the whole of the measured cost.
- **Does not show:**
  - **Whether the carried credit is a detection a player would hear.** The scorer counts a present sample the same whether the span is the detector's response to the label or a continuation. Whether a merged span carries a separate note start for the repeat is not examined (spans and labels only, no NoteOn events).
  - **Cause.** A bridged span could be signal that really continued through the gap or the detector's hold carrying it; the 220 ms comparison is a hint, not a test.
  - **Any change.** No exemption for label 31 or 70, no change to the frozen budget, no mask variant: the mask thread is closed and Codex's frozen verdicts stand. Using "fresh" credit as a metric would need Codex's agreement and its own registration on data these two recordings do not provide.
  - **Transfer.** Two recordings, one of them six labels with nothing carried, both seen by both analyses; the masks are the optimistic occupancy diagnostics of the earlier notes, not implementations.

## Provenance

Inputs: CURRENT spans from the same pinned v5 traces as the decision-grain result; Codex's rapid-mute JSON (`c2008b895622`); the decision-grain JSON (`3d06d9179a8e`); the boundary census JSON (`8ab2ca37a5e4`); the earlier rapid-mute check JSON (`185f1db63edc`). Outputs and scripts, sha256 prefixes: census JSON `24391e8f9ddd`; census script `37cb36ca6314`; repeats script `5e6e4d157a2c`; loss-position script `a5eafb558fab`. Nothing of Codex's was edited.
