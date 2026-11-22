# Epoch recovery for the unchanged spectral-patch experiment

2026-11-22. Claude and Codex are peers; this is coordination for my current
workstream, not an approval gate for Claude's independent work. The user has
renewed uninterrupted work for eight hours, from 10:25 to 18:25 UTC today.
Claude can carry an independent promising result through implementation and an
authorized GitHub job, checking the shared checkpoint to avoid duplicate work.

Run 45006866083 exhausted its 45-minute worker budget at epoch 63/80. It saved
no training weights or optimizer state. Those epochs cannot be resumed. This
separate execution-recovery job starts the identical experiment again, saving
model weights, Adam state, shuffle RNG, global Torch RNG, normalization and
progress after every completed epoch. A partial epoch is repeated on resume.

The scientific specification remains byte-identical:
`harmonic-spectral-patches-20261122.json`, SHA256
`dde4de4739f7c72945ef6c07c8b838e30914671b33de2fba9dc0f161936e6479`.
Inputs, source roles, mixtures, features, optimizer, seed, all 80 epochs,
training-only cutoff and every training, singleton, held-out and continuous
gate stay fixed. Training loss is not a tracking score. Installed output and
recorded frame scores are unchanged.

The separately frozen execution envelope is
`harmonic-training-recovery-20261122.json`: 120-minute GitHub CPU worker budget,
105-minute processing timeout, one compute thread and no automatic redispatch.
The processing timeout reserves time to upload the last completed checkpoint.
Checkpoint replacement is atomic. Restoration rejects mismatched source,
specification, dependencies, training bytes, normalization, configuration or
optimizer progress. The workflow starts fresh because the original job has no
checkpoint. The CLI supports a separately recorded future resume from this
source revision; no resume dispatch or artifact is being implied here.

Before recorded processing, the same GitHub job must pass synthetic tests of
uninterrupted versus checkpointed versus interrupted/resumed training: exact
predictions, loss history, model/optimizer tensors and RNG state. It also checks
a completed checkpoint, invalid identity/progress and an interrupted write.
The laptop runs only non-model guard/orchestration tests.

Files owned by this workstream: `tools/harmonic_training_checkpoint.py`,
`tools/portable_harmonic_context_learning.py`,
`tools/portable_harmonic_training_recovery.py`,
`tests/test_harmonic_training_checkpoint.py`, the execution envelope and
`harmonic-training-recovery.yml` in the worker checkout. Source/worker revisions,
run ID and artifact locations will be recorded in
`github-harmonic-training-recovery-20261122.json` before further processing.

Artifacts: small report/logs/progress; a separate epoch-checkpoint artifact;
bulk model/predictions retained remotely. Only the small report is scheduled
for collection. No polling or redownload of the completed timeout run.
