# CLAUDE-M3: removing CURRENT's own false output, and what is left once a hold is allowed (2026-11-22)

Saved data only: the saved v5 trace, saved spans and the saved Basic Pitch arm A spans. No audio, no model run, no job, no native edit,
nothing promoted or installed. Five scripts, each with its predictions written before it ran (failed ones are reported as failed):

- `CLAUDE-M3-NATIVE-RESCUE-FRONTIER-20261122.py` / `.json` — the additive native lane with rejected candidates rescued by `score_ratio` (R0–R6).
- `CLAUDE-M3-SUPPORT-FILTER-20261122.py` / `.json` — CURRENT ∩ support, where support is arm A and/or the native confirmation (S0–S6).
- `CLAUDE-M3-SUPPORT-DILATION-20261122.py` / `.json` — the same filter with the support held forward D ms, removal locations, run counts (P0–P8).
- `CLAUDE-M3-SUPPORT-LOSERS-20261122.py` / `.json` — which labels still lose at each hold, and how much (L0–L6).
- `CLAUDE-M3-NATIVE-ONLY-GATE-20261122.py` / `.json` — the same gate with the native confirmation as the only support (N0–N7).
- `CLAUDE-M3-SUPPORT-REPLICATION-20261122.py` / `CLAUDE-M3-SUPPORT-REPLICATION-EXTENDED-MIDDLE-20261122.json` — the same filter and
  gates on the second saved corpus with the hold grid unchanged (X0–X8). **This one changes two earlier answers; see answers 8 and 9.**

Scope: ordinary corpus, 512-sample callbacks, one recording, in-sample. All numbers are pitch-samples from the project's own
`score`/`compare` unless a row says 64-sample ticks. Every earlier hybrid was additive; this is the first pass at the other side of
Codex's request that "the recovered pitches and the removal of CURRENT errors" be measured together, per label and hold.

## Answers first

1. **CURRENT's false output is mostly unsupported, and removing the unsupported part is cheap in genuine presence.** CURRENT's false
   output is 11,429,794 pitch-samples (wrong 7,808,309, gap 3,621,485); the native ≥ 60 lane adds 153,262 more, so removal is where the
   large mass is. Keeping only CURRENT output that arm A **or** the native confirmation also reports (same pitch) removes 75.8% of the
   wrong-pitch and 35.6% of the gap output for 6.0% of the genuine presence (809,253 pitch-samples); precision goes 54.2% → 75.06%.
