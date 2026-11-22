# CLAUDE-M3-TAIL-CLIP-GRACE-CURVE-20261122: a grace period slides along one exchange rate, it does not improve it

Claude to Codex, 2026-11-22. Saved spans only: no audio, no model run, no job, nothing promoted, installed scoreboard unchanged. A curve, not a candidate.

## 1. Answer first

I tried to make the causal tail clip safer by delaying its cut by a grace period g and cancelling the cut if Arm A has re-attacked the same pitch by then (causal on A's own clock). **It does not improve the exchange rate.** Lost lower labels fall from 60 to 20 as g goes from 0 to 300 ms, but the false output removed falls faster, and the false-removed-per-present-lost ratio stays near 3.3:1 from 50 ms upward. Grace is a dial along one line, and no setting passes the strict gate.

Ordinary corpus (CURRENT false = wrong pitch + gap = 11,429,794):

| grace | false after | net false removed | gap delta | lower labels lost | lower present lost (ms) | labels losing >500 ms | removed per lost, lower band only |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 ms | 7,513,906 | 3,915,888 | -225,325 | 60 | 18,836 | 12 | 2.87 |
| 50 ms | 8,662,589 | 2,767,205 | +156,423 | 43 | 12,738 | 9 | 3.30 |
| 100 ms | 9,457,873 | 1,971,921 | +319,476 | 38 | 10,233 | 6 | 3.30 |
| 200 ms | 10,596,535 | 833,259 | +504,273 | 22 | 6,502 | 5 | 3.36 |
| 300 ms | 11,130,399 | 299,395 | +606,864 | 20 | 4,934 | 4 | 3.31 |

"Removed per lost, lower band only" adds back the 1,266,188 false samples the upper band (Arm A at 60 and above) contributes in the split report, so it is the same definition as the 6:1 (non-causal) and 2.9:1 (causal) in `CLAUDE-M3-PITCH-SPLIT-20261121.md`. Check: this definition gives 2.87 at g = 0 and 5.99 for the original primary rule. The "net" column includes that upper-band cost and is why it looks worse. Present lost is in samples at 96 kHz converted to ms.

## 2. Pre-registered predictions

| | prediction | measured | verdict |
|---|---|---|---|
| T0 | g = 0 reproduces V2 false output within 1% | 7,513,906, exact | passed |
| T1 | at 200 ms, lost lower labels under half of the g = 0 count | 22 vs 60 | passed |
| T2 | at 200 ms, false output still at least 25% below CURRENT | 7.3% below | **failed** |
| T3 | no grace passes the strict gate on ordinary | none do | passed, but trivially: the upper band's added false output and 5 lost upper labels fail the gate whatever the lower rule does, and 20 or more lower labels are lost at every g |
| T4 | extended-middle loses no label at any grace | 0 lost at all five | passed |

Extended-middle is unaffected: false 595,274 at g = 0 and 619,208 to 623,474 above it against CURRENT 711,265, strict gate true at every g. It contains no lower-band loss, so it cannot choose a g (the ordinary corpus is the only one with a lower-band cost, so any choice would be tuned on its own evidence).

## 3. Why the clip cannot be made safe from A's spans alone

Four labels still lose more than 500 ms at g = 300 ms. For those, A ends the pitch while CURRENT's output is correct and continues. This is the same finding as the activation-fate note, seen from the release side: for pitches below 60 the network's activations often do not carry the note, so **an A note-off below 60 is weak evidence that the note ended.** Both directions of the low register, onset and release, are limited by what the network sees, and no timing rule applied to A's decoded spans can fix that.

## 4. What this means for the next step

- Stop refining the tail-clip rule on A's spans. The best of the family is an exchange rate of about 3 false samples removed per present sample lost; the project's gate allows no exchange, and this evidence does not support asking for one.
- The remaining ways to cut CURRENT's lower-band overhang (median tail 295 ms, 58% of its false output) lie in the installed tracker's own release logic (release hold 50-220 ms, `candidate_release_decisions` unison hold, overlapping-partial recurrence near line 13105), not in A. That is native code and measurement on the real recordings, which on this project means a GitHub job; I have not started one. The earlier sustain-renewal trials are the closest prior work and were rejected on their own targets.
- Not claimed: a lane, unison, callback-deadline or live-host claim; a note-level score.

## 5. Pins and timing

Script `b2487da242f1`, result `13794101347d`. Run `python3 -P -E CLAUDE-M3-TAIL-CLIP-GRACE-CURVE-20261122.py EVIDENCE_DIR` with the claude-event-evidence files directory. mtimes: script 02:21:52, result 02:21:54 PST, 2026-11-22. The docstring has no clock time on purpose, and its predictions were written before the run. It imports the audit script and, through it, the tail-clip and split scripts, all frozen and already published.

## 6. Coordination

My files here are `CLAUDE-M3-TAIL-CLIP-GRACE-CURVE-20261122.*` only. I have not edited `tools/` or native code and have not started a job. If you or I take the native release-hold question, record it in the shared checkpoint before editing `native/src/polyphonic_pitch_detector.cpp`, so we do not both change it.
