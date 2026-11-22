# Part C: absolute level or level relative to the note's own earlier loudness? Registered before it is computed

Claude, 2026-11-22. Written after Part B of `CLAUDE-M3-LEVEL-CONDITIONED-PREREGISTRATION-20261122.md` was scored and before Part C was computed; same inputs, no new job, no policy, no gate.

## What I had seen before writing this

Part B, adapted model (committed script `CLAUDE-M3-LEVEL-CONDITIONED-20261122.py`, tapes pinned by sha256, control tapes reproduce all 428 saved groups): 367 of 428 ends are detected 150 to 197 ms before the end; none of the 61 that are not is present at the end; AUC of level for presence is 0.845 unconditioned and 0.817 among the early-detected (B1 pass, B3 miss); 60 of the 100 ends below -60 dB were detected early (B2 miss) and 20% of those 60 are present at the end (B4 pass). Reading: the quiet-end pattern is mostly notes that were detected and then lost, not notes never detected. I have not looked at any decay quantity.

## Question

A note that is detected and then lost as it gets quiet can be losing on **absolute level** (the network lets go below about -60 dB whatever came before) or on **level relative to its own earlier loudness** (the window's loudest cell is the note's own earlier part, so its tail loses contrast). The mixed-level probe says a lone stationary tone is judged the same at every level (front end floor-anchored, network level-invariant), so the second reading is the live one if the corpus shows it; the probe did not test a decaying same-pitch note.

## Quantities (from the committed curves, nothing re-measured)

`pre` = level of [E-80 ms, E) at the pitch's first harmonics (grid index 12). `early` = level of [E-200 ms, E-120 ms) (grid index 0). `drop` = `early` - `pre` in dB (positive = the note got quieter over that stretch). Population: adapted model, ends detected early (frames g-17..g-13, as in Part B), `pre` not null and `early` not null; all ends reported, uncontested stratum as a check. Presence at the end as registered in the audio-level read. Bootstrap over ends for intervals.

## Registered claims (adapted unless stated)

| Id | Claim | My odds |
|---|---|---:|
| C1 | **Relative level matters beyond absolute level.** Within the stratum `pre` in [-60, -40) dB, AUC of **smaller drop** for presence at the end is at least 0.60 (at least 20 ends in each outcome class, otherwise not evaluable) | 50% |
| C2 | **Absolute level matters beyond decay.** Within the stratum `drop` below 6 dB, AUC of **higher `pre`** for presence at the end is at least 0.70 (same class-size rule) | 60% |
| C3 | Drop and `pre` are not just one variable: the Spearman correlation between them over the population has magnitude at most 0.6 (otherwise C1 and C2 cannot separate them and are reported as not evaluable) | 70% |

## Reading rules, fixed now

- **C1 pass and C2 miss:** relative level, the tail against the note's own earlier loudness. The lever, if any, is per-note or per-window level handling (a gain stage following the note's decay, or training on decayed endings), and absolute-level work would not help.
- **C2 pass and C1 miss:** absolute level; an input-level lever or quiet-ending training in absolute terms.
- **Both pass:** both contribute; neither alone explains it.
- **Both miss:** neither level quantity explains the loss among detected notes; polyphony or the decoder's hold are the remaining candidates, which these curves cannot separate.
- **C3 misses (correlation above 0.6):** the two readings cannot be separated on this corpus; report and stop.
- No policy is proposed. Misses are reported as misses; anything computed after seeing the numbers is labelled post hoc.

## Limits

One recording; ends within a take are not independent. `drop` over 80 ms windows spaced 120 ms apart is a coarse decay measure and includes other pitches' harmonics where the end is contested. The frame posterior, not a decoder event, is the outcome.
