# Batched-cell VST3 passes the paired REAPER check

2026-11-23. Final, **PASSED** for the frozen host comparison. The separately
named batch-cell lab plugin delivered exactly the scalar plugin's MIDI in real
REAPER with the ordinary recording. No installed plugin or tracking score changed.

Run **45171884366**, source `8631bacf2ca9c8ef1fc6d11d1f93634d9bcccd86`,
worker `434be315603bf9a8c9ffb4815927e7ccdf1e3454`.
[GitHub run](https://github.com/Ajuntanaga/m3-offload/actions/runs/45171884366).
The HTTPS mirror/timeouts repair completed setup; the source, configuration,
input pins, package list and acceptance gates stayed frozen. Earlier setup run
45164257964 remains a terminal infrastructure failure, with no plugin measurement.

## Measured result

Both arms ran REAPER 7.86 on JACK dummy audio at 96 kHz / 512 samples using
production defaults and factory calibration, without offline policy macros.
All **22/22** arm checks and the exact paired MIDI comparison passed.

| Measurement | Scalar | Batch lab |
|---|---:|---:|
| Recorded samples consumed | 10,689,600 / 10,689,600 | 10,689,600 / 10,689,600 |
| Recording wall seconds (111.35 s source) | 111.368124 | 111.357133 |
| Recording MIDI events | 1,040 | 1,040 |
| Recording NoteOns | 520 | 520 |
| Changed dry-audio samples | 0 | 0 |
| Duplicate NoteOns / unmatched NoteOffs / final open | 0 / 0 / 0 | 0 / 0 / 0 |
| Settings restore / Panic cleanup | pass / pass | pass / pass |

All 1,040 ordered recording events match in phase, source sample, block offset,
status, pitch and velocity, with **zero time shift and zero sample tolerance**.
Capture overflow, recording discontinuities and nonfinite values are zero.
Panic was exercised with one active note, released it, returned Ready and left
zero owners with no Panic NoteOns. Tail/Panic wall-clock events are separate
controls; the complete event-file hashes differ and are not claimed identical.
The 520 NoteOns are from this production-default host setup, not the earlier
calibrated offline configuration or a fresh labeled-frame gain.

All three native test executables passed, including the scalar and batch
production-shaped allocation/deadline suites; seven report-logic tests and both
SDK package validators also passed. In those native realtime suites, scalar
wall p99/max were **105,102 / 181,324 ns**, batch **99,895 / 136,492 ns**;
both had zero deadline exceedances against 333,333 ns. These are native-suite
measurements, not timings collected from the REAPER audio thread. The existing
14-dataset core/component timing results remain separate evidence.

## Collection and limits

Small report artifact **14816963465**, `m3-batch-cell-host-report-45171884366-1`,
was collected exactly once (55,950 bytes). SHA-256
`fb9141f137d53b6adb7e3c355c8f6d2669a2fdc96f7d26c86e1087d227cb82bb`
equals the server digest. Report SHA-256:
`e057ce7416b257a028122155464856a03322c9acae254dfa18fd92775aeb498e`.
Receipt: `build/github-results/batch-cell-lab-host-45171884366/collection.json`.
Report: `build/github-results/batch-cell-lab-host-45171884366/report/batch-host-result/report/report.json`.
Bulk artifact **14816993329** (2,603,755 bytes), including the two uninstalled
bundles and event tables, remains remote. Do not repoll, rerun or redownload.

This completes the planned production-shaped host comparison for the CPU
optimization. It establishes delivery through REAPER on dummy audio. Physical
interface/device delivery, live guitar, broad acoustic re-pluck preservation
and improved chord tracking remain open. No promotion follows automatically.
The earlier roughly 17–18% CPU savings are from the bounded core comparison;
this host check confirms behavior preservation rather than a host speedup.

Claude: the compact result is now available above; no duplicate collection is
needed. Your seven-event envelope finding supports assignment flicker in those
windows. The independent ordinary 58 attack-zone check remains useful, as does
the controlled repeated-attack counterexample; neither is superseded by host
parity. Our shared next work is selective articulation/tracking improvement,
with installed output and the label budget preserved.
