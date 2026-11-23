# Trace-free timing recovery for the fixed continuation guard

Run 45179941790 is final/failure and its small report is collected once with a
verified server digest. The detector and motion native suites passed. The
screen stopped at the first fixture's timing companion: the command kept
`--diagnostic-stable-note-identity` but intentionally omitted all trace I/O,
while the replay CLI required a MIDI trace for that flag. This is a harness
failure; there is no completed scientific verdict.

The fix passes the existing diagnostic explicitly to `run_detector_replay`
without requiring a trace. It remains diagnostic-only, default false, and
requires independent output ownership and per-voice routing. Timing continues
to reject trace I/O. Its JSON records whether stable identity was enabled;
the screen requires that field to be true. This does not alter the detector
rule, any fixture or gate, the installed plugin, or production defaults.

Fourteen pure Python contracts pass locally, including a command contract
that requires the same diagnostic, ownership and batched-cell flags at block
32 with no trace I/O. Native compilation, detector/motion tests, six-fixture
identity checks and strict timing run on GitHub Actions only.

One technical recovery uses the unchanged `m3-stable-onset-freshness.yml` and
spec SHA-256 `55ab8bc9b6ad2eb3bd7fb37f0ddfb1b07622e66b20099d659d5bf6f9e2b42eaf`.
The source SHA and new run ID will be pinned in
`github-stable-onset-timing-recovery-20261123.json` before monitoring.
A scientific pass permits the planned full-corpus comparison only; a
scientific failure closes this exact rule without tuning. Claude's separate
ordinary acoustic work is unaffected. Acoustic re-pluck preservation remains
not measured.

Recovery dispatched once: [45181144376](https://github.com/Ajuntanaga/m3-offload/actions/runs/45181144376), source
`d0d5cc5efda659f55b1b60a794a6bc2a0d2873ae`, worker
`8fa28bab7cf2c4063791cc5fb09a55db57b43bff`. Compact report target:
`build/github-results/stable-onset-timing-recovery-45181144376/report/stable-onset-freshness/report.json`.
Final: run **45181144376** completed and the small report was collected once.
The scientific screen is **REJECTED_FIXED_SCREEN** (95/97): all four repeated
responses recovered, but both single-copy stable outputs gain retriggers.
See `CODEX-M3-STABLE-ONSET-FRESHNESS-RESULT-20261123.md`. Exact rule closed;
no full-corpus follow-up or retuning. Timing plumbing passed its checks.
