# Restart-evidence census: pre-registration (written and committed before the run)

2026-11-22, Claude. Saved data only: no audio, model run, job, native edit or installed change. Nothing is tuned, nothing is promoted, no rejected policy is rerun.
Script: `CLAUDE-M3-RESTART-EVIDENCE-CENSUS-20261122.py` (sha256 prefix `d64e4945fc14` at this commit; any later change is disclosed in the result).
Status when this was written: the plumbing `--selftest` passes, and `--dry` (which executes every code path of the run but writes and prints no result) passes with all
identity gates true. No cue-versus-class number has been printed or seen.

## Question

The rapid-mute check (`CLAUDE-M3-RAPID-MUTE-CHECK-RESULT-20261122.md`) found that truncating every CURRENT span at its first rapid-mute interval ("the cut") removes 59% of the false
output but loses 1,077,990 present samples, all of it in 23 labels (18 of them wholly) that are same-pitch re-strikes inside a CURRENT span that ran on across the mute, with
nothing resumed. Codex's closed joint-release result (`CODEX-M3-JOINT-RELEASE-RESULT-20261122.md`) says re-opening "would be a different note-identity design" that "needs its own
evidence". This census supplies the first piece of that evidence on saved data: **if a span is released at every marked run, does any saved causal cue restart the re-struck
labels without also restarting the sustained tails of the other truncated spans?** It does not propose a policy; it measures how separable the two groups are.

## Definitions (fixed; the script implements exactly these)

- **Marked runs**, **CURRENT**, **mask** (CURRENT minus the marked intervals) and **cut** (each CURRENT span truncated at the first marked interval starting inside it) are the
  rapid-mute check's, reused through its own helpers; the identity gates below tie them to its committed numbers.
- **Restart machine** (`restart_spans`). A CURRENT span is released at the start of each marked run inside it and a pitch is then *restarted at the first instant t at or after
  that run's end, outside every marked run, at which a cue supports the pitch (t < span end)*, and stays on (sticky) until the next marked run starts inside the span or the span
  ends. A span that begins inside a run is blanked until the run ends, exactly as in the cut and the mask. No cue is the cut; a cue that is always on is the mask. No threshold,
  hold, debounce or duration is introduced.
- **Cues** (state sets per pitch, no hold, nothing tuned): **L**, **E**, **A** are the frozen arms of `CODEX-M3-SUPPORT-EVENTS-PLAN-20261122.md` as built by the support check
  (`arm_support`: every positive callback supplies `[B, B+512)`; L = the last decision's direct set, E = every direct observation in the callback, A = E plus the selected active
  pooled onset-observed note; ordinary-disposition decisions only). **M** = the saved cropped-adapted model's note spans on the measured `emitted_ns` clock (event hashes pinned).
  **AM** = A united with M. **ORACLE** = the same-pitch label intervals, a comparator that uses the labels and is never a candidate. The L filter of the support check is also scored
  alone and intersected with each restart variant (`filter_L&restart_*`, the stack convention of the rapid-mute check).
- **Truncated span** = a CURRENT span with a marked run starting inside it after head handling. **Positive span** = a truncated span whose removed part `[cut, span end)` overlaps a
  same-pitch label. **Negative span** = every other truncated span. **Positive labels** = the labels that lose present output under the cut.

Structure disclosed before the run (counts only, from the selftest). Ordinary: 127 marked runs; the cut changes 245 spans, all of them truncations (none removed entirely, none
head-blank-only); **21 are positive spans, holding the 23 positive labels and the 1,077,990 present samples, and 224 are negative**. Extended-middle: 6 marked runs, 9 truncated spans,
all negative (no positives). Candidate-record coverage (plumbing, because per-note records are annotation-dependent): on ordinary 389,527 of 389,925 CURRENT-active decisions (99.90%)
carry a record for their pitch, and 27,431 of 27,431 and 94,893 of 94,893 inside the removed parts of positive and negative spans; extended-middle 42,700 of 42,700 and 2,132 of
2,132. The cues L/E/A themselves use only the trace's per-callback direct sets and the onset cue; the coverage shows the annotation-dependent serialisation cannot favour one class.

## Statistics (per cue, ordinary; extended-middle is a safety replication with no positives)

- **sens25** = positive labels whose present loss beyond the mask is at most 25 ms (2,400 samples) (of 23); the per-label extra losses are all saved.
- **spec** = negative spans (of 224; of 9 on extended-middle) with no restart before the span ends. **J = sens25/23 + spec - 1** (Youden-style; a random cue is about 0, a perfect one 1).
- **Volume exchange** relative to the mask: G = false output removed beyond the mask by the cue divided by what the cut removes beyond the mask (5,216,164 samples), C = present
  output lost beyond the mask by the cue divided by the cut's (1,073,640), **J_vol = G - C**. Exact re-admitted volume of the negatives is saved.
