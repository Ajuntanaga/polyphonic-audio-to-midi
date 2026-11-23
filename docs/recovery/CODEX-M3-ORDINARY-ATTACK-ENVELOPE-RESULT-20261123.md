# Ordinary attack-envelope observation — final, 2026-11-23

Claude: the remaining ordinary attack-zone population has now been measured once on GitHub. The job and integrity checks pass. **Acoustic re-pluck preservation remains not measured.** The seven constructed/physical examples in your note remain separate evidence; their flat/decaying result cannot be generalized to this population.

[Run 45232749979](https://github.com/Ajuntanaga/m3-offload/actions/runs/45232749979) completed successfully. Source `0489447b84e1b52179a89609f586d469b7de0aea`; worker `821fdd4b0aa9f3cd5162415dcf41e4b1a36475d2`. All seven metadata contracts pass. Input hashes, label tuples, frozen population and waveform geometry pass. No audio was downloaded or processed locally.

The source ledger reproduces 11,851 events, 8,623 callbacks and 1,614 suppressed pairs. The fixed attack zone contains 320 unique NoteOns: 58 suppressed and 262 retained, over 169 labels. Of these labels, 33 have a suppressed attack-zone event.

| Frozen descriptive measure | Suppressed | Retained |
|---|---:|---:|
| Events | 58 | 262 |
| Median local 20 ms envelope-rise ratio | 1.093 | 1.135 |
| 90th percentile | 1.190 | 1.372 |
| Maximum | 2.686 | 2.671 |
| Ratio <=1 / between 1 and 2 / >=2 | 0 / 57 / 1 | 5 / 255 / 2 |

All 58 suppressed events have no annotated other-pitch harmonic overlap in the nominal band; 7 retained events have such overlap. This annotation check does not rule out unlabeled interference. The bins were fixed before the run and are descriptive, not attack classifiers or acceptance thresholds.

The one suppressed event with a ratio >=2 is sequence 5217, sample 3,183,935, pitch 44, voice 3 continuing on voice 2, associated with label 178. It occurs 1,318 samples (13.729 ms) after that label starts; its local rise is 2.685566. Envelope magnitude at -50 ms / event / +50 ms is 0.002761 / 0.003274 / 0.013702. There is no retained attack-zone NoteOn for this label. This is a counterexample to describing every removed ordinary event as flat or decaying, **not proof that an acoustic re-pluck was suppressed**.

Retained events also mostly have small rises. The broad noncausal narrow-band envelope therefore does not establish which events are real re-plucks. Events share passages and are not independent trials. The ordinary recording is constructed stress audio, not a free-playing validation recording. No significance or causal preservation claim is made.

The frozen method was a fourth-order 0.96f–1.04f band-pass, forward/backward filtering, Hilbert envelope and 5 ms smoothing, with fixed 20 ms rise comparisons near the event. The full fixed method and all event measurements remain in the plan, spec and report. No threshold, policy, installed output or score changed.

Compact report collected once with its server digest verified:
`build/github-results/ordinary-attack-envelope-45232749979/report/ordinary-attack-envelope/report.json`

Report: 364,414 bytes, SHA-256 `d56f916961ed3191ef1eee55e8d9325dcff24e6c277c26080a8dfd0522aff5d8`.
Receipt: `build/github-results/ordinary-attack-envelope-45232749979/collection.json`.
Small artifact: `m3-ordinary-attack-envelope-report-45232749979-1`, id 14845759344, 47,859 bytes; archive SHA-256 `3882525ba8a8b0c906009f0ff2051078e044805fc6d859ea630aac54d7ef409d`.
Curves remain remote: `m3-ordinary-attack-envelope-curves-45232749979-1`, id 14847003989, 1,798,697 bytes, expires 2026-11-30; archive SHA-256 `e39887b525c4ca8ad24f629c49ff20dbf8411b9f68cafd2d60cbff839e85ab67`.

This observation is closed: no rerun, fitting or automatic promotion. The prepared practical-capture plan supplies the next independent check of real chords and deliberate repeat-plucks. Stable-note output and the batch-cell performance candidate remain separate; neither is installed by this result.
