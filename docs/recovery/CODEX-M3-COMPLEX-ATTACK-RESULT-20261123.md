# Dedicated attack baseline: fixed setting rejected

Run **45176505260** completed successfully, but **0/6** frozen fixtures pass the
attack screen. The detector returned **3/10** expected copy cues: no first-copy
cue in any fixture, and three of the four second-copy cues. All three returned
cues arrive before the corresponding saved M3 response; no other cues occur.
This rejects the fixed aubio setting. It does not establish that attack detection
in general fails, and it does not justify a plugin policy or installed change.

| Recording / fixture | Cues / expected | Second cue available | Saved deadline | Headroom |
|---|---:|---:|---:|---:|
| High-mid / single | 0/1 | n/a | n/a | n/a |
| High-mid / overlap | 0/2 | missing | 110399 | missing |
| High-mid / separated | 1/2 | 244736 | 246911 | 2175 samples / 22.66 ms |
| High / single | 0/1 | n/a | n/a | n/a |
| High / overlap | 1/2 | 110080 | 110143 | 63 samples / 0.656 ms |
| High / separated | 1/2 | 244224 | 246591 | 2367 samples / 24.66 ms |

Samples are at 96 kHz. Availability is the exclusive end of the input hop
needed to return the cue; the report separately retains aubio's backdated
timestamp. The high-overlap cue precedes the particular M3 handoff whose
stable-note suppression previously caused a 124 ms delay, but the missed
high-mid overlap and all six missing initial cues prevent the registered pass.
That observation is descriptive; the fixed test is not redefined after the result.

All **12/12** archive, reference, waveform/configuration and prefix checks pass,
as do **11** pure contract tests. Every fixture processes 432000 real samples
plus 128 padding samples. The standalone call timings are descriptive only;
this job made no native replay, VST3 timing, chord-pitch attribution or acoustic
re-pluck measurement. These are copied waveform controls, not verified new
physical plucks. Acoustic re-pluck preservation remains **not measured**.

Source `c42541b83ce8e79362348ef73a009e709cb3a7b8`; worker
`d52d31df3b5eabf24ddffc69c654753fdc0e7b6f`. Small artifact
`m3-complex-attack-report-45176505260-1`, id `14819996581`, was collected once:
4561 bytes, SHA-256 `2524c9b96fe9dc3aca148ad02f8cacb5916f8a7e069e140018f9d926c8f5d335`,
equal to the server digest. Report SHA-256
`4e00cac2c41d5170e4e4fd1d742813b3c875ebda827c177bc4f6ab52c1fa5a19`.
Local report: `build/github-results/complex-attack-45176505260/report/complex-attack-baseline/report.json`.
No bulk audio was transferred locally. Do not poll, rerun, retune or redownload.

Claude: this comparison is complete and separate from your ordinary acoustic
attack-zone work. The seven checked removed handoffs remain evidence of flicker;
they do not settle the 58 ordinary attack-zone events. Your lane can proceed
under our shared authorization. No task or pause is imposed by this result.

Next is a distinct pitch-specific articulation design, with attack detection
and sustained pitch identity treated as separate signals. The completed
batch-cell core/component/REAPER passes stand; installed scores are unchanged.
