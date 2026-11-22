# Saved quiet-cell reduction complete; scientific restart test remains separate

Codex to Claude, 2026-11-22 23:36 UTC. Run **45083623255** is final/success.
The compact report is collected and its server digest verified. This is the
mechanical measurement export discussed in the plan, not a detector trial or
restart classifier. Your boundary/restart census remains your distinct lane;
your script was not edited or run. No acknowledgement is needed.

Source `80d3767d9114f93155c7f348c60c55fac987d33a`; worker
`aea24a64713a2a3c1ba95079bff94973b25082e4`; workflow `quiet-cell-reduction.yml`
in `Ajuntanaga/m3-offload`. Twelve synthetic contract tests passed on the worker.
The archived input and both compressed/decompressed member identities passed.
No audio, model, native build, replay, fit or policy was executed by this job.

| Dataset | Fixed windows | Retained pitch rows | Reconstructed | Missing anchor | Current unavailable | Negative power residual |
|---|---:|---:|---:|---:|---:|---:|
| Ordinary | 127 | 246,651 | 181,406 | 55,835 | 9,410 | 0 |
| Extended-middle | 6 | 2,572 | 2,107 | 96 | 0 | 369 |

These are serialized pitch observations, not note matches or unique audio duration.
For quiet code 5 within these windows, ordinary has 24,532 reconstructed,
124 missing-anchor and nine unavailable rows; extended-middle has 1,224
reconstructed and 15 negative-power rows. Missing is not zero. A negative
power residual remains signed with normalized interval power blank; it is not
measured silence. The raw complex values are retained.

## Remote table handoff

Artifact **14777294469**, `m3-quiet-cell-reduction-tables-45083623255-1`:
47,502,091 archive bytes, server SHA-256
`f9ce49a12f0e66e02d2a790b7933c2e641b02af2161c041be2bd905ac6e86a35`.
Expires **2026-12-06T23:31:23Z**. Both members are at the artifact root:

- `ordinary-quiet-cell-intervals.tsv.gz`: 46,839,854 bytes;
  SHA-256 `642cedf3a521d181f848447251f6f7d2730be4c3dacffecdc94cb7371523553b`.
- `extended-middle-quiet-cell-intervals.tsv.gz`: 661,873 bytes;
  SHA-256 `ce3b28d9b96c859e28baa97190a61e1f021f18b3aadbd600569623938bff348c`.

Combined table size is 47,501,727 bytes, above the frozen 32 MiB local cap.
They remain remote for GitHub analysis; the original 388 MB archive also stays
remote. No reduction rerun or local bulk download is needed.

Marker `# m3_quiet_cell_intervals_v1`. Column order (43 columns):

```
sample tick quiet note available input_power decay
h1_hz h1_real h1_imag h2_hz h2_real h2_imag
h3_hz h3_real h3_imag h4_hz h4_real h4_imag
h5_hz h5_real h5_imag h6_hz h6_real h6_imag
window_ids anchor_sample interval_samples interval_status
interval_power_delta interval_power
h1_interval_real h1_interval_imag h2_interval_real h2_interval_imag
h3_interval_real h3_interval_imag h4_interval_real h4_interval_imag
h5_interval_real h5_interval_imag h6_interval_real h6_interval_imag
```

The first 25 fields preserve raw text. Each row is inside a previously frozen
rapid-mute window plus 20 ms before and 100 ms after, bounded by the recording
horizon. All serialized pitches in that region are kept, regardless of labels
or candidate strength; overlapping windows share one row with all window IDs.
The anchor is exactly 1,920 samples earlier at 96 kHz, same pitch, decay and
frequencies; no nearby sample substitution. Interval complex forcing is
`(z[t] - a^1920*z[t-1920]) / (1-a^1920)` in the existing baseband frame.
See the frozen plan and `CODEX-M3-QUIET-CELL-SEMANTICS-20261122.md` for details.

This removes old resonator memory algebraically; recent forcing can still be
leakage, background sound or a DC-filter transient. Neither nonzero raw state
nor nonzero recent forcing alone proves a fresh physical note. Separation of
re-strikes from tails, restart timing, label preservation and held-out utility
remain unmeasured. Existing strict/budget gates and prior rejections stand.

## Collection and continuity

Report artifact **14777234677**, `m3-quiet-cell-reduction-report-45083623255-1`,
6,997 bytes, server SHA-256
`5e7e7853e207190bc5ec0716693f5139ec01354c912bfbddebf70385cfb05fd7`.
The first transfer failed with zero bytes; a bounded recovery fetched this same
report successfully, without a second processing run. Both attempts are saved.
Receipt: `build/github-results/quiet-cell-reduction-45083623255/collection.json`.
Report: `report/quiet-cell-reduction/report/report.json` below that directory,
SHA-256 `528132128243d45194587a2c85fce24ae1492b4c4b8c274eed6515b94eb89c3f`.
Source portable run 45083439150 passed; no source CI result at this SHA is claimed.

Claude's existing session last reported a provider usage/spend limit, with a
five-hour reset listed at 2026-11-23 00:30 UTC. Clearance is unverified. This is
not a user pause; the current peer handoff is ready for that session, and the
next manual activity check is due at the reported reset. No duplicate
session or quota bypass. Installed/default output and recorded scores are unchanged.
