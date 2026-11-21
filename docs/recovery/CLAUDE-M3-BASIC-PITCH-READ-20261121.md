# Claude: independent read of the Basic Pitch comparison (run 44884737134) — 2026-11-21

Source: only the collected `report.json` (`m3_basic_pitch_comparison_v1`, state completed, installed_output_changed false, promotion false). Script and output: `CLAUDE-M3-BASIC-PITCH-READ-20261121.py/.json` (predeclared in the docstring, run once; the saved-CURRENT figures it reconstructs from the report's own deltas match the frozen baseline exactly: 13,525,345 present, 7,808,309 extra, 3,629,163 gap, 53,249 all-expected). No audio, no download, no dispatch. Pitch only, one corpus, one run, offline whole-file inference. Basic Pitch says nothing about string identity, unisons, onset timing, latency or the host.

## 1. Which clause failed

Every aggregate clause of the frozen rule passes on both datasets. Only the per-label clause fails, and only on ordinary.

| Ordinary clause | Result |
| --- | --- |
| coverage gain ≥ +5 pp | **+27.52 pp** (39.99% → 67.51%) |
| extra pitch-samples during labels | −5,388,708 (7.81M → 2.42M) |
| gap extras | −2,191,650 (3.63M → 1.44M) |
| exact pitch-set duration | +1,888,117 (0.60% → 21.78% of annotated) |
| all-expected duration | +2,225,370 |
| no label loses present or longest hold | **fails: 99 of 499 labels lose present duration, 96 lose longest hold** |

Extended-middle (the note-52 false-upper-note control) passes every clause: no label lost, extras −289,620, gap −156,321, exact set 73.15% → 88.44%, coverage 97.49% → 99.95% (+2.46 pp, which is below +5 only because CURRENT was already at 97.5%; the +5 pp clause is ordinary-only).

## 2. The losses: what they are

- 99 labels lose 2,343,938 present samples (24.4 s); 321 labels gain 11,649,719; 79 are unchanged.
- 33 of the 99 go to exactly zero (Basic Pitch never produced that pitch there), and those 33 are 71.3% of the loss (1,671,346 samples). The rest are partial: median loss 15% of the label, 27 under 5%.
- By band (CURRENT coverage → Basic Pitch coverage of annotated samples, labels losing):

| Band | CURRENT | Basic Pitch | Labels losing |
| --- | ---: | ---: | ---: |
| below 48 | 70.0% | 71.1% | 57 of 139 |
| 48–59 | 63.9% | 66.8% | 40 of 147 |
| 60–71 | **5.8%** | **65.6%** | 2 of 135 |
| 72+ | **0.0%** | **65.6%** | 0 of 78 |

  Below 60 the two detectors have almost the same total coverage but find different labels (each wins and loses about equally: below 48 −1.27M / +1.38M, 48–59 −1.02M / +1.32M). In four-semitone bins the per-note losses cluster at 40–51 (26 + 22 + 15 of the 99), where CURRENT is slightly ahead in aggregate. Above 60 Basic Pitch recovers 8.96M samples (5.62M at 60–71, 3.34M at 72+) and loses 47k.
- Losses do not track polyphony: about 20% of labels lose at every density (21%, 21%, 20%, 19% for 2, 3, 4, 5 pitches).

## 3. Polyphony

| Pitches in the interval | Labels | CURRENT coverage | Basic Pitch coverage | Intervals with any all-expected time |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 34 | 45.1% | 80.4% | 15 of 17 |
| 3 | 108 | 41.2% | 72.6% | 18 of 36 |
| 4 | 132 | 40.1% | 71.2% | 14 of 33 |
| 5 | 225 | 38.5% | 60.7% | **2 of 45** |

Basic Pitch degrades with chord size (80% → 61%; 67 of the 225 five-pitch labels get zero) while CURRENT declines more gently (45% → 38%). A full five-note chord is almost never produced by Basic Pitch; it is not a solution to the four- and five-note case.

## 4. The report-only union (never part of the verdict)

| Ordinary | Expected present | Extra during labels | Gap extras |
| --- | ---: | ---: | ---: |
| CURRENT | 13.53M | 7.81M | 3.63M |
| Basic Pitch | 22.83M | 2.42M | 1.44M |
| Union | 25.63M | 9.32M | 4.45M |

What CURRENT adds over Basic Pitch is 2.80M genuine pitch-samples with 6.90M extra and 3.01M more gap extras: **29% genuine** (pitch-sample share, my arithmetic from two report fields; not frames). Whole-corpus pitch-sample share during labels: Basic Pitch 90.4%, CURRENT 63.4%, union 73.3%. Union exact pitch-set duration is 13.35%, below Basic Pitch alone (21.78%), because CURRENT's extras break exact sets. Extended-middle: the union adds 0 genuine and 309k extra over Basic Pitch.

So a blind union is a poor fusion, and CURRENT's contribution is mostly the extras the rest of this work has been trying to remove. The union is also the only configuration that cannot lose a label by construction; the 99 losses and the 2.80M are the same material seen from two sides.

## 5. What I think this shows

1. **The upper register is not missing from the recordings.** An independent model on the same audio places 65.6% of the 60–71 and 72+ annotated time (CURRENT: 5.8% and 0%), at 90% pitch-sample share overall. So the evidence for upper notes exists; CURRENT does not use it.
2. **This is a pitch result, not a lane result.** It does not touch the persistent 61.5% / 40%-by-run lane accuracy or the higher-string-index lean measured earlier. Both blockers stand: pitch evidence above 60 (this result) and string assignment (earlier).
3. **Not a drop-in.** It fails the frozen rule on a real mechanism (about one label in five loses time, a third of those outright), is offline, uses lookahead (Melodia) and a 127.7 ms minimum note, and drops with chord size. These are properties of the comparator, so I read the useful question as "what is it seeing at 60+ that CURRENT's candidate stage does not", not "should it be integrated".
4. **Whether CURRENT lacks the evidence or discards it: answered in section 7.** (I first framed this as a tension with my earlier "about 66% of missing ≥60 genuine frames are not serialized" (`CLAUDE-M3-GOAL-REPLY-20261120.md`). That figure came from the saved trace's inclusion filter, which drops candidates with score/threshold < 0.20, no direct peak, or no local peak/evidence; it never meant "absent from the detector". The unfiltered v5 table keeps those rows, so section 7 supersedes the framing, with the weakness caveat stated there.)

## 6. Requests and limits

- No new run is needed to read this, and none is requested. The one open question (5.4) was answered by a single predeclared per-label join of this report and the saved v5 table, in my own files: section 7.
- Optional, your call: the 448-event `ordinary-notes.json` is small; if the remote bulk artifact can supply it alone, a frame-level join of Basic Pitch note events against CURRENT's rendered pitches would say which of the 33 zeroed labels CURRENT genuinely hears. I have not downloaded anything.
- Not verified: anything about string identity or live behaviour; whether Basic Pitch's lookahead accounts for part of its upper-register coverage; whether CURRENT's 60+ loss would persist under the installed host's settings.
- I did not re-score anything; if any figure above disagrees with the JSON, the JSON wins.

## 7. Where CURRENT stands on the notes Basic Pitch hears (per-label join)

Script and output: `CLAUDE-M3-BASIC-PITCH-STATE-JOIN-20261121.py/.json` (predeclared in the docstring, run once, saved v5 table `ordinary-current-on-512-outcome-v5.tsv.gz` plus this report; no audio, no download, no dispatch). Join is per label only: the report has Basic Pitch's present duration per label and no frame timing, so no tick-level alignment is claimed. All 499 labels matched the table by (id, note); Pearson r between the table's per-label rendered share and the report's CURRENT coverage is 0.96. State names and groupings are the frozen contract's `classify` (Codex's definitions; I did not re-derive the stage mapping here). Same-note labels in a tick (unisons) each count the same rendered note.

Population: 213 labels at notes 60–84; 204 of them (96%) are blind in CURRENT (coverage under 10%). Strata by Basic Pitch coverage of the label: HIGH ≥ 50%, MID, ZERO (Basic Pitch also misses it).

| Stratum (blind labels) | Labels | Ticks | Rendered | Share of non-rendered ticks: no usable evidence | observed, not rendered |
| --- | ---: | ---: | ---: | ---: | ---: |
| HIGH (Basic Pitch covers ≥ 50%; mean coverage 88.5%) | 140 | 148,014 | 1.2% | **2.9%** (all `quiet`) | **97.1%** |
| MID | 18 | 19,692 | 1.4% | 2.5% | 97.5% |
| ZERO (both miss) | 46 | 47,376 | 0.01% | 1.2% | 98.8% |
| Control: CURRENT hears (≥ 50%) | 9 | 10,099 | 85.6% | 0.8% | 99.2% |

Median per-label fraction of ticks with energy observed is 1.0 in every stratum, and `unobserved` and `unavailable` are absent from all of them. Under the fixed reading rule the HIGH stratum is "after observation": CURRENT's own table has observed energy for the pitches Basic Pitch hears and then does not render them. "Observed" here means the detector evaluated that pitch on that tick and a row exists; it does not mean the candidate scored near its admission threshold (`classify` calls a row `formed` if any of the direct, local or evidence flags is set, whatever the score). Both bands read the same way (60–71: 2.2% no evidence; 72–84: 4.0%).

Within the 97% the states differ by stratum (share of non-rendered ticks):

| State | HIGH | ZERO | Control |
| --- | ---: | ---: | ---: |
| admission (formed, not admitted) | 72.4% | 45.6% | 17.1% |
| dp | 16.7% | 3.2% | 38.7% |
| formation (candidate never formed) | 5.5% | **50.0%** | 36.4% |
| spectral / selected_not_rendered / quiet | 2.3% / 0.2% / 2.9% | 0.0% / 0.0% / 1.2% | 0.3% / 6.7% / 0.8% |

So where Basic Pitch also hears the note, CURRENT has usually formed a candidate and holds it back after admission (formation misses are only 5.5%); where Basic Pitch hears nothing, half the CURRENT misses are candidates that never formed. This is a descriptive difference between strata, not a cause.

What it says, and what it does not:
1. For the labels Basic Pitch covers, CURRENT's front end does evaluate those pitches (energy observed on essentially every tick, a row present in 97% of the non-rendered ticks), so "the detector never looks at the upper register" is not supported; the non-rendered ticks are mainly in `admission` (a candidate row exists, flags set, not selected), then `dp`. This does not show those candidates are strong: the rows the old trace filter dropped (the earlier "not serialized about 66%") are in this table, and by `classify`'s rule can only land in `admission` (a direct, local or evidence flag set) or `formation` (none set); I did not check which. It agrees with the earlier penalty finding and does not contradict the relief screen's recovery. The 66% figure was a statement about the trace filter and should not be quoted as "unobserved by the detector".
2. Basic Pitch's per-label coverage is a second, independent indication that those notes are really present, which the annotation alone does not give for audibility. It cannot say which ticks within a label, and the join is one dataset and one block.
3. It does not touch string assignment. The lane problem (61.5% tick accuracy, about 40% of runs) stands, and the relief screen's wrong-string growth is still the cost of recovering these notes.
4. What I did not test (and the check that would separate "strong candidate held back" from "weak candidate correctly ignored"): the score/threshold ratio of the HIGH-label `admission` rows, which the v5 table should carry; and whether admission scores of HIGH-label candidates separate from the false-note candidates the rule must keep out (gap and wrong-note frames), which is the question a promotion rule would need; my earlier family of scalars did not find a clean one, and Basic Pitch coverage per label is too coarse to relabel frames.
