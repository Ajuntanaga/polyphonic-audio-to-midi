# Presence at the label end follows how loud the note is (post hoc, saved data only)

Claude, 2026-11-22. **Post hoc and descriptive**: not registered, no new measurement, no audio opened. Inputs are the committed ends file (groups from the saved tapes of run 45029161409) and the committed level curves of the registered audio-level read (run 45034800737, `CLAUDE-M3-AUDIO-RELEASE-RESULT-20261122.md`). Script `CLAUDE-M3-LEVEL-DEPENDENCE-20261122.py`, output `CLAUDE-M3-LEVEL-DEPENDENCE-RESULT-20261122.json` (sha256 `fd23b7845690895f591a16e43df26b50cbbe3f1fbdccc6062b363e4060dedb67`).

## Answer

Whether a model still shows presence at the end of a label depends strongly on the narrowband level of the note just before the end, and that is a better predictor than pitch. Ordinary corpus, all 428 evaluable ends, `pre` = level of the 80 ms before the label end at the pitch's first harmonics (dB re full scale):

| `pre` | n | adapted present | original present |
|---|---:|---:|---:|
| below −70 dB | 29 | 0% | 0% |
| −70 to −60 | 71 | 17% | 1% |
| −60 to −50 | 56 | 61% | 25% |
| −50 to −40 | 144 | 70% | 33% |
| −40 to −30 | 128 | 93% | 48% |

- **Level, not just pitch.** The probability that an end with presence is louder than one without (AUC): adapted 0.85 for level, 0.71 for lower pitch; original 0.745 and 0.55. Within a pitch band the level effect stays: adapted AUC 0.81 (MIDI < 48), 0.80 (48–59), 0.93 (60–71), 0.87 (72+). Example, MIDI 60–71: presence 7% below −60 dB, 54% at −60 to −50, 97% at −50 to −40 (adapted).
- **The `neither` group is mostly the quiet ends.** Median `pre` of `neither` is −61 dB against about −40 dB for the other groups; 100 of the 428 ends sit below −60 dB and the adapted model shows 12 of them.
- **High notes are the quiet ones here.** Median `pre` by band: −38.6 dB (MIDI < 48), −42.2 (48–59), −56.3 (60–71), −65.5 (72+), with adapted presence 82%, 66%, 46% and 42%. Part of the known weakness on upper strings may therefore be a level effect.

## What this does not show

- The level here is absolute (dB re full scale at one pitch), but a model that normalises inside its window would respond to the level **relative to the loudest content in that window**. I cannot compute that from these curves, so absolute level may be standing in for relative level and for polyphony (quiet notes sounding next to loud ones).
- "Present at the label end" mixes detection and release timing; this is not note-level recall. One recording, ends within a take are not independent.
- It says nothing about cause, and it does not change any gate or the installed tracker.

## Question for Codex (no gate, your lane)

Does the streaming path's front end normalise per window (min-max over the window's log spectrum, as in the original Basic Pitch layer) or against a fixed reference? That decides which lever is real:

- **Per-window normalisation:** an input gain would change nothing and a quiet note is judged against the loudest content in its 2 s window; the lever, if any, is spectral weighting or masking, tested on synthetic two-tone windows (same quiet tone alone and next to a tone 20 and 35 dB louder; a pure gain sweep on one tone as the invariance check).
- **Fixed reference:** quiet high notes lose contrast in absolute terms and an input-level stage in front of the model is worth one bounded GitHub contrast.

I will write either spec if you want it; nothing is queued for a run from my side.
