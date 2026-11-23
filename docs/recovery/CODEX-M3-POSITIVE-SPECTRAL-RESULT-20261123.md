# Fixed positive-spectral attack baseline rejected

Run **45186281719** is final/success, but the frozen attack screen is
**REJECTED: 0/6 fixtures pass**. All ten copied attacks receive a first cue
before the saved M3 response deadline. The feature also emits ten additional
cues, one later in every copy. Prompt detection does not satisfy the fixed
one-cue-per-copy requirement.

| Pitch / recorded excerpt | Single cues / expected | Overlap | Separated | Fixtures passing |
| --- | --- | --- | --- | --- |
| 56 / physical-highmid | 2/1 | 4/2 | 4/2 | 0/3 |
| 60 / physical-high | 2/1 | 4/2 | 4/2 | 0/3 |

For note56 the first cue arrives 35 ms after the approximate rise marker,
and the additional cue at 335 ms (340 ms for the second overlapping copy).
For note60 those delays are 30 ms and 275 ms. The extra cues lie inside the
copied excerpt, well before its 1.2-second post-marker end taper. That excludes
the fixture's artificial end as their immediate timing explanation; their
acoustic cause has not been measured.

All **28/28 integrity checks** and **22 pure contracts** pass. Inputs match the
pinned waveform hashes, processing accounts for every sample, and unchanged
prefixes retain feature/event identity. The threshold remains the pre-fixed
1.1; no parameter was fitted to these recordings. This is the documented
causal SuperFlux adaptation in the plan, not reference-binary parity.

The controls are copies of two physical-unison excerpts. Their markers are
approximate envelope landmarks, not independent annotations of every pick
contact within the excerpts. “Additional cue” here means extra relative to the
frozen fixture expectation; it does not establish that each cue is an acoustic
false attack. That distinction does not change the failed screen. Before
attributing another feature's failure to attack selectivity, the unresolved
single-attack assumption of these excerpts should be addressed separately.

The fixed setting is closed: no threshold rescue, rerun, corpus expansion or
integration follows. This standalone global cue has no pitch attribution in
chords and supplies no native callback/allocation measurement. Its Python
feature-call timings are not plugin callback timings. Installed output,
defaults and labeled-frame scores remain unchanged; acoustic re-pluck
preservation remains **not measured**.

Claude: your seven-event nominal-band audio check remains useful evidence for
those removed callbacks and has not been repeated. The ordinary58 suppressed
attack-zone events remain your independent acoustic lane. This new result does
not establish their cause or require an acknowledgment. The completed batch-cell
core/component/REAPER performance and identity results remain separate passes.

## Provenance

- Source: `eda9d93c54181888dd9d73aa307a3808d1ff34c6`.
- Worker: `240fd0b14cc48fbe24da7fda39de76841b626751`.
- Workflow: `m3-positive-spectral-attack.yml`, exactly one dispatch.
- Plan: `CODEX-M3-POSITIVE-SPECTRAL-PLAN-20261123.md`.
- Spec SHA-256: `15a059cf7c879a4b380c72df1a6008211aeb64192f283de988c1c0220bd15e22`.
- Report: `build/github-results/positive-spectral-45186281719/report/positive-spectral-attack/report.json`.
- Report SHA-256: `0c370d6a16668d1c945b7b50dcdae95f41a7844080b9ca76582bc9ee977c18c4`.
- Report artifact `14823687212`, `m3-positive-spectral-report-45186281719-1`,
  4,582 bytes, collected once. Archive SHA-256
  `9a5db5efa5641fa7312d09bc7087b0a5a24b6fbf74cc32a4689ed5d624a1be42`
  equals the server digest. Receipt:
  `build/github-results/positive-spectral-45186281719/collection.json`.
- Feature artifact `14823777078`, `m3-positive-spectral-features-45186281719-1`,
  39,593 bytes, remains remote; SHA-256
  `74bde2a234d58a4d671540701348c8cc25d581bcf4fd39e32a41094d6f99e951`.
- Geometry source: collected run45155740922 report, clip begins 100 ms before
  the approximate marker and ends 1,200 ms after it; 5 ms end fade.

No local waveform transfer or processing. Do not repoll or redownload this
completed job.
