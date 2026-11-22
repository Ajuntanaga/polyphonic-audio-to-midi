# Release probe result: the adapted model does not hold longer than the original on synthetic tones

Claude, 2026-11-22. One CPU run on the public worker, no retry, nothing promoted, no gate touched. Plan and predictions: `CLAUDE-M3-RELEASE-PROBE-PROPOSAL-20261122.md` (c2ceb1b); exact treatments fixed before the run: `CLAUDE-M3-RELEASE-PROBE-TREATMENTS-20261122.md` (7089b21); code, 40 pure tests and spec: 101cef2. Run 45031841272 (source 101cef2, evidence from Codex's run 45029161409 with both model hashes verified before inference, 30 s, the 40 tests re-run green in the job). Compact report kept in the repo as `CLAUDE-M3-RELEASE-PROBE-REPORT-45031841272.json` (sha256 c122264b760c); full outputs for all 50 windows are in the worker artifact `m3-basic-pitch-release-probe-outputs-45031841272-1` (14 days).

## Answer first

**The probe does not reproduce the lengthening. On a synthetic tone the adapted model releases no later than the original after an abrupt cut, and no later on a smooth decay. P0, P1 and P3 miss as registered; P2 is not evaluated because P1 is not a pass.** Under the reading rule I registered for "P1 false" (the probe is not representative of the real-audio tail), this probe cannot be used to choose between an abrupt-end exposure and a decay-shaped end or teacher term. It supports neither. Codex's fit choice is not informed by it, and I am not recommending one from it.

## Registered predictions, judged as registered

| | prediction | result |
|---|---|---|
| P0 | abrupt end: adapted and original release delays differ by at most 25 ms at every pitch | **miss.** Differences (adapted minus original) at MIDI 45/52/59/66: -34.8, +23.2, +11.6, -11.6 ms. Only pitch 45 exceeds 25 ms and there the adapted model is *earlier*. The signs are mixed, so the "adapted releases later on abrupt cuts" branch of my reading is not supported either. One frame is 11.6 ms. |
| P1 | smooth decay: adapted release level at least 3 dB lower than the original's, for at least 2 of 3 taus, at at least 3 of 4 pitches | **miss.** 0 of 4 pitches count. At tau 0.1 the adapted release levels are -61.4/-58.4/-56.3/-55.3 dB against -63.4/-63.4/-62.4/-62.4 dB for the original: shallower, not deeper. |
| P2 | (only if P1) at tau 0.2 the adapted delay exceeds the original's by at least 30 ms at 3 of 4 pitches | **not evaluated** (P1 not a pass). For the record the delays differ by -46/-23/+12/-12 ms at tau 0.2, and every tau 0.2 release but one is edge-affected (below). |
| P3 | per model, releases at pitches 52 and 59 differ by at most 3 dB in level at every evaluable tau | **miss.** Original: -0.0/-1.0/+1.0 dB at tau 0.05/0.1/0.2. Adapted: -4.0/-2.0/+2.5 dB; the tau 0.05 miss is two frames (23 ms: 335 ms at 59 against 358 ms at 52; one frame is 2.0 dB at that tau). tau 0.4 is excluded (pitch 59 censored in both). |

Per-pitch tables (all cases, all pitches, both models), from `CLAUDE-M3-RELEASE-PROBE-TABLES-20261122.py`; `*` marks a release frame of 165 or more (edge-affected) and `>=`/`<=` a censored bound:

| original | MIDI 45 | MIDI 52 | MIDI 59 | MIDI 66 |
|---|---|---|---|---|
| abrupt | 80 ms | 68 ms | 45 ms | 45 ms |
| decay tau 0.05 | 370 ms / -64.3 dB | 358 / -62.3 | 358 / -62.3 | 347 / -60.3 |
| decay tau 0.1 | 730 / -63.4 | 730 / -63.4 | 718 / -62.4 | 718 / -62.4 |
| decay tau 0.2 | 1032* / -44.8 | 1043* / -45.3 | 1067* / -46.3 | 1067* / -46.3 |
| decay tau 0.4 | 1067* / -23.2 | 1078* / -23.4 | >=1078 / <=-23.4 | >=1078 / <=-23.4 |

| adapted | MIDI 45 | MIDI 52 | MIDI 59 | MIDI 66 |
|---|---|---|---|---|
| abrupt | 45 ms | 91 ms | 57 ms | 33 ms |
| decay tau 0.05 | 440 ms / -76.4 dB | 358 / -62.3 | 335 / -58.2 | 324 / -56.2 |
| decay tau 0.1 | 707 / -61.4 | 672 / -58.4 | 649 / -56.3 | 637 / -55.3 |
| decay tau 0.2 | 985 / -42.8 | 1020* / -44.3 | 1078* / -46.8 | 1055* / -45.8 |
| decay tau 0.4 | 1043* / -22.7 | 1055* / -22.9 | >=1078 / <=-23.4 | >=1078 / <=-23.4 |

Controls: the silence window gives a maximum note probability of 0.16 (original) and 0.03 (adapted), both below the 0.3 threshold; every sustained tone is detected by both models (plateau at frame 78, post hoc below: original 0.79-0.80, adapted 0.99). The report's `note_at_end` field is the last window frame, an edge frame, and understates the plateau; ignore it.

## Post hoc readings (labelled post hoc; not registered)

All from the saved outputs with `CLAUDE-M3-RELEASE-PROBE-POSTHOC-20261122.py` (json beside it).

1. **Direction.** Over the 18 comparisons where both models are active and uncensored, the adapted release is earlier in 13, later in 4, equal in 1; mean difference -18.7 ms. Tau 0.1 is the clearest: earlier at all four pitches by 23 to 81 ms. Nothing here is an adapted-later signal.
2. **Shape, not time, is what differs.** The adapted note output is a saturated switch: 0.99 at frame 78 (original 0.80), then a short fall. From 0.9 of the plateau to the 0.3 threshold the adapted output takes 5 to 7 frames at tau 0.05 and 12 to 19 frames at tau 0.1; the original takes 17 to 21 and 39 to 44 frames. Both cross 0.3 at nearly the same moment.
3. **Both models hold a decaying tone down to about -55 to -64 dB.** At tau 0.05 and 0.1 the release delay is 6.5 to 8.8 time constants for both models (the original 7.2 to 7.4), i.e. a roughly fixed level, not a fixed time. Hypothesis, not tested here: the graph normalizes each window's log spectrum by that window's own minimum and maximum (the `normalized_log` boundary Codex's constant-window correction guards), and my synthetic windows have exact-zero lead-in, so the floor the tone is measured against is far lower than any recording's noise floor. If that is right, the release levels measured here would be much shallower on real audio and the probe says little about real tails. A floor variant of the probe is the direct test.
4. **Only tau 0.05 and 0.1 are clean.** At tau 0.2 and 0.4 almost every release lands on frame 165 or later (the window edge, past the causal readout frames), so those cells are flagged and weak.

## What this does and does not say

- It says the adapted model's extra real-audio gap output (carried-in tails, 96.6% of the added gap; still sounding at gap end 59.2% against 21.5%) is not the adapted model holding a plain decaying tone deeper than the original does. On a plain tone it does not.
- It does not say the real tails are not a fault, and it does not say what causes them. Candidates the probe cannot separate: more notes sounding at the label end (adapted-only notes carry 25% of the added gap), the saturated plateau carrying a note across a label end, and interactions with real noise floors, polyphony and the window normalization.
- Caveats: synthetic harmonic tones (1 to 6, 1/k), noise-free, exact-zero lead-in, one window position, one run, 11.6 ms frame resolution, a 3 dB bar that is only 1.5 frames at tau 0.05 and 3 frames at tau 0.1, and edge frames at the slow decays. Not guitar audio and not a gate.

## Suggested next steps (not run; Codex's call, or mine on a scoped job)

1. **Floor variant, registered first.** Same tones plus white noise at fixed floors, to test whether release level moves with the window floor (the hypothesis in item 3). About 30 s of CPU; it would be a new registered probe, not a rerun.
2. **Real-audio release curves.** If the corpus tapes in the flat-normalization evidence keep the per-frame note outputs, read the note probability and the audio level around each label end for both models. That asks the original question on real audio instead of on a synthetic tone.
3. Until one of those exists, the fit candidate (abrupt-end boundary views) is unsupported by this probe and should be judged only on its own gates.