- Restart latency of each positive span relative to the first same-pitch label start in its removed part, and the frozen label budget per variant (read as new over-budget labels
  beyond the mask's {31, 70}).
- **Nesting consequence (logical, not a prediction):** the mask already fails the frozen budget on ordinary (labels 31 and 70, head losses inside marked runs) and the cut sits below
  every restart variant, so **no restart variant can pass the frozen label budget on ordinary**. Cues are therefore judged against the mask, not against a pass/fail budget.

## Identity gates (all must hold; any failure voids the readings and is reported as a harness failure)

- **I0** the no-cue variant equals the cut and an always-on cue equals the mask span for span, and the CURRENT, mask, cut and L-filter rows equal the committed rapid-mute check
  (`CLAUDE-M3-RAPID-MUTE-CHECK-20261122.json`, sha256 prefix `185f1db63edc`) on both recordings.
- **I1** every restart variant lies between the cut and the mask, and L is inside E is inside A is inside AM, M inside AM.
- **I2** the positive labels equal the cut anatomy's 23 (`CLAUDE-M3-RAPID-MUTE-CUT-ANATOMY-20261122.json`, sha256 prefix `fb219633382e`) and the label-timed present-only
  restart reproduces its oracle-restart row.
- **I3** per-label present losses sum to the aggregate loss for the cut, the mask, the ORACLE cue and the oracle restart (reported for every variant).
- **I4** the ORACLE cue restarts every positive label with no loss beyond the mask and restarts no negative span (J = 1 by construction).

## Predictions (made before any cue-versus-class number was seen; odds are my probability that the statement is true)

| | Statement (ordinary unless stated) | Odds |
| --- | --- | --- |
| P1 | cue A: at least 12 of the 23 positive labels lose no more than 25 ms beyond the mask (sens25 >= 12) | 50% |
| P2 | cue A leaves at least 50% of the 224 negative spans unrestarted (spec >= 0.50) | 35% |
| P3 | cue A is not informative: J < 0.20 | 65% |
| P4 | the model cue M and A united with M are both not informative (J < 0.20 for M and for AM): the model's spans cover the mute, so they restart nearly everything | 80% |
| P5 | cue A keeps at least half of the cut's false-output removal beyond the mask (G >= 0.50) | 50% |
| P6 | no candidate cue (L, E, A, M, AM) reaches J >= 0.50 | 92% |
| P7 | cue A leaves at least one new over-budget label beyond the mask's 31 and 70 | 92% |
| P8 | extended-middle: cue A leaves at least 5 of the 9 negative spans unrestarted | 45% |

## Reading rule

1. If a gating identity fails, nothing is read; I fix the harness and any rerun is disclosed as a rerun.
2. A candidate cue is **informative** when J >= 0.20 and J_vol >= 0.20 on ordinary, **strongly informative** when both are >= 0.50; otherwise **not informative**. Informative means
   a lead for Codex's own sustained-pitch-versus-new-note design, never a recommendation: both recordings are seen design data, the restart is sticky by construction (a diagnostic,
   not a behaviour), and nothing has been tested held-out or on the native retrigger path.
3. Misses are reported as misses, and any analysis added after seeing the result (latency or span-length breakdowns, per-label stories) is labelled post hoc.
4. The answer in the result note comes first: which cue, if any, separates the re-struck labels from the tails, and at what volume exchange.

## Separate: predictions about Codex's native joint-reset screen (scored when its result is published)

Codex's frozen native screen (`CODEX-M3-NATIVE-JOINT-RESET-PLAN-20261122.md`; commits `0f2143e`, `b9aa57a`) was dispatched at 14:03 PST. I have not read any of its outputs: no result
note exists, and its run-record JSON (modified 14:10) is unread. Scored against Codex's own gates, as published:

| | Statement | Odds |
| --- | --- | --- |
| N1 | the screen fails the user's label budget on ordinary (at least one label over 25 ms / 5%, or newly completely missed) | 85% |
| N2 | the screen misses the >=20% ordinary gap-output reduction bar | 75% |
| N3 | processing allocations are zero and block32 p99 <= 166,666 ns, max <= 333,333 ns, zero overruns | 90% |
| N4 | flag-off snapshot and raw MIDI match the CURRENT references on both recordings | 95% |
| N5 | some frozen clause fails, so the screen is rejected | 92% |

## What I have and have not seen

Seen: the rapid-mute check and its post hoc cut anatomy (including the 23 positive labels and their mechanism), Codex's closed joint-release result, Codex's native-reset plan, the
structure counts and plumbing booleans above. Not seen: any restart time, latency, sensitivity, specificity, volume exchange or label budget for any cue. Limitations: the two
recordings are design data, so every result is a screen; positives are 21 spans (23 labels), so J has wide uncertainty and no interval is claimed; label-level sensitivity and
span-level specificity are mixed in J by design (the budget is per label, the tails are per span); the cues are per-callback state, so a restart can lag a re-strike by up to one
callback (512 samples) plus the detector's own evidence delay.

## Exclusions

No native or release-hold job, no rerun of the rejected latch, no promotion, no change to the installed tracker, Codex's frozen gates or the label budget, no tuning of any cue, and no
change to `tools/` or native code.
