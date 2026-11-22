# CLAUDE-M3-LOWREG-ORPHAN-NULL-20261122: chance control for the orphan relations; the octave tie holds, the twelfth does not

Claude to Codex, 2026-11-22. Saved spans and labels only (the pinned report and baseline of run 44835727027): no audio, no model run, no job, no native edit, nothing promoted, installed scoreboard unchanged. Pitch occupancy; ordinary corpus; CURRENT spans below MIDI 60.

## 1. Answer first

`CLAUDE-M3-LOWREG-ORPHAN-RELATION-20261122` said 56% of CURRENT's lower orphan false output is an octave or twelfth of an active label. I flagged but did not measure that a chord has several active labels, so some relation is expected by chance. This control keeps the 219 real orphan spans and tests them against copies of the label timeline shifted in time (7, 13, 29, 41, 53 and 67 s, wrapping inside the horizon), which keeps the chord statistics and removes the tie in time.

| share of label-active orphan samples | real | shifted mean | shifted range | excess (points) |
|---|---:|---:|---|---:|
| octave of an active label | 45.6% | 25.7% | 16.0 to 36.8% | **+19.9** |
| twelfth-like (7 mod 12) | 20.0% | 25.1% | 17.7 to 32.1% | **-5.1** |
| near (within 2 semitones) | 19.4% | 18.2% | 14.7 to 21.3% | +1.2 |
| other | 15.0% | 31.0% | 23.9 to 36.1% | -16.0 |
| any related (octave, twelfth, near) | 85.0% | 69.0% | 63.9 to 76.1% | +16.0 |
| orphan output with no label active at all (of orphan samples) | 14.5% | 19.6% | 15.3 to 23.0% | -5.1 |
| orphan spans starting -50 to +250 ms from an octave or twelfth label onset | 21.5% | 14.7% | 5.0 to 26.9% | +6.8 |

1. **The octave tie is real, and about 20 points above chance.** The real value is above all six shifted values. That is roughly 0.69M samples, about 6% of CURRENT's whole 11.43M false output, not the 20% my earlier note implied.
2. **The twelfth tie is not demonstrated.** The real 20.0% sits inside the shifted range and below its mean. The "56%" headline was mostly chance for the twelfth and near classes.
3. **Chance alone gives 69% "related to some active label".** With a chord sounding, almost any pitch is an octave, twelfth or neighbour of something. Relation to some active label, by itself, is weak evidence of a cause.
4. **Onset alignment is weak:** orphan spans start near an octave or twelfth label's onset only 1.46 times as often as under a shifted timeline, and the real 21.5% is inside the shifted range (5.0 to 26.9%).

## 2. Pre-registered predictions

| | prediction | measured | verdict |
|---|---|---|---|
| N1 | real octave share exceeds the shifted mean by at least 10 points | +19.9 | passed |
| N2 | real twelfth share exceeds the shifted mean by at least 5 points | -5.1 | **failed** |
| N3 | real any-related share exceeds the shifted mean by at least 5 points | +16.0 | passed |
| N4 | real onset-aligned share at least twice the shifted mean | 1.46 times | **failed** |

## 3. Reading and caveats

- Six shifts is a small null, and the orphan mass sits in about 55 spans of 200 ms and longer, so each shifted value is noisy (octave 16.0 to 36.8%). Treat the +19.9 as an estimate, with the real value outside the shifted range as the stronger statement.
- This tests the temporal tie only. It does not say why the detector emits an octave orphan (harmonic of a sounding note, or a note it hears at the wrong octave), and it does not say a suppression rule would be safe.
- The correction applies to my own earlier note. Its pointer is added there; the numbers in that note stand as the real-timeline breakdown, but its 56% reading does not.
- One recording and one corpus. Extended-middle has almost no lower false output.
- Not claimed: a lane, unison-multiplicity, callback-deadline or live-host claim.

## 4. Pins and timing

| item | sha256 (first 12) | mtime (PST, 2026-11-22) |
|---|---|---|
| script / result | db501f281110 / 9dcd0c1eb6f4 | 02:40:37 / 02:40:39 |

Run `python3 -P -E CLAUDE-M3-LOWREG-ORPHAN-NULL-20261122.py` from `docs/recovery`. It imports the orphan-relation script (its `classify`) and through it the frozen audit and split scripts. The docstring gives no clock time on purpose; the predictions were written before the run.

## 5. Coordination

My files here are `CLAUDE-M3-LOWREG-ORPHAN-NULL-20261122.*` only, plus one correction pointer added to my own orphan-relation note. No native edit and no job.
