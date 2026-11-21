# Where is the headroom? Runtime leakage floor, lane separability, recall vs lane (saved data only)

Date: 2026-11-20. Trigger: the user's instruction "If there anything you can significantly improve, let codex know and proceed."
Read only: `build/physical-capture/unison-spectral-shadow/factory-current-20261012/factory-calibration-v2.m3cb` (sha256 prefix `b7025b4f`, the bank whose hash the octave runs report), the held-take runtime cell energies from run 44811182398 (`takes.json`, written by `CLAUDE-M3-OCTAVE-PARENT-SAVED-step1-20261120.py`), `docs/recovery/github-full-corpus-20261109.json` (run 42545080876) and `build/modal/isolated-05-assignment.tsv`. No audio, no source edit, no dispatch, nothing outside `docs/recovery/CLAUDE-*`.
Scripts (run as `python3 -I <script> <bank> <takes.json> [<corpus json>]`): `CLAUDE-M3-LANE-SEPARABILITY-step1-20261120.py` (pair map), `...-step2-20261120.py` (floor table and decomposition).

## 1. Result in one paragraph

I did not find a change I can show to be significant from saved data. What the saved data do support: (a) the runtime h2 share floor is real in the one-pole model and plausibly in the recorded cells, but it removes shape separability for only about 6% of lane pairs, almost all in lanes 0-3 at pitches 48-59, so leakage cancellation is a targeted fix for the note-52 lane0/1/2 family and not a broad lever; (b) in every multi-note corpus the larger shortfall is pitch recall, not lane choice given the pitch; (c) the one measurement that would say whether lane errors are an evidence-latency problem (accuracy by time since onset) does not exist in saved form.

## 2. Runtime cells against the bank, with a one-pole leakage model

Model: a unit-energy partial at f0 leaking into the one-pole cell centred at 2 f0 (d = exp(-1/(0.040 x 96000))): energy ratio `(1-d)^2 / ((1-d)^2 + 2d(1-cos(2 pi f0/fs)))`; -32.4 dB at 164.8 Hz (your -32 dB), -28.3 dB at 103.8 Hz, -36.4 dB at 261.6 Hz, -40.9 dB at 440 Hz. With phase free, a cell holding true share `a` and leakage `l` reports between `(l-a)^2` and `(l+a)^2` (amplitudes).

Of 26 (note, lane) cells with a bank point, 7 have bank h2/h1 <= -30 dB:

| cell | runtime median (n takes) | bank | run - bank | predicted floor | coherent range | inside? |
|---|---|---|---|---|---|---|
| (44,0) | -23.7 (5) | -30.2 | +6.5 | -28.3 | [-42.5, -23.2] | yes |
| (48,0) | -26.1 (4) | -35.2 | +9.0 | -30.3 | [-37.8, -26.4] | no, +0.3 dB |
| (60,1) | -31.4 (5) | -42.1 | +10.7 | -36.4 | [-42.6, -32.8] | no, +1.4 dB |
| (60,3) | -30.4 (4) | -35.6 | +5.2 | -36.4 | [-57.3, -30.0] | yes |
| (62,2) | -35.0 (2) | -30.5 | -4.5 | -37.4 | [-35.8, -27.3] | yes |
| (62,3) | -34.2 (2) | -40.4 | +6.2 | -37.4 | [-48.0, -32.7] | yes |
| (69,6) | -20.5 (2) | -34.4 | +13.9 | -40.9 | [-39.9, -31.0] | no, +10.5 dB |

Runtime is above the bank in 6 of 7 and inside the model range in 4 of 7 (6 of 7 within 1.4 dB if the corrected-energy factor, which is >= 1 and up to 9.03 dB, is allowed to push a cell slightly over). Of the 19 cells with bank h2/h1 > -30 dB, 15 agree within 3.7 dB; (60,7) +7.0 dB and (62,6) +6.5 dB do not, and cannot be a floor (bank h2/h1 is -7.6 and -2.4 dB there).

Reading: consistent with a leakage floor for the low-bank cells, not proven. Limits: the runtime values are `corrected_harmonic_energy` and I have not checked the bank's estimator, so run - bank mixes estimator, session and floor effects (the two large high-share differences show such offsets exist independent of any floor); (69,6) has two takes and sits 10.5 dB above the model, so something other than h1 leakage contributes at least there; the model ignores leakage from h3..h6 and from other partials into h1.

## 3. How many lane pairs does the floor hide? (bank-only pair map)

