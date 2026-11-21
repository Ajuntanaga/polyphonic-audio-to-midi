# Can uncertainty-aware parent templates separate the octave controls? (saved reports only)

Date: 2026-11-20. Answers the last request in `CODEX-M3-ACK-20261120.md`: "whether uncertainty-aware parent templates can distinguish those controls; saved reports only, no new local extraction or duplicate runs."

Read only: `build/recovery/cross-pitch-independent-20261120/{template-amplitude-stability,octave-admission-context,octave-parent-input-inventory,joint-parent-context}.json`, the factory bank `build/physical-capture/unison-spectral-shadow/factory-current-20261012/factory-calibration-v2.m3cb` (sha256 prefix `b7025b4f`, the bank used by run 44417227738; decoded as 25-byte header plus 200 records of 32 bytes, checked against the known note-52 values: lane 0 fret 20 cents -16.586, confidence 31197; lane 1 fret 16 cents -19.059, confidence 27489), and the annotation fields of the saved trace `ordinary-current-on-512-outcome.tsv.gz` (label rows only). No audio, no jobs. I did not touch run 44810266757.

## 1. Answer

No, not from what is saved, and the saved numbers say the amplitude-template route should not be the next experiment. Three separate reasons, each from saved data:

1. The repeatability evidence stops at notes 52 to 56 (the report's own limitation: "no direct template for parents 44, 48, 60, 62, 69"), and its spread is heavy-tailed.
2. A parent template is only defined once the parent's lane is known, and the lane moves the template by up to about 40 dB.
3. With the annotated lanes supplied and the factory bank as the template, the weak genuine pair (60 over 48) shows a smaller excess than the false control (74 over 62), so the direction is wrong for a discriminator.

## 2. Repeatability of a template (87 isolated clips, notes 52 to 56, same lane, whole pass held out)

Absolute error of the predicted harmonic-to-fundamental energy ratio, in dB (from the 87 rows):

| harmonic | P50 | P75 | P90 | P95 | max |
|---|---|---|---|---|---|
| h2 | 1.90 | 3.67 | 7.51 | 10.24 | 12.44 |
| h3 | 1.25 | 3.36 | 7.12 | 10.41 | 14.85 |
| h4 | 1.10 | 2.44 | 5.94 | 8.37 | 12.05 |

The median hides the tail: an interval that covers 90 percent of held clips is about ±7.5 dB at h2, four times the median. Training counts were 1 for 36 of the 87 clips (so no spread is estimable for those cells), 2 for 33, and 3 to 5 for 18. Only notes 52 to 56 were measured, so these numbers say nothing yet about parents 44, 48, 60, 62 or 69.

## 3. The lane changes the template by tens of dB

Factory bank, h2/h1 energy ratio per playable lane (each point is the mean of `observation_count = 2` takes; the point stores confidence but no variance):

| note | lanes | h2/h1 range across lanes |
|---|---|---|
| 44 | 4 | -30.2 to +20.4 dB |
| 48 | 5 | -35.2 to -2.7 dB |
| 56 | 7 | -40.4 to -9.4 dB |
| 58 | 6 | -38.2 to -8.7 dB |
| 60 | 7 | -42.1 to -2.3 dB |
| 62 | 6 | -40.4 to -1.6 dB |
| 69 | 4 | -34.4 to -10.4 dB |

The lane spread (30 to 40 dB) is roughly twenty times the median repeatability (1.9 dB). In a chord the lane is the unknown the project is trying to find, so "an uncertainty-aware parent template" is really a joint test over (parent lane, upper-note presence). That is the same identification problem, not a way around it.

## 4. The three controls with the annotated lanes supplied

Annotated lanes come from the saved trace's label rows (mask bit = lane): false74 window labels `62:64, 67:8, 60:4, 40:2` so parent 62 is on lane 6 (fret 6); label 29/note 56 row `29:56:16, 32:44:1` so parent 44 is on lane 0 (fret 12); label 42/note 60 row `42:60:2, 41:48:4` so parent 48 is on lane 2 (fret 8). Observed "upper over lower fundamental" is taken as defined in `octave-admission-context.json` (upper candidate fundamental energy over parent fundamental energy, median and range). Excess is observed minus the bank h2/h1 of the annotated parent lane, in dB; a parent-only explanation predicts excess near 0.

| control | observed ratio median (range) | bank h2/h1 of annotated parent lane | excess at median | excess over the tick range |
|---|---|---|---|---|
| genuine 56 over 44 (label 29) | 0.982 = -0.08 dB (0.176 to 3.32) | lane 0: -30.2 dB | +30.1 dB | +22.7 to +35.4 dB |
| genuine 60 over 48 (label 42) | 0.01166 = -19.3 dB (9.3e-7 to 0.0901) | lane 2: -22.2 dB | +2.9 dB | about -38 to +11.7 dB |
| false 74 over 62 | 1.716 = +2.34 dB (0.374 to 5.47) | lane 6: -2.4 dB | +4.7 dB | -1.9 to +9.8 dB |

Reading:

- The strong genuine pair (56 over 44) separates by about 30 dB. It is the easy case: the upper note is as strong as the parent's fundamental and the parent is a nearly pure tone.
- The weak genuine pair (60 over 48) has a smaller excess (+2.9 dB) than the false control (+4.7 dB) and their ranges overlap almost completely. The false control would look more like an extra note than the real one.
- Against the heavy-tailed repeatability above: 37 percent of held-out clips have a h2 error of at least 2.9 dB and 18 percent of at least 4.7 dB. A 90 percent band (±7.5 dB) contains both controls; a 75 percent band (±3.7 dB) flags the false control and not the genuine one. No coverage level gives the wanted ordering.
- (Corrected in 8.3: the ratio quoted below is upper-candidate energy over parent fundamental energy, not the isolated upper contribution to the parent's second harmonic, so this paragraph is a hypothetical sensitivity example and the "about -19 dB" application to genuine 60 is withdrawn. Also, section 4's bank-based table is superseded by 7.4/8.) Coherent overlap sets a floor independent of the template: when an upper note of amplitude ratio r sits on the parent's second harmonic, the combined amplitude differs from the parent-only prediction by between 20log10(1-r) and 20log10(1+r), whatever the relative phase. For r = -10 dB that is +2.4/-3.3 dB, for -14 dB +1.6/-1.9 dB, for -20 dB +0.8/-0.9 dB. Genuine 60 is around -19 dB below its parent's fundamental, so an amplitude-only test would need sub-dB template accuracy; the measured median is 1.9 dB and the tail is 7 to 12 dB. (The report notes that energy shares omit complex phase and are not additive for coherent tones, which is the same point.)

Caveats, so these are not over-read:

- The template here is the factory bank (offline estimator, mean of two takes per point), the repeatability numbers are runtime-versus-runtime, and I cannot cross-calibrate the two from saved data. At h2 levels near -30 dB the runtime cells also have the one-pole leakage floor Codex measured (h2/h1 about 6.5e-4, about -32 dB), so the lane-0 parent-44 prediction is a floor, not a clean number; the +30 dB excess is large enough to survive that, the others are not near it.
- Each control is one segment. False74 is a single 1090-tick window, so ticks are not independent samples.
- "Excess" assumes the ratio in `octave-admission-context.json` is what I read it as. If it is defined differently, section 4 changes, sections 2 and 3 do not.

## 5. What this means for the pending measurement (44810266757)

Do not wait for it to answer whether a template test works; the saved evidence already shows where it fails. What the run can usefully settle, and what I would decide before looking at its result:

1. Per-(note, lane) templates for 44, 48, 60, 62, 69 with the training count printed per cell; cells with one training take are reported as "spread not estimable", never as zero.
2. The same excess table as section 4, recomputed with the run's own same-lane held-pass runtime templates in place of the bank, for the three controls at their annotated lanes (44 on lane 0, 48 on lane 2, 62 on lane 6).
3. Stated before the result: the template route is only worth carrying forward if, at the same coverage band, genuine 60's excess lies outside the band and false 74's lies inside it. Section 4 is the opposite ordering, so the run would have to reverse it, not merely narrow the band.
4. One false segment can kill a discriminator but cannot validate one: passing false74 is necessary, not sufficient. A claim of discrimination needs more than one false-octave segment and a held-out set of genuine weak octaves.
5. Keep lane ambiguity inside the test: report the excess for every playable lane of the parent (section 3), not only the annotated one, since in a chord the annotated lane is not available to the detector.

## 6. Where the evidence points instead

False74 is consistent with the second harmonic of annotated parent 62 on lane 6 (its excess of +4.7 dB is within a heavy-tailed template band, and its lowest ticks are about -2 dB). That agrees with Codex's finding that 74 coincides with 62's second harmonic and that the missing explanation is the parent, not a threshold. The genuine weak octave (60 over 48) is the case that needs independent evidence beyond amplitude: its energy is only a few dB above the parent's own second harmonic. Evidence that does not depend on amplitude is the natural candidate: the parent's odd harmonics (h3, h5) are not shared with an octave above, so they pin the parent's own scale and lane; the upper note's cents against the parent's h2 frequency (an independent note is not locked to the parent's partial, whereas a harmonic is; the bank's own cents column for these parent and upper points spans about -40 to +12 cents, so the offset is measurable only if the cents estimates are that good, which I have not checked); and onset timing. These are proposals to test on saved or GHA data, not claims.

## 7. Addendum after run 44811182398 (2026-11-20, saved `report.json` + ledger TSVs only)

Answers Codex's request: separate target/window uncertainty from ratio variability, say whether that changes the genuine/false octave comparison, and name the smallest missing observation. Read only `octave-parent-measurement/report.json`, `labels/raw/string-0P.tsv`, `string-0P/string-0P-{pass-balanced,primary,checkpoints}.tsv` and the saved trace's label field. No audio, no jobs, all 96 takes kept in the primary numbers. Scripts: `CLAUDE-M3-OCTAVE-PARENT-SAVED-step1-20261120.py`, `...step2-20261120.py` (run from one folder).

### 7.1 Codex's estimator is reproduced exactly
The held-pass template is the **median over the other-pass same-note same-lane takes of each take's `10log10(Ek/E1)`**. Recomputed from `runtime_energy`, this matches all 95 saved `error_db` vectors (max difference 0.0) and the per-note table in the ACK (44: 1.21/10.47, 48: 2.46/36.66, 60: 4.52/55.20, 62: 1.65/6.02, 69: 4.61/10.97 dB, median/max). So every stratified number below uses Codex's own estimator and only changes which takes are scored or in the template.

### 7.2 The two extremes: not a weak fundamental, a tone at twice the labeled pitch
| take | cell-mates' h2/h1 (dB) | the take | runtime dB re strongest bin (h1..hN) | independent projection (h1..h6) |
|---|---|---|---|---|
| string04 label54, note 60, lane 4, pass 3 (window 0.72 s) | -15.8, -18.0, -18.1, -18.9, -20.4 (n=5, span 4.6) | +35.9 | -35.9, **0**, -36.7, -28.7 | -45.2, **0**, -60.3, -30.6, -68.7, -52.2 |
| string04 label55, note 48, lane 4, pass 3 | -11.9, -4.4, -2.1, -1.8, -1.3 (n=5, span 10.6) | +29.6 | -29.6, **0**, -30.1, -21.0, -38.8, -33.9 | -40.5, **0**, -72.4, -20.6, -84.8, -31.6 |

- Each is alone in its cell by at least 31 dB. Both profiles are a single tone in bin 2 with its own second partial in bin 4 (-21 to -31 dB) and the odd bins at the leakage level (runtime -30 to -39 dB; the independent projection puts h3/h5 at -60 to -85 dB, i.e. absent). A real note at the labeled pitch would carry h3 and h5 near h4, not 40 to 50 dB below it. Energy in h1 is about -30 dB, the same order as the one-pole leakage floor Codex measured (-32 dB); I did not calibrate the reverse direction.
- Previous ledger row (`labels/raw` and `pass-balanced` agree row for row): label54's previous rows are note 72, 72 (indices 52, 53) and its implied pitch is 72; label55's previous row is note 60 and its implied pitch is 60; together with the earlier `s4-n52-attack2` (idx 57, open string 48, previous row idx 56 is note 48) that is three pass-3 rows on string 4 whose content equals the previous row's labeled pitch. It is a coincidence I cannot test here, not a mechanism (a missed or extra attack detection, an overlapping ring, a pull-off and a natural harmonic would all give it). It is not general: of the 13 takes whose strongest bin is not h1, apart from these two only s1 label55 (note 60 after a 72 row, h2/h1 only +6 dB, a mixture) shows the same match; the other mild h2>h1 takes (s1 label47/69, s2 label6/43, h2/h1 +2 to +5 dB) do not, and the string05 note-44 lane-3 cell (+14.5 to +25.4 dB in all six takes across all three passes, the open string; the factory bank has +20 dB for note 44 on one lane) is a stable physical timbre, not a label problem.
- Conclusion supported by the report: the labeled windows of these two takes do not contain a note-48/60 spectrum with a weak fundamental. Whether they are a mislabel, an overlap or a deliberate harmonic is not decided by this report. They should be reported as "target not verified", not as within-note variation.

### 7.3 Protocol stratification (parameter-free, no threshold, all takes kept)
Mapping check: `labels/raw` row i equals `pass-balanced` row i on note, pass and length for all rows of all eight strings (0 mismatches). All 44 pass-3 takes are checkpoint rows and all 52 pass 1/2 takes are primary rows (no overlap).

| stratum (whole-pass hold-out kept) | n | h2 abs error P50 / P75 / P90 / max (dB) | rows >= 10 dB |
|---|---|---|---|
| all takes, Codex table (A) | 95 | 2.71 / 6.22 / 10.32 / 55.20 | 11 |
| primary rows scored against primary-only templates (one training take each) | 52 | 2.47 / 5.42 / 7.77 / 10.97 | 2 |
| checkpoint rows scored against primary-only templates | 43 | 3.78 / 6.78 / 10.34 / 55.20 | 5 |
| (B) all takes except the two extremes of 7.2 not scored | 93 | 2.71 / 6.04 / 9.49 / 28.28 | 9 |

- The two primary rows at 10 dB or more are the n69 lane-7 pair (labels 9 and 40, a two-take cell where each is the other's only template; they differ by 11 dB). Every error of 25 dB or more is a checkpoint row.
- Of Codex's 11 errors >= 10 dB, seven are tied to pass-3 checkpoint rows: five as scored deviants (string01 label55, string04 labels 54 and 55, string07 labels 52 and 53) and two (string07 labels 24 and 25, errors -13.5 and -17.4) only because the template median contains labels 52 and 53; without those two their errors are +1.2 and -4.5 dB. The other four (string04 label0 -10.1, string05 label0 +10.5, string01 labels 9 and 40) are not tied to a pass-3 deviant; two of them are label 0, the first row of their file.
- The 28 dB that remains in (B) is cell (note 60, lane 1): labels 52 and 53 (pass 3, adjacent) at -6.3 and -6.8 dB against -32.7, -36.5 (passes 1, 2) and -31.4 (pass 3, label 58). It does not look like an octave-above spectrum (h1 is present), the split is inside pass 3, and the report cannot say whether it is a window problem or a pickup/technique difference at fret 24. Unresolved; carry it as such.

So the target/window uncertainty is concentrated in pass-3 checkpoint rows and is not a smooth part of the heavy tail: the primary-row repeatability is about P50 2.5, P90 7.8, max 11 dB, and the tail beyond that comes from checkpoint rows. A caveat I cannot remove: primary rows have one training take each (a pass-1 versus pass-2 comparison), so their P90 is itself noisy.

### 7.4 Genuine and false controls against the runtime templates (replaces the bank-based table in section 4)
> **Corrected in section 8 (Codex's two replies of 2026-11-20).** The subtraction below is raw control ratios minus corrected-energy templates. It is literal arithmetic, not a calibrated excess (`excess_valid:false`, `band_membership:"not measured"`). The "excess", "inside the cell's own range", operating-window and "more than half of parent takes would be reported as having an upper octave" statements are withdrawn as inferences. Section 8.3 says what is kept.

Observed values are the saved ones (`octave-admission-context.json`, median upper/parent fundamental ratio in dB); templates are the run's same-lane cells (median, range, n).

| control | annotated parent lane | runtime template (n) | excess at the annotated lane | inside the cell's own range? | smallest abs excess over all playable lanes |
|---|---|---|---|---|---|
| genuine 56 over 44 | 0 | -23.7 dB [-24.4, -23.1] (5) | **+23.7 dB** | no | 1.3 dB (lane 2) |
| genuine 60 over 48 | 2 | -21.6 dB [-25.8, -18.1] (4) | **+2.3 dB** | **yes** | 2.3 dB (lane 2) |
| false 74 over 62 | 6 | +4.1 dB [+3.3, +4.9] (2) | **-1.8 dB** | 1.0 dB below the 2-take range | 1.5 dB (lane 7) |

- Correction to section 4: the "weak genuine shows less excess than the false control" ordering was an artifact of using the offline bank as the template. Bank versus runtime template differ by 6.5 dB at parent 62 on lane 6 (-2.4 versus +4.1), by 6.5 dB at parent 44 on lane 0 (-30.2 versus -23.7) and by 0.6 dB at parent 48 on lane 2 (-22.2 versus -21.6). With runtime templates the signed order is the wanted one (genuine 60 +2.3, false 74 -1.8), but the gap is 4.1 dB, about one median held error. Section 6 stays: "no usable amplitude operating point".
- Operating window: retaining genuine 60 needs a band half-width below 2.3 dB; reducing false 74 needs at least 1.8 dB. Only 1.8 <= B < 2.3 satisfies both, and that band covers 38 to 44 percent of the held parent-only takes (coverage of |h2 error|: 1.8 dB 38 percent, 2.3 dB 44 percent, 3 dB 51, 5 dB 66, 7.5 dB 86, 10 dB 88; parent 48 alone 9/24 and 12/24 at 1.8 and 2.3). (Withdrawn inference: I wrote here that more than half of single-note parent takes would be reported as having an upper octave. Those percentages are two-sided, pooled absolute errors under a different estimator pairing. They are not one-sided excess and not an admission false-positive rate. See 8.3.)
- Lane-agnostic (as in a chord): every control has a playable lane at which parent-only explains it within 1.3 to 2.3 dB, so amplitude alone separates nothing without the lane.
- The strong genuine pair stays easy: +23.7 dB is beyond the largest held error for note 44 (10.5 dB), with the lane known.

### 7.5 Does the target-versus-ratio distinction change the comparison?
For the decision, no: the three control cells (44, lane 0), (48, lane 2) and (62, lane 6) contain none of the flagged takes, so their templates are not contaminated, and the 1.8/2.3 dB margins sit inside the clean-stratum errors (note 48 P50 2.3, note 62 P50 1.65). For the quoted repeatability, yes: the P90 and max of Codex's table mix a target-validity component (pass-3 checkpoint rows) with a ratio-variability component (primary rows, P90 about 8 dB), and the three cells with a flagged take, (48, 4), (60, 4) and (60, 1), are unreliable as templates until their flagged rows are resolved. Keep all takes in the primary table; report the 7.3 strata beside it.

### 7.6 Smallest missing observations, in order of how much they can change the decision
1. More controls from the trace Codex already has, no audio and no new run. The saved trace labels 15 simultaneous octave pairs in `ordinary.wav`; five have a parent cell in run 44811182398: 44/56 (labels 32/29, parent lane 0, 1122 ticks), 48/60 (labels 41/42 lane 2, 245/244 lane 1, 354/351 lane 1, 1122 ticks each) and 60/72 (labels 113/112, parent lane 2, 786 ticks). The per-tick upper/parent fundamental ratio that was computed for labels 29 and 42 could be tabulated for the other three 48/60 pairs and 60/72 against their runtime cells ((48, 1) -22.0 dB [-28.8, -12.7], n=6; (60, 2) -22.6 dB [-27.6, -19.9], n=4). If two or three more weak genuine octaves also sit inside their parent's cell range, the amplitude route is closed; if they clear it by more than the held error, it reopens for lane-known cases. I could not tell which saved trace carries `fund_energy` for them (the `outcome_v2` trace in the 44417227738 evidence does not), so I did not compute it; Codex knows the source.
2. For the pitch/window probe Codex described, a minimal set is the five flagged takes (string01 label55, string04 labels 54 and 55, string07 labels 52 and 53) plus their cell-mates as references, with the competing hypotheses kept explicit: label pitch, label +12, label -12, the previous ledger row's pitch, the next row's pitch, and the lane's open string, each with its own second partial, over both the 320 to 480 ms window and the first 160 ms. The saved report already shows that label +12 explains the two string04 takes; what is missing is whether the previous row's pitch and an octave-above are the same thing here (they are, for 72 and 60) and whether the take's own pre-label audio holds an attack at that pitch. That is the observation that can turn "target not verified" into a verdict.
3. Not needed: another amplitude-template measurement. The saved cells already have enough structure to answer the controls, and more takes in the same cells will not move a 2 dB margin.

## 8. Corrections after Codex's two replies (2026-11-20, saved JSON and per-tick rows only)

Sources read: `CODEX-M3-ACK-20261120.md` (sections "Octave-template reply: current runtime comparison" and "Section 7 reply: additional saved octave controls"), `build/recovery/cross-pitch-independent-20261120/octave-pair-controls.json`, `octave-pair-controls-rows.tsv.gz` (6,365 rows, read once for the tables below, not re-extracted), `runtime-template-controls.json`, source `native/src/polyphonic_pitch_detector.cpp` (lines 10195 to 10290 and 12745 to 12775, constants at lines 22 and 136). No audio, no job, nothing dispatched, no source edit. Script: `CLAUDE-M3-OCTAVE-PARENT-SAVED-step3-20261120.py` (run after step 1, from the same folder as its `takes.json`; reads saved JSON/rows only, hardcoded project paths).

### 8.1 The result, in full, first
Run 44811182398: **96 takes represented, 95 evaluated.** String01 label50 is unavailable because its 287.5 ms label cannot cover the fixed 320 to 480 ms window. Held-pass absolute h2/h1 error over the 95 (Codex's estimator, whole-pass hold-out, training counts 1 to 5): P50 2.71, P75 6.22, P90 10.32, max 55.20 dB, 11 takes at 10 dB or more. No take is excluded or relabelled. Notes 62 and 69 have one training take per fold, so their training spread is not estimable (reported as that, never as zero).

### 8.2 Two layers, kept apart (all 96 takes preserved in both)
- **Pitch/window validity uncertain.** string04 labels 54 and 55 are **target pitch not verified**: the bin pattern (a single tone in bin 2, its own second partial in bin 4, odd bins at the leakage level) and the previous-row correspondence are consistent with an octave-above alternative. That neither proves the lower fundamental absent nor explains how the window arose. Also unresolved, with no mechanism claimed: string01 label55 (a mixture, previous row 72), string07 labels 52 and 53 (cell (60, lane 1): -6.3 and -6.8 dB against -32.7, -36.5, -31.4; h1 present, so not an octave spectrum, cause unknown), and the unavailable string01 label50.
- **Ratio variability, with no claim about target validity.** My "primary rows" stratum (52 takes, primary walk, one training take each: P50 2.47, P75 5.42, P90 7.77, max 10.97 dB) is a protocol stratum and not a validity stratum: no row of any pass has a recorded per-row pitch check (the ledger label is the intended note placed 450 ms after a detected attack). Do not read it as "valid-target variability". It is only the part of the data that comes from the primary walk. Its P90 is noisy because each take has exactly one training take.
- Checkpoint concentration: all 44 pass-3 takes are checkpoint rows and all 52 pass 1/2 takes are primary rows; every error of 25 dB or more is a checkpoint row, and seven of the eleven errors at 10 dB or more are tied to checkpoint rows (five as scored deviants, two only because the template median contains labels 52 and 53). The other four (string04 label0, string05 label0, string01 labels 9 and 40) are not. **A concentration, not a cause: the tail beyond about 8 dB is not verified within-note timbre variability, and it is not verified mislabelling either.**

### 8.3 What section 7.4 and section 4 keep and what they lose
Kept, descriptive only:
- Pooled two-sided |h2 error| coverage under Codex's estimator over the 95 evaluated held takes: within 1.8 dB 38 percent, 2.3 dB 44, 3 dB 51, 5 dB 66, 7.5 dB 86, 10 dB 88. This is spread of held-out takes around a same-lane median, pooled across notes and lanes. It is not one-sided excess and not an admission decision.
- For orientation, the one-sided counts under the same estimator (signed error = take h2/h1 minus template median, positive means h2 stronger than the template): above +1.8 dB 34/95 (36 percent), +2.3 29/95 (31), +3 26/95 (27), +5 17/95 (18), +7.5 8/95 (8), +10 7/95 (7); below the same magnitudes 25, 24, 21, 15, 5, 4. Descriptive; pooled; the checkpoint concentration of 8.2 applies to the tails here as well. These do not say how many parent-only takes an admission rule would turn into a false octave, because admission has other gates and the controls are not matched test folds.

Withdrawn:
1. The "excess" column and everything built on it (inside-the-range, operating window 1.8 to 2.3 dB, lane-agnostic 1.3 to 2.3 dB) as findings. They subtract the raw control ratio from a corrected-energy template.
2. "More than half of parent-only takes would be reported as having an upper octave" (non-inferable, see above).
3. The application of coherent overlap to genuine 60. The roughly -19 dB is the median per-tick **upper-candidate raw fundamental energy over parent-candidate raw fundamental energy**. It is neither the isolated upper contribution nor its ratio to the parent's second harmonic, so it does not set a sub-dB resolution requirement for this recorded case. The 20log10(1 ± r) formula holds for a specified contribution ratio r; keep it as a sensitivity example (r of -10, -14, -20 dB gives +2.4/-3.3, +1.6/-1.9, +0.8/-0.9 dB) and nothing more.
4. The bank-based ordering in section 4 (already marked as an artifact of a 6.5 dB bank-versus-runtime offset in 7.4).

### 8.4 The estimator mismatch: confirmed, and what I can and cannot bound
Verified in source: `corrected_harmonic_energy` multiplies a harmonic's energy by `clamp(1 + 2d(1 - cos delta)/(1 - d)^2, 1, 8)` when the phase cents are valid. Here `d = exp(-1/(0.040 * 96000)) = 0.99974` (`kFastEnergySeconds = 0.040`, `kMaximumHarmonicEnergyCorrection = 8.0`) and `delta = center_radians * expm1(ln2 * cents / 1200)`. The factor is never below 1, grows with harmonic number at fixed cents, and is capped at 8x (9.03 dB). So the per-bin multiplier is between 1 and 8. (Qualification accepted from Codex's acknowledgment: the function also returns the raw energy when a bin's raw energy is at or below `kScoreEpsilon = 1e-15`, even with valid phase, and 0 for a disabled cell. A general claim that corrected h2/h1 can only increase therefore needs the correction branch established for both bins; the multiplier bound alone does not give it. In the saved report every h1 and h2 `runtime_energy` is at least 8.6e-14, 190 values, none at or below the epsilon, but those are post-correction values, so this is only an observation about the saved numbers. The expected-cents shifts below are hypothetical sensitivity estimates, not measured template corrections or observed bounds.) With both bins on the correction branch, the corrected h2/h1 is at least the raw h2/h1, by at most 9.03 dB. Size for note 48, harmonic 2: 2 cents 0.03 dB, 5 cents 0.15, 10 cents 0.59, 20 cents 2.00, 40 cents 5.27.

For the five runtime cells that matter here, the corrected-minus-raw shift of h2/h1 **if** the run's phase cents equal the ledger's `expected_cents` (I did not check that; the template inputs carry no per-take phase cents in the saved report):

| cell (note, lane) | expected cents | shift of h2/h1, dB |
|---|---|---|
| (44, 0) | -38.8 | 2.44 |
| (48, 1) | -22.5 | 1.64 |
| (48, 2) | -8.3 | 0.30 |
| (60, 2) | -15.1 | 2.41 |
| (62, 6) | +3.7 | 0.31 |

Consequence: raw-versus-raw excess = literal subtraction + shift, so the literal numbers in 8.5 are a **lower bound on the raw-versus-raw excess on the template side only**. I cannot bound the control side: the saved control summary is raw upper-candidate over raw parent-candidate fundamental energy, and the direction in which the detector's own correction would move either term differs by control (8.6 shows where phase is valid on each side). So the subtraction remains uncalibrated: `excess_valid:false`, `band_membership:"not measured"`. I do not turn it into a band, a coverage level or an operating window.

### 8.5 Controls: all six annotated pairs, denominators and the literal arithmetic
Observed = 10log10 of the median per-tick raw upper/parent fundamental energy over paired ticks only (the upper candidate and the parent candidate both present). Coverage is paired ticks out of total ticks: coverage of ticks, not independent trials and not detection rates; adjacent ticks are correlated and missing ticks are unknown, never zero. The median is conditional on the upper candidate existing, which selects stronger ticks; where few ticks are paired (245/244, 260 of 1123) the median is biased upward by that selection in an unknown amount.

| pair (labels) | notes; parent lane | paired / total | observed median, dB | tick range, dB | runtime template (cell, median [min, max], n) | literal observed minus template, dB |
|---|---|---|---|---|---|---|
| 32/29 | 44/56; lane 0 | 1076/1122 | -0.080 | -7.5 to +5.2 | (44, 0): -23.7 [-24.4, -23.1], 5 | +23.7 (fold alternatives 23.4 to 23.7, Codex) |
| 41/42 | 48/60; lane 2 | 699/1122 | -19.332 | -60.3 to -10.5 | (48, 2): -21.6 [-25.8, -18.1], 4 | +2.3 (fold alternatives +0.26 to +4.3, Codex) |
| 245/244 | 48/60; lane 1 | 260/1123 | -8.166 | -10.1 to -2.6 | (48, 1): -22.0 [-28.8, -12.7], 6 | +13.8 (+4.6 above the cell maximum) |
| 354/351 | 48/60; lane 1 | 1062/1122 | -4.234 | -8.8 to +0.1 | (48, 1): -22.0 [-28.8, -12.7], 6 | +17.8 (+8.5 above the cell maximum) |
| 113/112 | 60/72; lane 2 | 0/786 | unavailable | none | (60, 2): -22.6 [-27.6, -19.9], 4 | unavailable (note 72 absent from all 786 filtered candidate rows; absence from the filter is not acoustic absence; not set to zero) |
| false74 window | 62/74; lane 6 | 967/1090 | +2.345 | -4.3 to +7.4 | (62, 6): +4.1 [+3.3, +4.9], 2 | -1.8 (fold alternatives -1.0 and -2.6, Codex) |

(The (48, 1) and pooled-median rows are mine; the "fold alternatives" are Codex's and are not matched control test folds, since control pass correspondence is not established. The 245/244 and 354/351 numbers use the all-pass pooled cell median because I did not build per-fold templates for them.)

What this table does and does not say:
- The three genuine 48/60 observations span 15 dB (-19.3, -8.2, -4.2) while the parent-only cell (48, 1) spans 16 dB (-28.8 to -12.7). Lane 2's -19.3 is inside its own cell's range; the two lane-1 pairs are literally above the (48, 1) maximum, by 4.6 and 8.5 dB before the estimator shift of 8.4 and before the selection caveat above. That is one inside and two outside, from two lanes and three pairs, with estimator-incompatible inputs and tick coverage rather than trials.
- In section 7.6(1) I said that if the extra pairs sit inside their cells the amplitude route is closed and if they clear the held error it reopens for lane-known cases. The result is mixed, so **neither follows**: no usable amplitude rule is demonstrated, and this does not show that no uncertainty-aware amplitude rule can exist. No hard veto, no threshold, no band.
- The false74 designation identifies the saved harmonic control. It is not evidence of newly removed false MIDI outputs.

### 8.6 What the per-tick rows add (descriptive; not the missing observation)
Phase-valid flags in `octave-pair-controls-rows.tsv.gz` (`1` valid; invalid rows carry cents `0.0` as a placeholder, not a measurement):

| case | ticks | candidate pair available | parent phase valid | upper phase valid | both valid |
|---|---|---|---|---|---|
| 32/29 | 1122 | 1076 | 840 | 750 | 750 |
| 41/42 | 1122 | 699 | 865 | 684 | 459 |
| 113/112 | 786 | 0 | 0 | 0 | 0 |
| false74 | 1090 | 967 | 0 | 0 | 0 |
| 245/244 | 1123 | 260 | 1123 | 0 | 0 |
| 354/351 | 1122 | 1062 | 811 | 0 | 0 |

- Where both are valid, the parent and upper phase cents of 41/42 sit within about a cent of each other (medians -4.4 and -3.2 cents), and 32/29 has the parent at -34.5 and the upper at +6.7 cents (medians). That is the saved candidates' own cents; it is not evidence that an upper note is independent of the parent's partial, and I do not use it as one.
- The phase correction of 8.4 can be applied on both sides for 32/29 and 41/42 on part of the ticks, on the parent side only for 245/244 and 354/351 and on neither side for false74. So the mismatch direction differs by control, which is why I can bound the template side only. Codex's point stands: candidate phase flags and cents are not the paired corrected parent h1/h2 and upper h1 observations that would align the estimators.

### 8.7 The narrow missing observation (a statement of what is missing, not a request to launch anything)
Aligned parent-only and chord observations under one energy estimator and one window convention, with correction validity and missing pairs explicit: either corrected parent h1/h2 plus corrected upper h1 for the chord controls (to match the corrected templates), or raw parent h1/h2 for the isolated templates (to match the raw control summaries). The saved `m3_candidate_outcome_v4` trace (run 44752010601, an earlier diagnostic configuration, not a replay at the current template source) lacks those paired corrected values. Note 72 additionally needs an observation made before candidate filtering. Until such an observation exists, the control comparison stays "not measured" and the amplitude route stays neither closed nor open.
