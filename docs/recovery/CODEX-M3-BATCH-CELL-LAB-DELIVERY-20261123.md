# Deliver the tested batch-cell lab build

2026-11-23. Codex is collecting the existing, uninstalled lab VST3 from final
run 45171884366. This is delivery of the build already tested, not a new build,
replay, policy, promotion or installation. Claude's ordinary-58 acoustic work
remains independent; no duplicate job is started.

Collect artifact 14816993329 once (2,603,755 bytes), verify its recorded server
SHA-256 `4f7f258acb5b2c340509b9a4943a1b2a1e3fadb4e804ced77c5c0449e481d6a0`,
and extract only the separately named batch lab bundle. The tested batch binary
must equal `b55357fd1d737b7d7db2ecd18a9848ffe832076c614fd1d4e064567ad471bc7f`.
Stage it beneath `build/deliverables/m3-batch-cell-lab-20261123/` with a receipt
and a plain-language readme. No local audio or native execution is needed.

The demonstrated benefit is preserved output with reduced core processing cost;
the roughly 17-18% reduction belongs to the bounded core comparison. REAPER
verified identical recording MIDI, dry audio, state restore and Panic on dummy
audio. Physical-device/live-guitar performance and improved note quality remain
unverified. The installed plugin and its defaults stay unchanged.

## Delivered

At 16:58 UTC the bundle was staged successfully. The one 2,603,755-byte
collection matches the recorded server digest. The 1,313,437-byte package is:

`build/deliverables/m3-batch-cell-lab-20261123/M3_Batch_Cell_Lab.vst3.tar.gz`

Package SHA-256:
`ee812f162babdeebe6ec7a754ae820c115933983cb65a01d7dcef818e9cbc49a`.
The extracted binary is 3,590,864 bytes and equals the tested binary hash above.
The lab class ID `12F2F7A911C34C54A8448E6771CB862D` differs from the scalar
class ID. The SDK's moduleinfo uses trailing commas; it was parsed in memory
for this metadata comparison and preserved byte-for-byte in the bundle.

The directory includes the extracted VST3, `README.md` and `manifest.json`.
Only the lab tar member was extracted from the evidence archive. No recording,
scalar plugin installation, native execution, build or new job was involved.
Receipt: `build/github-results/batch-cell-lab-host-45171884366/bulk-collection.json`.
Checkpoint: `docs/recovery/m3-batch-cell-lab-delivery-20261123.json`.

Claude: this is delivery of our already-passing performance build. Your seven
audio checks stay recorded; ordinary58 remains a distinct unresolved acoustic
check. This collection does not settle acoustic re-pluck preservation or change
any tracking policy, default, gate or installed output.
