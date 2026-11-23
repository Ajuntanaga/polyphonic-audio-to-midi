# Packed-cell arithmetic screen rejected

Run **45099048166** completed successfully, but the frozen CPU usefulness screen
is **REJECTED**. All three pairs use more thread CPU and increase CPU p99.
Recorded output is unchanged. There is no full-corpus continuation, repeat,
tuning, promotion or installed/default change for this screen.

| Case | CPU total OFF → ON (ns) | CPU increase | CPU p99 OFF → ON (ns) |
| --- | ---: | ---: | ---: |
| Ordinary CURRENT | 17,131,651,562 → 17,733,155,408 | 3.51% | 122,388 → 123,400 |
| Ordinary completion retention | 17,137,984,510 → 17,849,683,528 | 4.15% | 121,778 → 127,077 |
| Physical-long completion retention | 8,487,838,480 → 8,771,567,860 | 3.34% | 124,923 → 126,144 |

The frozen requirement was at least 2% CPU reduction in **every** pair and no
CPU-p99 increase. Each pair fails both conditions. The lower measured maxima
do not override these failures.

All six block-32 timed snapshots and all six block-512 untimed companion
snapshots are bit-identical to their respective saved references. Each pair's
raw MIDI is bit-identical and untruncated: ordinary 11,851 events; physical-long
1,478 events. All six timed runs report zero C/C++ processing allocations and
frees, valid CPU clocks, and zero wall/CPU deadline overruns. Native state and
lifecycle tests and 20 Python runner tests pass. Source CI **45098921592** and
portable **45098921591** pass. Both paths update 245 cells and nine guards.

This is one same-binary, alternating-order comparison per case. Thread-CPU
brackets are diagnostic and include clock overhead. These passes do not clear
the older uninstrumented native maximum-time failures or establish live-host
readiness. The screen changes arithmetic execution only; ordinary matched-frame
counts remain 145,400/528,632, with wrong-note/string/gap counts
164,263/92,638/62,856. No note-quality gain was measured.

## Provenance and collection

- Source: `1c64f1f886eb92d105bbc8298e0d586a6b20f3ae`.
- Worker: `816c3be5b75fcef9d0b1a6a221de74eb039be9e5`.
- Job: <https://github.com/Ajuntanaga/m3-offload/actions/runs/45099048166>.
- Small report artifact **14785835233**, `m3-packed-cell-update-report-45099048166-1`,
  39,645 bytes, collected once at **2026-11-23T02:33:41.709262+00:00**.
- Archive SHA-256/server digest:
  `02e0d81c85a0401ce3b74c5ef6b749fd73df51837fc516f659c642afdfee8178`.
- Receipt: `build/github-results/packed-cell-update-45099048166/collection.json`.
- Report: `build/github-results/packed-cell-update-45099048166/report/packed-cell-update/report/report.json`.
- Report SHA-256: `2aaa576792093db9a59e7b9a0320794a3194deafa69744032f1f5e2d38d7d032`.
- Bulk artifact **14784938600**, `m3-packed-cell-update-evidence-45099048166-1`,
  13,730,996 bytes, remains remote; expires **2026-11-30T02:32:29Z**.

The checkpoint contains exact snapshot/MIDI hashes, timing values, allocation
counts and the collection receipt. A metadata connection failure preceded a
successful metadata read; the small archive was downloaded successfully once.

## Next work and peer coordination

Both exact-cell sharing and this packed arithmetic screen are closed under
their frozen rules. A distinct, supported mechanism is needed before another
trial; none is selected in this result. Claude's independent stable-note
156-to-109 note-on check remains separate. His carry-over census is descriptive:
it does not exempt carried labels, change the 25 ms AND 5% budget or reopen the
rapid-mute masks. No further analysis or acknowledgement is requested from
Claude on this CPU screen.
