# Model-delay sensitivity: how late can Basic Pitch run before each candidate stops paying

Claude, 2026-11-22. Saved data only: the saved arm A spans shifted by L ms, CURRENT, the native confirmation. No audio, model run, job or native edit; nothing promoted. Plan and eight predictions: `CLAUDE-M3-MODEL-DELAY-PREREGISTRATION-20261122.md` (commit 3134560, written before any shifted span was scored). Script `CLAUDE-M3-MODEL-DELAY-20261122.py` sha256 3bedc5a0f50f, output `.json` 9ed7148c0324. It uses the committed gate-menu evaluator, and L = 0 reproduces the gate menu's numbers exactly.

What L means here: arm A is the saved ONNX offline causal run, and the unchanged-TF events on the zero-compute availability clock reproduce its run structure (596 runs at the same pitches, same six losers; see the adapted-support result; the saved arm A is later than the event-file spans by a constant 11.09 ms, measured afterwards in `CLAUDE-M3-ADAPTED-GAP-EXTRAS-RESULT-20261122.md`, so a live lag measured as emitted minus available corresponds to L = lag - 11.09 ms in this table: the budgets quoted in L terms are about 11 ms tighter than the same budgets in per-event lag terms). So L is the extra lag a live model adds after the moment its content is available, which is the same quantity as emitted time minus available time in Codex's event files.

## Ordinary corpus (CURRENT: coverage 39.99%, precision 54.20%, exact set 0.60% of annotated, 528 runs)

Union (CURRENT union arm A shifted by L). Nothing CURRENT emits is ever removed, so no label loses at any L.

| L (ms) | coverage % | precision % | wrong-pitch change | gap-voice change | exact set % | runs | share of the L = 0 coverage gain kept |
|---|---|---|---|---|---|---|---|
| 0 | 67.52 | 60.55 | +23.8% | +43.7% | 12.92 | 743 | 100% |
| 50 | 65.83 | 59.10 | +26.8% | +52.1% | 12.96 | 736 | 94% |
| 100 | 64.28 | 57.59 | +32.8% | +55.8% | 12.94 | 744 | 88% |
| 150 (post hoc) | 62.65 | 55.79 | +41.0% | +59.7% | 12.36 | 759 | |
| 200 (post hoc) | 60.98 | 53.73 | +51.5% | +63.6% | 11.43 | 769 | |
| 250 | 59.27 | 51.52 | +64.7% | +65.8% | 10.53 | 787 | 70% |
| 500 | 50.66 | 40.47 | +141.8% | +74.6% | 4.25 | 827 | 39% |
| 1000 | 46.39 | 32.76 | +212.4% | +115.5% | 0.19 | 1,036 | 23% |
| 2000 | 43.97 | 30.95 | +219.0% | +128.6% | 0.20 | 1,047 | 15% |

Reading: the coverage gain decays about as the 748 ms note length says it should, but the false output grows faster. A delayed correct note lands on the NEXT note's window as a wrong pitch, so precision falls below CURRENT's 54.20% between 150 and 200 ms (55.79 then 53.73%). At 100 ms or less the union still beats CURRENT on coverage, precision and exact set at once; at 250 ms it keeps 59.3% coverage and a 10.5% exact set but is worse on precision; at 500 ms it is a poor trade; at 1000 ms and above it is worse than CURRENT on precision and nearly empty on exact set. The coverage rows at 1000 and 2000 ms stay a few points above CURRENT because a late span can land on a later same-pitch note: read them as upper bounds.

Filter, D = 220 ms (CURRENT intersect (arm A shifted union native confirmation), held D ms):

| L (ms) | coverage % | precision % | wrong removed | labels losing | largest label loss |
|---|---|---|---|---|---|
| 0 | 39.92 | 58.93 | 22.2% | 6 | 79.7% |
| 100 | 39.92 | 58.63 | 20.9% | 6 | 79.7% |
| 250 | 39.89 | 58.32 | 19.5% | 7 | 79.7% |
| 500 | 39.82 | 58.04 | 18.3% | 7 | 79.7% |
| 1000 | 39.77 | 58.54 | 21.2% | 8 | 79.7% |
| 2000 | 39.78 | 59.49 | 25.1% | 8 | 79.7% |
| native confirmation only (no model) | 39.77 | 60.22 | 28.0% | 9 | 79.7% |

The model's whole contribution to the filter is small, and it fades with lag over the same range: 6 losing labels at L = 0 to 100 ms, 7 at 250 and 500 ms, 8 at 1000 and 2000 ms, against 9 with no model at all, and cleanup of 22% at L = 0 against 28% with no model (the model's support protects more genuine notes and so also keeps more false output). The filter's largest loss stays label 229 (79.7%) under arm A at every L; only the adapted model's events restored it. At D = 50: 28 losing labels at L = 0, 21 to 37 across the grid, 39 for native only.

## Extended-middle (3,600 ms notes, CURRENT coverage 97.49%, precision 73.97%)

