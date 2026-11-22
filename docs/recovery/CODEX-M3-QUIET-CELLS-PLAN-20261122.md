# Raw resonator observation through rapid-mute decisions

Codex, 2026-11-22 22:56 UTC. Claude's published availability tally establishes
that the saved v5 trace has no measured per-pitch energy/onset inside quiet-code-5
decisions. This is the missing observation; another threshold or release policy
is not justified. The rejected reset and mask remain rejected.

## Ownership and frozen scope

Codex claims `native/offline/replay.{hpp,cpp}`, `replay_main.cpp`, its offline
trace test, `tools/portable_quiet_cell_observation.py`, its Python contract test,
the new spec, and worker `quiet-cell-observation.yml`. One CPU GitHub observation
will replay ordinary and extended-middle CURRENT at block 512 with the existing
settings/input pins and `--diagnostic-spectral-lane-collision` only. No detector
policy/source change, trial reset, model, installed/default change or gate change.
Native execution remains on GitHub Actions. No local audio or native build.

Claude keeps the distinct saved boundary-evidence census and scientific analysis;
this note is the format handoff, not an acknowledgement gate. No duplicate replay
or census is needed. Both peers retain the user's standing authority.

## Trace contract

New opt-in flag `--outcome-cell-trace FILE` requires the existing v5
`--outcome-trace FILE --outcome-trace-annotations`. The v5 bytes and candidate
tuple are unchanged. For **every serialized v5 candidate**, including quiet and
out-of-range requested candidates, write one sidecar row in the same order.
Read only the existing const `demodulated_harmonic_tracks_for_diagnostics` getter;
do not force admission scoring, selection, onset, or lifecycle updates.

Marker: `# m3_outcome_cells_v1`. TSV column order:

`sample tick quiet note available input_power decay h1_hz h1_real h1_imag
h2_hz h2_real h2_imag h3_hz h3_real h3_imag h4_hz h4_real h4_imag
h5_hz h5_real h5_imag h6_hz h6_real h6_imag`

The 18 harmonic values are the raw baseband fast cells, without carrier rotation,
phase correction, normalization or score weights. Doubles use `%.17g`.
`available=0` means no configured cells; it is not measured silence. Disabled
harmonics have zero frequency and zero complex value. `input_power` and `decay`
come from the same const getter. State/output ownership remains in the v5 table.
These are resonator observations, not the missing preselection/onset scores.

## Required checks and stop conditions

On each recording, run untraced, v5, and v5+cells companions. All six complete
snapshots/raw-MIDI outputs must equal the saved CURRENT reference. Both v5 files
must equal each other **and** the historical v5 SHA. No policy result is scored.
Stream-check exact sidecar row coverage/order against v5 `(sample,tick,quiet,note)`;
check finite values, valid booleans, nonnegative frequency/power and valid decay.
Report row/available counts by quiet code, including code 5, with unavailable
rows kept. Stop and report any identity/coverage failure; no automatic rerun.
Native unit coverage will verify trace identity and measured raw cells during
quiet decisions on a small generated fixture. Python contract tests use only
generated text and mocked execution locally. This is an instrumentation identity
check, not a timing/allocation or live-host acceptance result.

## Evidence and interpretation

The small report/log artifact is collected once; gzip sidecars, v5, snapshots and
raw MIDI stay remote until a named analysis needs them. Estimated sidecar output
is about 1.3 million rows on ordinary (hundreds of MB raw, compressed remotely).
Report exact sizes and hashes before any evidence collection. Source/worker SHAs,
run ID and artifact IDs go in the new checkpoint. No recordings enter source git.

The observation can show raw pitch energy/phase through a mute interval and
whether a fresh attack is measurable before the existing quiet path resumes.
It cannot attribute changed state to the rejected reset or prove a restart rule
generalizes to free playing. Claude can pre-register its interpretation before
the sidecar arrives. The current 25 ms AND 5% per-label budget remains frozen.

## Implementation ready — 2026-11-22 23:01 UTC

The sidecar is implemented in the offline writer only; the existing const
getter and detector source are unchanged. Candidate tuples remain 46 fields.
Seven generated-text/mocked-command Python tests pass. They cover exact quiet
row correspondence, unavailable cells, malformed/nonfinite values, preserved
input/reference pins, six companion commands and fail-closed identity errors.
The native fixture and corpus identity checks have not run locally; the worker
will build and run both native test targets before any recorded replay. One
scoped source/workflow review and whitespace check passed. No scientific result
is implied by these contract tests.

Worker: `quiet-cell-observation.yml` in `Ajuntanaga/m3-offload`. Output root:
`build/github-results/quiet-cell-observation`; compact report:
`report/report.json`. For each dataset the sidecar member is
`<dataset>-current-on-512-cells-raw-cells.tsv.gz` in the remote evidence artifact.
Source/worker commits and the one run ID follow in the checkpoint. Claude's
boundary census remains separate; no duplicate analysis is requested.

## Dispatched once

GitHub run **45080860628** is in progress (native build at first observation).
Source `4f9d921f049c69b81b7e8599e36f7a88bf58c651`; worker
`d07c4043c87cc2ded99d3c628f4a1ac01780171f`. Checkpoint:
`docs/recovery/github-quiet-cell-observation-20261122.json`. Report artifact:
`m3-quiet-cell-observation-report-45080860628-1`; evidence artifact:
`m3-quiet-cell-observation-evidence-45080860628-1`. Local collection destination:
`build/github-results/quiet-cell-observation-45080860628`. Identity results are
pending. Claude: the full column order and exact member stems are above; your
separate boundary analysis can proceed without waiting for this observation.

## Source CI harness repair

The source CI native test/build/package job passed; its authored-source gate
failed. Local reproduction found one omitted allowlist entry for
`native/neural/ort_contract_test.cpp`, the standalone experimental adapter test
already added in d879bf8. The repair permits ONNX only at that exact path and
extends the existing boundary test; production paths and other dependencies
remain rejected. Both source validators and that focused test pass locally.
This does not change the pinned observation source or dispatch another replay.
Claude: this is validator maintenance only; your analysis lane is unaffected.
