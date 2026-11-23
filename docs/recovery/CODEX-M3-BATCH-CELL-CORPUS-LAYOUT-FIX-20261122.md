# Full-corpus job: input-layout failure and correction

Run `45112016975` is final/failed before any replay. The native build, both
native test targets and all 28 runner contracts passed. The runner then looked
for `m3-inputs/calibration.m3cb`, but the verified release extracts the corpus
into `m3-inputs/corpus`, as the successful `batch-cell-update.yml` already uses.
Its report has an empty execution order and no dataset results. This is a
workflow setup failure, not a measured rejection of the CPU optimization.

The 5,509-byte small artifact was collected once. Its archive SHA-256 matches
the server digest (`f97dbadf963b66557118d3a819e17d3db9f6bc308d90ae9eebce600914375d7a`).
Receipt: `build/github-results/batch-cell-corpus-45112016975/collection.json`.
There is no bulk replay evidence. Do not repoll or redownload that job.

Worker `f91add2c6638ec55ba9032f24083ff1ed1223b2c` fixes the corpus argument
and checks all declared input paths before the build. A mock shell invocation
of the actual workflow replay step accepts the nested 30-file layout and
rejects the former parent path; YAML and all six shell blocks parse. No local
native execution or recording access was used for this check.

The corrected job retains source `d9c217184bc26873e1deee931b6df10173de223c`,
native implementation `5c2d999acf6cc2bc9966b6fec6ba27f74cf06b2f`, the same
126 fixed replays, all references, settings, limits and reading rules. One
new dispatch replaces the failed setup; it is not a retry of a replay or a
tuned scientific screen. Follow
`github-batch-cell-corpus-layout-fix-20261122.json` for its run and collection.
The bounded 16.6–18.4% CPU saving remains a bounded result; full-corpus,
host/device timing and acoustic re-pluck acceptance remain separate.

Corrected run `45112657375` was dispatched once at 04:34 UTC on 2026-11-23.
GitHub passed input verification, the 28 runner contracts, native build and
both native test targets. The fixed 126 replay check began at 04:36:02 UTC.
No corpus verdict is available yet. Its small-report destination is
`build/github-results/batch-cell-corpus-45112657375`; bulk remains remote.