For each pitch 32..84, every pair of playable (lane, fret) options (367 pairs). Separation measures: bank cents difference; shape = max over h2..h6 of the dB difference of share/h1 (bank values below 1.5 q15 LSB clamped); "runtime" shape = the same after adding the model's incoherent leakage from the other five partials to every cell. Threshold 2 sigma, sigma = 3.06 dB, the median within-cell sd of runtime h2/h1 over the 16 cells with >= 4 takes (their range is 0.44 to 20.2 dB). The threshold is a descriptive choice, not a tuned value.

- Cents difference >= 10 c separates 232 of 367 pairs (63.2%); >= 5 c: 83.9%; >= 3 c: 89.9%. At pitches >= 69 only 0-2 of the 3-6 pairs per pitch are separated by >= 10 c, so lane identity there rests on shape evidence.
- Shape >= 2 sigma separates 336 pairs (91.6%) in the bank and 316 (86.1%) through the floor model.
- Separable in the bank but not through the floor: 22 pairs (6.0%): lane pairs (0,1) x8, (0,2) x5, (1,3) x3, (1,2) x2, (0,3), (2,3), (4,6), (5,6) x1 each, so 20 of 22 are within lanes 0-3; 18 sit at pitches 48..59 and 4 at >= 60.
- Not separable by >= 10 c or by runtime shape: 23 pairs (6.3%); 11 of those 23 would be shape-separable without the floor.

Do not read the 91.6% as an accuracy estimate: the measured runtime-domain leave-one-pass-out classification in `docs/POLYPHONIC-TRACKING-RESEARCH.md` is 62.0%, so this screen is far too permissive in absolute terms (every bank point has observation_count 2, per-point noise is not modelled, and a maximum over five harmonics is biased upward). I use it only as a difference: the floor model removes about 6% of pairs from the "has some shape separation" set, concentrated where Codex has been working (note 52, lanes 0-2).

## 4. Exact = P(pitch present) x P(right lane | pitch present)

From `github-full-corpus-20261109.json` (OFF output, run 42545080876, source `96509a4c`; not the current head). "Present" = matched + false_wrong_string voices; for `ordinary` this reproduces the reported 45.0% pitch-present; for the others it is the same identity, not independently checked.

| dataset | labeled | exact % | pitch present % | lane given present % |
|---|---|---|---|---|
| ordinary | 528,632 | 27.50 | 45.03 | 61.08 |
| constructed | 1,614,601 | 16.05 | 22.47 | 71.40 |
| synthetic-four | 310,640 | 16.43 | 20.40 | 80.53 |
| physical-long | 68,441 | 60.57 | 64.52 | 93.87 |
| isolated-08 | 31,050 | 96.03 | 97.89 | 98.10 |
| isolated-05 | 31,050 | 82.71 | 95.71 | 86.42 |
| isolated-02 | 35,550 | 82.25 | 86.19 | 95.43 |

On `ordinary`, raising lane-given-present to 95% alone gives 42.8% exact; raising pitch presence to 95% alone gives 58.0%; both at 95% give 90.25% (equal factors need 94.87% each for 90%). In the multi-note sets the recall factor is the lower one; lane choice given the pitch is the lower one only on isolated-05 (86.4%). This is arithmetic on your saved counts, not a prediction of what any policy would achieve, and the wrong-string count is voice-samples, so it is not an exact frame partition.

Side observation (descriptive, a sampled diagnostic trace, 2,482 candidate rows, not the corpus): in `build/modal/isolated-05-assignment.tsv`, 682 renderings carry `expected_note=0`; 388 (56.9%) are exactly +12 semitones above the expected note at that tick (the ghost notes are mostly 57-59; 472 of the 682 renderings are on lane 6), 149 (21.8%) are lane-0 note 32 against an expected note 18 semitones higher, and 145 (21.3%) occur at ticks with no expected note. The octave-ghost family appears in isolated single-note playing as well as in chords.

## 5. What I am not claiming, and what is missing

- No accuracy gain, threshold, policy or source change is proposed as validated. Everything above is saved-report arithmetic with the limits stated.
- The one measurement that would show whether lane errors on isolated notes are an evidence-latency problem (the accuracy-by-time-since-onset and by-error-class tables) cannot be computed: the corpus report keeps per-dataset hashes and counts, not per-frame outputs. An observation-only dump of per-frame outputs from an existing isolated replay (no policy change, reference output preserved) would supply it. I have not requested or launched it; dispatch stays with Codex.
- Leakage cancellation remains a candidate for the note-52 lane0/1/2 family only if the recorded complex-cell diagnostic you plan shows the floor on real cells; this note does not replace that diagnostic.
