# Pre-registration: what false output the cropped-ONNX support filter leaves behind

Claude, 2026-11-22. Written and committed before the script is run (the commit time is the record). Nothing here is a result. Descriptive, saved data only; not a candidate.

## Why

The label budget stays as is (user, 2026-11-22), so the support filter cannot pass it on labels 263 and 364, and that line is closed unless confirmation gets faster. The open problem in `RESUME.md` is the false-output / held-note trade-off. The filter removes only about a fifth of CURRENT's wrong-pitch output (adapted, D = 220: 22.28%), and nobody has measured what the remaining output is. `CLAUDE-M3-SPLIT-FALSE-OUTPUT-ANATOMY-20261121.py` split CURRENT's own false output on ordinary into orphan notes (no label of that pitch overlaps), tails (after the last overlapping same-pitch label), heads and in-between: lower band (pitch below 60) 36.5% orphan, 58.1% tail, 2.7% head, 2.7% between, tail median 294.66 ms; upper band 45.9 / 33.4 / 20.7 / 0. I have seen those CURRENT numbers. I have **not** seen the same split applied to any filter's output.

## What will be run

`CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.py`, ordinary corpus only, emitted clock, D = 220, no grace, supports cropped adapted and cropped unmodified (the same hash-verified event members as the earlier results). The filter is exactly the committed one (support = model spans union the native confirmation, held forward 220 ms, filter = CURRENT intersect support); the script only classifies its output. Extended-middle (six labels, all MIDI 52) is not used.

## Definitions (fixed now)

- **CURRENT span:** CURRENT's spans unioned per pitch (touching spans merged), as in the earlier anatomy. Every filtered span lies inside exactly one CURRENT span (the script checks it), and a filtered sample takes the class of the CURRENT span it came from, so a filter that splits a span does not turn its tail into an orphan.
- **Classes of a CURRENT span:** *orphan* if no merged same-pitch label interval overlaps the span; otherwise with `first` and `last` the earliest start and latest end among the overlapping same-pitch labels: *head* = the part before `first`, *tail* = the part after `last`, *between* = the rest of the span inside [first, last) outside the labels. Time inside a label is present, not false.
- **False volume** of a class = output samples of that class (CURRENT's or the filter's); over all classes it equals the scorer's `extra_pitch_voice_samples` + `unlabeled_gap_voice_samples`. **Removal share** of a class = 1 − (filter's class volume / CURRENT's class volume).
- **Tail records:** for every CURRENT span with a tail, *kept tail volume* = filtered samples in [last, span end) and *kept extent* = the end of the last filtered sample in that region minus `last` (0 if none). A *surviving* tail has kept volume > 0. Extent and volume statistics (median, p10, p90, with the earlier anatomy's quantile convention) are over surviving tails; *removed entirely* = the share of CURRENT tail spans with no kept tail volume.
- **Oracle bounds (labelled, not implementable; they use the labels):** *tail cut* removes every tail sample, *orphan cut* removes every orphan span, *both*. By construction no present sample is removed (a tail lies outside every same-pitch label; an orphan overlaps none), so precision = present / (present + false remaining). They size the headroom of a perfect release detector, a perfect false-note detector, or both.
- **Also reported, no predictions:** the split of each class into false output under another label (extra) and in no label (gap); surviving orphan counts; everything by band (pitch below 60, 60 and above, all).

## Identity checks (must all pass or nothing is reported)

1. CURRENT's classification reproduces the committed `CLAUDE-M3-SPLIT-FALSE-OUTPUT-ANATOMY-20261121.json` (ordinary, both bands, every field including span counts and tail quantiles).
2. For CURRENT and for each filter, the class volumes sum to the scorer's extra + gap, extra and gap separately agree, and present equals the scorer's present.
3. The two D = 220 filter rows (coverage, precision, wrong-removed share, gap delta) and the two event-file hashes equal the committed `CLAUDE-M3-ONNX-SUPPORT-20261122.json`.

A `--selftest` flag runs checks 1 and 2 for CURRENT only, with no event file opened, to catch plumbing errors before the real run.

## Predictions, each can fail (cropped adapted unless stated; "all" = both bands summed)

| Id | Claim | Odds |
|---|---|---:|
| R0 | All identity checks pass | 97% |
| R1 | All: the filter removes a larger share of CURRENT's orphan volume than of its tail volume | 75% |
| R2 | All: tail removal is under 15% of CURRENT's tail volume (the model's own note-off lag plus the 220 ms hold keep the support past the end) | 65% |
| R3 | All: orphan removal is between 25% and 50% of CURRENT's orphan volume | 55% |
| R4 | Lower band: tails are more than 50% of the filter's remaining false output | 70% |
| R5 | Lower band: the median kept extent of surviving tails is at least 200 ms | 60% |
| R6 | All: the tail-cut oracle lifts the filter's precision by at least 10 points (about 59.1% now) | 70% |
| R7 | Lower band: cropped unmodified and cropped adapted differ by less than 3 points in the tail share of remaining false output | 80% |
| R8 | All: the orphan-cut oracle lifts the filter's precision by less than the tail-cut oracle does | 80% |

## Reading rule (fixed now)

The largest class of the adapted filter's remaining false output (all) names the lever: tail means held-note overhang that a support hold does not remove and the largest false-output lever is a release cue; orphan means false notes the support confirms and the lever is on the detection side; head or between means neither, and the report says so. R1 to R3 say what the filter does to each class, whatever the largest class is. The oracle numbers are headroom, not a result: they use labels.

## What cannot be concluded

One recording (ordinary only). Saved spans with the support on the emitted clock; no lane, string, unison or MIDI-lifecycle claim; no audio or live behaviour. The oracles use the labels and show what a perfect detector could remove, not what any detector can. Nothing is promoted and no gate changes.
