# Restricted union under model delay: the pitch-range partition widens the lag budget

Claude, 2026-11-22. Saved data only: saved arm A spans with pitch >= 60, shifted by L ms, unioned with CURRENT. No audio, model run, job or native edit; nothing promoted. Plan and six predictions: `CLAUDE-M3-RESTRICTED-UNION-DELAY-PREREGISTRATION-20261122.md` (commit 97a6ba3, before the first run). Script `CLAUDE-M3-RESTRICTED-UNION-DELAY-20261122.py` sha256 a5a1ff7e3e7a, output `.json` c606f117bb55; same evaluator as the delay sweep (`CLAUDE-M3-MODEL-DELAY-RESULT-20261122.md`). One cut only (60, the one from my earlier false-output look at this same recording).

## Ordinary corpus (CURRENT: coverage 39.99%, precision 54.20%, exact set 0.60% of annotated, 528 runs)

Restricted union (CURRENT union arm A spans at pitch >= 60, shifted by L), with the full union beside it. It only adds, so no label loses at any L.

| L (ms) | coverage % (full) | precision % (full) | wrong change | gap change | combined false change | exact set % | gain kept |
|---|---|---|---|---|---|---|---|
| 0 | 63.32 (67.52) | 62.37 (60.55) | +5.3% | +29.8% | +13.1% | 14.32 | 100% |
| 50 | 62.11 (65.83) | 61.17 (59.10) | +8.0% | +35.4% | +16.7% | 14.45 | 95% |
| 100 | 60.90 (64.28) | 59.95 (57.59) | +12.0% | +38.4% | +20.4% | 14.35 | 90% |
| 150 | 59.55 (62.65) | 58.58 (55.79) | +16.4% | +42.3% | +24.6% | 13.70 | 84% |
| 200 | 58.15 (60.98) | 57.15 (53.73) | +21.3% | +45.8% | +29.0% | 12.82 | 78% |
| 250 | 56.76 (59.27) | 55.72 (51.52) | +26.9% | +47.6% | +33.4% | 11.94 | 72% |
| 500 | 49.41 (50.66) | 48.34 (40.47) | +57.7% | +53.1% | +56.2% | 5.12 | 40% |
| 1000 | 45.09 (46.39) | 43.98 (32.76) | +81.1% | +46.0% | +70.0% | 1.61 | 22% |

Reading: dropping the model's spans below pitch 60 costs 3.4 to 4.2 points of coverage at small lag (63.3 against 67.5% at L = 0) and buys precision at every lag. The precision crossover with CURRENT (54.20%) moves from between 150 and 200 ms for the full union to between 250 and 500 ms here (55.72% at 250). At 100 ms the restricted union has 60.9% coverage, 60.0% precision and a 14.4% exact set, better on precision and exact set than the full union at the same lag. It is still a union: the combined false output rises at every lag (+13.1% at L = 0, mostly late tails in the gaps, +29.8% gap voice), so the strict extras clause is still unmet and nothing about the label-rule question changes.

## Extended-middle (all labels pitch 52; check only)

The restricted union adds no coverage there (97.49% at every L) and only false output: wrong-pitch change +2.8% at L = 0 rising to +25.5% at 1000 ms, precision 73.97% (CURRENT) to 73.57% at L = 0 and 70.39% at 1000 ms. My plan called this check vacuous; it is not, it shows what the model's >= 60 spans cost when the notes are low: a little false output and no gain. No labels lose.

## Predictions, as registered: 6 of 6 pass

E0 reproduces the earlier restricted numbers (63.32%, 62.37%, +13.1%). E1 holds on ordinary (precision above and coverage below the full union at every L; on extended-middle the restricted precision is up to 0.16 pp lower than the full union's at L = 0, 50, 250, 500 and 1000, which I did not claim). E2 precision above 54.20% at 200 ms (57.15%) and below it at 500 ms (48.34%). E3 no label loses at any L. E4 combined false +20.4% at 100 ms (limit +25%). E5 gain kept at 250 ms is 72% (full union 70%).

## What this means

- For the one route that moves coverage, the lag budget goes from about 150 ms (full union) to about 250 ms (pitch >= 60 only) at the price of about 4 points of coverage: that matters because it makes a real-time ONNX run easier to satisfy, not because it changes the decision.
- It matches the user's own framing: each tuner locks to the string or pitch range it is set to. A pitch-range partition (CURRENT below 60, the model's spans at 60 and above added) is the reading the data supports; it is a design hint from one recording used in design, not a result for new material, and not a gate pass.
- Remaining false output is mainly model tails after a note ends, which the model's own release handling decides; no label-free fix is known (my earlier gate scan found none cheap).

## Caveats

Fixed pure shift; one recording per corpus; the cut at 60 was chosen from earlier looks at this same ordinary recording, so a held-out recording would be needed before any cut is trusted. 150 and 200 ms are in the registered grid here but were post hoc in the full-union sweep. No string, lane, unison, native deadline or live-host claim.
