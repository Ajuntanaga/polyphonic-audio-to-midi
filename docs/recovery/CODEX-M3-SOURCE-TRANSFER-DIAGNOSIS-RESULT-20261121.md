# Saved source-transfer diagnosis: solo and mixed errors both remain

Completed diagnosis of saved predictions from rejected GitHub run `44966587324`. This analysis changes no detector, model, cutoff, source label, installed output or acceptance decision. Source `7481905c4b38bad52770c59c7b9c0fdb3eca75a0`; worker `99e7422982c1394977977bf73ccb8dfb7e40367d`.

The test role has errors even without simultaneous notes. Mixtures also fail when every component was exact in its sampled solo examples. That supports addressing single-source transfer/false-pitch rejection as well as chords; it does not uniquely identify a model, annotation or interference mechanism.

## Measured populations

Exact means every intended pitch found with no extra pitch. These are sustained sampled pitch sets, not tuner labeled-frame/string matches or live MIDI. A singleton contains one source component; multiple components at the same pitch remain in the mixed population.

| Role | Solo exact | Intended solo pitches found | Solo extra pitches | Mixed exact |
|---|---:|---:|---:|---:|
| train | 3033/3052 (99.38%) | 3048/3052 (99.87%) | 17 | 10689/12512 (85.43%) |
| calibration | 685/740 (92.57%) | 729/740 (98.51%) | 55 | 2076/3151 (65.88%) |
| test | 570/809 (70.46%) | 687/809 (84.92%) | 315 | 981/3082 (31.83%) |

Test solo losses are 122 intended pitches and 315 extras. Of 155 test sources, 86 are exact in every observed solo, 38 sometimes exact, and 31 never exact. All test sources have solo observations. Six calibration sources have none and remain explicitly unknown; they are not counted as clean.

Of the 122 test solo misses, 85 occur on the 15 sources already marked octave-ambiguous or unresolved non-octave disagreement. The other 140 sources were not examined by that targeted verification: their solo examples contain 37 misses and 228 extras. These descriptive strata exclude nothing and establish neither incorrect labels nor a correct detector; the earlier verification used different selected windows. All 555 sources remain in every original score.

Among 478 test mixtures whose sources were always exact in sampled solos, 367 are exact (76.78%): 111 fail, with 94 missing pitches and 38 extras. Mixtures containing a source with a solo error are exact in 614/2604 cases (23.58%), with 2242 missing pitches and 2303 extras. Each mixture appears once in these groups. Per-source exposure counts in `sources.json` are non-additive and cannot assign an extra pitch to a particular source.

There are **zero identical source/crop/effective scheduled gain solo controls** for the 41,361 train, 10,521 calibration and 8,619 test uniquely attributable mixed targets. Clean-solo/mixed differences therefore cannot isolate masking or other mixture interference. Scheduled gain is not measured audibility. Shared-pitch targets stay in a separate unison bucket; Boolean pitch presence does not establish string multiplicity.

## Evidence and validation

The plan was frozen before prediction inspection: `CODEX-M3-SOURCE-TRANSFER-DIAGNOSIS-PLAN-20261121.md`. Archive `14731592882`, `m3-harmonic-source-variation-evidence-44966587324-1`, is 8,013,695 bytes and matches server SHA-256 `cccd31450089b1ac3e49cc0c390144123e9311ab4ff99540285695fefa6d6db5`. One completed collection resumed a timed-out partial transfer. Only six original prediction/plan files were extracted; the model was not extracted or loaded. Receipt: `build/github-results/harmonic-source-variation-44966587324/prediction-evidence-collection-receipt.json`.

`tools/saved_source_transfer.py` reproduced overall, per-note, per-pitch-count and silence counts, source uses, role/plan/target identities and the frozen cutoff `0.586877167224884`. All 555 sources are retained. Five synthetic tests passed; the saved-array analysis ran once and all integrity checks passed. No audio, model inference, fitting, remote processing or native execution occurred. Claude remains paused; no new Claude review is claimed.

Full outputs:

- `build/recovery/m3-source-transfer-diagnosis-20261121/report.json`
- `build/recovery/m3-source-transfer-diagnosis-20261121/sources.json` (555 rows)

Report SHA-256 `650a1bbef3e0e25679eee6b430186e508a45960a22421a14e4a9a8f578566466`; source table SHA-256 `25a210e2cc084fc0e4d83544030f3c2752afda77570a8d4f9bd4108a9c17f95e`. Input pins and analysis-script hash are in the report; compact counts and consistency strata are retained in `github-harmonic-source-variation-20261121.json`.

## Decision and next step

The source-variation screen remains rejected. Five-pitch exact counts remain train 1779/2529 (70.34%), calibration 269/639 (42.10%) and test 24/327 (7.34%); continuous replay remains skipped. These reused source-disjoint development roles are not a fresh benchmark, and pass, protocol and source content remain confounded.

Design a distinct single-source transfer and false-pitch rejection change that also preserves complete chords, before another fit. Keep all 555 sources, original roles, labels, cutoff protocol and safety gates. The saved clean-solo/mixed contrast is unpaired and does not establish interference. No refit, exclusion, cutoff retune or new job queued.

A later causal interference claim would need identical-crop/effective-level solo controls. Their absence does not require another observation job now. The immediate design must improve transfer and false-pitch rejection while preserving the complete-chord benefit. Keep the original precision, recall, complete-set and silence gates, followed by continuous per-label/false-output and native/live gates. Reliable live use and overall project completion remain unmeasured.
