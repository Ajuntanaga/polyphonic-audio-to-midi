# Frozen component versus mixture observation

The saved model misses some pitches in solo examples and more in mixtures,
but those comparisons used different crops and effective levels. This one
GitHub CPU observation asks which mixture misses were already present in the
exact component alone. It does not fit or modify a detector.

Reference: run **44966587324**, source
`7481905c4b38bad52770c59c7b9c0fdb3eca75a0`, model SHA256
`bf9a974f1cd6d2e6bb8461044a114e45017661a7276f5b9d759072c8da8b4dec`.
The model remains rejected. Cutoff stays **0.586877167224884**. Exact input,
artifact and dependency pins are in `paired-component-mixture-20261122.json`.

Before any component inference, regenerate all original plans and reproduce
all 16,384 training, 4,096 calibration and 4,096 test mixture probabilities
within absolute **1e-6**, with **zero changed cutoff decisions** and identical
targets. Any failure stops the job. Only then use the same renderer for each
original component alone: same crop, component RMS normalization, component
gain and global mixture gain. The sum of solos must reproduce its mixture
within absolute **1e-14**. Single-component outputs must also reproduce their
original mixture outputs.

Each distinct expected pitch in a mixture contributes once. A unison is found
alone if any of its own same-pitch components supplies that pitch. A different
component's ghost pitch does not count as its own detection. Report four states:
retained, emerged after summation, lost after summation, already missing alone.
Separately count mixture extra pitches present in any solo or new after
summation. Report role, component count, distinct-pitch count, pitch band and
effective component level strata, plus complete sets and complete sets among
examples whose own pitches were all detected alone.

Interpretation is descriptive. Already-missing-alone errors justify examining
single-source transfer; lost-after-sum errors justify examining mixture
interaction. Neither count uniquely attributes a mechanism: normalization,
phase and model context all change on summation. Intended labels do not prove
audibility. Recording pass and content remain confounded, and these roles have
already informed development. No source exclusions, relabeling, cutoff tuning,
new fitting, continuous replay, native execution or installed/default changes.

Execution: one `paired-component-mixture.yml` job in `Ajuntanaga/m3-offload`,
CPU, 45-minute limit, shared processing concurrency lock. Reuse the three
existing input releases and frozen artifact. Collect the small report/log
artifact once; paired probability arrays remain remote. Local validation uses
synthetic arrays only. A synthetic model save/load check executes on GitHub.

This is a diagnosis of sampled sustained pitch sets, not a new labeled-frame,
string-assignment, MIDI-delivery or live-readiness result. Claude is paused;
no new Claude review is claimed.
