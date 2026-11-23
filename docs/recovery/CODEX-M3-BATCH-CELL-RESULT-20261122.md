# Batched independent resonators passed the bounded CPU screen

Run `45109184192` is final/success, source
`5c2d999acf6cc2bc9966b6fec6ba27f74cf06b2f`, worker
`6b3e63b84291c1d5b5f190b5f6c842052178fcff`. The default-off array layout and
two-cell SSE2 arithmetic preserve each resonator's original operation order.

| Fixed pair | CPU total saved | CPU p99 before / after (ns) | Wall maximum before / after (ns) |
|---|---:|---:|---:|
| ordinary, current-on | 16.679% | 78709 / 73662 | 137442 / 221711 |
| ordinary, completion retention | 16.601% | 78594 / 72913 | 175128 / 142214 |
| physical-long, completion retention | 18.387% | 78453 / 72242 | 154677 / 148828 |

All three pairs pass the fixed >=2% total CPU saving and no CPU p99 growth
rule. All twelve snapshots retain saved identity, the three paired raw MIDI
streams are bit-identical, all six timed runs have zero C/C++ processing
allocations/frees and zero overruns. Both native test targets, 20 runner
contracts, source CI `45109131301` and portable check `45109131320` passed.

Thread-CPU brackets carry measurement overhead. This is a useful bounded
screen, not full-corpus, production-host or live readiness acceptance.
Installed output and scores are unchanged. The next step is the frozen full
corpus validation in `CODEX-M3-BATCH-CELL-CORPUS-PLAN-20261122.md`.

Small report artifact `14789106870`, 40312 bytes, collected once; archive
SHA-256 `2577cd10adf46fd143db84184ec07f0495c14ad015d9ad020382afada5f02f69`
matches the server digest. Report SHA-256
`1e95b28dd72646ea2cbbbe3a429a5db5fd0995a16f7338915640ecde01a90212`.
Local report:
`build/github-results/batch-cell-update-45109184192/report/batch-cell-update/report/report.json`.
Bulk artifact `14789415826` stays remote. Do not repoll, redownload or repeat
this completed screen.
