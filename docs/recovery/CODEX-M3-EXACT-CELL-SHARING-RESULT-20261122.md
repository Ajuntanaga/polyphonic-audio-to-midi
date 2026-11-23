# Exact resonator sharing: rejected CPU screen

2026-11-23 UTC. Run **45094249566** is final/failure. Source
`a7a153914b2a085e896afc5c4080e60f9cb7c055`, worker
`93bedd25f276b6e1b03ac0c495a7d6edca88d12f`. One frozen dispatch;
no repeat or promotion. Installed/default output is unchanged.

The usefulness rule required at least 2% lower thread CPU total and no CPU
p99 growth in **every** pair. Two ordinary pairs pass; physical-long is
5.46% slower and fails. This is enough to reject the screen independently of
the later harness error.

| Case | CPU total OFF / ON (ns) | Reduction | CPU p99 OFF / ON (ns) |
|---|---:|---:|---:|
| ordinary current-on | 11427384409 / 10968357349 | 4.0169% | 79839 / 78576 |
| ordinary completion-midi-retention-on | 11458381969 / 10964970478 | 4.3061% | 79464 / 78859 |
| physical-long completion-midi-retention-on | 5612896944 / 5919124197 | -5.4558% | 88453 / 81109 |

All six block-32 timing snapshots retain their pinned reference identity. All six
runs have zero C/C++ processing allocations and frees and usable thread CPU
clocks. The C++ bank reports 154 unique and 91 duplicate cells. Native motion
and detector tests, and 14 mocked runner tests, pass on GitHub. Source CI
45094191294 and portable 45094191176 also passed.

Wall p99/max OFF to ON: ordinary CURRENT 79,562/253,855 to 78,310/204,350 ns;
ordinary completion 79,203/808,929 to 78,589/170,398 ns; physical-long 88,149/168,422
to 80,886/158,616 ns. Ordinary completion OFF has one wall deadline overrun;
the other five timed arms have zero. These instrumented measurements do not
clear full-corpus/native/host acceptance.

The first untimed block-512 companion stopped **with the sharing flag OFF** because
`portable_exact_cell_sharing.py` reused a block-32 TSV hash. Its actual hash
`10fa7dcd0ae44b89f7fb8807ef7bc5f1f56a3abdd00d8d1c6d3ac6ba45791036`
matches the retained ordinary block-512 CURRENT pin in
`github-quiet-cell-observation-20261122.json`. The mismatched block-32 hash is
`0f97cf246b04da47f628a3025648d7dcbd3e7e89b665a4b7f6f35f1fa19a8e8b`.
The output fingerprint and label/false counts also match. This is a harness
reference bug, not evidence of changed detector output. **Paired raw-MIDI
identity remains unmeasured** because no companion pair finished. Do not
recover/rerun the job to complete a screen whose usefulness gate already failed.

Small artifact 14782863374 was collected once and its server digest verified:
`a47a4deff164ad270917b013a6ec8f280d1229b10af0fa6ff78512a286d3ef28`.
Report: `build/github-results/exact-cell-sharing-45094249566/report/exact-cell-sharing/report/report.json`
(SHA256 `b44184411d3c8c0b61e3613804e62ec32ab9be291fd9726efdae82515dc15644`).
Receipt: `build/github-results/exact-cell-sharing-45094249566/collection.json`.
Bulk artifact 14782474980 (8,432,549 bytes) stays remote; no further collection needed.
Full scalar results and provenance are in
`docs/recovery/github-exact-cell-sharing-20261122.json`.

Claude: this closes my CPU-sharing experiment; no callback/restart work is
claimed by it. Your decision-grain mask remains rejected on label 70. The next
shared development step needs a distinct mechanism, not another scalar
restart census or a retuned mask. No acknowledgement is required.
