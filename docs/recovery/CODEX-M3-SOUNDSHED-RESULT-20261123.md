# Soundshed causal comparison result

2026-11-23. **REJECTED_CAUSAL_PITCH_SCREEN**. The single GitHub job completed successfully; none of the four fixed arms passes the cross-corpus screen. Installed output, defaults and the labeled-frame scoreboard are unchanged.

Run **45218379585**, source `1a00073578ba8296ff0415cc99ce77fd1f5918ef`, worker `638f5bb6292f1c293205a17e19828a99ebe9656d`. Source CI **45218053120** passed. The worker passed all **71 unchanged upstream checks** and **58 comparison checks**; both saved CURRENT measurements reproduce exactly. Native/audio execution was on GitHub only.

## What the fixed comparison measured

These percentages measure pitch presence in annotated audio over sample time, not correct string assignment, labeled-frame match percentage, overall accuracy or live readiness. Extra wrong-pitch output and output in unlabeled gaps are separate. Deltas below are pitch/voice-samples at 96 kHz; simultaneous voices may overlap. Negative extra-output deltas mean fewer extras.

Primary is range-preserving: CURRENT outside MIDI 35..88, Soundshed inside. All annotations remain in the denominators. The other arms are report-only saved-span combinations, not combined native implementations. Settings, detector-emitted clock, 5 pp ordinary-gain target, 25 ms AND 5% per-label loss budget, and no wrong-pitch/gap-growth gates were frozen before dispatch.

| Corpus / arm | CURRENT → candidate pitch presence | Wrong-pitch delta | Gap-voice delta | Budget failures | Newly missed |
|---|---:|---:|---:|---:|---:|
| ordinary / range_preserving | 39.9932% → 43.6338% | -6,934,678 | -1,811,238 | 161/499 | 59 |
| ordinary / soundshed | 39.9932% → 41.7255% | -7,544,681 | -2,064,910 | 174/499 | 72 |
| ordinary / union | 39.9932% → 56.8962% | +126,401 | +584,179 | 0/499 | 0 |
| ordinary / pitch_split_60 | 39.9932% → 52.7071% | -263,629 | +276,870 | 3/499 | 1 |
| extended-middle / range_preserving | 97.4879% → 99.2935% | -528,259 | -169,917 | 0/6 | 0 |
| extended-middle / soundshed | 97.4879% → 99.2935% | -528,259 | -169,917 | 0/6 | 0 |
| extended-middle / union | 97.4879% → 99.2935% | +0 | +0 | 0/6 | 0 |
| extended-middle / pitch_split_60 | 97.4879% → 97.4879% | -341,249 | -19,199 | 0/6 | 0 |

Ordinary primary gains **1,231,227 present pitch-samples**, but 175 labels lose present time and 172 lose longest hold; 161 exceed the budget and 59 become entirely missed. Its **3.6406 pp** aggregate gain also falls short of the 5 pp target. Exact pitch-set time improves 0.5973% → 6.7549%; that does not cancel the label losses.

Extended-middle primary is successful on its six labels: present time improves by 37,440 samples, exact pitch-set time 73.1452% → 99.2935%, with no lost label or false-output increase. This does not establish cross-corpus acceptance.

The union preserves every ordinary label and increases pitch presence to 56.8962%, but adds 126,401 wrong-pitch and 584,179 gap voice-samples. The fixed MIDI-60 split reaches 52.7071% while reducing wrong-pitch output, but adds 276,870 gap voice-samples and fails three labels (42, 172, 227); label 42 becomes entirely missed. These descriptive arms supply no passing alternative.

## Timing and MIDI

Ordinary detector-only p99 is **404,301 ns**, maximum **749,620 ns**; extended-middle p99 **391,145 ns**, maximum **558,931 ns**. Both exceed the separate M3 targets of 166,666 / 333,333 ns. Neither overruns its full 512-sample callback deadline. Allocation use was not measured; these are native runner measurements, not VST3 host or hardware timing.

Raw MIDI pairing is valid: ordinary 562 transitions / 281 NoteOns; extended-middle 24 / 12. No note remains open at recording EOF. String assignment, unison multiplicity and acoustic re-pluck preservation are not measured by this comparison.

## Evidence and decision

Small report artifact `m3-soundshed-report-45218379585-1`, id **14838044078**, **184,320 bytes**, collected once. Server digest and archive SHA-256 agree: `28d5b2205cb919985a827a20b17f3bea0e098efb261e291112b12a365927cf00`.

Local report: `build/github-results/soundshed-comparison-45218379585/report/soundshed-result/report/report.json`; SHA-256 `0d1962b8ad8653e5d8949bf8c5b726ec07e0a530874bc58a3c7d002687e7bfde`. Receipt is `collection.json` in that run directory. Compact metrics and source pins are in `github-soundshed-comparison-20261123.json`.

Bulk artifact `m3-soundshed-evidence-45218379585-1`, id **14838928396**, **926,779 bytes**, remains remote (expires 2026-12-07). No repeat collection or processing is needed.

Close this fixed setting: no retuning, rerun, expansion or runtime integration. Claude: the exact report is available for your independent use; no duplicate comparison is needed. Your ordinary-58 acoustic lane remains separate. The seven checked suppressed attacks are documented as lane flicker, while broad acoustic re-pluck preservation remains unmeasured. Neither result changes installed behavior or establishes reliable live use.
