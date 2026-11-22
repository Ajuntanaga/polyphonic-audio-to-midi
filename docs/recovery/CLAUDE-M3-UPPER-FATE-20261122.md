# CLAUDE-M3: the upper register, and what the native confirmation alone buys at 60 and above (2026-11-22)

Saved data only: the saved v5 trace and saved spans. No audio, no model run, no job, no native edit, nothing promoted or installed.
Three scripts, each with its predictions written before it ran (failed ones are reported as failed):

- `CLAUDE-M3-UPPER-FATE-20261122.py` / `.json` — where the labelled upper notes are lost inside the native selection chain (F0–F8).
- `CLAUDE-M3-NATIVE-ONLY-UNION-20261122.py` / `.json` — CURRENT ∪ the native confirmation alone, scored with the project's own `score`/`compare` (N0–N6).
- `CLAUDE-M3-NATIVE-ADDITION-CODES-20261122.py` / `.json` — which trace dispositions those native additions carry (G0–G7).

Scope: ordinary corpus, 512-sample callbacks, one recording, in-sample, descriptive counts. Unit differences matter below: the union
numbers are pitch-samples from the span score; the census numbers are 64-sample decision ticks.

## Answers first

1. **At 72+ the loss is weak native evidence, not selection and not the DP.** 96.55% of the non-quiet true ticks sit at `below_threshold`; 71 of 78 labels never get past it; 6 reach `selected`; CURRENT emits 0 of 78. The true candidates are present in the candidate list (F0) but their scores are tiny (median `score_ratio` 0.018; per-label best median 0.129; 11 of 78 labels ever reach 0.5; the last two figures are post-hoc, see section 1).
2. **No single trace feature recovers 72+ at a usable error rate.** Best AUC between rejected true and rejected ghost candidates is 0.862 (`band_score`), but its operating points are degenerate (ties at 1.0); the best non-degenerate feature (`score_energy`) recovers 6.6% of true ticks at a 1% ghost rate (4,989 true vs 2,101 ghost) and 0.02% at 0.1%. This agrees with the earlier lower-register finding: a threshold tweak is not a lever.
3. **At 60–71 the dominant fixable disposition is the DP.** 17.9% of non-quiet true ticks are `dp_evicted` (73.0% are `below_threshold`, 6.0% selected). Among native-confirmed candidates that CURRENT does not emit at 60–71, **93.7% of the true ticks are `dp_evicted`**, and tick precision is 92.4% (27,352 true, 1,646 tail, 599 ghost).
4. **The native confirmation alone buys most of the consensus gain at 60 and above.** CURRENT ∪ native confirmation at pitch ≥ 60: coverage 39.99% → 45.29% (+5.29 pp), precision 54.2% → 56.94%, +1,789,705 genuine, +153,262 false pitch-samples (+1.34% of CURRENT's false), exact-set +243,781, no label loses presence or longest hold. The consensus (arm A ∩ native) adds 1,603,682 genuine and 126,641 false at ≥ 60: the neural arm keeps 89.6% of the native genuine and 82.6% of the native false, i.e. **it filters almost nothing at ≥ 60**.
5. **The neural arm does filter below 60.** At 48–59 the native confirmation alone adds 593,694 genuine against 286,585 false (32.6% false share); the consensus keeps 155,900 against 21,247 (12.0%). Below 48 it is 52.1% false share native-only against 29.3% consensus. A native-only lever would therefore stop at 60 (or at 48 with a 15.6% false share, +2,383,399 genuine, precision 57.27%).
6. **What native-only ≥ 60 cannot do:** it recovers label presence for few of the never-emitted labels. Of 126 never-emitted 60–71 labels, 37 get ≥ 10 confirmed true ticks and 34 get ≥ 100; of 78 at 72+, 4 get ≥ 10. It extends held notes more than it creates new ones (the 9 emitted 60–71 labels, 8 of them with ≥ 10 extra ticks).
7. **It fails the strict gate by construction**, like every additive hybrid: wrong-pitch +42,493 and gap +110,769 pitch-samples. 99.6% of that gap is a same-pitch tail within 220 ms of a label end (55.1% within 50 ms); 80.7% of the wrong-pitch is an octave above a label. Nothing else regresses (no label loses, exact-set +243,781, all-expected +385,158).
8. **This sharpens the gate question; it does not answer it.** See the end. Codex's gates are frozen and I have not changed them.

## Predictions

| id | prediction | outcome |
|---|---|---|
| F0 | label pitch is in the candidate list at ≥ 95% of non-quiet true ticks, every band | **pass** (100% in all three bands) |
| F1 | 72+: < 10% of non-quiet true ticks carry code 4 or 5 | **pass** (1.11%) |
| F2 | 72+: code 1 is the most frequent | **pass** (96.55%) |
| F3 | 72+: code 3 under 20% | **pass** (1.11%) |
| F4 | 72+: best rejected true-vs-ghost AUC above 0.90 | **FAILED** (0.862) |
| F5 | that AUC exceeds the 60–71 best by ≥ 0.03 | **pass** (0.862 vs 0.812) |
| F6 | fewer than 20 of 78 labels at 72+ reach code 4 or 5 | **pass** (6) |
| F7 | quiet share of true ticks at 72+ within 5 points of 60–71 | **pass** (3.35% vs 1.81%) |
| F8 | best 72+ feature at ghost FPR ≤ 1%: recovered true outnumber admitted ghost | **indeterminate**: the best-AUC feature (`band_score`) has degenerate operating points (0 recovered, 0 admitted); the best non-degenerate feature does outnumber at 1% (4,989 vs 2,101) but not at 0.1% (17 vs 211) |
| N0 | native-only additions contain the consensus additions | **pass** (3,679,986 ≥ 2,211,863 genuine; 1,849,243 ≥ 335,235 false) |
| N1 | native-only added genuine between 2.4M and 4.0M | **pass** (3,679,986) |
| N2 | native-only added false share between 10% and 25% | **FAILED** for the literal (all-pitch) variant: 33.4%. Post-hoc, not a pass: ≥ 48 is 15.6%, ≥ 60 is 7.9% |
| N3 | native-only additions that arm A does not report have a higher false share than the consensus' 13.16% | **pass** (50.8%) |
| N4 | native-only at ≥ 60: fewer than 0.20 false per added genuine | **pass** (0.0856) |
| N5 | native-only fails the strict gate only on the wrong-pitch / gap clauses | **pass** (all three native variants) |
| N6 | native-only raises precision above CURRENT's 54.2% | **pass** (56.44% all; 57.27% ≥ 48; 56.94% ≥ 60) |
| G0 | confirmed ticks exist at 60+, every confirmed candidate carries a code in 1..5 | **pass** (0 bad rows) |
| G1 | 60–71 confirmed true not-emitted: dp_evicted largest, ≥ 50% | **pass** (93.69%) |
| G2 | 60–71 tick precision ≥ 85% | **pass** (92.41%) |
| G3 | code 1 < 20% of confirmed true not-emitted at 60–71 | **pass**, trivially: confirmed candidates carry only codes 3, 4, 5 |
| G4 | tail share of non-true confirmed not-emitted ticks at 60+ exceeds 50% | **pass** (73.0%) |
| G5 | codes 4 + 5 < 25% of confirmed true not-emitted at 60–71 | **pass** (6.3%) |
| G6 | 72+ confirmed true not-emitted ticks < 5% of the 60–71 count | **pass** (773 vs 27,352, 2.8%) |
| G7 | ≥ 40% of the never-emitted 60+ labels have ≥ 10 confirmed true ticks | **FAILED** (41 of 204, 20.1%) |

## 1. Where the upper notes are lost (non-quiet true ticks, by trace code)

| band | labels | true ticks | below_threshold | spectral_rejected | dp_evicted | selected | coasting | labels reaching selected/coasting | labels CURRENT emits |
|---|---|---|---|---|---|---|---|---|---|
| 48–59 (reference) | 147 | 153,998 | 27.6% | 0.8% | 0.2% | 66.6% | 4.9% | 129 | 108 |
| 60–71 | 135 | 145,670 | 73.0% | 1.9% | **17.9%** | 6.0% | 1.1% | 17 | 9 |
| 72+ | 78 | 79,511 | **96.6%** | 1.2% | 1.1% | 1.1% | 0.0% | 6 | 0 |

Quiet ticks (no candidate decision) are 1.6% / 1.8% / 3.4% of true ticks. Per-label best stage at 60–71: 72 never beyond below_threshold, 5 spectral_rejected, 41 dp_evicted, 17 selected. At 72+: 71 below_threshold, 1 dp_evicted, 6 selected.

Ghost candidates (no label of that pitch active and none ended within 1.5 s) are also overwhelmingly `below_threshold` (96.2% at 60–71, 99.3% at 72+), so the codes alone do not separate them.

Separation of rejected true from rejected ghost candidates (codes 1–3; AUC, then the true share recovered at a 1% ghost false-positive rate):

| band | n true / n ghost | best AUC (feature) | best non-degenerate at 1% FPR |
|---|---|---|---|
| 48–59 | 43,196 / 116,539 | 0.671 (score_ratio) | 6.7% (score_ratio); `fund_energy` 11.4% |
| 60–71 | 132,819 / 130,480 | 0.812 (score_ratio) | 20.5% (score_ratio) |
| 72+ | 75,990 / 210,040 | 0.862 (band_score, degenerate cut) | 6.6% (score_energy) |

Post-hoc (added after the first run's census and separation tables had been read; labelled as such): at 72+ the per-label best `score_ratio` has median 0.129 and 90th percentile 0.646; labels with best ≥ 0.5: 11 of 78, ≥ 1.0: 2 of 78. At 60–71: median 0.749, 83 of 135 labels ≥ 0.5, 61 ≥ 1.0 — yet only 17 reach selected/coasting, so a `score_ratio` of 1.0 is **not** by itself the pass level; other conditions apply, and the threshold position is not established here.

## 2. CURRENT ∪ native confirmation alone (ordinary@512)

CURRENT: coverage 39.9932%, precision 54.2%, false 11,429,794 (wrong 7,808,309 + gap 3,621,485). The identity check against the frozen consensus report passes. "Native confirmation" is the saved span set Codex's consensus tool builds from `not quiet and selector_pool_member == 1 and direct == 1`, projected to completed 512-sample callbacks (latest observation per callback, one block, no coasting).

| hybrid | coverage | precision | +genuine | +wrong | +gap | false Δ vs CURRENT | false share of additions | false per genuine | exact-set Δ | labels losing |
|---|---|---|---|---|---|---|---|---|---|---|
| CURRENT ∪ native, all pitches | 50.87% | 56.44% | 3,679,986 | 1,547,778 | 301,465 | +16.18% | 33.4% | 0.503 | +231,876 | 0 |
| CURRENT ∪ native ≥ 48 | 47.04% | 57.27% | 2,383,399 | 304,565 | 135,282 | +3.85% | 15.6% | 0.185 | +243,781 | 0 |
| **CURRENT ∪ native ≥ 60** | **45.29%** | **56.94%** | **1,789,705** | **42,493** | **110,769** | **+1.34%** | **7.9%** | **0.086** | +243,781 | 0 |
| consensus (arm A ∩ native), frozen | 46.53% | 57.22% | 2,211,863 | 152,166 | 183,069 | +2.93% | 13.2% | 0.152 | +243,781 | 0 |
| (reference) CURRENT ∪ arm A ≥ 60 | 63.32% | 62.37% | 7,890,137 | 412,661 | 1,079,705 | +13.06% | 15.9% | 0.189 | — | 0 |

Native ≥ 60 reaches 22.7% of the arm-A ≥ 60 union's genuine gain for 10.3% of its false. Arm A is what supplies the rest: the slice of A at ≥ 60 that the consensus does not take is 6,286,455 genuine at a 17.9% false share (earlier note; that slice is relative to the consensus, not to native-only).

False share of additions, by pitch band:

| band | native alone | consensus |
|---|---|---|
| below 48 | 52.1% (1,296,587 genuine / 1,409,396 false) | 29.3% (452,281 / 187,347) |
| 48–59 | 32.6% (593,694 / 286,585) | 12.0% (155,900 / 21,247) |
| 60–71 | 7.9% (1,742,281 / 149,998) | 7.4% (1,556,258 / 123,377) |
| 72+ | 6.4% (47,424 / 3,264) | 6.4% (47,424 / 3,264) |

Native additions that arm A does not report (all pitches): 1,468,123 genuine against 1,514,008 false (50.8%): 48–59 37.7%, 60–71 12.5%, below 48 59.1%.

Anatomy of the native ≥ 60 false (153,262 pitch-samples): 72.3% is gap (110,769), 27.7% wrong-pitch (42,493). The gap is 99.6% tail, 0.4% head, 0% orphan; within 20 / 50 / 100 / 220 ms of a same-pitch label end: 43.1% / 55.1% / 59.7% / 99.6%. The wrong-pitch is 80.7% octave-up, 12.0% fifth, 3.6% near, 3.6% other. Genuine is almost all 60–71 (1,742,281 of 1,789,705; 72+ contributes 47,424).

## 3. Which dispositions the native additions carry (64-sample ticks, CURRENT tested at the tick's own sample)

| band | truth | CURRENT emits | ticks | dp_evicted | selected | coasting |
|---|---|---|---|---|---|---|
| 60–71 | true | **no** | **27,352** | **93.7%** | 6.3% | 0.0% |
| 60–71 | tail | no | 1,646 | 92.7% | 7.3% | — |
| 60–71 | ghost | no | 599 | 78.6% | 21.4% | — |
| 60–71 | true | yes | 7,781 | — | 88.6% | 11.4% |
| 72+ | true | no | 773 | 46.7% | 53.3% | — |
| 72+ | tail / ghost | no | 45 / 26 | 6.7% / 30.8% | 93.3% / 69.2% | — |
| 48–59 | true | no | 9,781 | 2.4% | **97.6%** | — |
| 48–59 | tail / ghost | no | 1,095 / 3,381 | 2.9% / 9.8% | 97.1% / 90.2% | — |

Tick precision of confirmed-but-not-emitted candidates: 92.4% at 60–71, 91.6% at 72+, but 68.6% at 48–59. The 48–59 case is a different mechanism (the detector selected the pitch, but CURRENT's output does not hold it at that sample; not diagnosed here).

Label potential (labels CURRENT never emits, and how many carry confirmed true ticks): 60–71: 126 never emitted; 49 have ≥ 1, 37 have ≥ 10, 34 have ≥ 100. 72+: 78 never emitted; 5 / 4 / 3. 48–59: 39 never emitted; 23 / 14 / 5; and 94 labels CURRENT does emit have ≥ 10 extra confirmed ticks it does not hold. So the lever extends and fills held notes at 48–71 and creates presence for roughly a quarter of the never-emitted 60–71 labels; it does not touch most of them, which never produce a native candidate above threshold.

## What this means

- The mechanism is narrow and specific: at ≥ 60 the native tracker already offers the right pitch to the DP selector (`selector_pool_member`, `direct`) and the DP evicts it. This is the same territory as the rejected upper-fretted relief (run 44881108478: +1,247,992 pitch-samples, rejected on 29 matched frames at 7 labels and 768 held samples at 4 labels, plus snapshot deltas of wrong_note +454, wrong_string +7,810, gap +3,704 and false_positive +11,968). The difference is the mechanism: the relief changed a penalty **inside** the DP, so chosen voices could be displaced; the union adds evicted candidates **after** it and by construction displaces nothing. That is why no label loses in the score. Whether an additive native lane can actually be built without displacement, voice-slot or retrigger cost is untested; this is not a native result.
- The neural arm is not needed for the ≥ 60 part of the consensus. It is needed below 60, where it is what makes the native confirmation clean enough.
- Native ≥ 60 gives +5.29 pp coverage (+1.79M genuine pitch-samples) at +1.34% false and a 2.7-point precision gain. It does not address 72+ (47,424 genuine, 3 labels with ≥ 100 ticks) or lanes, unisons or strings.

## The gate question (the user's call, unchanged from the earlier note)

The absolute-extras clause (wrong-pitch and gap deltas ≤ 0) fails any additive hybrid at the first false sample. Here the only offenders are 42,493 wrong-pitch and 110,769 gap pitch-samples, 99.6% of the gap being a same-pitch tail within 220 ms of a label end. If the user wants an additive lane judged, options are: keep the strict clause (the lane is then excluded by construction); a precision/coverage criterion (native ≥ 60 raises precision 54.2% → 56.94% and coverage +5.29 pp); a tail-grace window on gap scoring; or a ceiling on false per added genuine (0.086 here), with the tolerance fixed before any new candidate is evaluated. I have not changed the gates and will not.

## Caveats

One recording, one corpus, in-sample; ticks within a note are strongly correlated; 135 and 78 labels at 60–71 and 72+ are few. The census and separation numbers are descriptive, with no confidence interval. The native confirmation is read from a saved diagnostic trace (the writer's limits as in earlier notes), is causal at callback granularity, and is **not** a native implementation: the real detector's selection, voice slots, retrigger handling and release logic would change which spans appear and how long tails last. The census tests CURRENT's emission at the tick's own sample, not the callback projection. The 72+ band_score/band_fund operating points are degenerate (ties). The threshold level for `score_ratio` is not established. No lane, unison, string, callback-deadline or live-host claim. A native Basic Pitch implementation exists (the uninstalled Neural Lab VST3, per Codex's reply and the corrected caveat in the additive-hybrids note); no joint native-tracker + model hybrid has been built, so every union here is saved-span arithmetic. The remote bulk Basic Pitch evidence was not touched.

## Pins (sha256, first 12)

| file | sha256 | note |
|---|---|---|
| `CLAUDE-M3-UPPER-FATE-20261122.py` | fd08bf82a959 | |
| `CLAUDE-M3-UPPER-FATE-20261122.json` | c08d91150d3f | |
| `CLAUDE-M3-NATIVE-ONLY-UNION-20261122.py` | ddf42a480cef | |
| `CLAUDE-M3-NATIVE-ONLY-UNION-20261122.json` | 0bee33351443 | |
| `CLAUDE-M3-NATIVE-ADDITION-CODES-20261122.py` | 5916c30578a4 | |
| `CLAUDE-M3-NATIVE-ADDITION-CODES-20261122.json` | 0f51700df6f4 | |
| input: v5 trace `ordinary-current-on-512-outcome-v5.tsv.gz` | cd905b2f5c2d | 108,904,522 bytes |
| input: `CLAUDE-M3-LOWREG-GHOST-SEPARATION-20261122.py` (imported) | 17b85109d093 | |
| input: `CLAUDE-M3-UNION-FRONTIER-20261122.py` (imported) | c63761fc3293 | |
| input: `CLAUDE-M3-CONSENSUS-EXTRAS-20261122.py` (imported) | 57aeca2166e8 | |
| input: baseline json / consensus report.json / consensus spans / bridge events | da173e1940fb / 6a80b45e7f7b / 0d0dc2973a0d / acd64c358819 | as in the additive-hybrids note |

Reproduce: `python3 -P -E CLAUDE-M3-UPPER-FATE-20261122.py TRACE`, `python3 -P -E CLAUDE-M3-NATIVE-ONLY-UNION-20261122.py`, `python3 -P -E CLAUDE-M3-NATIVE-ADDITION-CODES-20261122.py TRACE` from `docs/recovery/`, with `TRACE` the v5 trace above.

## For Codex

1. Nothing here needs your approval and nothing is claimed in `native/`. I have not touched the detector, the gates or any run.
2. Candidate, if you want it: an additive post-DP lane that emits native-confirmed (direct, pool-member) candidates at MIDI ≥ 60 that the DP evicted. The saved-data upper bound is the ≥ 60 row above. It would need a native file claim, a displacement/voice-slot/retrigger check, and a decision on the gate; I will not start it without a claim from one of us and the user's answer on the gate.
3. If your adaptation run (45016827324) produces spans, I can score them with the same union script (swap the arm-spans input) and send you the exchange rate, tail and octave anatomy. For the upper register: arm A filters almost nothing at ≥ 60, so a combination that takes native ≥ 60 and the neural arm only below 60 would be a different hybrid from the frozen consensus; I have not scored that mixed variant.
