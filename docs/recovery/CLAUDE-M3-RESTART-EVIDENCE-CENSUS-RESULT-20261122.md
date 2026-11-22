# No saved causal cue tells a re-struck note from a sustained tail after a rapid-mute window, and the re-strikes begin where the cues cannot look: restart-evidence census result

Claude, 2026-11-22. Pre-registration: `CLAUDE-M3-RESTART-EVIDENCE-CENSUS-PREREGISTRATION-20261122.md` (commit `d3b51a6`, committed 22:19:45 UTC and pushed before the single `--run` at 22:20:10 UTC). Saved data only (the two pinned v5 traces, the adapted cropped ONNX events, the saved labels); no audio, model run, job, native edit, promotion or tuned cue. The census script did not change after the pre-registration commit (sha256 prefix `d64e4945fc14` before and after; one run, 37 s, CPU only). The sections marked POST HOC were written after the result was seen and say so. The last scoring table covers my predictions about Codex's native joint-reset screen, which I read only after my census JSON existed.

## Answer

1. **No candidate cue is informative.** The rule I fixed in advance: informative means J >= 0.20 and J_vol >= 0.20 on the ordinary recording (J = sens25/23 + spec - 1; J_vol = G - C; definitions below). Measured J: L -0.055, E -0.053, A +0.082, M -0.122, AM +0.011. Measured J_vol: 0.449, 0.389, 0.174, 0.210, 0.053. No cue meets both, none is strongly informative (both >= 0.50). The label-timed ORACLE gets J = 1 by construction.
2. **The cue that finds the re-strikes does not tell them from the tails.** A (every direct observation plus the selected onset cue) restarts all 21 positive spans and 18 of the 23 positive labels lose no more than 25 ms beyond the mask. It also restarts 157 of the 224 negative spans (70%) and re-admits 3,744,356 of the 6,087,264 false samples the cut removes from them. It keeps 20.5% of the cut's false-output removal beyond the mask.
3. **The cues that leave the tails alone restart the re-strikes late.** L (the last decision's direct set) leaves 124 of 224 negative spans unrestarted (spec 0.554) and E (every direct observation) leaves 105 (0.469); they keep 52% and 45% of the cut's removal at 7.1% and 6.1% of its present loss, which is the best volume exchange of any cue (J_vol 0.449 and 0.389). But only 9 and 11 of the 23 labels lose 25 ms or less beyond the mask, and the positive spans restart a median 42.7 ms (L) and 37.3 ms (E) after the run ends, against 5.3 ms for the negatives that restart (POST HOC).
4. **The model cue does not help.** M (the saved cropped adapted ONNX note spans) restarts 154 of 224 negative spans, every one of them at the instant the run ends, because the model's spans simply persist through the mute; AM (A united with M) restarts 202. A separate network is independent of the detector but is still a sustained-presence signal.
5. **What a perfect discriminator would be worth.** Cutting every CURRENT span at its first marked window and restoring only the label-timed present output removes 59.2% of CURRENT's false output (11,429,794 to 4,663,613), moves precision from 54.20% to 74.36% and loses no label (the frozen budget passes). Every cue lands between the mask (57.78%) and that ceiling, and by nesting none can pass the frozen label budget (the bare mask already fails labels 31 and 70), so the cues are judged against the mask. The label budget is untouched.
6. **POST HOC: all 23 positive labels begin inside a marked run or within 25 ms after its end.** Against the nearest preceding marked run, 16 label starts fall inside the run (0.27 to 7.07 ms before its end) and 7 fall 0.26 to 22.49 ms after it; none later. L, E and A read only decisions with ordinary disposition, so they cannot see inside a run, and a design that releases at the run and waits for a later cue to re-open finds the new note only after its attack. This is consistent with Codex's native reset losing five labels whole (four start inside a run, one within 25 ms).
7. **What would help next.** Per-pitch evidence from the attack itself, which sits in the last callbacks of the run. The per-note candidate records exist there (counted over every decision of the removed parts, in-run ones included: 100% carry a record for their pitch), so a saved-data run-interior onset/energy census is the next check I can pre-register. Not started; nothing here argues for or against a native change.

Predictions: 6 of 8 about the census hit (Brier 1.1003, mean 0.1375) and 5 of 5 about Codex's native screen hit (Brier 0.1039). Both census misses are the same error: I overestimated A's selectivity.

## What was measured

- **Marked runs, CURRENT, mask, cut** are the rapid-mute check's (reused through its own helpers; identity gates below tie them to its committed numbers). **Truncated span** = a CURRENT span with a marked run starting inside it: 245 on ordinary. **Positive span** = a truncated span whose removed part `[cut, span end)` overlaps a same-pitch label: 21 spans holding the 23 **positive labels** (the labels that lose present output under the cut: 18 re-strikes of a pitch CURRENT never released, and 5 first onsets after output that began 0.5 to 1.1 s early, from the cut anatomy). **Negative span** = every other truncated span: 224.
- **Restart machine.** A span is released at each marked-run start inside it and restarted at the first instant t at or after that run's end, outside every marked run and before the span ends, at which the cue supports the pitch; it then stays on until the next run starts inside it. No cue is the cut; an always-on cue is the mask. No threshold, hold or duration.
- **Cues** (per-callback state sets, nothing tuned): L, E, A are the frozen arms of the support-events plan (ordinary-disposition decisions only); M = the cropped adapted ONNX note spans on the measured `emitted_ns` clock; AM = A united with M; ORACLE = the same-pitch label intervals (labels used; a comparator, never a candidate).
- **Statistics.** sens25 = positive labels whose present loss beyond the mask is at most 25 ms (2,400 samples), of 23. spec = negative spans never restarted, of 224. J = sens25/23 + spec - 1. G = false output removed beyond the mask by the cue over the cut's (5,216,164). C = present output lost beyond the mask by the cue over the cut's (1,073,640). J_vol = G - C.

## Identity: the harness is sound

All gates hold on both recordings: no cue equals the cut and an always-on cue equals the mask span for span; every restart variant lies between the cut and the mask and the cue sets nest (L in E in A in AM; M in AM); the CURRENT, mask, cut and L-filter rows equal the committed rapid-mute check; per-label present losses sum to the aggregate loss for every variant; the ORACLE cue restarts every positive label and no negative span; and on ordinary the 23 positive labels equal the cut anatomy's and the label-timed restart reproduces its oracle row. Candidate-record coverage: 389,527 of 389,925 CURRENT-active decisions (99.898%) carry a record for their pitch; 27,431 of 27,431 and 94,893 of 94,893 inside the removed parts of the positive and negative spans (extended-middle 42,700 of 42,700 and 2,132 of 2,132).

The limit is the same as for the rapid-mute check: the scorer, trace reader and budget code are shared repository code, so this catches mis-wiring, not a misreading Codex and I share.

## Per-cue results (ordinary)

| Cue | sens25 (of 23) | spec (of 224) | G | C | J | J_vol | Informative |
|---|---:|---:|---:|---:|---:|---:|---|
| L | 9 | 124 (0.554) | 0.520 | 0.071 | -0.055 | 0.449 | no |
| E | 11 | 105 (0.469) | 0.451 | 0.061 | -0.053 | 0.389 | no |
| A | 18 | 67 (0.299) | 0.205 | 0.031 | +0.082 | 0.174 | no |
| M | 13 | 70 (0.312) | 0.320 | 0.110 | -0.122 | 0.210 | no |
| AM | 21 | 22 (0.098) | 0.066 | 0.013 | +0.011 | 0.053 | no |
| ORACLE | 23 | 224 (1.000) | 0.972 | 0.000 | 1.000 | 0.972 | by construction |

(ORACLE keeps the labelled interval whole, so the false output inside a positive span's re-struck part stays in: G is 0.972, not 1.)

| Cue | Positive spans restarted / never | Restart before / within 25 ms / later than 25 ms of the label start | Negative spans restarted: samples re-admitted of the 6,087,264 the cut removes | New over-budget labels beyond the mask's {31, 70} | New missed labels |
|---|---|---|---:|---|---|
| L | 20 / 1 | 1 / 8 / 11 | 100: 2,247,585 | 12 labels | 70 |
| E | 21 / 0 | 1 / 10 / 10 | 119: 2,606,671 | 11 labels | 70 |
| A | 21 / 0 | 2 / 15 / 4 | 157: 3,744,356 | 42, 239, 349, 470 | 70 |
| M | 18 / 3 | 5 / 7 / 6 | 154: 3,183,608 | 9 labels | 42, 70 |
| AM | 21 / 0 | 6 / 14 / 1 | 202: 4,416,184 | 42 | 70 |
| ORACLE | 21 / 0 | 0 / 21 / 0 | 0: 0 | none | none |

## The variants (ordinary, voice samples; budget = the frozen per-label 25 ms and 5% rule)

| Variant | Present | False | Precision | Over-budget labels | Newly missed |
|---|---:|---:|---:|---|---|
| CURRENT | 13,525,345 | 11,429,794 | 54.20% | 0 | 0 |
| mask | 13,520,995 | 9,879,777 | 57.78% | 2 (31, 70) | 0 |
| restart L | 13,444,987 | 7,169,685 | 65.22% | 14 | 1 (70) |
| restart E | 13,455,481 | 7,529,795 | 64.12% | 13 | 1 (70) |
| restart A | 13,487,737 | 8,809,940 | 60.49% | 6 | 1 (70) |
| restart M | 13,403,101 | 8,209,267 | 62.02% | 11 | 2 (42, 70) |
| restart AM | 13,506,795 | 9,535,922 | 58.62% | 3 | 1 (70) |
| restart ORACLE (still blanked inside runs) | 13,520,995 | 4,807,287 | 73.77% | 2 (31, 70) | 0 |
| cut | 12,447,355 | 4,663,613 | 72.75% | 23 | 18 |
| oracle restart (cut, label-timed present kept) | 13,525,345 | 4,663,613 | 74.36% | 0 | 0 |

Read these as occupancy under a sticky diagnostic restart, not as policies. The aggregate columns flatter L (precision 65.22% for 0.59% of present output) because the per-label budget is what it fails: 12 labels beyond the mask's two, label 70 lost whole. The user's decision on the frozen budget ("Leave it as is", `2bf0e2a`) stands.

## Extended-middle (safety replication; 6 runs, 9 truncated spans, no positive span)

L, E and A restart none of the nine spans, so they equal the cut (gap 183,006 to 46,016, every gate passes). M and AM restart five of nine and re-admit 40,955 of the 136,990 samples the cut removes (G 0.293, gap 86,971, still passing). With no positives it can only show what a cue does to tails: the three direct-observation cues leave all nine alone here, where on ordinary A restarts 70%. Nine spans cannot say whether that is selectivity or just fewer events.

## POST HOC 1: timing, what the negative spans are (script `CLAUDE-M3-RESTART-EVIDENCE-POSTHOC-20261122.py`)

Descriptive only: no prediction, threshold or policy, nothing tuned. Disclosure: the script was run three times after the census result (part 3 and then part 1b were added); each regeneration reproduced every earlier number exactly.

**Timing.** Delay after the end of the first marked run, for the spans that restart. The first same-pitch label start of a positive span lies a median 1.24 ms before its run end (minimum 7.07 ms before; maximum 849.16 ms after, in spans with several runs where the label follows a later one), so the delay is also the latency after the re-strike.

| Cue | Positives restarted: median ms (IQR) | Negatives restarted: median ms (IQR); at the run end | AUC positive restarts earlier (never = infinite) | AUC positive restarts later, among the restarted |
|---|---|---|---:|---:|
| L | 20: 42.67 (16.0 to 53.33) | 100: 5.33 (0 to 10.67); 37 | 0.638 | 0.771 |
| E | 21: 37.33 (10.67 to 48.0) | 119: 5.33 (0 to 10.67); 43 | 0.580 | 0.791 |
| A | 21: 10.67 (5.33 to 21.33) | 157: 5.33 (0 to 10.67); 45 | 0.524 | 0.679 |
| M | 18: 0 (0 to 93.19) | 154: 0 (all 154 at the run end) | 0.487 | 0.667 |
| AM | 21: 0 (0 to 10.67) | 202: 0 (163 at the run end) | 0.436 | 0.626 |

The first AUC mixes "restarts at all" with "restarts sooner" (most negatives never restart), so the second isolates the restarted spans: a positive restarts later than a negative with probability 0.77 (L) and 0.79 (E). That is the opposite of the intuition that a quick restart marks a note worth keeping: a tail resumes at the run end because the detector never lost the pitch, a re-struck note resumes after its attack and the evidence delay. It is a pointer (21 positives, design data, uses the labels to define the groups), and a rule built on it would be a new design needing its own pre-registration.

**What the 224 negative spans are.** 181 (80.8%; 80.04% of the removed samples) are overhangs of a labelled same-pitch note: the output ran on past the label's end, and the last such label ends a median 42.0 ms (IQR 38.67 to 47.33; 28.0 minimum, 457.28 maximum) before the cut, i.e. the detector's release lag after a real mute. 43 (19.2%; 19.96%) have no same-pitch label near the span at all. Restarts by class (overhang of 181, unlabelled of 43): L 78 and 22, E 96 and 23, A 127 and 30, M 151 and 3, AM 172 and 30. So M separates unlabelled output (3 of 43 restarted) from overhangs (151 of 181), but overhangs dominate and the model keeps those too.

**Relation to concurrent labels (context only: every overlapping label counts, no chance baseline).** Harmonic of a sounding lower note 14 spans (6.25%; 9.63% of removed samples), subharmonic of a sounding higher note 87 (38.84%; 42.55%), other relation 123 (54.91%; 47.82%), no concurrent label 0. Every removed part overlaps some other label in a polyphonic recording, so this does not support a harmonic-error explanation of the tails.

## POST HOC 2: cross-check against Codex's native reset (script `CLAUDE-M3-NATIVE-RESET-CROSSCHECK-20261122.py`)

Inputs: the census JSON, the ordinary v5 trace for the marked runs, and the native `report.json` Codex collected from run 45075475603 (local file, SHA-256 `3bedd04bd9b1cccc60faed718fcbdbf15e855d86a8d968b6aeb6fe3237773b8a`, checked by the script; not in git and not re-downloaded). Disclosure: its first run printed a wrong index test (it required a census loss under cue M to equal the native present total for every fully missed label); I replaced it with the four checks below and added the nearest-run analysis before committing. The numbers both versions share were identical.

- **Checks pass.** The native per-label table sums to CURRENT's present total (13,525,345); every positive label maps to a positive span of the same pitch; no census loss exceeds the label's own present; and for the six (label, cue) pairs the census marks newly missed, the census loss equals the label's whole present output (label 70 under all five cues, 3,494; label 42 under M, 45,785).
- **Position of the 23 positive labels against the nearest preceding marked run:** 16 start inside it (0.27 to 7.07 ms before its end), 7 within 25 ms after its end (0.26 to 22.49 ms), 0 later. The runs end at the attack (rapid-mute result: the last run ends at the next annotated onset, median 0.41 ms after it), so a cue that is read only after the run has ended starts looking at the new note after the attack has happened.
- **The labels the native reset hurt are mostly these labels.** Of the 15 pitch-present budget failures, 9 are positives (19, 42, 70, 123, 200, 225, 263, 306, 364) and 6 are not (14, 109, 124, 213, 217, 228). All five whole-label losses (42, 70, 200, 306, 364) are positives: four start inside a run, one (70) within 25 ms. 14 of the 23 positives are not lost natively (31, 91, 128, 159, 174, 178, 239, 245, 302, 349, 355, 456, 459, 470), as the model-support veto would protect them (the mechanism is not tested here). 10 labels lose present output natively without being positives (14, 99, 101, 109, 124, 181, 213, 217, 228, 389): that is state-dynamics damage after a release (re-selection, lane and retrigger effects) which the saved-data census does not represent.
- **The census cues are more lenient than the native re-open path.** On the four natively whole-lost labels other than 70, the census restarts within about 6 to 56 ms under L, E, A and AM (total losses 538 to 5,402 samples of 27,801 to 71,863; label 42 is lost whole only under M, 45,785), while native lost them whole; native reactivates through ordinary selection, evidence, attack and lane rules, which are stricter than a state set. So the census does not predict native outcomes label by label; it only says what the saved cues could and could not separate.

## Predictions, scored

Census (made before any cue-versus-class number was seen):

| Id | Claim (ordinary unless stated) | Odds | Measured | Result |
|---|---|---:|---|---|
| P1 | A: sens25 >= 12 | 50% | 18 | hit |
| P2 | A: spec >= 0.50 | 35% | 0.299 | **miss** |
| P3 | A is not informative: J < 0.20 | 65% | +0.082 | hit |
| P4 | M and AM both J < 0.20 | 80% | -0.122 and +0.011 | hit |
| P5 | A: G >= 0.50 | 50% | 0.205 | **miss** |
| P6 | No candidate cue reaches J >= 0.50 | 92% | maximum +0.082 | hit |
| P7 | A leaves at least one new over-budget label beyond 31 and 70 | 92% | four (42, 239, 349, 470) | hit |
| P8 | Extended-middle: A leaves at least 5 of 9 unrestarted | 45% | 9 of 9 | hit |

Six of eight against 5.1 expected; Brier sum 1.1003 (mean 0.1375). The identity gates held (not scored). Both misses concern A's selectivity: I expected the onset cue to be much more discriminating than it is.

Codex's native joint-reset screen (written into the pre-registration before I had read any of its outputs; scored against its published result `CODEX-M3-NATIVE-JOINT-RESET-RESULT-20261122.md`):

| Id | Claim | Odds | Published | Result |
|---|---|---:|---|---|
| N1 | Label budget fails on ordinary | 85% | 15 pitch-present failures; 42, 70, 200, 306, 364 fully missed | hit |
| N2 | Gap reduction below the 20% bar | 75% | 12.4185% | hit |
| N3 | Zero allocations; block32 p99 <= 166,666 ns and max <= 333,333 ns; zero overruns | 90% | p99 80,385 ns, max 173,797 ns; no allocations or overruns | hit |
| N4 | Flag-off identity on both recordings | 95% | identity retained | hit |
| N5 | Some frozen clause fails, so rejected | 92% | rejected | hit |

Brier sum 0.1039 (mean 0.0208). Across all 13: 11 hits, sum 1.2042, mean 0.0926. The native predictions were verdicts on gates at 75 to 95% odds; they test calibration, not whether I understood the mechanism, and the one place they touch it (N1) was the easy direction.

## Provenance

- `CLAUDE-M3-RESTART-EVIDENCE-CENSUS-20261122.py` (`d64e4945fc14`, committed in `d3b51a6`; selftest and result-free `--dry` passed first), output `CLAUDE-M3-RESTART-EVIDENCE-CENSUS-20261122.json` (`7f04df44c18a`, 133,375 bytes), one run 2026-11-22 22:20:10 UTC, exit 0.
- POST HOC: `CLAUDE-M3-RESTART-EVIDENCE-POSTHOC-20261122.py` (`de5c26000892`) and its output (`05f9c37c4a70`); `CLAUDE-M3-NATIVE-RESET-CROSSCHECK-20261122.py` (`a2a65495c4ea`) and its output (`934da89e754b`).
- Inputs pinned as in the plan: ordinary trace raw sha256 `b664c7ff0ce8` and events `4e0601c42dbd`; extended-middle trace `78929974b9cc` and events `1eea72fdc62b`; committed inputs rapid-mute check JSON `185f1db63edc` and cut anatomy JSON `fb219633382e`. Codex's native report as above.
- Reused code: the rapid-mute check, the support-events check, the filter residual anatomy and the adapted-support modules in this directory; no change to `tools/` or native code.

## What cannot be concluded

- Both recordings are design data I had already examined, and the question came from one of them. A cue judged not informative here is a statement about these two recordings; none of this is held out, and a positive result would also have been only a lead.
- 21 positive spans (23 labels) in one recording with chords separated by mutes: J has wide uncertainty and no interval is claimed (spans are clustered by chord, so a naive interval would be too narrow). A is the cue nearest the bar (J +0.082, J_vol 0.174); with this few positives I would not read that gap as large, and the substantive reason it is unusable is that it restarts 70% of the tails.
- The restart is sticky by construction and the cues are per-callback state sets, so a restart can lag a re-strike by up to one callback (512 samples) plus the detector's own evidence delay. This is a diagnostic of separability, not a behaviour; no MIDI lifecycle, retrigger, lane or string claim.
- Label-level sensitivity and span-level specificity are mixed in J by design (the budget is per label, the tails are per span).
- The cross-check depends on Codex's local report (pinned by SHA-256) and says nothing about native code paths beyond what the report's per-label table shows; the explanation that a release waiting on a later cue misses the attack is consistent with the data and untested against the native reactivation code.
- Labels are annotated note times; audible ring after an annotated end scores as false.
- Nothing is promoted; no gate, default, native file, installed tracker or label budget changes, and no rejected policy was rerun.
