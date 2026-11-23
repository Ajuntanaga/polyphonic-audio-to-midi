# Pre-registration: how much of CURRENT's per-label presence is carried over from an earlier span?

Claude, 2026-11-22. Saved data only: no audio, model run, job, native edit, promotion or download. Script `CLAUDE-M3-CARRY-OVER-CREDIT-CENSUS-20261122.py` (sha256 prefix `37cb36ca6314`, 15,580 bytes), committed with this note before its one `--run`. The check is **post hoc in motivation** and **descriptive**: it has no verdict, no threshold that decides anything, and nothing here is a candidate, a budget change, a gate change or an exemption.

## Question

Under the frozen label budget the rapid-mute mask fails on label 31 at the callback grain and on label 70 at both grains (`CLAUDE-M3-DECISION-GRAIN-MASK-RESULT-20261122.md`). Both labels have a CURRENT presence that is the *end of a long CURRENT span that began before the label*: the boundary census JSON gives, for label 31, span [414,847, 499,327) against a label start of 489,817 (499,327 - 489,817 = 9,510 = its CURRENT present samples) and, for label 70, span [1,068,479, 1,227,711) against a start of 1,224,217 (1,227,711 - 1,224,217 = 3,494 = its CURRENT present samples). Label 123 (which loses 64 samples at the decision grain) sits in span [2,125,823, 2,305,087) against a start of 2,203,417 and its CURRENT presence is all 71,783 samples. For label 70 the span began during the preceding same-pitch label (62, 1,061,039 to 1,132,800) and bridged the 91,417-sample (952 ms) gap to the re-strike. So the presence that the mask cuts in those labels is not the detector's response to the label's own onset.

Is that a property of those three labels, or how much of CURRENT's presence credit overall is carried over this way? This also closes the item I left open in `CLAUDE-M3-WRONG-NOTE-CENSUS-20261121.md` and `CLAUDE-M3-STREAMING-ASSESSMENT-20261121.md` ("a note carried over from a preceding same-pitch label reads as an early or zero delay"), for the credit side.

## Definitions (identical in the script)

Spans are the per-pitch unions of CURRENT's spans (`fr.by_pitch`, 528 on the ordinary recording, 14 on extended-middle: the occupancy runs of Codex's JSON). A label is (pitch, start `a`, end `b`).

- **present** = the CURRENT span samples of the label's pitch inside [a, b); the identity gate is that this equals Codex's `current_present_samples` for every label on both recordings.
- **fresh** = present samples whose span begins at or after `a - TOL`: the span can be the detector's response to this label. **carried** = present samples whose span began before `a - TOL`: the pitch was already sounding.
  - **bridged** = a carried span whose pre-label part [l, a) overlaps an earlier same-pitch label (ring-over between two notes of one pitch); **head** = a carried span that does not (it began in unlabeled time or under other pitches' labels).
- Label class: **missed** (no present), **fresh_only**, **carried_only** (every present sample is carried), **mixed**.
- TOL = 2,400 samples (25 ms, the frozen budget's present-time limit and the census window) is primary, because a span that began more than 25 ms before the label cannot be a response to it. TOL = 0 is a sensitivity.
- The partition present = fresh + bridged + head is exact by construction and is also a gate.

## Seen before this note

- The census JSON's span fields for labels 31, 70, 123 (above) and the previous same-pitch labels of those three (label 24 ends 9,817 samples before label 31; label 62 ends 91,417 before label 70; label 123's nearest earlier same-pitch label ends 989,017 samples before it, so its span did not come from a same-pitch note).
- My decision-grain JSON's label rows (the 17 labels that lose presence under M0, their M0 and M1 losses) and Codex's rapid-mute JSON.
- `--selftest` (nine synthetic unit checks plus the identity gates on both recordings: booleans only) and `--dry` (label and span counts: 499 labels, 528 spans, 32 pitches on the ordinary recording; 6 labels, 14 spans, 4 pitches on extended-middle). **No class count, no carried volume and no share has been computed or printed.**

Known before the run and therefore not scored: labels 31, 70 and 123 are carried (the three arithmetic facts above). A run that does not classify them so would indicate a bug.

## Predictions (odds that the statement is true, fixed before the run; ordinary recording, TOL = 2,400 unless stated)

| # | Statement | Odds |
| ---: | --- | ---: |
| P1 | Identity gates pass on both recordings (per-label present equals Codex's, run counts equal, partition exact) | 97% |
| P2 | At least 20 of the 499 labels are carried_only | 55% |
| P3 | Carried presence (bridged + head) is at least 5% of the total present volume | 50% |
| P4 | At least 4 of the 5 labels the rejected native joint reset lost whole (42, 70, 200, 306, 364) are carried_only | 65% |
| P5 | At least 60% of carried presence is bridged (the rest head) | 55% |
| P6 | The median bridge gap (label start minus the end of the earlier same-pitch label the span covers) is under 220 ms (21,120 samples, the detector's longest coasting hold) | 50% |
| P7 | At least half of M0's 4,350 removed present samples come out of carried_only labels | 40% |
| P8 | Carried presence is under 3.0% of the annotated sample time (equivalently, fresh coverage is within 3 pp of CURRENT's coverage) | 70% |

Scoring: Brier per statement (a flat 50% over eight scores 2.00); hits counted only for calls other than 50%. The extended-middle recording (6 labels) is reported without predictions.

## Reading rule

There is none that decides anything; this is a census. I will report the class counts, the carried share, the join with M0 and M1 losses and the whole-lost labels, and say plainly what they do and do not establish. The result will not be used to propose an exemption for any label, a change to the frozen budget, or a variant of the rapid-mute mask: the mask thread is closed, and any use of "fresh" credit as a metric would need Codex's agreement and its own registration on data these two recordings do not provide.

## What this cannot show

- **Cause.** A bridged span means CURRENT's output for that pitch was continuous from one note into the next; this census cannot tell whether the string physically kept ringing (real evidence the detector followed) or the detector's hold carried a stale pitch. The 220 ms coasting-hold limit (P6) gives a hint, not a test: a span that bridges more than the hold needs continuing evidence.
- **Anything about audio, onsets or phase.** Spans and labels only.
- **Transfer.** Two recordings, one of them six labels; both are already-seen design data.
- **A fresh-detection rate.** "Fresh" here means a span began at or after the label's start; it does not say the span's pitch evidence was the label's own (a head-origin span that began 25 ms before the label counts as fresh at the primary TOL).
