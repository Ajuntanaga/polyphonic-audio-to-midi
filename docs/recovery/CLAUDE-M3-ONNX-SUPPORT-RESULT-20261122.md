# Cropped-ONNX events as the CURRENT filter's support, on the measured emitted clock: result

Claude, 2026-11-22. Pre-registration: `CLAUDE-M3-ONNX-SUPPORT-PREREGISTRATION-20261122.md` (commit `6d78489`, written before any event was opened). Saved events and saved spans only; no audio, model run, job or native edit; nothing promoted; installed scoreboard unchanged.

## Answer

**By the reading rule fixed in advance, the faster cropped-ONNX path retains the proposed cleanup benefit**, for both the unmodified and the adapted events. At D = 220 on ordinary, with the model events at their measured emitted clock (per-event lag 10.1 to 14.7 ms, inside Codex's 24.28 ms bound):

| Support (D = 220, ordinary; CURRENT coverage 39.9932%) | Coverage | Precision | Wrong-pitch removed | Gap delta | Labels losing | Over the frozen budget | Strict gate |
|---|---:|---:|---:|---:|---:|---:|---|
| arm A (saved ONNX offline causal run) | 39.923 | 58.93 | 22.15% | -291,474 | 6 | 3 | False |
| cropped unmodified | 39.923 | 58.94 | 22.17% | -291,595 | 6 | 3 | False |
| cropped adapted | 39.966 | 59.12 | 22.28% | -344,176 | 5 | 2 | False |
| arm A union cropped adapted | 39.966 | 58.49 | 19.79% | -291,218 | 5 | 2 | False |

Extended-middle, D = 220: every support keeps coverage 97.488% with 0 labels losing, strict gate True and the budget met (precision 78.53% unmodified, 78.01% adapted; wrong-pitch removed 26.0%; gap -21,374 and -4,014).

**Retained is not acceptable.** Under the frozen label budget (25 ms and 5% per label, decided earlier today) both cropped supports still fail on ordinary, and the strict gate still fails. The adapted support leaves two labels over budget: label 263 (pitch 33) loses 34.83 ms (10.18% of its present time) and label 364 (pitch 42) loses 50.57 ms (6.76%, also its longest hold). Its other three losers are within budget (3.32, 0.68 and 5.34 ms). The unmodified support also loses label 229 (pitch 42): 151.99 ms, 79.7% of that note. The adaptation recovers it. No label becomes completely missed under any of them.

So the obstacle for this support is no longer runtime backlog; it is two ordinary labels that the filter clips by 35 to 51 ms. The adapted model's rejection as a replacement stands (Codex's frozen gates); this scores its events only as a support, which is a separate candidate.

## Predictions, scored (each could fail)

| Id | Claim | Odds | Observed | Result |
|---|---|---:|---|---|
| S0 | Files pair-valid, counts 1,192 / 1,223 / 28 / 42 | 75% | all valid, counts equal | hit |
| S1 | Unmodified: 5 to 7 labels, wrong removed 21% to 24% | 70% | 6 labels, 22.17% | hit |
| S2 | Adapted loses no more labels than unmodified | 75% | 5 vs 6 | hit |
| S3 | Adapted removes at least as much wrong output | 60% | 22.28% vs 22.17% | hit (by 0.11 points) |
| S4 | Both lose at most 34 labels at D = 50 | 80% | 28 and 17 | hit |
| S5 | Adapted loses at least 5 labels at D = 220 | 85% | 5 | hit, **rationale wrong** (below) |
| S6 | Extended-middle D = 220 safe for both | 85% | 0 labels, flag True | hit |
| S7 | Both fail the frozen label budget | 80% | 3 and 2 labels over | hit |
| S8 | Adapted coverage 39.946 to 39.986, precision at least 59.0 | 60% | 39.966, 59.12 | hit |

Nine of nine. At the stated odds I expected about 6.7, and the hits are correlated: most predictions leaned on the same availability-clock TensorFlow numbers, so a clean sweep says "the saved-event arithmetic carried over", not that I calibrated well. S5 was stated as "lag can only cost", and that is not what the data show at D = 50: adapted on the emitted clock loses 17 labels, fewer than the 20 on the availability clock. The detector's off events arrive about 10 ms late too, which works like a small extra hold. The threshold held; my reason for it did not.

## Other observations

- **Cropping and backend do not matter for this use.** The cropped unmodified support reproduces arm A almost exactly (596 runs each; 22.17% vs 22.15% removed; the same six D = 220 losers). This repeats the earlier TensorFlow result.
- **D = 50 (ordinary):** unmodified 28 labels losing, 56.2% wrong-pitch removed, coverage 39.586; adapted 17 labels, 50.2% removed, coverage 39.800; maximum loss 421.59 ms on both. The strict gate and the budget both fail there.
- **The model now has a say.** The earlier emitted-clock result was within a label or two of the native-only control because a roughly 72 s backlog pushed model spans past the recording end. Here the unmodified and adapted rows differ from the native-only control by wide margins at D = 50 (28 and 17 labels against the control's 39).
- **Post hoc, labelled:** the same script on `available_ns` (`CLAUDE-M3-ONNX-SUPPORT-20261122-available_ns.json`) gives the same retained reading and the same nine checks. D = 220 numbers match the earlier TensorFlow availability-clock values (adapted: 39.966%, 22.65%, -344,176, 5 labels).

## Limits

Two recordings examined before, so this cannot validate itself. Extended-middle has 28 and 42 events and six labels all at MIDI 52, so it can only show safety. The emitted clock reconstructs FIFO delivery on the worker CPU from a bounded lag; it is not a DAW, device or native-callback measurement, and the per-event lag here (maximum 14.73 ms) is the saved event record, not a new run. D was only 50 and 220. Native-only filtering is still ordinary-specific, as Codex noted (extended-middle coverage 97.49% to 73.33%); this result is about the model-supported filter. No lane, unison, string, MIDI-lifecycle or live-host claim. Nothing here selects anything for native code.

## Provenance and one plumbing note

- Inputs: the four members Codex pinned for artifact 14759705414 (run 45034216124), fetched by HTTP range requests from the user's public CI repository (16 requests, about 41 KB of compressed payload; Codex's 28.8 MB transfer had timed out) and each checked against the pinned SHA-256 before use: `unmodified_cropped/ordinary-events.json` `c1c48293b6c9`, `adapted_cropped/ordinary-events.json` `4e0601c42dbd`, `unmodified_cropped/extended-middle-events.json` `18b235815be2`, `adapted_cropped/extended-middle-events.json` `1eea72fdc62b`. They are kept, with a hash manifest, under `build/github-results/basic-pitch-temporal-crop-45034216124/claude-range-members/` (a new folder; Codex's receipt and collection files are untouched).
- Script `CLAUDE-M3-ONNX-SUPPORT-20261122.py`, sha256 `a1cf6c1b66b5` as committed with this note. The first run crashed in `predictions()` before writing any output (it iterated the result dictionary's keys, which included the string `clock`); I fixed the loop to name the two corpora and re-ran. Nothing else, no threshold, prediction or rule, changed after the pre-registration commit.
- Outputs: `CLAUDE-M3-ONNX-SUPPORT-20261122.json` (emitted clock, the registered view) and `CLAUDE-M3-ONNX-SUPPORT-20261122-available_ns.json` (post hoc).
