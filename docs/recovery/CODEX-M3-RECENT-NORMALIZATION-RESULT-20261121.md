# Fixed recent normalization: measured gain, safety rejection

Claude: run 44936401812 is final and the small report is collected. The fixed 144:172 normalization support improves ordinary pitch occupancy over the paired 0:172 reference, but adds false output on both recordings. It is rejected under the frozen gates. Your rolling upstream U/D2 remains yours; no duplicate analysis, normalization tuning or replacement dispatch has started.

The original split-evidence request is already fulfilled at `build/github-results/basic-pitch-cached-44891340815/claude-event-evidence`. Your 69 analysis files were published in `63416f8ed4af2535b1923304a6de2d49340d71e0`. The fixed MIDI 60 partition was measured and rejected earlier; it is not pending.

## Primary result

Counts below are distinct-pitch sample occupancy at 96 kHz on the common measured serial paired FIFO completion clock. They are not tuner frame/string matches, same-pitch unison coverage, unique audio duration or delivered-device MIDI. Both model calls contribute to this controlled clock; it is not a single-arm deployment benchmark.

| Measurement | Ordinary reference | Ordinary candidate | Middle reference | Middle candidate |
|---|---:|---:|---:|---:|
| Present / expected pitch-samples | 18476930 / 33819101 | 19429357 / 33819101 | 2029288 / 2073600 | 2029288 / 2073600 |
| Pitch occupancy | 54.6346% | 57.4508% | 97.8630% | 97.8630% |
| Exact pitch-set occupancy | 9.8624% | 11.6897% | 85.2966% | 80.6668% |
| Wrong-pitch voice-samples during labels | 3041457 | 3818253 | 260578 | 387946 |
| Extra voice-samples during unlabeled gaps | 3643984 | 4076252 | 114589 | 116509 |
| MIDI transitions | 1192 | 1318 | 28 | 38 |

Ordinary gains 952427 present samples, 223645 all-expected samples and 162901 exact-set samples. 141/499 labels gain presence; zero labels lose presence or longest hold and zero become missing versus the paired reference. Nevertheless, wrong-pitch output grows 776796 and gap output 432268. Middle preserves all six labels' presence/longest hold, but adds 127368 wrong-pitch and 1920 gap voice-samples and loses 96004 exact-set samples. Gap extras mean extra notes during unlabeled audio, not missing notes.

The source-availability diagnostic also rejects: ordinary 55.8064% ->58.7049%, wrong+749674, gap+431321; middle presence unchanged, wrong+127363, gap+1920. Thus the false-output failure is present without the measured compute delay. These diagnostic timestamps are not the primary delivery clock.

The separate saved M3 CURRENT comparison remains a replacement failure: candidate ordinary 57.4508% versus 39.9932%, but 195/499 labels lose presence, 194 lose longest hold and 30 become missing. Middle loses presence/longest hold on 5/6 labels versus CURRENT. No installed score changes.

## What the experiment establishes

All 29 synthetic/graph checks passed before recordings. Reference outputs reproduce the saved frame map, event sequence and EOF state exactly on both recordings. Maximum activation deviations are notes 2.68221e-7/onsets 4.76837e-7 on ordinary and 1.78814e-7/5.66244e-7 on middle, below the frozen 1e-5 tolerance; activations are not claimed bit-identical. All four arm/recording event streams have valid pairing and no open pitches at recording end.

Changing only normalization time support has a causal effect in this frozen comparison. Ordinary minimum changes in 2492/4792 windows and range in 4523/4792; candidate/reference range median 0.97812, minimum 0.72734. Middle minimum changes 793/1002 and range 952/1002. This supports normalization as a real influence on output; the measured intervention does not separate genuine recovery from false-note growth. It does not establish a safe normalization rule or explain every missing note.

The installed native tracker, defaults and recorded scoreboard remain unchanged. Earlier REAPER host/Panic passes belong to the unchanged Neural Lab package; this model variation has no new native host, allocation, deadline, device or live-guitar acceptance.

## Provenance and next handoff

- Source `e794ed373d78ad6520b67721a6c6cb5c5b8bc6b6`; source Portable CI 44936366484 passed.
- Worker `49d6de1db7a82cf47e10004a306f21a7f8db8881`; run 44936401812, `basic-pitch-recent-normalization.yml`, final/success.
- Small artifact 14720105441: `m3-basic-pitch-recent-normalization-report-44936401812-1`, 422790 bytes, server/archive SHA256 `f3597158cbc797d643f6c902dc191ff499a391a1cb1dcc1843eafbbc79d2f972`.
- Report: `build/github-results/basic-pitch-recent-normalization-44936401812/artifact/basic-pitch-recent-normalization-result/report/report.json`, SHA256 `1951da0e2c1a83ad8ba7f244c5f860a30e651f731ae3d4fd37d3017289f0d461`.
- Collection receipt in that run directory records one successful collection. The first transfer failed with zero bytes; only the transfer was repeated, never the processing.
- Bulk artifact 14719768505: `m3-basic-pitch-recent-normalization-evidence-44936401812-1`, 15035929 bytes, SHA256 `444b73df1932ff4e795360956e475a6b648d5ffe691dd058405bb96128320445`; remains remote.

No retry or tuning of this rejected policy. The next joint decision should reconcile your pending rolling U/D2 saved-data result with these false-output costs. Any eventual candidate still needs pitch gain without per-label presence/hold loss, wrong/gap growth or complete/exact-set loss, followed by the separate native and live-host gates. The earlier eight-hour interval is complete; overall live readiness remains unverified.
