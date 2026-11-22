# Raw cells through mute decisions: observation passed, restart interpretation pending

Codex, 2026-11-22 23:12 UTC. One GitHub CPU run **45080860628** completed
successfully. All six complete snapshot/raw-MIDI companions match saved CURRENT;
both v5 companions per recording match the historical trace. Sidecar coverage and
ordering pass on both recordings. This closes the missing-observation problem,
not the restart-design problem. No policy or installed output changed.

## Result

| Recording | Decision ticks | Cell rows | Code-5 ticks | Code-5 rows | Available / nonzero code-5 rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| ordinary | 167025 | 1310294 | 10949 | 24729 | 24720 / 24720 |
| extended-middle | 35025 | 95436 | 888 | 1289 | 1289 / 1289 |

The nine ordinary unavailable rows remain explicitly unavailable. They must not
be interpreted as measured silence. Raw resonator cells being nonzero does not
establish a fresh attack: stored filter state can persist after the input ends.
The new sidecar contains neither previously omitted admission scores nor a
forced lifecycle/onset update. It reads the existing const fast baseband cells.

Native motion/detector test targets pass 2/2; generated contract tests pass 7/7.
These are observation identity/coverage checks. No new timing, allocation,
held-note quality or live-host acceptance is established by this run.

## Claude handoff and coordination

Claude, your boundary/restart census remains your lane; I will not duplicate it.
The new cells make the run interior observable while preserving the output you
analyzed. The next material question is whether a causal change in those cells
separates the 23 restart-positive labels from shortened false-tail spans, early
enough to respect the frozen label budget. Nonzero energy alone cannot answer it.
Both recordings are already-seen design data; any selected rule still needs an
independent corpus check. Your published boundary result can stand separately.

There is no acknowledgement gate and no need for another recorded replay.
The user's standing CPU-job authority applies equally: a remote reduction of
these saved sidecars can return a compact per-window table without bringing the
389 MB artifact onto the laptop. If collecting selected members is sufficient,
their exact byte counts and hashes are below. Keep the original hashes and all
unavailable rows. The existing v5 traces are unchanged and already retained.

Marker: `# m3_outcome_cells_v1`. Column order is unchanged from the plan:

```text
sample tick quiet note available input_power decay h1_hz h1_real h1_imag h2_hz h2_real h2_imag h3_hz h3_real h3_imag h4_hz h4_real h4_imag h5_hz h5_real h5_imag h6_hz h6_real h6_imag
```

Fields are tab-separated, 25 columns, double values written with `%.17g`.
Harmonics are raw fast complex baseband values, without carrier rotation,
phase correction, normalization or score weighting. Disabled harmonics have
zero frequency/value. The v5 candidate tuple stays at 46 fields. One sidecar row
exists per serialized v5 candidate in the same order, including quiet/requested
out-of-range rows. State ownership and annotation context remain in v5.

## Provenance and collection

- Repository/workflow: `Ajuntanaga/m3-offload`, `quiet-cell-observation.yml`.
- Source: `4f9d921f049c69b81b7e8599e36f7a88bf58c651`.
- Worker: `d07c4043c87cc2ded99d3c628f4a1ac01780171f`.
- Checkpoint: `docs/recovery/github-quiet-cell-observation-20261122.json`.
- Collected report: `build/github-results/quiet-cell-observation-45080860628/report/quiet-cell-observation/report/report.json`.
- Report SHA256: `49f328bdc1821cf9cdd6a587661cc1e1f21a536a8a9957623ec2ab5c80609e44`.
- Collection receipt: `build/github-results/quiet-cell-observation-45080860628/collection.json`.
- Small report artifact **14777422047**, `m3-quiet-cell-observation-report-45080860628-1`, **8777 bytes**; collected once, server/archive digest verified: `98f2cb3cd7b28ba29817ac2eedbb416f3715785703d81e796e3d7bd82985a09e`.
- Remote evidence artifact **14777925317**, `m3-quiet-cell-observation-evidence-45080860628-1`, **388717092 bytes**, expiry **2026-11-29T23:08:33Z**, server SHA256 `11d52807b731af3bfbb98a2a4f8696e61e82921e8e13a6b8837e1c6fe74a9728`. Not downloaded locally.

Exact sidecar names recorded by the report (archive prefix has not been inspected):

| Sidecar | Gzip bytes | Gzip SHA256 |
| --- | ---: | --- |
| `ordinary-current-on-512-cells-raw-cells.tsv.gz` | 132487577 | `7389b95e5364e99a35914b2dd6523581ce43984466648bd2604051b586be4872` |
| `extended-middle-current-on-512-cells-raw-cells.tsv.gz` | 9769279 | `769148c773ab754b69ed5e2c41485efdbce9d4953a45b77d49420e5f9262e260` |

Raw SHA256: ordinary `d74f110c5adaa94c2e903c46cb6f0f7be4c17899d5ee22afe567d83271f324a3`
(469969482 bytes); extended-middle `1b6903765acc26428f952b1e5c460f4808dfdca8ec50dba8d4923b49b96b48c7`
(36036364 bytes). Complete companion identities and all artifact member hashes
are in the checkpoint/report; no duplicate snapshot/v5 download is needed.

## Source CI and remaining work

Initial source CI45080818103 failed the authored-source gate; its native
tests/build/package job passed. The exact-path allowlist repair **c73889c** now
passes CI **45081339946** and portable **45081339953**. It fixes the existing
standalone ONNX adapter-test allowlist only, and does not change this run's source.
Both checks are final; do not poll or rerun them.

The rejected native rapid reset remains rejected: five newly completely missed
labels, increased wrong-string output and retriggers. The bare mask and latch
also remain rejected. No duration threshold, budget, installed default or prior
verdict is adjusted here. Reliable live guitar MIDI is still unverified.
