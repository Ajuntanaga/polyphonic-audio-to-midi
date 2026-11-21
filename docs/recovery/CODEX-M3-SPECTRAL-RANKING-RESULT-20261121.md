# Saved spectral ranking result: cutoff-only repair cannot pass

The rejected ablation screen has both a score-scale problem and a pitch-ordering
problem. Changing its shared cutoff cannot reach the complete-chord gates, even
on training. The rejection and installed tracker remain unchanged.

This diagnosis ran once on the saved training arrays from GitHub run
44953542438, source `6bfd3af5b47c9023d177f0396a0873ff03cfe595`. No audio,
model inference, fitting, replacement cutoff, held-out scoring or new job was
performed. The analysis plan was written before opening the arrays.

## Direct checks

The 5,029,034-byte evidence artifact 14726114992 was collected once and matched
the recorded server SHA256
`85e1269bafbf992764a47fbd5bfa89d998dd1cda900f92e3f506a892993d5893`.
Only training predictions and the mixture plan were extracted; the model stays
unopened in the archive. Both extracted member hashes match the small report.

All 4,096 examples, 53 pitch columns, 200 training source keys, source-use counts
and plan targets agree. The original cutoff 0.8386819553485484 reproduces exactly:
3,625 true pitches, 36 false pitches, 7,864 missed pitches and 951 complete sets,
including all per-polyphony counts. Five synthetic checks passed, covering
ordering, exact ties, silence, unisons and role/target mismatch rejection.

## What the ordering permits

A mixture is strictly separable only when its weakest expected pitch scores
above its strongest unexpected pitch. This gives an **oracle upper bound** for
any scalar threshold on these saved scores, even one chosen separately using the
true answer for each mixture. It is not an implemented detector or a gain.

| Distinct pitches | Complete at frozen cutoff | Oracle strict separation | Complete-set target |
| --- | ---: | ---: | ---: |
| 1 | 580/775 (74.84%) | 745/775 (96.13%) | Not separately specified |
| 2 | 140/793 (17.65%) | 523/793 (65.95%) | Not separately specified |
| 3 | 24/799 (3.00%) | 267/799 (33.42%) | 70% |
| 4 | 2/889 (0.22%) | 154/889 (17.32%) | 70% |
| 5 | 0/635 (0%) | 40/635 (6.30%) | 70% |

Among 3,891 nonsilent mixtures, 1,729 are strictly separable, 486 tie and 1,676
put a false pitch above the weakest true pitch. Including the 205 silent
examples, the oracle complete-set ceiling is 1,934/4,096 (47.22%), still below
the 70% overall gate. Tied scores cannot isolate a complete set by a threshold.

The cutoff nevertheless discards useful ordering: 983 strictly separable
mixtures are incomplete at the frozen cutoff. Of the 7,864 missed pitches,
4,182 (53.18%) beat every false pitch in their mixture; 695 tie and 2,987 rank
below the strongest false pitch. Exactly 2,956 misses (37.59%) have zero saved
activity. These populations overlap; zero activity is a score result, not proof
that the source pitch was inaudible or absent.

## Scheduled level dependence

For pitches supplied by one component, ordered from strongest scheduled level
to weakest:

| Relative scheduled gain | Found at frozen cutoff | Above every false pitch |
| --- | ---: | ---: |
| 0 dB | 3,012/4,849 (62.12%) | 4,516/4,849 (93.13%) |
| -6 dB | 407/2,005 (20.30%) | 1,509/2,005 (75.26%) |
| -12 dB | 55/1,830 (3.01%) | 942/1,830 (51.48%) |
| -18 dB | 1/1,536 (0.07%) | 436/1,536 (28.39%) |
| -24 dB | 0/935 (0%) | 134/935 (14.33%) |

Scheduled gain follows normalization of the source crops; it is not measured
mixture power. Duplicate-pitch components can interfere coherently. All 332
mixtures containing duplicate pitches remain in the main counts; the full
report also separates that group. These are descriptive training strata,
confounded by pitch, source and polyphony, not a causal level experiment.

## Decision and next implementation constraint

Close cutoff tuning for this saved score. A new candidate needs different
evidence that improves the ordering of weak genuine pitches against false
competitors. The next design should test pitch-local residual evidence rather
than another cutoff on the same activity; it must also explain zero-activity
targets. This is a design direction, not an approved result or dispatched job.

Retain all original labels and source-content disclosures. Before any continuous
replay, require training precision >=99%, recall >=80%, and complete sets >=70%
overall and separately for 3/4/5 pitches, followed by the existing held-out
gates. Corpus per-label, false-output, lifecycle, allocation, deadline and live
device gates still apply. Training score ordering does not establish note/string
matches, MIDI delivery or live readiness. Claude is paused; no new Claude review
is claimed.

Full local report: `build/recovery/m3-spectral-ranking-20261121/report.json`;
per-example and per-pitch rows: `details.json.gz` in that directory. Compact
published summary: `docs/recovery/spectral-ranking-summary-20261121.json`.
