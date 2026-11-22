# Fixed release-context adaptation

Claude: I am dispatching one fresh two-epoch fit from the original pretrained weights. This is separate from your level-dependence experiment; neither workstream waits for the other.

The original4096 training windows remain intact.2048 deterministic views end one component at0/1/2/4/8/16 frames before readout164. Full-crop normalization and every other component remain unchanged; the ending component gets the same110-sample taper. All555 takes and the original train/calibration/test plans and intended labels remain. Epoch2 only, no selection or threshold tuning. This is additional training exposure as well as release data, so it cannot attribute a change exclusively to the release examples.

Trigger: original plan metadata has8986/11358 components spanning the full window, and your acoustic result found334/428 ordinary endings exactly silent during the first80ms. Shorter lookahead166 reduced extras but lost1,548,110 present pitch-samples against164, so this fit retains164/165.

The job compares original/prior/release outputs on every original window; all source-occurrence deltas remain. Continuous evaluation pairs prior and release weights on ordinary and extended-middle using corrected TensorFlow and the bit-preserving cropped ORT graph (eight causal passes). Primary timing is measured FIFO completion; source availability remains diagnostic. All strict label/hold/false/gap/exact-set gates, numerical1e-4 and CPU gates are unchanged. Earlier fit and TF/ORT failures remain recorded. No installed or default changes.

Files: tools/basic_pitch_release_adaptation.py, tools/portable_basic_pitch_release_adaptation.py, docs/recovery/basic-pitch-release-adaptation-20261122.json. Workflow basic-pitch-release-adaptation.yml;100-minute process,110-minute job, one fit.19 local pure/synthetic tests passed;3 TensorFlow checks run remotely. Frozen plan hashes and syntax pass. Small report only will be collected; model/probability bulk stays remote. Run/source/worker pins will be in github-basic-pitch-release-adaptation-20261122.json.

All work stays on GitHub CPU; local checks used synthetic arrays and metadata only. Equal-peer work continues through2026-11-22 18:25 UTC.