2. **With the native ≥ 60 lane added back, that is the first span hybrid in this series that passes the extras clauses in aggregate**
   (Codex's Neural Lab trial, run 44929394064, also passed them, with 192 labels losing presence). Coverage 42.89%,
   precision 76.81%, false 4,378,870 (−61.7% of CURRENT's false), wrong −5,873,557, gap −1,177,367, exact-set +283,679, all-expected
   +333,214. **But 106 of 499 labels lose presence (99 also longest hold), and the output has 227% more note runs.** The strict gate
   still fails, now on the label clause instead of the extras clauses.
3. **A causal hold of the support trades the label losses against the removal, nearly one for one.** Holding the support forward
   D ms (never backward) gives, for filter plus lane:

   | hold | coverage | precision | false vs CURRENT | wrong Δ | gap Δ | exact-set Δ | all-expected Δ | labels losing (present / longest) | lost share of CURRENT present | runs vs CURRENT |
   |---|---|---|---|---|---|---|---|---|---|---|
   | 0 ms | 42.892% | 76.81% | −61.69% | −5,873,557 | −1,177,367 | +283,679 | +333,214 | 106 (106 / 99) | 5.98% | +226.7% |
   | 50 ms | 44.878% | 69.65% | −42.14% | −4,340,944 | −475,296 | +315,375 | +385,158 | 28 (28 / 23) | 1.02% | +53.2% |
   | 100 ms | 45.061% | 65.92% | −31.08% | −3,324,983 | −227,057 | +297,772 | +385,158 | 17 (17 / 13) | 0.56% | +43.2% |
   | 220 ms | 45.215% | 61.53% | −16.34% | −1,687,401 | −180,705 | +256,962 | +385,158 | 6 (6 / 3) | 0.18% | +39.0% |
   | 500 ms | 45.240% | 59.60% | −9.27% | −939,332 | −120,679 | +249,349 | +385,158 | 5 (5 / 2) | 0.11% | +43.8% |

   Every row passes the wrong-pitch, gap, exact-set and all-expected clauses in aggregate (CURRENT: coverage 39.99%, precision 54.2%,
   528 runs). Every row fails the label clause. The wrong-pitch removal share (filter only) falls 75.8% → 56.1% → 43.1% → 22.2% →
   12.6% as the hold grows, so precision falls with it.
4. **The labels that still lose at D = 220 lose little, except one.** Six labels lose a total of 23,687 pitch-samples (0.18% of
   CURRENT's present time): 152 ms, 51 ms, 35 ms, 5.3 ms, 3.3 ms, 0.7 ms. Five of the six are below MIDI 60. The 152 ms loss is label
   229 (pitch 42): CURRENT holds the true pitch for 191 ms, arm A reports it for 0 ms and the native confirmation for 16 ms inside the
   label, so this is a true CURRENT note the support does not see. The other five lose their first samples (the confirm delay):
   label 364 loses its first 50.6 ms although arm A covers 605 ms of its 749 ms. At D = 500 the same labels remain minus label
   42 (5 losers, worst 67 ms), and the D = 500 losers are a subset of the D = 220 losers.
5. **Any confirm-before-emit gate loses its confirm delay by construction**, because a note can only start when its support
   starts. The strict clause counts any negative delta however small (0.7 ms counts), so no support that ever lags CURRENT's first
   sample can pass it. A per-label tolerance can be read off the tables: at D = 220, losers above 5% of their own present time: 3;
   above 10%: 2; above 25%: 1 (label 229, 79.7%).
6. **The additive side, for comparison, is label-safe but cannot reduce extras.** Widening the lane by rescuing rejected candidates
   (`below_threshold`, `spectral_rejected`, `dp_evicted` at pitch ≥ 60 with `score_ratio ≥ c`) gives:

   | c | coverage | precision | added genuine | added false | false share | false / genuine | marginal false / genuine | 72+ genuine / false | exact-set Δ | labels losing |
   |---|---|---|---|---|---|---|---|---|---|---|
   | ∞ (native lane) | 45.285% | 56.94% | 1,789,705 | 153,262 | 7.89% | 0.086 | — | 47,424 / 3,264 | +243,781 | 0 |
   | 1.0 | 46.206% | 57.16% | 2,101,129 | 281,646 | 11.82% | 0.134 | 0.412 | 78,656 / 10,944 | +241,221 | 0 |
   | 0.8 | 47.255% | 57.29% | 2,455,945 | 483,886 | 16.46% | 0.197 | 0.570 | 120,128 / 41,152 | +243,269 | 0 |
   | 0.5 | 49.562% | 57.43% | 3,236,036 | 996,083 | 23.54% | 0.308 | 0.657 | 241,536 / 175,744 | +222,595 | 0 |
   | 0.25 | 53.471% | 57.69% | 4,557,904 | 1,832,807 | 28.68% | 0.402 | 0.633 | 565,597 / 412,323 | +331,209 | 0 |

   At c = 0.25: +13.5 pp coverage with no label losing time, but false is +16.04% of CURRENT (wrong +1,450,927, gap +381,880) and the
   72+ band has a 42% false share. The best c = 0.25 coverage is within 1.8 pp of the Neural Lab's 55.24% in saved-span arithmetic,
   without losing any labels, at the cost of that false output. `score_ratio` has no demonstrated pass level here (c = 1.0 is just a
   grid point).
7. **No variant yet satisfies the whole strict gate.** The extras-clean hybrid loses a few labels' time; the label-safe hybrid adds
   extras. Combining the rescue lane with the filter and hold (more coverage and fewer extras than the filter alone, no extra label
   losses because the lane is additive) is unmeasured; the lane's rescued spans are not in the saved files, only the trace.
8. **A gate that uses only the native selector's own confirmation (no Basic Pitch model) looks good on the ordinary corpus and does
   not replicate on the second saved corpus (answer 9). Treat this row as retracted as a general claim.** On ordinary, native
   confirmation as the only support, held forward, plus the native ≥ 60 lane:

   | hold | coverage | precision | false vs CURRENT | wrong Δ | gap Δ | exact-set Δ | all-expected Δ | labels losing (present / longest) | lost share of CURRENT present | runs vs CURRENT |
   |---|---|---|---|---|---|---|---|---|---|---|
   | 50 ms | 44.374% | 73.21% | −51.94% | −5,116,945 | −820,205 | +328,899 | +385,158 | 39 (39 / 34) | 2.28% | +62.3% |
   | 100 ms | 44.725% | 68.45% | −39.01% | −4,144,814 | −314,014 | +311,424 | +385,158 | 26 (26 / 21) | 1.40% | +42.8% |
   | 220 ms | 45.065% | 62.77% | −20.92% | −2,144,404 | −246,599 | +265,475 | +385,158 | 9 (9 / 6) | 0.55% | +35.0% |
   | 500 ms | 45.187% | 60.36% | −12.18% | −1,173,986 | −217,956 | +249,349 | +385,158 | 6 (6 / 3) | 0.25% | +43.2% |

   At 220 ms it removes more false than the model-supported version at the same hold (−20.9% against −16.3%, precision 62.77% against
   61.53%) with three more labels losing (9 against 6; worst single loss −44,928 pitch-samples, 468 ms). Both the confirmation and the
   lane come from the selector's own trace, so this variant describes a tracker-internal rule: emit a CURRENT note only while the
   selector's confirmation has held the same pitch within the last D ms, and add the confirmed ≥ 60 pitches. No model is involved in
   the measured numbers.
9. **Second corpus (`extended-middle`: 6 labels, sustained chords, CURRENT already at 97.49% coverage, precision 73.97%, wrong
   528,259, gap 183,006, 14 runs), same code and the same hold grid, nothing tuned on it.**
   - **The model-supported filter replicates and is cleaner there.** CURRENT ∩ (A ∪ native confirmation) at holds of 50, 100, 220 and
     500 ms loses **no label and no present time**, removes 32.2 / 29.3 / 26.0 / 20.9% of the wrong-pitch output, raises precision
     73.97% → 80.22 / 79.60 / 78.53 / 77.09%, adds exact-set +170,047 / +154,944 / +137,344 / +110,464, leaves the run count
     unchanged (14 → 14, +0.0%), and **passes the project's own `no_pitch_safety_regression` at all four holds**. At D = 0 one label
     loses 508 pitch-samples (5 ms) and runs are +7.1%.
   - **The native-only gate does not replicate.** On this corpus the native confirmation barely covers the sustained chords: native
     only as support at D = 220 loses 24.8% of CURRENT's present time (coverage 97.49% → 73.33%), 4 of the 6 labels lose time (worst
     −246,272 pitch-samples, 2.6 s), exact-set −269,375 (−342,909 with the lane), and with the lane wrong-pitch is +121,022 and
     false is +4.1% of CURRENT's. At D = 0 it loses 49.8% of present time and all 6 labels. So the ordinary-corpus native-only result (0.55%
     lost) is specific to a recording of short, sharply struck notes, and a gate that waits for the native confirmation alone would
     cut sustained notes whose confirmation lapses while they decay.
   - **The ≥ 60 lane is harmful where CURRENT is already complete.** CURRENT ∪ native ≥ 60 lane adds 0 genuine and +258,366 wrong-pitch
     samples here (exact-set **−77,630**, false +36.3%, runs +186%); every filter-plus-lane row fails `no_pitch_safety_regression`
     on this corpus. The lane's ordinary gain is a coverage gain, and it has nothing to add where coverage is 97.5%.
   - So the candidate that holds up on both saved corpora is the **model-supported filter without the lane**, held 50–220 ms:
     extended-middle strict-gate clean; ordinary 28 / 17 / 6 labels losing small amounts of time with extras reduced (wrong
     −4.38M / −3.37M / −1.73M, gap −586k / −338k / −291k) and no exact-set regression. That variant needs Basic Pitch arm A running
     live (the Neural Lab worker path exists but joint use with the native tracker is unbuilt).
10. **Filter plus rescue lane, ordinary only (`CLAUDE-M3-SUPPORT-RESCUE-COMBINED-20261122.py`; the rescue spans need the v5 trace, which
    exists for ordinary only).** The two sides had only been scored apart. Combined: the filtered CURRENT (A ∪ native support held D ms)
    plus a lane at pitch ≥ 60. Two lanes, grid fixed before the run (D ∈ {50, 220}, c ∈ {∞, 1.0, 0.5, 0.25}): the *unsupported* rescue
    lane of answer 6, and a *supported* one, the native ≥ 60 confirmation plus the rescue candidates that arm A also reports (the rescue
    spans intersected with arm A held forward D ms).
    - **Supporting the rescue lane with the model cuts the false it brings in, by half or more at c = 0.5 and 0.25.** False per added
      genuine pitch-sample (over the filter alone, D = 220): unsupported c = 1.0 / 0.5 / 0.25 = 0.134 / 0.308 / 0.402; supported =
      0.105 / 0.152 / 0.170 (native-only lane 0.086). It costs coverage: supported gives up 0.12 / 0.70 / 1.47 pp against unsupported at
      c = 1.0 / 0.5 / 0.25 (51.93% against 53.40% at c = 0.25).
    - **D = 220, supported lane** (CURRENT: coverage 39.99%, precision 54.2%, false 11,429,794):

      | c | coverage | precision | wrong Δ | gap Δ | exact-set Δ | all-expected Δ | false vs CURRENT | runs vs CURRENT | labels losing |
      |---|---|---|---|---|---|---|---|---|---|
      | 1.0 | 46.02% | 61.79% | −1,644,139 | −160,394 | +271,299 | +412,551 | −15.8% | +47.5% | 6 (0.18% of present) |
      | 0.5 | 48.80% | 62.59% | −1,495,713 | −70,981 | +338,690 | +547,849 | −13.7% | +59.7% | 6 (0.18%) |
      | 0.25 | 51.93% | 63.50% | −1,393,655 | **+60,454** | +475,250 | +775,185 | −11.7% | +91.9% | 6 (0.18%) |

      At c = 1.0 and 0.5 every extras clause and the exact-set and all-expected clauses pass in aggregate; the label clause is the one
      that fails (the same 6 labels as without any lane). At c = 0.25 the gap clause also fails (+60,454).
    - **D = 50, supported lane.** Coverage 45.62 / 48.26 / 51.26% (c = 1.0 / 0.5 / 0.25), precision 69.87 / 70.44 / 71.11%, wrong
      −4.32M / −4.21M / −4.14M, gap −456k / −372k / −244k, exact-set +339k / +434k / +583k, all-expected +411k / +546k / +757k, false
      −41.8 / −40.1 / −38.4% of CURRENT's, runs +60 / +71 / +100%. All three pass the extras clauses; 28 labels lose 1.02% of CURRENT's
      present time. So at 50 ms the lane takes coverage from 39.99% to 51.26% and precision from 54.2% to 71.1% together, for 28 labels'
      small losses.
    - **The label losers do not change.** Adding any lane leaves the loser count at 28 (D = 50) and 6 (D = 220) because the lanes only
      add pitches ≥ 60 and the losses are at the confirm delay and at pitches the support never reports. Run count rises with a
      stronger lane (+48% to +92% at D = 220, supported), which would be extra note-ons in a real emitter.
    - **Not replicated, and probably not replicable here.** The trace exists for ordinary only, so this combination cannot be scored on
      extended-middle. There, an unsupported ≥ 60 lane added only false; whether a supported lane stays clean is unknown.
11. **The lane's extra runs are mostly flicker, and a short forward hold of the lane merges most of it, at the price of gap output
    (`CLAUDE-M3-LANE-FRAGMENTATION-20261122.py`, ordinary only, saved trace).** CURRENT has 528 runs. The supported lane
    spans at c = 0.5, D = 220 are 387 runs of which 77.3% are shorter than 50 ms (CURRENT's own runs: 40.5% shorter than 50 ms, so short
    runs are not by themselves spurious on this recording of short struck notes). Holding only the *lane* forward h ms (never CURRENT's
    own spans), grid h ∈ {0, 30, 60, 120} ms fixed before the run:

    | variant | h = 0 | 30 ms | 60 ms | 120 ms |
    |---|---|---|---|---|
    | (a) D = 220, c = 0.5: runs vs CURRENT | +59.7% | +17.2% | +12.9% | +10.4% |
    | (a) coverage / precision | 48.80 / 62.59% | 49.89 / 62.49% | 50.30 / 62.16% | 51.00 / 61.58% |
    | (a) wrong Δ / gap Δ | −1,495,713 / −70,981 | −1,370,501 / **+68,934** | −1,281,697 / +208,389 | −980,594 / +312,175 |
    | (a) exact-set Δ | +338,690 | +380,290 | +405,250 | +444,675 |
    | (b) D = 50, c = 0.25: runs vs CURRENT | +100.2% | +41.3% | +32.8% | +25.8% |
    | (b) coverage / precision | 51.26 / 71.11% | 52.71 / 70.65% | 53.19 / 69.97% | 53.86 / 68.83% |
    | (b) wrong Δ / gap Δ | −4,143,848 / −243,993 | −3,969,651 / −55,065 | −3,842,561 / +130,812 | −3,481,738 / +299,855 |
    | (b) false vs CURRENT | −38.4% | −35.2% | −32.5% | −27.8% |

    A 30 ms hold removes most of the extra runs (a: +59.7% → +17.2%; b: +100% → +41%) and raises coverage and exact-set, but it
    extends lane notes past their ends, so the gap-voice clause (which counted −70,981 at h = 0 for variant a) turns positive at 30 ms
    for variant (a) and at 60 ms for variant (b); variant (b) at 30 ms still passes the extras clauses (wrong −3.97M, gap −55k) with
    runs +41%. Labels losing stay 6 (a) and 28 (b) at every hold. It is the same trade as the support hold, now between note count and
    gap output.
    - Predictions H4 (gap and wrong both still ≤ 0 at h = 120 for variant a) and H6 (coverage rises less than 1.5 pp from h = 0 to 120)
      failed; H0–H3, H5 and H7 passed.
12. **Confirming by persistence does not rescue the labels without giving the removal back (`CLAUDE-M3-PERSISTENCE-CONFIRM-20261122.py`,
    both corpora, filter only).** Rule: emit a CURRENT note when the support (arm A ∪ native, held D ms) reports it, or after it has
    lasted L ms unsupported. It is causal and replaces "never emit unsupported notes" with "emit them L ms late". Grid fixed before the
    run: L ∈ {∞, 500, 220, 100, 50} ms, D ∈ {50, 220} ms.

    | ordinary | L = ∞ | 500 | 220 | 100 | 50 |
    |---|---|---|---|---|---|
    | D = 220: labels losing | 6 | 4 | 3 | 3 | 3 |
    | D = 220: wrong-pitch removed | 22.1% | 9.3% | 4.4% | 2.0% | 1.0% |
    | D = 220: precision (CURRENT 54.2%) | 58.93% | 55.91% | 55.01% | 54.54% | 54.35% |
    | D = 220: false vs CURRENT | −17.7% | −6.8% | −3.3% | −1.5% | −0.7% |
    | D = 50: labels losing | 28 | 10 | 8 | 7 | 4 |
    | D = 50: wrong-pitch removed | 56.1% | 15.2% | 8.2% | 3.6% | 1.7% |
    | D = 50: precision | 67.45% | 57.03% | 55.71% | 54.82% | 54.47% |

    The false notes CURRENT emits are mostly long-lived: a persistence rule of 500 ms already gives back 58% (D = 220) to 73% (D = 50)
    of the removal while cutting label losses by only a third (6 → 4) to two thirds (28 → 10), and never reaches zero (3 labels still
    lose at L = 50: with a delay of L ms, any label whose CURRENT note is shorter than L or whose first L ms are unsupported loses
    time). On extended-middle every L keeps 0 labels losing and the safety flag True, but the removal also falls (D = 220: 26.0 /
    14.1 / 4.0 / 1.8 / 0.9%; precision 78.53% → 74.10%). So the filter's gain is rejecting *sustained* unsupported notes, which is exactly
    what a persistence rule re-admits; a gate with persistence is a different trade (fewer lost labels, far less cleanup), not a
    free repair. Persistence is measured on CURRENT's saved spans, not on a live emitter.
    - Prediction Q5 (removal above 20% at L = 220) failed (4.4%); Q0–Q4, Q6 and Q7 passed.

## Predictions

| id | prediction | outcome |
|---|---|---|
| R0 | lane(∞) reproduces the saved native ≥ 60 spans; added genuine / false 1,789,705 / 153,262 | **pass** |
| R1 | as c falls, added genuine and the false share both rise at every step | **pass** |
| R2 | marginal false per genuine from lane(∞) to lane(0.5) exceeds 0.25 | **pass** (0.583) |
| R3 | at c = 0.25 whole-hybrid precision falls below the native-only lane's 56.94% | **FAILED** (it rises to 57.69%) |
| R4 | at c = 1.0 the added genuine over the native lane is under 1.0 pp of expected (~340,000) | **pass** (311,424) |
| R5 | at c = 0.25 the 72+ band adds fewer than 500,000 genuine pitch-samples | **FAILED** (565,597) |
| R6 | no lane loses a label; all fail only on wrong/gap clauses | **pass** |
| S0 | every filtered CURRENT span set is contained in CURRENT before any addition | **pass** |
| S1 | CURRENT ∩ A removes more than 25% of CURRENT's wrong-pitch output | **pass** (85.3%) |
| S2 | CURRENT ∩ A loses at least one label | **pass** (208) |
| S3 | filtered CURRENT has higher precision than 54.2% | **pass** (74.76%) |
| S4 | adding the native confirmation to the support does not rescue the labels | **pass** (106 still lose) |
| S5 | CURRENT ∩ A removes more than 15% of CURRENT's genuine | **pass** (31.4%) |
| S6 | (A ∪ native filter) ∪ native ≥ 60 lane has coverage above 39.99% | **pass** (42.89%) |
| P0 | D = 0 reproduces the support-filter numbers (present −809,253; wrong −5,916,050) | **pass** |
| P1 | labels losing fall monotonically as D grows | **pass** (106, 28, 17, 6, 5) |
| P2 | whole-hybrid precision falls monotonically as D grows | **pass** (75.06, 67.45, 63.52, 58.93, 56.94) |
| P3 | at D = 220 the losers are at most half of the D = 0 count (≤ 53) | **pass** (6) |
| P4 | at D = 220 the wrong-pitch removal share is still ≥ 60% | **FAILED** (22.2%) |
| P5 | at D = 0 at least half of the removed samples fall in the first 220 ms of the label | **FAILED** (36.0%: 10.1 / 10.4 / 15.5% in 0–50 / 50–100 / 100–220 ms) |
| P6 | CURRENT ∩ native confirmation alone (D = 0) loses more than 150 labels | **FAILED** (130; 129 longest) |
| P7 | the D = 0 output has more than 20% more runs than CURRENT | **pass** (+178.6%) |
| P8 | no variant at D ≤ 220 reaches zero label losses | **pass** (minimum 6) |
| L0 | the loser counts reproduce the dilation run | **pass** |
| L1 | at D = 220 every loser loses under 10% of its own present time | **FAILED** (79.7% and 10.2%) |
| L2 | at D = 220 the median loser loses under 50 ms | **pass** (20.1 ms) |
| L3 | at D = 0 at least half of the 106 losers lose under 5% of their own present time | **FAILED** (44 of 106) |
| L4 | the D = 500 losers are a subset of the D = 220 losers | **pass** |
| L5 | at D = 220 at least half of the lost samples fall in a label's first 50 ms | **FAILED** (36.8%; 57.2% at D = 500) |
| L6 | at D = 220 at least four of the six losers are below MIDI 60 | **pass** (5) |
| N0 | native-only at D = 220 without the lane reproduces the dilation numbers (present −74,605; wrong −2,186,897) | **pass** |
| N1 | native-only plus the lane at D = 220 has wrong-pitch and gap deltas ≤ 0 | **pass** (−2,144,404; −246,599) |
| N2 | its coverage is above 44.5% | **pass** (45.065%) |
| N3 | its precision is above 60% | **pass** (62.77%) |
| N4 | its exact-set delta is above +200,000 | **pass** (+265,475) |
| N5 | at D = 220 between 5 and 9 labels lose | **pass** (9, the upper edge) |
| N6 | label losses are non-increasing over D = 50, 100, 220, 500 | **pass** (39, 26, 9, 6) |
| N7 | at D = 500 the wrong-pitch delta with the lane is still ≤ 0 | **pass** (−1,173,986) |
| X0 | CURRENT re-scored on extended-middle equals the saved report | **pass** |
| X1 | CURRENT ∩ (A ∪ native) at D = 0 removes more than 25% of CURRENT's wrong-pitch output | **pass** (35.8%) |
| X2 | filter precision exceeds CURRENT's 73.97% at every hold | **pass** (81.77, 80.22, 79.60, 78.53, 77.09) |
| X3 | no hold up to 220 ms reaches zero labels losing, A ∪ native filter | **FAILED** (0 labels lose at 50, 100 and 220 ms; 1 at D = 0) |
| X4 | at D = 220 the filter-only lost share of present time is under 1% | **pass** (0.0%) |
| X5 | native-only + lane at D = 220: wrong ≤ 0 and gap ≤ 0 | **FAILED** (wrong +121,022; gap −91,936) |
| X6 | the same variant's exact-set and all-expected deltas ≥ 0 | **FAILED** (−342,909; −500,991) |
| X7 | the same variant's coverage is not below CURRENT's | **FAILED** (73.33% vs 97.49%) |
| X8 | the same variant's total false is below CURRENT's | **FAILED** (+4.09%) |
| C0 | c = ∞ lane equals the saved native ≥ 60 spans; filter D = 220 + that lane reproduces the dilation run | **pass** (45.215%, −1,687,401, 6 labels) |
| C1 | filter D = 220 + unsupported rescue c = 0.5 has coverage above 48.0% | **pass** (49.49%) |
| C2 | filter D = 220 + unsupported rescue c = 0.25: precision above 55% and wrong ≤ 0 and gap ≤ 0 | **FAILED** (precision 61.64%, wrong −278,967, but gap **+90,406**) |
| C3 | the same variant's exact-set delta exceeds +256,962 | **pass** (+446,728) |
| C4 | labels losing fall below 6 once a rescue lane is added | **FAILED** (6 at every lane) |
| C5 | supported rescue c = 0.25, D = 220 has lower false per added genuine than the unsupported lane | **pass** (0.170 vs 0.402) |
| C6 | supported rescue c = 0.25, D = 220 reaches coverage of at least 47.0% | **pass** (51.93%) |
| C7 | supported rescue c = 0.25, D = 220 has higher precision than the unsupported lane | **pass** (63.50% vs 61.64%) |
| C8 | at D = 50 no rescue lane brings label losses below 20 | **pass** (28 at every lane) |
| H0 | h = 0 reproduces the combined result (a: 48.797%, +59.66%; b: 51.260%, +100.19%) | **pass** |
| H1 | output runs fall as the lane hold h grows (both variants) | **pass** (a 843, 619, 596, 583; b 1,057, 746, 701, 664) |
| H2 | at h = 120 variant (a) has runs below +30% over CURRENT | **pass** (+10.4%) |
| H3 | precision falls as h grows (both variants) | **pass** (a 62.59 → 61.58; b 71.11 → 68.83) |
| H4 | at h = 120 variant (a) keeps gap Δ ≤ 0 and wrong Δ ≤ 0 | **FAILED** (wrong −980,594 but gap **+312,175**) |
| H5 | the lane's own short-run (< 50 ms) share exceeds CURRENT's | **pass** (77.3% vs 40.5%) |
| H6 | coverage rises less than 1.5 pp from h = 0 to 120 | **FAILED** (+2.20 pp for a, +2.60 pp for b) |
| H7 | labels losing present or longest are unchanged by h | **pass** (6 and 28) |
| Q0 | L = ∞ reproduces the filter-only numbers (ordinary D = 220: present −23,687, 6 labels) | **pass** |
| Q1 | ordinary D = 220, L = 100: fewer than 6 labels lose | **pass** (3) |
| Q2 | ordinary D = 220, L = 100: wrong-pitch removal below 15% | **pass** (2.0%) |
| Q3 | ordinary D = 220: labels losing non-increasing as L falls | **pass** (6, 4, 3, 3, 3) |
| Q4 | ordinary D = 220: precision non-increasing as L falls | **pass** (58.93 → 54.35%) |
| Q5 | ordinary D = 220, L = 220: wrong-pitch removal stays above 20% | **FAILED** (4.4%) |
| Q6 | extended-middle D = 220: 0 labels lose and safety True at every L, removal at L = 100 below 26.0% | **pass** (1.8%) |
| Q7 | ordinary D = 50, L = 100: labels losing at most 13 | **pass** (7) |

## 1. The support filter (S0–S6)

CURRENT ∩ support is the per-pitch intersection of CURRENT's spans with the support spans, scored against the same labels.
Intersection is the causal model of a confirm-before-emit gate: a note starts when its support arrives and ends when either side ends.

| filter | coverage | precision | present removed | wrong removed | gap removed | exact-set Δ | labels losing (present / longest) | worst loss |
|---|---|---|---|---|---|---|---|---|
| CURRENT ∩ A | 27.423% | 74.76% | 31.4% | 85.3% | 45.2% | −53,249 | 208 (208 / 205) | −71,801 |
| CURRENT ∩ (A ∪ native) | 37.600% | 75.06% | 6.0% | 75.8% | 35.6% | −36,392 | 106 (106 / 99) | −44,249 |
| … ∪ native ≥ 60 lane | 42.892% | 76.81% | 0% (net +980,452) | 75.2% | 32.5% | +283,679 | 106 (106 / 99) | −44,249 |
| CURRENT ∩ A, ∪ native ≥ 60 lane | 32.802% | 76.52% | 18.0% (net −2,431,968) | 83.4% | 41.9% | −1,940 | 201 (201 / 198) | −71,801 |
| (control) CURRENT ∪ native ≥ 60 lane | 45.285% | 56.94% | 0% | −0.5% | −3.1% | +243,781 | 0 | 0 |

The control reproduces the saved native-only ≥ 60 union exactly.

## 2. What a forward hold does (P0–P8)

Support held forward D ms after it ends (`dilate`). Filter only, support = A ∪ native:

| hold | coverage | precision | present removed | wrong removed | gap removed | false vs CURRENT | labels losing | worst loss | runs vs CURRENT |
|---|---|---|---|---|---|---|---|---|---|
| 0 ms | 37.600% | 75.06% | 5.98% | 75.77% | 35.57% | −63.03% | 106 | −44,249 | +178.6% |
| 50 ms | 39.586% | 67.45% | 1.02% | 56.14% | 16.18% | −43.48% | 28 | −29,849 | +5.1% |
| 100 ms | 39.769% | 63.52% | 0.56% | 43.13% | 9.33% | −32.42% | 17 | −18,905 | −4.9% |
| 220 ms | 39.923% | 58.93% | 0.18% | 22.15% | 8.05% | −17.69% | 6 | −14,591 | −9.1% |
| 500 ms | 39.948% | 56.94% | 0.11% | 12.57% | 6.39% | −10.62% | 5 | −6,464 | −4.4% |

Filter-only exact-set and all-expected deltas are 0 at every hold ≥ 50 ms (−36,392 at 0 ms); the exact-set gains in the filter-plus-lane
rows above are larger than the lane's own +243,781 at 50, 100 and 220 ms (+315,375, +297,772, +256,962) and about equal at 500 ms
(+249,349), a difference I have not decomposed.

Where the removed own-pitch samples fall inside label windows (offset from the label's start), A ∪ native:

| hold | total removed | 0–50 ms | 50–100 ms | 100–220 ms | 220–500 ms | > 500 ms |
|---|---|---|---|---|---|---|
| 0 ms | 809,253 | 10.1% | 10.4% | 15.5% | 30.9% | 33.1% |
| 220 ms | 23,687 | 36.8% | 0.2% | 0% | 32.6% | 30.4% |

The loss at D = 0 is not mainly an onset effect: 64% of it falls after the first 220 ms. It is the support dropping out mid-note.

Other supports: native confirmation alone at D = 0 reaches precision 82.28% (wrong removed 85.07%, gap removed 60.8%) but loses 11.2% of
genuine presence and 130 labels (129 longest hold, worst −66,560), with 2,166 runs (+310%); at D = 220: coverage 39.7726%, precision
60.22%, wrong −2,186,897, gap −357,368, 9 labels losing (6 longest), worst −44,928, runs −13.07%. Arm A alone at D = 0 loses 208
labels; at D = 220 it still loses 194 and its precision is 62.02%.

## 3. Who still loses (L0–L6)

Per-label loss of present time at each hold (A ∪ native, filter only), as milliseconds and as a share of CURRENT's own present time:

| hold | labels losing | lost pitch-samples | median loss | max loss | median share | losers above 5% / 10% / 25% / 50% |
|---|---|---|---|---|---|---|
| 0 ms | 106 | 809,253 | 37.3 ms | 460.9 ms | 7.5% | 62 / 44 / 22 / 7 |
| 50 ms | 28 | 137,703 | 35.3 ms | 310.9 ms | 5.7% | 15 / 9 / 4 / 3 |
| 100 ms | 17 | 75,749 | 26.2 ms | 196.9 ms | 4.7% | 8 / 5 / 3 / 2 |
| 220 ms | 6 | 23,687 | 20.1 ms | 152.0 ms | 3.8% | 3 / 2 / 1 / 1 |
| 500 ms | 5 | 15,241 | 34.8 ms | 67.3 ms | 6.8% | 3 / 2 / 1 / 0 |

The six losers at D = 220 (label, pitch, label length, CURRENT's present time in it, loss, where it falls):

| label | pitch | length | CURRENT present | loss | arm A in label | native in label | where the loss falls |
|---|---|---|---|---|---|---|---|
| 229 | 42 | 748 ms | 191 ms | −152.0 ms (79.7%) | 0 ms | 16 ms | 220–500 ms and later |
| 364 | 42 | 749 ms | 749 ms | −50.6 ms (6.8%), longest −50.6 | 605 ms | 437 ms | first 50 ms |
| 263 | 33 | 348 ms | 342 ms | −34.8 ms (10.2%) | 140 ms | 296 ms | first 50 ms |
| 398 | 34 | 748 ms | 709 ms | −5.3 ms (0.7%), longest −5.3 | 649 ms | 624 ms | first 50 ms |
| 42 | 60 | 748 ms | 477 ms | −3.3 ms (0.7%), longest −3.3 | 0 ms | 16 ms | 220–500 ms |
| 389 | 33 | 511 ms | 141 ms | −0.7 ms (0.5%) | 322 ms | 440 ms | first 50 ms |

## What this means

- The false output the project keeps adding to its record is mostly CURRENT's own, and two sources (the saved Basic Pitch arm, a
  separate model, and the native selector's confirmation flag, which comes from the same selector that produces CURRENT's notes, so it
  is not independent of CURRENT) both report most of it as unsupported. A causal removal rule exists on saved spans.
- **Correction to what this note said before the second corpus was scored:** I had written that the model is not what makes the
  removal possible, because on ordinary the native confirmation alone, held 220 ms and with the lane, removed more false (−20.9%)
  than the model-supported version (−16.3%). On extended-middle the native-only gate loses a quarter of CURRENT's present time. The
  model-supported support (arm A ∪ native) is the one that held on both corpora; the native-only gate is ordinary-specific.
- The additive lane and the filter are separable. The filter generalizes (extended-middle clean at 50–500 ms); the ≥ 60 lane helps
  coverage on ordinary and only adds false on extended-middle (exact-set −77,630).
- No hold makes the label clause pass, because the loss has two parts: a confirm delay at some onsets (every row) and a few true CURRENT
  notes that the support never sees (label 229). The first part is intrinsic to any confirm-before-emit gate; the second can only be
  fixed by a better support.
- The additive and removal sides now bracket the gate. A zero-loss label rule with zero extras is not demonstrated by any saved-data
  variant here; the extras-clean variant at D = 220 costs 0.18% of CURRENT's present time over 6 labels.
- The filter at D = 220 plus the native ≥ 60 lane is a candidate for the "measure recovery and removal together" request on the
  ordinary corpus only: coverage +5.22 pp, false −16.3%, precision 54.2% → 61.5%, runs +39% (a real emitter would turn extra runs
  into extra note-ons, so that is not a free quantity). On extended-middle the lane fails (exact-set −77,630), so any lane would need
  its own condition. The filter alone at 50–220 ms is the part that held on both corpora.
- Once the rescue lane must also be reported by the model (answer 10), the ordinary recording's best saved-data variants move a lot.
  D = 220, c = 0.5: coverage 39.99% → 48.80%, precision 54.2% → 62.6%, false −13.7%, exact-set +338,690, the extras clauses pass, 6
  labels lose 0.18% of present time. D = 50, c = 0.25: coverage → 51.26%, precision → 71.1%, false −38.4%, exact-set +582,844, extras
  clauses pass, 28 labels lose 1.02%. Both are ordinary-only, in-sample, and carry +60% to +100% more note runs, so they show a
  direction (a model-supported lane is much cheaper in false than an unsupported one), not a result to promote.

## The gate question (the user's call, unchanged in kind from the earlier note)

The strict gate's label clause (no label may lose any present or longest-hold time) and its absolute-extras clause (wrong-pitch and
gap deltas ≤ 0) pull in opposite directions on the ordinary recording: every variant that removes extras loses some label time (at
best 6 labels, 0.18% of CURRENT's present time) and every variant that never loses label time adds extras. **On the second corpus
they do not conflict:** the same model-supported filter at 50–500 ms passes the project's own `no_pitch_safety_regression`
(no label loses, wrong and gap fall, exact-set rises). So the conflict is a property of ordinary's short struck notes (many onsets,
each costing a confirm delay), not of the filter. Alternatives
the user might choose between: keep both clauses as written (reject every saved-data variant so far); a per-label tolerance fixed
before evaluation (for illustration only: a rule of loss ≤ 50 ms and ≤ 5% of the label's own present time would pass three of the six
D = 220 losers and still fail labels 229, 364 and 263; I chose that example after seeing the loser table, so it is not a usable
tolerance, and any real value must be fixed before looking at results); a precision-and-coverage criterion; or an exchange-rate
ceiling on false per genuine. Codex's gates stay frozen; I have not changed them, and no result above is claimed as an acceptance.

## Caveats

- One recording per corpus, in-sample; descriptive counts; no lane, unison, string, callback or live-host claim. The second corpus has
  only 6 labels (sustained chords, 14 CURRENT runs, CURRENT already at 97.5% coverage), so it tests whether the filter does harm where
  there is nothing to recover, not whether it recovers; its "no label loses" is six labels. The hold grid was fixed on ordinary and not
  tuned on extended-middle, but ordinary's numbers were seen before extended-middle was scored.
- Arm A is an offline causal Basic Pitch run with measured FIFO timestamps, not a native implementation; a real support would add its
  model compute and latency, which these spans include only through the measured timestamps.
- The native confirmation is read from a saved diagnostic trace at the 512-sample callback grid (`confirmation_spans`); a real gate
  would change which spans exist (voice slots, retrigger, release), and a changed CURRENT would change what the filter sees.
- Intersection and the forward hold are span arithmetic. The extra runs are not scored as note-ons; fragmentation (runs +39% to +227%
  at the strongest filter) is real MIDI cost. Answer 11 shows what a short lane hold does to the run count, but no variant here is
  scored as note-ons (merge rules, minimum note length and same-pitch retrigger would change the count), so it is still unpriced as MIDI.
- The rescue-lane spans are scored but not saved. The filter-plus-rescue combination (answer 10) was run on ordinary only, because the
  rescue spans need the v5 trace and no trace exists for extended-middle; the lane grid (c) and the hold grid were fixed before the
  run, but the filter and lane were each designed on ordinary's numbers, so it is in-sample.
- The native-only gate is the selector's own confirmation delayed: its precision gain may partly reflect the confirmation excluding
  coasting and tail states that CURRENT keeps, which would be a property of this recording's note endings. I have not separated the two.
- The saved confirmation is a diagnostic trace projected to callbacks; the native lifecycle must be able to reproduce it online
  (latest observation per completed callback, one block) before any of these numbers describe built behavior.
- Predictions failed and are listed as failed: R3, R5, P4, P5, P6, L1, L3, L5, and the others in the table above.
- No post-hoc number is used as a pass; the table of tolerances is a reading of the loser table, not a rule.

## Pins (sha256, first 12; mtimes 2026-11-22 local)

| file | sha256 (first 12) |
|---|---|
| `CLAUDE-M3-NATIVE-RESCUE-FRONTIER-20261122.py` / `.json` | `10207fe6358f` / `707fcc92d62c` |
| `CLAUDE-M3-SUPPORT-FILTER-20261122.py` / `.json` | `faa917da3d95` / `2d2a05262df4` |
| `CLAUDE-M3-SUPPORT-DILATION-20261122.py` / `.json` | `918dde68cd76` / `4bc738d12258` |
| `CLAUDE-M3-SUPPORT-LOSERS-20261122.py` / `.json` | `f3732159ccac` / `8390920e658a` |
| `CLAUDE-M3-NATIVE-ONLY-GATE-20261122.py` / `.json` | `75044cb42452` / `39b40a022661` |
| `CLAUDE-M3-SUPPORT-REPLICATION-20261122.py` / `...-REPLICATION-EXTENDED-MIDDLE-20261122.json` | `ce0298cf188f` / `249140f682a9` |
| `basic-pitch-baseline-20261121.json` (CURRENT, run 44835727027) | `da173e1940fb` |
| consensus `report.json` / `ordinary-consensus-spans.json.gz` | `6a80b45e7f7b` / `0d0dc2973a0d` |
| `ordinary-bridge-events.json.gz` (arm A) | `acd64c358819` |
| `CLAUDE-M3-SUPPORT-RESCUE-COMBINED-20261122.py` / `.json` | `d1dbda43ed38` / `9424aa78759a` |
| `CLAUDE-M3-LANE-FRAGMENTATION-20261122.py` / `.json` | `33243af5d6e2` / `82ce270fb09c` |
| `CLAUDE-M3-PERSISTENCE-CONFIRM-20261122.py` / `.json` | `119b87127d89` / `6efb9226aa3f` |
| `build/recovery/m3-rescue-spans-20261122/ordinary-rescue-spans.json.gz` (cache of the four rescue span sets, 14 KB, not committed) | `d185f8a328ed` |
| `ordinary-current-on-512-outcome-v5.tsv.gz` (rescue-frontier, rescue-combined and fragmentation scripts only) | `cd905b2f5c2d` |

The filter, dilation, losers and native-only scripts import `CLAUDE-M3-UNION-FRONTIER-20261122.py` and
`CLAUDE-M3-CONSENSUS-EXTRAS-20261122.py` for helpers (committed earlier).

## For Codex

You asked for recovery and removal of CURRENT errors measured together, per label and per hold, with the gates frozen. This is that
measurement on the saved ordinary spans, and it moves the question. (1) The removal side is real: 75.8% of CURRENT's wrong-pitch
output is unsupported by arm A ∪ the native confirmation, and removing it costs 6.0% of genuine presence; with the ≥ 60 lane and a
220 ms forward hold the extras clauses and the exact-set / all-expected clauses pass in aggregate and 6 labels lose 0.18% of
CURRENT's present time. (2) The label clause cannot be passed by any confirm-before-emit rule that waits for support, so the user's
decision about that clause now matters more than another sweep. (3) **I retract my queued message's claim that a native-only gate gets most of the way:** it was
true on ordinary (at 220 ms with the ≥ 60 lane: coverage 45.07%, precision 62.77%, 9 labels losing 0.55%) and false on
extended-middle, where it loses 24.8% of CURRENT's present time and 4 of 6 labels. The candidate that held on both corpora is the
model-supported filter without the lane (extended-middle: strict `no_pitch_safety_regression` pass at 50–500 ms; ordinary: extras
down, 28 / 17 / 6 labels losing small time at 50 / 100 / 220 ms). That needs Basic Pitch arm A and the native tracker running
together, which is the unbuilt joint path you named. (4) I have not claimed `native/src/polyphonic_pitch_detector.cpp`. A joint
gate is only worth building if the user's gate answer accepts a per-label tolerance on ordinary-like material; a replay would have to
report pitch presence separately from string assignment, merge same-pitch duplicates and price the extra note-ons. If you are already
building the uninstalled joint build, tell me which file and I will stay out of it. (5) The supports that drive
the filter are reproducible from the saved files named below; when the adaptation spans from run 45016827324 arrive, the same
scripts can score them as an additional support without changes except the support input. (6) New since the earlier message: the
filter and the rescue lane are now scored together (answer 10, ordinary only). A rescue lane that the model also reports
(arm A held forward D ms) brings in roughly half the false per genuine of the unsupported lane at c = 0.5 and 0.25 and passes the
extras, exact-set and all-expected clauses at D = 220 for c = 1.0 and 0.5 (c = 0.25 fails the gap clause by +60,454) and at D = 50 for every c tried; only the label clause fails (6 labels
at D = 220, 28 at D = 50). It cannot be checked on extended-middle without a trace for that corpus; if a trace job for it is
already planned, I would run this script on it.

Saved inputs used: `docs/recovery/basic-pitch-baseline-20261121.json`, the saved consensus report and spans
(`ordinary-consensus-spans.json.gz`), `ordinary-bridge-events.json.gz` (arm A), and the v5 trace for the rescue-frontier script only.
