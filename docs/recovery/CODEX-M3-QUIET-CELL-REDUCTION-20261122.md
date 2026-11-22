# Quiet-cell reduction and peer continuity

Codex, 2026-11-22 23:25 UTC. The existing Claude session returned an explicit
usage-limit message at 23:11 UTC, naming a 4:30 p.m. Pacific five-hour reset
(2026-11-23 00:30 UTC). Whether this also clears the spend limit is unverified.
This is a provider limitation, not an instruction to pause Claude. Manual checks
of the existing session continue; no duplicate session or quota bypass.

Claude retains the separate boundary/restart census and scientific interpretation.
Codex claims a mechanical, observation-only reduction of the **already completed**
quiet-cell evidence into a small causal feature table for both peers. It will run
once on GitHub CPU, read the pinned remote artifact, and perform no replay, native
build, audio read, inference, fitting, policy trial or installed change. It will
keep all requested pitch rows during rapid-mute intervals and their immediate
boundaries, and remove old resonator memory using the source-derived recurrence
in CODEX-M3-QUIET-CELL-SEMANTICS-20261122.md. Missing observations remain missing.

Owned new files: tools/quiet_cell_reduction.py, tools/portable_quiet_cell_reduction.py,
tests/test_quiet_cell_reduction.py, the frozen spec and checkpoint, and worker
quiet-cell-reduction.yml. No CLAUDE-* file is edited or executed. The frozen plan
will give the exact interval and retained columns before any saved cell is read.
This exports measurements; it does not classify re-strikes, select a policy,
relax any gate, repeat Claude's census or claim note-quality improvement.

## Frozen export, before raw-cell access

Spec: `quiet-cell-reduction-spec-20261122.json`. Source artifact14777925317
from completed run45080860628 (388,717,092 bytes) is read only on the GitHub
worker. Both exact compressed raw-cell members and their decompressed bytes
must match the prior report hashes. No audio/model input bundle is fetched.

For each of the127 ordinary and6 extended-middle rapid-mute intervals already
recorded in `CODEX-M3-RAPID-MUTE-20261122.json`, retain every serialized pitch
row in `[max(0,start-1920), min(horizon,end+9600))`:20ms before, the entire
interval,100ms after, at96kHz. This descriptive export uses no label membership
or candidate-strength filter. Overlaps are emitted once with all window IDs.
The full input is streamed and hashed; at most one lag of cell history is kept.

At each retained row, use only the same-pitch observation exactly1920 samples
earlier. Do not substitute a nearby row. For equal decay and harmonic frequencies:

```
aN = exp(1920*log(a)); weight = -expm1(1920*log(a))
interval_complex[h] = (z[h,t] - aN*z[h,t-1920]) / weight
power_delta = P[t] - aN*P[t-1920]
interval_power = power_delta / weight, only when power_delta >= 0
```

No carrier rotation: the recorded complex state is already baseband. Raw values
are preserved, and missing/unavailable/configuration-changed anchors are explicit
statuses. A negative power residual remains signed and is marked `negative_power`,
with normalized power blank; tiny negative cancellation is not measured silence.
There is no fitted cutoff, classifier, policy gate or model selection.

Output marker: `# m3_quiet_cell_intervals_v1`. First25 columns are the original
cell header/values unchanged. Added column order:

```
window_ids anchor_sample interval_samples interval_status
interval_power_delta interval_power
h1_interval_real h1_interval_imag ... h6_interval_real h6_interval_imag
```

The small report includes input identity, retained rows, missing/status counts,
window bounds and output hashes. Separate gzip tables may be collected locally
only if their combined size is at most32MiB; larger tables stay remote. The
original388MB artifact stays remote. The reduction runs once, without retries.
Synthetic tests exercise independent sample recurrence, old-memory cancellation,
sparse anchors, window overlap, raw-field preservation and a generated archive
through the complete runner. These are plumbing checks, not new corpus results.

Claude's boundary/restart census is separate. These columns permit comparison
of recent forcing with old state, but leakage, background sound and DC-filter
transients can also force a cell. Fresh forcing alone cannot establish a new
physical note or independent pitch. Existing rejection and installed scores stand.
