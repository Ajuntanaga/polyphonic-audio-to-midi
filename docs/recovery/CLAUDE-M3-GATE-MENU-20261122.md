# What each label-clause rule would admit: a decision menu (not a gate, not a pass)

Claude, 2026-11-22. Saved data only; no audio, model run, job or native edit; nothing promoted; Codex's frozen gates are untouched. The open decision is the user's: the strict gate asks that no label lose any present or longest-hold time AND that wrong-pitch and gap output never rise. This table shows, for every saved candidate, what it gives and how many labels each per-label tolerance would reject, so the choice can be made on the numbers. The tolerance grid (0, 1, 5, 10, 25, 50% of a label's own CURRENT present time or longest hold) was fixed in the script before the run. All figures are one recording per corpus, both used in earlier design.

Script `CLAUDE-M3-GATE-MENU-20261122.py` (sha256 first 12 `09207cb64a65`), JSON `CLAUDE-M3-GATE-MENU-20261122.json` (`09ab07fcac5f`). Sources: CURRENT and labels from the baseline, arm A from the saved ONNX offline causal run (not a real-time measurement), the adapted rows from Codex's adapted-TF events on the zero-compute availability clock (content only; the measured completion clock is dominated by a ~72 s backlog), the native confirmation from the saved consensus spans.

## Ordinary (CURRENT: coverage 39.99%, precision 54.2%, exact set 0.6% of annotated samples, 528 runs)

| candidate | coverage | precision | wrong-pitch vs CURRENT | gap voice vs CURRENT | exact set | runs | labels losing anything | labels over 1 / 5 / 10 / 25 / 50% |
|---|---|---|---|---|---|---|---|---|
| Basic Pitch arm A, replacement | 54.95% | 73.86% | −61.5% | −1.5% | 9.89% | 596 | 198 | 192 / 166 / 134 / 85 / 64 |
| adapted TF, replacement (availability) | 71.88% | 76.73% | −71.4% | **+41.9%** | 37.59% | 611 | 166 | 159 / 125 / 78 / 20 / 9 |
| CURRENT ∪ arm A (additive) | 67.52% | 60.55% | **+23.8%** | **+43.7%** | 12.92% | 743 | **0** | 0 / 0 / 0 / 0 / 0 |
| filter arm A + native, D = 220 | 39.92% | 58.93% | −22.2% | −8.0% | 0.6% | 480 | 6 | 3 / 3 / 2 / 1 / 1 |
| filter arm A + native, D = 50 | 39.59% | 67.45% | −56.1% | −16.2% | 0.6% | 555 | 28 | 24 / 19 / 13 / 5 / 4 |
| filter adapted + native, D = 220 | 39.97% | 59.19% | −22.6% | −9.5% | 0.6% | 520 | 5 | 2 / 2 / 1 / 0 / 0 |
| filter adapted + native, D = 50 | 39.79% | 66.16% | −52.0% | −13.4% | 0.6% | 567 | 20 | 17 / 14 / 10 / 3 / 2 |

## Extended-middle (CURRENT: coverage 97.49%, precision 73.97%, exact set 73.15%, 14 runs, 6 labels)

| candidate | coverage | precision | wrong-pitch vs CURRENT | gap voice vs CURRENT | exact set | runs | labels losing anything (largest) |
|---|---|---|---|---|---|---|---|
| Basic Pitch arm A, replacement | 97.97% | 84.50% | −50.6% | −39.1% | 85.38% | 14 | 5 (0.98%) |
| adapted TF, replacement (availability) | 98.16% | 71.55% | **+30.4%** | −34.1% | 66.28% | 21 | 5 (0.66%) |
| CURRENT ∪ arm A | 98.62% | 73.73% | +3.3% | 0.0% | 72.31% | 17 | 0 |
| filter arm A + native, D = 220 / 50 | 97.49% | 78.53% / 80.22% | −26.0% / −32.2% | −11.7% / −23.4% | 79.77% / 81.35% | 14 | 0 |
| filter adapted + native, D = 220 / 50 | 97.49% | 78.07% / 79.91% | −26.0% / −29.5% | −3.3% / −25.9% | 79.77% / 80.65% | 14 | 0 |

## What the menu says

- **A replacement is far from any label tolerance**: arm A used alone costs 198 labels some time (85 lose more than a quarter of their own present time), the adapted model 166 (20 lose more than a quarter, 9 more than half). The gain is real (coverage +15 to +32 points, precision 54% → 74 to 77%, exact set 0.6% → 10 to 38% of annotated samples) but it comes with per-label losses no small tolerance covers, and the adapted model adds gap voice (+41.9%).
- **The additive union loses no label at any tolerance and raises coverage 39.99% → 67.52%, exact set 0.6% → 12.9% and precision 54.2% → 60.55%**, but the absolute wrong-pitch and gap-voice samples rise (+23.8% and +43.7%), so it fails only the strict extras clause. A rule that judges by coverage and precision together, with no label loss, is the one rule that admits it; it needs Basic Pitch running live next to the tracker.
- **The filters remove false output without adding any, but cannot cover all labels**: the adapted-support filter at D = 220 has 5 labels losing something, 2 over a 5% tolerance, 1 over 10% (label 263, 10.2%) and none over 25%; arm A's filter at D = 220 still has one label over 50% (label 229, 79.7%). At D = 50 the removal is much larger (wrong-pitch −52 to −56%, precision 66 to 67%) and 20 to 28 labels lose time, 2 to 4 of them more than half.
- **Extended-middle does not conflict**: every filter passes the strict rule there; the conflict is a property of the ordinary recording's short struck notes, whose first tens of milliseconds are unconfirmed.
- What this menu cannot say: strings, unison multiplicity, native deadlines, real-time pace of any model, or how a person would hear the difference. One recording per corpus, both used in design.

## The decision this leaves to the user (three plain options)

1. **Keep the strict rule**: nothing saved passes; the additive union is rejected on extras, every filter on labels.
2. **Allow a small per-label loss** (a number you fix before we evaluate anything further; for orientation from the grid above, the adapted-support filter at D = 220 has 2 labels over at 5%, 1 over at 10% and none over at 25% on ordinary, and none on extended-middle): the filter needs a live model.
3. **Judge by coverage and precision with no label loss and allow absolute extras to rise**: the additive union passes (+27.5 points coverage, +6.4 points precision, no label loses time); it needs a live model too.

Neither route is buildable until a model runs in real time next to the native tracker (Codex's ONNX conversion lane, 45022754580 failed its first interface check and is being retraced). Any chosen rule would be a new frozen gate evaluated on a held-out recording, not on these two.

## Addendum, same day: what a live model has to deliver (`CLAUDE-M3-MODEL-DELAY-RESULT-20261122.md`)

Shifting the saved arm A spans by L ms: the union (option 3) keeps its advantage over CURRENT on coverage, precision and exact set only while the model's extra lag is under about 150 ms (precision 57.6% at 100 ms, 55.8% at 150, 53.7% at 200, below CURRENT's 54.2% from there; coverage still 59.3% at 250 ms), and is a poor trade at 500 ms or more. The filter (option 2) works without any model (native confirmation alone: 9 losing labels, 28% cleanup); a model within about 100 ms of lag trims that to 6 losing labels, and under arm A label 229 (79.7%) stays lost at every lag, so a 25% per-label tolerance is met only by the adapted model's events, which Codex's screen rejected. Option 3 therefore commits the project to a real-time model with a tight lag budget; options 1 and 2 do not.
