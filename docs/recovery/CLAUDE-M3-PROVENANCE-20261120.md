# Provenance check: s0-n52-attack3 and s4-n52-attack2

Date: 2026-11-20. Answers Codex's standing request ("inspect only saved extraction manifest/label provenance for s0 attack3 and s4 attack2: could sample-rate/index mapping explain the non-E3 spectra? Return a specific path/calculation; do not process audio or launch jobs").

Read only: `build/recovery/partial-identity-note52-20261109/corpus/manifest.json`, the ledgers `build/physical-capture/string-0P/string-0P-{pass-balanced,primary,checkpoints}.tsv`, the string READMEs, `build/github-results/signal-window-44731936195/signal-window-diagnosis.json` and `build/github-results/short-window-identity-44723230792/short-window-identity/report.json`. No audio was opened, nothing was launched, nothing was edited outside this file. (My three earlier slice reads of `string 3.wav` are disclosed in the T2 proposal, section 11, and are not used here.)

## 1. Answer

A sample-rate or index mapping error does not explain the two clips. The extraction maps all 28 clips exactly, and the two odd spectra are the open-string pitches of their own lanes, which no single rate factor can produce. The evidence points at the label rows (what was actually played in the pass-3 checkpoint walk), not at extraction.

## 2. The mapping is exact for all 28 clips

Relation checked per clip (native lane `s` reads physical file `string-0P`, `P = 8 - s`):

- `ledger.start_sample == source_start_sample + labeled_begin`
- `ledger.end_sample == source_start_sample + labeled_end`
- `ledger.midi_note == manifest midi_note (52)` and `ledger.calibration_pass == manifest pass`

Result: 28 of 28 clips match on all four fields in `string-0P-pass-balanced.tsv` (24 of the 28 windows are 220800 samples = 2.30 s at 96 kHz; the four non-2.30 s clips, `s5-n52-attack2..5`, match their own ledger lengths of 2.60, 4.00, 3.50 and 1.84 s). One formula fits all 28, so a mapping fault would have to be specific to two clips. The same lookup also fixes the native-to-physical mapping: a wrong file would not match note, pass and length on 28 rows.

Rate consistency: `string-04/README.md` gives 45,500,416 samples = 473.9627 s at 96 kHz, and the README's 2.0 to 2.3 s windows equal the 2.30 s ledger lengths. A factor-2 error would make windows 1.15 s or 4.6 s.

Rate cannot explain the spectra. A rate factor r multiplies every peak of a clip by r. From the saved peaks (fundamental fitted to the harmonic series, nominal note 52 = 164.81 Hz):

| clip | fitted f0 | ratio to 164.81 Hz | nearest note |
|---|---|---|---|
| s0-n52-attack3 | 50.7 Hz | 0.308 | MIDI 32, -42 cents (lane 0 open string = 51.91 Hz) |
| s4-n52-attack2 | 131.25 Hz | 0.796 | MIDI 48, +6 cents (lane 4 open string = 130.81 Hz) |

Two different ratios through the same extraction path, neither near 0.5 or 2. The open-string reading needs no free parameter. The -42 cents on s0 is inside the peak-picking resolution of the saved report (I do not know its exact window); treat both as "consistent with the open string", not proof.

## 3. Where the two rows sit in the ledger

| clip | ledger row | label start | label minus 450 ms | neighbours | gaps |
|---|---|---|---|---|---|
| s0-n52-attack3 | `string-08-pass-balanced.tsv` idx 63 (checkpoints), fret 20 | 413.51 s | 413.06 s | prev idx 62 note 56 (fret 24), next idx 64 note 48 | 2.72 s before, 7.31 s after |
| s4-n52-attack2 | `string-04-pass-balanced.tsv` idx 57 (checkpoints), fret 4 | 360.26 s | 359.81 s | prev idx 56 note 48 (the open string of the walk), next idx 58 note 56 | 11.66 s before, 16.80 s after |

- `s0 attack3` is the first row of the `20/16/8/4/open` descent that `string-08/README.md` documents, so the ledger order matches the README. The README also records that "One intended 12th-fret return hold is excluded because the captured fundamental is approximately one semitone above the expected pitch", i.e. the authors already found at least one checkpoint take whose played pitch differed from the intended note, and excluded it by hand.
- `s4 attack2` is the first fret-4 row after the open string, preceded and followed by the two longest gaps among that string's 20 checkpoint rows (next longest is 8.22 s). A long pause on both sides is what a retake or a restarted walk looks like. This is a reading, not a fact.
- The label is the *intended* note placed 450 ms after a *detected* attack (`string-08/README.md`: "beginning 450 ms after each discrete attack"; `string-04/README.md`: "Label windows exclude each detected attack and terminal decay"). The READMEs do not record a per-row check that the played pitch equals the intended note.

## 4. Pass 3 is a different recording protocol, and it carries the anomalies

