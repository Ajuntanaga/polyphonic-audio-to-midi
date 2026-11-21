# Fixed whole-pitch spectral ablation screen

The previous dictionary retained approximately one pitch per nonsilent mixture at its train-only 99%-precision cutoff and recovered no complete three-to-five-pitch training mixture. This screen tests a different evidence measure: does removing every template for one pitch make the other pitches unable to explain the remaining spectrum?

## Source finding kept separate

The completed source verification found eight sustained non-octave disagreements and seven octave-related ambiguities among the targeted takes. Saved provenance does not establish an indexing, crop-coordinate or pitch-shift fault. The five next-cue-like string-01 discrepancies have an agreeing row between them, contradicting a uniform index offset. The three other non-octave cases favor an open string. Intended cue labels are not independent played-pitch measurements.

`source-consistency-20261121.json` records these findings without replacing the source manifest, changing a label or filtering an example. It records 40 examined takes and 515 not examined. A capture-time cue/performance ledger anchored to source samples would be needed to justify any alternative labels. The original benchmark remains authoritative. This metadata is pinned in the screen but not used in model fitting or source selection.

## Frozen computation

- Keep the original 555 sources and pass roles: 200 training, 200 calibration, 155 test. Keep the existing seeds, gains and 16,384-sample trailing context at 96 kHz.
- Average Hann power spectra from seven 4,096-sample and three 8,192-sample windows inside that context. Retain 20–12,000 Hz. The averaging reduces phase sensitivity; it does not make coherent mixtures exactly power-additive.
- Build all 200 training note/string templates from the median of the same nine crops. Whiten from the templates only and normalize each template column.
- Split retained spectral coordinates by alternating bins within each window. Fit ridge-regularized nonnegative coefficients on one half. Remove all templates of one MIDI pitch, refit every competitor, and evaluate both fits on the other half. Swap halves. Support is the smaller fractional residual reduction. Correlated spectral halves are a predictive check, not independent validation.
- Use one cutoff chosen on 4,096 training mixtures for at least 99% precision, maximizing recall under the existing tie rule. Zero support is never admitted. Persist the model and cutoff before evaluating the 1,024 calibration and 1,024 test mixtures. These bounded counts override the inherited generator defaults; all source keys must appear in their role.
- Training must reach at least 80% pitch recall, 70% complete sets, and 70% complete sets separately for three, four and five distinct pitches, with zero silence outputs. Otherwise stop before held-out scoring. Both held-out roles must independently reach 95% precision, 80% recall, the same complete-set gates and zero silence outputs.
- Only if all representation gates pass, replay ordinary and extended-middle once on the existing measured serial FIFO clock. Require full CURRENT score identity, at least five percentage points of ordinary pitch coverage gain, no per-label presence or longest-hold loss, and no wrong-pitch or extra-gap growth on either recording.

## Execution and interpretation

One GitHub CPU job, 45-minute limit, existing pinned input releases, no new upload. The laptop runs only synthetic tests. The small report and logs are collected once with the server digest; model and detailed predictions stay remote. No automatic cutoff retuning or repeat of a rejected configuration.

The ordinary recording reuses source takes, so continuous gains there remain descriptive. Sustained RMS-normalized mixtures do not establish attacks, decays, string assignment, unison multiplicity, MIDI lifecycle or native real-time performance. This screen cannot establish live readiness or change the installed tracker. Complete source and worker revisions, the run ID, collection state and result belong in `github-spectral-ablation-20261121.json`.

Standing authorization: `m3-standing-job-authorization-20261121.json`. Source edits, scoped publication and the one bounded CPU run are covered. Claude is currently paused; no fresh Claude approval or review is claimed.
