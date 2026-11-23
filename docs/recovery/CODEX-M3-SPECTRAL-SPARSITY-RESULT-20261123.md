# Spectral-sparsity attack test: transfer rejected

Run **45184195705** completed successfully, but the frozen attack screen is
**REJECTED_TRANSFER**. Calibrating the threshold on note56 gives five timely
cues for five inserted copies. Applying that threshold unchanged to note60
still detects all five copies on time, but emits **ten cues: five unwanted
extra triggers**. Every transfer fixture fails the no-extra-cue requirement.

| Role / pitch | Single | Overlap | Separated | Fixtures passing |
| --- | --- | --- | --- | --- |
| Calibration / 56 | 1/1 cues | 2/2 | 2/2 | 3/3 |
| Fixed transfer / 60 | 2/1 cues | 4/2 | 4/2 | 0/3 |

First cues arrive 36.0–38.1 ms after the approximate rise marker in calibration
and 28.3–31.8 ms in transfer, all before their saved M3 response deadlines.
The extra transfer cues arrive about 277–280 ms after the rise marker, during
the same inserted copy. Prompt detection therefore does not establish useful
attack selectivity.

Only delta was fitted, to **0.08404658566816414**: 10 of 87 exact threshold
regimes passed all calibration fixtures. Transfer data did not select it.
All 18 integrity checks and 29 pure contracts pass. The six waveform hashes
and unchanged-prefix feature identities are preserved. These are constructed
copies of two recorded pitches, not independent physical re-plucks. This test
provides no new labeled-frame score, native timing or allocation measurement.
Python feature timings are not plugin callback timings.

The fixed representation/setting is closed. No threshold rescue, rerun or
full-corpus expansion follows. No detector, installed plugin, default or
scoreboard changed. Acoustic re-pluck preservation remains **not measured**.
Claude's ordinary suppressed-attack acoustic work remains a separate,
independently authorized lane; this result does not require an acknowledgment.

## Provenance

- Source: `abd20609b16df718da9650d7fe638c8b8d9c6e85`.
- Worker: `0a2a0973638aebe3aa7eac15ad8bfe843888ede9`.
- Workflow: `m3-spectral-sparsity-attack.yml`, exactly one dispatch.
- Plan: `CODEX-M3-SPECTRAL-SPARSITY-PLAN-20261123.md`.
- Report: `build/github-results/spectral-sparsity-45184195705/report/spectral-sparsity-attack/report.json`.
- Report SHA-256: `a834a5861e434cd60b6526dc5f03f16a4e353faaa44524d65b21a1bca848e9ed`.
- Report artifact `14823295687`, 4,938 bytes, collected once; archive SHA-256
  `812e89ed8ff81c2e201117cd6dd6c8a3c0689908d454c8ee87c7f3da3bf189ea`
  equals the server digest. Receipt: `build/github-results/spectral-sparsity-45184195705/collection.json`.
- Feature artifact `14823480502`, 65,019 bytes, remains remote. No local audio.

The earlier batch-cell core/component/REAPER identity and performance passes
remain valid and separate from this rejected articulation feature.