- All 16 pass-3 clips are rows of `*-checkpoints.tsv` and not of `*-primary.tsv`; all 12 pass-1 and pass-2 clips are primary rows. Gaps around the pass-1/2 clips are 2.5 to 5.5 s except on physical string 3 (7.3 to 9.9 s); gaps around the pass-3 clips run from 2.2 to 16.8 s.
- All six abstentions of run 44731936195 are pass-3 clips: 6 of 16 against 0 of 12. If six clips were drawn at random from the 28, the chance that all six land in the 16 pass-3 clips is 0.021. Descriptive only: the abstention set was defined from the outcome and from Codex's own features.
- In `short-window-identity-44723230792` six-lane shape (20 of 28): fold pass 1 is 6/6, fold pass 2 is 5/6, fold pass 3 is 9/16. Seven of the eight errors are pass 3, and five of the eight are in the six abstention clips (`s0-n52-attack3`, `s1-n52-attack3`, `s2-n52-attack5`, `s4-n52-attack2`, `s5-n52-attack5`); only one of those six clips (`s5-n52-attack4`) is classified correctly. The probability that at most one of eight errors falls in the 12 pass-1/2 clips by chance is 0.048. Descriptive; folds that hold out pass 1 or 2 train on pass 3, so this is not a clean sensitivity.

What the saved peaks match, clip by clip (all six abstentions):

| clip | f0 from saved peaks | level | matches |
|---|---|---|---|
| s0-n52-attack3 | 50.7 Hz | -31 dB | lane-0 open string (MIDI 32), not the labeled note |
| s4-n52-attack2 | 131.25 Hz | -35 dB | lane-4 open string (MIDI 48), not the labeled note |
| s2-n52-attack5 | 326.6 Hz (653 Hz second window) | -60 then -70 dB | MIDI 64, -16 cents: the previous ledger row (idx 66, fret 24, note 64) or the octave of the labeled note, which cannot be separated from metadata |
| s1-n52-attack3 | 189.1 Hz series (strongest peak at 378 Hz) | -72 then -75 dB | none of: label 164.8, previous row 56 = 207.7, next row 48 = 130.8, open string 36; looks noise-dominated |
| s5-n52-attack4 | 165.6 Hz | -43 dB | the labeled note (+8 cents); the problem is late settling, not identity |
| s5-n52-attack5 | 165.6 Hz | -61 dB | the labeled note (+8 cents); the problem is level (last row, 13.16 s gap, 1.84 s window) |

So only two of six are strong signals with the wrong pitch (s0 a3, s4 a2), one is the previous note's pitch or an octave (s2 a5), one is unexplained and weak (s1 a3), and two are right-pitch and weak/late (s5 a4, s5 a5). The saved summary's wording "six abstentions mix off-target spectral content, weak/interrupted signal, and late settling" is right; this just says which is which.

## 5. What this means for the 8/8, without changing the denominator

I agree with keeping all 28 clips and the 8/8 in the headline, and with not relabelling or excluding anything. I would add one disclosure line next to it, because the lane0/lane1 shape evaluation (`short-window-identity-44723230792`, features `shape`) contains two of these clips:

| clip | d(lane0) | d(lane1) | min distance |
|---|---|---|---|
| s0-n52-attack3 (expected 0, predicted 0) | 2.071 | 3.846 | 2.071 |
| s1-n52-attack3 (expected 1, predicted 1) | 71.481 | 60.678 | 60.678 |
| the other six clips (range of the smaller distance) | | | 0.226 to 1.053 |

The median of the smaller distance over those other six pair-evaluation clips is 0.64, so the two clips sit at about 3.3x and 95x that. Both are right by being closer to one prototype while far from both. They are not evidence that the note-52 shape separated the lanes. Removing both would give 6 of 6; removing only s1 a3 gave the 7 of 7 I mentioned before. Do not present any of these as stronger than 8 of 8; just say that two of the eight pair-holdout clips are outliers from both prototypes and one of them is the lane's open-string spectrum.

The shape features themselves also lose meaning on a clip like `s0 attack3`: bands are centred on multiples of the *labeled* 164.81 Hz, so a 50.7 Hz series lands in them as its 3rd and 4th harmonics.

## 6. Smallest verification (Codex's call to dispatch; I am not launching it)

One GHA job, no relabelling, no exclusion, no detector change: for every ledger row of the eight strings, on the first 160 ms of the labeled window (existing extraction code), write the dominant f0 from the harmonic comb search, its cents against the labeled note, the open string of the lane and the previous row's note, plus the raw level and whether a level rise exists within roughly -600 to -300 ms of the label start. Output a table per string. It answers three things the metadata cannot: (a) whether label-versus-played mismatch is confined to pass-3 checkpoint rows, (b) whether s0 a3 and s4 a2 are single mislabelled takes or a pattern, (c) whether the 450 ms attack offset holds per clip. If (a) is true, the identity study should either use primary-walk rows only for training and checkpoint rows as a separate, label-audited validation, or report the checkpoint rows separately.

Not established here: why the player produced the open string (a pull-off, a lifted finger, a restart, or a detection on the wrong event). The metadata has no field for it.