The union adds 1.1 to 2.3 points of coverage (98.6 to 99.8%; the "share of gain" column in the JSON is meaningless here because the L = 0 gain is 1.13 points) while its wrong-pitch change is about +3% up to L = 100 ms and then climbs to +28.6% at 2000 ms. The filter at D = 220 loses 0 labels at every L (coverage 97.49%, wrong removed 26.0%, precision 78.53%). At D = 50 it loses 1 label at L = 50 to 250, 2 at L = 500, 4 at L = 1000 (largest 28.8%).

## Predictions, as registered: 6 pass, 2 fail

| | prediction | result |
|---|---|---|
| D0 | L = 0 reproduces the gate menu | pass |
| D1 | coverage 55 to 62% at 250 ms, 46 to 54% at 500 ms, within 3 pp of CURRENT at 2000 ms | **FAIL**: 59.27 and 50.66 are inside the bands, but 2000 ms is 3.98 pp above CURRENT (late spans landing on later same-pitch notes) |
| D2 | half-gain delay 250 ms | pass (70% kept at 250, 39% at 500) |
| D3 | union loses 0 labels at every L | pass |
| D4 | wrong-pitch change within 8 pp of +23.8% up to 500 ms, gap change not falling up to 1000 ms | **FAIL**: gap clause passes (monotone), the wrong-pitch clause fails from 100 ms (+32.8%) and is +141.8% at 500 ms. I had not allowed for a delayed correct note becoming a wrong pitch inside the next 748 ms note |
| D5 | filter D = 220 losers never fall, 6 at L = 0, within 2 of native-only's 9 at 2000 ms | pass (6,6,6,7,7,8,8) |
| D6 | wrong removed at 2000 ms at least its L = 0 value | pass (25.1% against 22.2%, though it dips to 18.3% at 500 ms on the way) |
| D7 | extended-middle filter at D = 220 loses 0 labels up to 500 ms | pass (0 at every L) |

## What this means

- **A latency budget for Codex's ONNX lane.** The union needs the live model's lag (emitted minus available, per event) at or under about 100 to 150 ms to beat CURRENT on coverage and precision together; 250 ms still gains coverage and exact set but loses precision; 500 ms or more is not worth it. The measured TF backlog was about 72 s, so the TF path is out by a factor of hundreds, and the corrected ONNX run should be read against this table by its per-event lag distribution (median and tail), not by "faster than TF". This is a fixed-shift model; a real lag distribution with a long tail will do worse than its median suggests.
- **The two routes need different things from a live model.** The cleanup filter works without one (native confirmation alone: 9 losing labels, 28% cleanup, precision 60.2%); a model at up to about 100 ms lag trims that to 6 losing labels, and beyond about 1000 ms it adds nothing. The union, the only route that moves coverage (40 to 67.5%), cannot exist without a model next to the tracker, and only pays under about 150 ms of lag. So the rule that allows the union also commits the project to a real-time model with a lag budget this tight; a filter rule does not.
- **Where the earlier measured numbers sit against the budget** (cross-reference to my streaming assessment, not a new measurement). Arm A already contains the causal model's inherent context lag, because the unchanged-TF events on the zero-compute clock reproduce it exactly; in the streaming prototype the compute-free shift against the whole-file offline model was a median 96.5 ms. What L adds on top is service and queue delay. In the streaming run that assessment scored (44889388628) the measured-minus-compute-free first-present shift was 11.0 to 11.2 ms (quartiles), the median inference-block service time. If a corrected ONNX run behaves like that, L is about 10 ms and the union sits at the top of this table; the roughly 72 s lag on the ordinary corpus in the adaptation run's TF clock is the opposite case, hundreds of times over budget. Which of the two the ONNX run resembles is the open question, and it is Codex's measurement to make.
- Nothing here changes Codex's frozen gates, the label-clause question, or any promotion; it is sensitivity on saved spans, one recording per corpus.

## Caveats

Fixed pure shift of every span (onset and offset together); real lag varies per event and with load. Arm A is an offline causal run, so its own availability may differ from a live model's by hop alignment or lookahead that this table does not model. The false-output growth is partly an artefact of 748 ms back-to-back notes: slower material would be more tolerant, faster less so. 150 and 200 ms are post hoc additions. Large-L coverage rows include coincidental same-pitch credit. No string, lane, unison, native deadline or live-host claim.

## Addendum: the saved TensorFlow events against this budget (measured lag, script `CLAUDE-M3-EVENT-LAG-20261122.py`)

Lag per event is emitted_ns minus available_ns in Codex's saved adaptation event files (run 45022134487). On the ordinary corpus the unmodified TensorFlow run has a median lag of 30.5 s, p90 62.4 s, maximum 72.1 s, and 0.4% of its 1,192 events inside 150 ms and 0.7% inside 250 ms; the adapted run is the same (median 32.2 s, 0.5% and 0.7%). On extended-middle the medians are 9.9 s (unmodified) and 9.1 s (adapted), maximum 15.0 s, and 0% inside 150 ms. No event has negative lag. So the TF path is not near either budget, by about a factor of 200 at the median, and the same script is what a corrected ONNX events file should be read with: the median and tail shares inside 100/150/250 ms come first, then the real scoring on the emitted clock. The script has a self-test and reads the events json the streaming recorder writes (`.json` or `.json.gz`). It scores nothing and is not a gate; saved data only.
