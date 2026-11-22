# Pre-registration: the cropped-ONNX events as the support of the CURRENT filter, on the measured emitted clock

Claude, 2026-11-22. Written and committed before any of the four event files was opened; the commit time is the record. Nothing here is a result.

## Why this, and what I have and have not seen

`CODEX-M3-ONNX-EVENT-LATENCY-20261122.md` bounds the added FIFO lag of the completed temporal-crop run 45034216124 at 24.28 ms for every detector event (ordinary unmodified 24.28, adapted 15.16, extended-middle 11.58 and 11.80 ms) and asks whether the faster implementation keeps the proposed cleanup benefit. My earlier emitted-clock result (`CLAUDE-M3-ADAPTED-SUPPORT-RESULT-20261122.md`) was dominated by a roughly 72 s TensorFlow backlog that pushed model spans past the recording end, so the model had almost no say; this run removes that backlog. It is the first emitted-clock score where the model can contribute.

Inputs: the four compact event members Codex pinned for artifact 14759705414 (`unmodified_cropped` and `adapted_cropped`, ordinary and extended-middle; 166,525 / 170,851 / 4,379 / 6,330 bytes). Codex's local transfer of the 28.8 MB archive timed out, so I fetched only those four members from the artifact's zip by HTTP range requests (16 requests, about 41 KB of compressed payload), from the user's own public CI repository, and verified each member's SHA-256 against Codex's pin before writing it. All four matched. **I have checked sizes and hashes only; no event has been read.** What I know from the notes: event counts (1,192 / 1,223 / 28 / 42), the lag bounds above, and the earlier availability-clock results of the TensorFlow events (the numbers the predictions lean on).

## What will be scored

The committed scorer `CLAUDE-M3-ADAPTED-SUPPORT-20261122.py` and loss table `CLAUDE-M3-ADAPTED-SUPPORT-LOSERS-20261122.py`, unchanged, through `CLAUDE-M3-ONNX-SUPPORT-20261122.py`: support = model spans union the native confirmation, held forward D ms, filter = CURRENT intersect support; D in {50, 220}; both corpora; four supports (arm A, cropped unmodified, cropped adapted, arm A union cropped adapted). Primary clock `emitted_ns`. A run on `available_ns` is post hoc and labelled as such.

## Frozen label rule (decided earlier today, before this run)

`CLAUDE-M3-LABEL-RULE-DECISION-20261122.md`: per label, present-time and longest-hold loss at most 25 ms and at most 5% of that label's own CURRENT value; no label CURRENT detects may become completely missed; wrong-pitch and gap output may not grow. The strict gate (`no_pitch_safety_regression`) is reported beside it, never replaced by it.

## Predictions, each can fail (D = 220 on ordinary unless stated)

| Id | Claim | Odds |
|---|---|---:|
| S0 | All four files pair-valid and event counts equal Codex's 1,192 / 1,223 / 28 / 42 | 75% |
| S1 | Cropped unmodified: 5 to 7 labels losing, wrong-pitch removed share 21% to 24% (arm A: 6 labels, 22.15%) | 70% |
| S2 | Cropped adapted loses no more labels than cropped unmodified (availability-clock TF: 5 vs 6) | 75% |
| S3 | Cropped adapted removes at least as large a share of wrong-pitch output as cropped unmodified (22.65 vs 22.40 on the availability clock) | 60% |
| S4 | The model has a say: both cropped supports lose at most 34 labels at D = 50 (native-only control 39, 72 s backlog 38) | 80% |
| S5 | Emitted lag costs: cropped adapted loses at least 5 labels (the availability-clock count) | 85% |
| S6 | Extended-middle, D = 220: both cropped supports 0 labels losing and the strict safety flag True | 85% |
| S7 | Both cropped supports FAIL the frozen label budget at D = 220 on ordinary (the largest earlier losers were 50.57 ms and 10.18%) | 80% |
| S8 | Cropped adapted coverage 39.946 to 39.986% and precision at least 59.0% (availability-clock TF adapted: 39.966%, 59.19%) | 60% |

## Reading rule (fixed now)

**Cleanup benefit retained** for a cropped support only if, at D = 220: ordinary coverage within 0.10 points of CURRENT (39.9932%), wrong-pitch removed share at least 20%, gap output down by at least 250,000 samples (arm A: -291,474), and extended-middle has 0 labels losing with the strict safety flag True. Otherwise **not retained**. Judged separately for the unmodified and the adapted events. The label-budget result is reported next to it and does not change it.

## What cannot be concluded

This scores the events as a support on two recordings that were examined before; it is not the adaptation's acceptance (Codex's frozen gates decide that, and the adaptation was rejected), not a tracking result, and says nothing about native deadlines, strings, DAW or device latency, or live delivery. The lag bound is an upper bound on added FIFO delay, not a measured percentile; the emitted clock here reconstructs FIFO delivery on the worker CPU, not a host. A "retained" reading would mean only that the saved-event arithmetic holds up under that bound; it would not make the support acceptable, and it would not make the native-only filter a model-free alternative on both corpora (extended-middle coverage loss stays as Codex noted). Any grid value other than D in {50, 220} and any lane variant would be post hoc and labelled.
