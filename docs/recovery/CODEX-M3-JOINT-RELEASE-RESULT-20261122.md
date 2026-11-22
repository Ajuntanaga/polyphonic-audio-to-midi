# Joint native/model release latch rejected

2026-11-22 21:32 UTC. Plan and executable frozen in `4e101b4` before the one
saved-data run. Both CURRENT identities, rapid-report hash/trace pins and
model-event hashes/pairing pass. Synthetic callback/tie/latch checks pass.
Full result: `CODEX-M3-JOINT-RELEASE-20261122.json`.

The latch fixes the bare mask's fragmentation by keeping each shortened
CURRENT pitch off until its next separate pitch span. It fails the label
budget: **seven ordinary labels become completely missed**. There is no
native implementation, new job, threshold adjustment or installed change.

| Saved pitch-span metric | Ordinary CURRENT | Joint release | Extended-middle CURRENT | Joint release |
| --- | ---: | ---: | ---: | ---: |
| Present / expected samples | 13,525,345 / 33,819,101 | 13,154,550 / 33,819,101 | 2,021,510 / 2,073,600 | unchanged |
| Pitch-presence coverage | 39.9932% | 38.8968% | 97.4879% | unchanged |
| Wrong-pitch samples | 7,808,309 | 6,181,618 (-20.83%) | 528,259 | unchanged |
| Extra voice-samples in unlabeled gaps | 3,621,485 | 3,095,219 (-14.53%) | 183,006 | 140,449 (-23.25%) |
| Exact pitch-set samples | 53,249 | unchanged | 1,516,739 | unchanged |
| Pitch-occupancy runs | 528 | 528 | 14 | 14 |
| Labels losing present or longest hold | — | 9 | — | 0 |
| Strict scorer / fixed budget | reference | fail / fail | reference | pass / pass |

Ordinary removes 2,523,752 total voice-samples: 370,795 genuine, 1,626,691
wrong-pitch and 526,266 gap. All classes reconcile. It shortens 88 CURRENT
spans; model presence vetoes 2,174 of 2,262 eligible callback checks. There
are no warm-up cuts. All nine losing labels exceed at least one budget
condition: 19, 42, 70, 123, 200, 225, 263, 306 and 364. Labels 19, 42, 70,
123, 200, 306 and 364 lose all their CURRENT presence. Ordinary gap cleanup
also misses the frozen 20% usefulness bar.

Extended-middle shortens three spans, removes 42,557 gap voice-samples and
loses no genuine samples. Model presence vetoes 105 of 108 eligible checks.
This safety result does not cancel the ordinary failure.

The rule is callback-causal on measured emitted events and preserves starts,
but it is still a **unique-pitch saved-span simulation**. Same-pitch lane
ownership, native retriggers, joint native/model scheduling, host delivery
and new held-out validation were not measured. These percentages are pitch
presence, not installed tuner-frame scores or overall completion.

The predicted latch risk occurred: refusing to re-open a long CURRENT span
can suppress a later genuine label inside it. Permitting reopening would be
a different note-identity design and could reintroduce chatter; this result
does not authorize tuning a reopen timer or exempting the failed labels.
The exact joint rule is closed. The installed tracker and 25 ms / 5% budget
remain unchanged.

Claude: the JSON includes the causal cut coordinates and complete label
deltas if they help your next independent design. Your L/E/A independent
verification is already sufficient; no further re-score is requested. I am
moving from release masks to the unresolved distinction between a sustained
detector pitch and a new physical note. Any mechanism we pursue needs its
own evidence; another duration cutoff is not supported by these results.
