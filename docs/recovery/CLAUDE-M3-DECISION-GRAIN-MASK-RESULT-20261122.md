# Result: at the decision grain the rapid-mute cue costs 84% less present output, but label 70 still fails the frozen budget

Claude, 2026-11-22. Registered in `CLAUDE-M3-DECISION-GRAIN-MASK-PREREGISTRATION-20261122.md` (commit `cbedb6d`); script `CLAUDE-M3-DECISION-GRAIN-MASK-20261122.py` (sha256 prefix `c9fa7d51aae9`, unchanged since the commit); output `CLAUDE-M3-DECISION-GRAIN-MASK-20261122.json`. One scored run. Saved data only: no audio, model run, job, native edit, promotion or download. Both recordings are already-seen design data. The check was post hoc in motivation (it was prompted by labels 31 and 70) and scores exactly one finer mask.

## Answer

1. **Identity gate passed (P1).** On both recordings M0 reproduces every number in Codex's JSON: CURRENT totals, masked totals, per-label comparison, budget block and run counts. The per-tick reader reproduces the callback reader, and M0's intervals equal Codex's marked intervals.
2. **Pre-registered reading: CLOSED.** M1 (the same disposition-5 cue read at every 64-sample decision, applied to the 64 samples after it) still fails the frozen label budget on the ordinary recording, on label 70 alone. Extended-middle passes under both masks. By the rule I fixed beforehand, the granularity route is closed and no further variant is run. Nothing is accepted and nothing here is a candidate.
3. **But most of M0's failure was the grain.** Ordinary recording, CURRENT against M0 against M1:

| | CURRENT | M0 (callback grain) | M1 (decision grain) |
| --- | ---: | ---: | ---: |
| Present pitch samples removed | | 4,350 | **703** |
| Wrong-pitch samples removed | | 30,980 (0.397%) | **4,019 (0.051%)** |
| Gap-extra samples removed | | 1,519,037 (41.945%) | **1,551,245 (42.835%)** |
| Share of the affected CURRENT output that is false | | 99.720% | **99.955%** |
| Precision (present / present + wrong + gap) | 54.20% | 57.78% | 57.80% |
| Pitch presence coverage | 39.99321% | 39.98035% | 39.99113% |
| Labels losing any presence / losing longest hold | | 17 / 15 | **3 / 3** |
| Labels over the frozen budget | | 31, 70 | **70** |
| Labels newly missed; aggregate pitch safety | | none; passes | none; passes |
| Occupancy runs (CURRENT 528) | | 806 | 862 |

4. **Which labels move.** Of M0's seventeen labels, fourteen lose nothing under M1. The rest:

| Label (pitch) | CURRENT present | Allowance | M0 presence / hold loss | M1 presence / hold loss |
| --- | ---: | ---: | ---: | ---: |
| 31 (55) | 9,510 | 475.5 | 679 / 679 | **64 / 231**: within budget |
| 123 (37) | 71,783 | 2,400 | 231 / 231 | 64 / 231: within budget |
| 70 (48) | 3,494 | 174.7 | 959 / 1,983 | **575 / 2,790**: over budget (presence 16.5%, hold 79.9%) |

   Label 31 now loses one decision (64 samples). That decision falls inside its run, which is why the hold loss is 231 and not 64; 231 is within the 475.5 allowed. So of the two labels that sank Codex's screen, one was largely a grain artifact. Label 70 is not: its CURRENT presence is a single 3,494-sample run (36 ms of a 71,783-sample annotation, 4.9%), the cue flags decisions inside that run, and M1 cuts it into smaller pieces than M0 does (longest remaining piece 704 samples against M0's 1,511). The budget is 5% of 3,494, about 2.7 decisions.
5. **Where M0 was losing present output.** By region (ordinary, CURRENT output removed):

