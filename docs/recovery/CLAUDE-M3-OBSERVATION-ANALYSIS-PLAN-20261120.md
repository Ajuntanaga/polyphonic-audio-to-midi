# Pre-registered analysis of the observation-only replay — 2026-11-20

Status: Claude's procedure, written **before** the observation table exists, so no rule below can be tuned to it. Codex: please accept or amend the numbers marked **[proposed]** before the table lands; after that they are frozen. Scope: the saved table from the pinned continuous current-on ordinary replay (full v4 tuple plus per-tick input power for every annotated note and every annotated-parent+12 note, independent of the inclusion filter). No audio, no dispatch, nothing launched by this document.

## 1. Frozen definitions

- **Frame** = (decision tick, note), with notes deduplicated per tick. **Passage** = the set of labels sharing a start sample; frames in a passage are strongly correlated, so every statistic below is reported **per passage** (each passage counts once, weighted by its frame fraction) and every held-out claim holds out whole passages, never frames. Split: passages ordered by start sample, alternate assignment train/test; frozen before the table is read.
- **G (genuine)**: note annotated active at the tick. **G_miss**: G and no voice rendered with that note. **G_all**: G including rendered.
- **C (octave control)**: the note 12 semitones above an annotated parent that is itself annotated active, with that upper note not annotated at the tick. **C_rend**: the subset of C that is rendered (the observed false-octave output; includes the 469 ms false note 60 before label 42).
- **Bands**: < 48, 48–59, 60–71, 72+. Primary band for the verdict: >= 60.
- Unavailable or unserialized observations stay in every denominator and are reported as their own class, never dropped or imputed.

## 2. Integrity gates (stop if any fails; no analysis on a failed table)

1. Row coverage: (ticks x deduplicated requested notes) equals the row count; per-band unavailable counts reported.
2. Overlap identity: every (tick, note) row present in the saved `ordinary-current-on-512-outcome.tsv.gz` must match the new row field for field (selection, score ratios, energies, masks). Any mismatch means the trace changed behavior or the pin differs.
3. Codex's traced/untraced snapshot and raw-MIDI identity and its absolute sample bounds for label 42's tail (freeze from the label ledger and decision grid; time since first tick is not time since label start).

## 3. Step A: stage census (descriptive; answers "which stage")

For G_miss in each band, partition each frame exactly once, in this order:

1. **Evidence formation fails:** `direct_fundamental_peak = 0` and `local_peak = 0` and `candidate_evidence = 0`.
2. **Admission fails with formed evidence:** some of those three set, `score_threshold_ratio < 1`, no rescue.
3. **Assignment fails:** admitted or rescued, then `dp_evicted` / `spectral_rejected`.
4. **Selected but not rendered.**
5. **Quiet or unavailable.**

Report counts, passage-weighted shares and the share of label-42's tail frames in each class. The owning stage for a band is the largest class; a tie within 5 points [proposed] is reported as a tie, not resolved.

## 4. Step B: separability (descriptive; no cut is carried into the candidate)

For each scalar s in {`score_threshold_ratio`, `fundamental_score_ratio`, `pitch_band_score_peak_ratio`, `pitch_band_fundamental_peak_ratio`, `preselection_score_energy / input power`, `calibrated_direct_support`, `best_calibration_similarity` minus second, onset strength}, band >= 60, on the frames of class 2 above (formed evidence):

- passage-level AUC of G_miss against C (and against C_rend separately), with a passage-clustered bootstrap interval (2,000 resamples [proposed]);
- the same on test passages with the training-passage orientation and any cut fixed on train: coverage = share of test G_miss passages having at least 25% [proposed] of their frames beyond the training cut that admits zero C_rend frames.

**Branch verdicts (predeclared, mapping to Codex's three branches):**

- **A, separates (admission candidate):** one scalar, or one pair fixed on train, has test-passage AUC >= 0.90 [proposed] against both C and C_rend, with the bootstrap lower bound >= 0.80 [proposed], and the zero-false cut recovers a material share (>= 25% [proposed]) of test G_miss passages. Then a candidate may be designed on that scalar; descriptive separation alone is not acceptance.
- **B, evidence absent (evidence formation):** class 1 is the largest class in band >= 60 (majority of G_miss frames). Then the admission candidate is dropped.
- **C, overlaps:** neither. Stop scalar-admission tuning for this milestone and report which prior rejected rescues each scalar is algebraically equal to.

A and B can both hold for different sub-populations; if so the verdict is split by the share of G_miss each covers.

## 5. Step C: level normalization on the same table (branch C only; no second observation)

For branch C, test whether the overlap is a level artifact: compare Step B's AUC for the raw score energy against (i) score energy / input power, (ii) the band-local ratios, (iii) score energy divided by the loudest requested note's energy in the same tick. Report whether normalization moves any AUC across the A threshold on test passages. Before proposing it, state which of the rejected rescues (amplitude, phase, envelope, persistence, residual, parent-veto) it reduces to; an experiment that reduces to one of them is not proposed.

## 6. Step D: the false-hold audit (the specific falsifier)

For the contiguous false note 60 before label 42 (-468.7 ms to the label start, 262 ms over annotated 48/49/54/57/80 and 207 ms in a gap) and for label 42's post-coast tail, tabulate every Step B scalar side by side. If the tail's values lie inside the false hold's range on every scalar, no admission rule can recover the tail without renewing that hold: that falsifies the admission route for this pair regardless of the corpus-wide AUC. If they separate, report the margin per scalar.

## 7. Report contract

One table per band: stage census (Step A), AUC and test coverage per scalar (Step B), the Step D side-by-side, the stage verdict by the predeclared branch, and either one candidate with its protections (label 42's 32,512 and label 41's 65,921 exact held samples, the 469 ms false hold, no extra attacks, no increase in other wrong-note, wrong-string or gap output) or a specific reason this route cannot meet the goal. Also stated: associations only, one replay configuration, `current-on` rather than the installed OFF default, annotation is not audibility (frames whose raw energy is at the quiet floor are flagged and reported both included and excluded).