| Region | Samples | Present | Wrong-pitch | Gap extra |
| --- | ---: | ---: | ---: | ---: |
| In both masks | 667,520 | 447 | 1,075 | 1,490,061 |
| Only in M0 | 28,288 | 3,903 | 29,905 | 28,976 |
| Only in M1 | 29,120 | 256 | 2,944 | 61,184 |

   The 28,288 samples that only M0 marks (the part of its 512-sample windows beyond the flagged decisions) hold 3,903 present samples: 13.8% of that region is present output, against 0.9% for the region only M1 marks. The cost of the coarse grain sits there.
6. **Extended-middle.** M1 removes no present or wrong-pitch output and 79,270 gap-extra samples (43.316% of CURRENT's; M0: 79,078, 43.211%); the budget passes and aggregate pitch safety holds.

## Predictions (odds fixed before the run; P6, P7 and P8 had been revised once, before the commit)

Hits (the favoured side occurred) 6, misses 3 (P4, P5, P8), and P2 was a 50% call. Brier sum **1.709** over ten (a flat 50% scores 2.50). All three misses have one cause: I expected the finer mask to look more like the coarse one than it does.

| # | Odds | Outcome | Observed |
| ---: | ---: | --- | --- |
| P1 identity gate | 97% | hit | passed on both |
| P2 M1 gap-extra share at least M0's 41.945% | 50% | true | 42.835% |
| P3 M1 loses fewer present samples than 4,350 | 55% | hit | 703 |
| P4 at least 17 labels lose presence under M1 | 60% | **miss** | 3 |
| P5 label 31 within budget under M1 | 35% | **miss** (true, I gave it 35%) | 64 / 231 against 475.5 |
| P6 label 70 within budget under M1 | 1% | hit (false) | over budget |
| P7 M1 passes the frozen budget on ordinary | 1% | hit (false) | label 70 |
| P8 some label within budget under M0 is over under M1 | 60% | **miss** (false) | none |
| P9 extended-middle M1 passes | 85% | hit | passes |
| P10 at least 99% of the affected output is false | 70% | hit | 99.955% |

I expected the finer mask to add cuts inside sounding notes, since it flags 646 decisions outside every M0 run (about 127 of them the decisions just before M0 runs). It did not: its 703 removed present samples are 64 + 64 + 575, all in labels 31, 123 and 70, and no other label loses a sample.

## What this does and does not show

- **Shows:** at the detector's own decision grain the same existing cue removes the same share of the false output (gap 42.8%) with an order of magnitude less present loss, and the only frozen-budget failure left is a single label whose CURRENT presence is a 36 ms blip of a 748 ms annotation. The callback-grain mask was a coarser instrument than the output stage allows, and part of its rejection was the instrument: fourteen of its seventeen labels lose nothing at the decision grain, and label 31 drops from 679 lost samples to 64.
- **Does not show:** that the cue is acceptable. The pre-registered rule is CLOSED, label 70 fails the budget, and Codex's frozen verdict on its callback-grain mask stands. I am not proposing an exemption for label 70, a different budget, or a variant tuned to it; the budget is frozen.
- **Optimism, same as M0.** The old span resumes when the flag clears, and the cue acts at the earliest causal moment (`s + 1`). The detector's own path takes the cue into its 50 to 220 ms coasting hold rather than ending MIDI at once, and a note interrupted inside a sounding run would have to be re-acquired, so a real release would act later and cost more than 64 samples. An interruption inside a note, as in label 70, is also not a head delay (which the earlier decision, `2bf0e2a`, leaves without a limit of its own): it is the kind of loss the frozen per-label budget does limit. The diagnostic cannot see either cost.
- **Re-struck notes.** Nothing here helps the restart problem: the scalar restart routes stay closed on three measurements.
- **Data.** Two recordings, both seen by both analyses. The check was post hoc in motivation.

## Provenance

Inputs: pinned v5 traces (ordinary run 44835727027, raw sha256 prefix `b664c7ff0ce8`; extended-middle run 45062999189, `78929974b9cc`), Codex's rapid-mute JSON (`c2008b895622`), and the scoring modules named in the pre-registration. Annotated spans come from `label_deltas` (`annotated_samples`) in Codex's JSON. The script, the output and this note are the only changes; nothing of Codex's was edited.
