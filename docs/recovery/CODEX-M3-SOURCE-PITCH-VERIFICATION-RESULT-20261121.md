# Targeted source verification: sustained disagreement, no relabeling

GitHub CPU run [44951646663](https://github.com/Ajuntanaga/m3-offload/actions/runs/44951646663) completed successfully. All 15 flagged held-out takes favored another pitch in every systematic short window (283/283); all 25 selected agreeing controls favored their label (525/525). The independent long-window spectra support eight non-octave disagreements. Seven octave-related cases need separate interpretation: these waveforms do not establish which note the player intended.

This is a targeted source observation selected after the earlier diagnostic, not a new detector score or an unbiased error-rate estimate. All 555 source rows, original labels, held-out scores and installed outputs remain unchanged. No model fit, exclusion or relabeling occurred.

## Measured source evidence

All pitches below are MIDI numbers. “Periodic” is the fixed short-window estimator. “Peak” is the strongest spectral peak, not necessarily the fundamental. Label-band percentages are median fractions of measured spectral power in the first eight harmonics of the nominal label; odd-band shares help expose even-harmonic ambiguity. They are descriptive measurements, not probabilities or acceptance thresholds.

| Source take | Label | Periodic | Peak | Short windows | Label harmonic power | Odd label harmonic power |
|---|---:|---:|---:|---:|---:|---:|
| string-01:50 | 60 | 84 | 84 | 3 | 99.016% | 0.027% |
| string-01:51 | 72 | 84 | 84 | 4 | 98.555% | 0.003% |
| string-01:53 | 84 | 72 | 72 | 18 | 0.071% | 0.069% |
| string-01:54 | 72 | 60 | 60 | 26 | 20.440% | 20.035% |
| string-01:56 | 60 | 64 | 76 | 26 | 0.009% | 0.008% |
| string-01:57 | 64 | 68 | 68 | 26 | 0.585% | 0.582% |
| string-01:58 | 68 | 72 | 72 | 26 | 0.064% | 0.064% |
| string-01:60 | 76 | 80 | 80 | 12 | 0.014% | 0.013% |
| string-01:61 | 80 | 84 | 84 | 4 | 0.033% | 0.029% |
| string-04:54 | 60 | 72 | 72 | 8 | 98.957% | 0.001% |
| string-04:55 | 48 | 60 | 60 | 26 | 99.954% | 0.034% |
| string-04:57 | 52 | 48 | 48 | 26 | 0.002% | 0.001% |
| string-06:68 | 40 | 52 | 52 | 26 | 99.990% | 0.000% |
| string-08:63 | 52 | 32 | 32 | 26 | 0.004% | 0.004% |
| string-08:66 | 36 | 32 | 32 | 26 | 0.033% | 0.031% |

Eight non-octave cases have at most 0.585% median power in the nominal label's harmonic bands. Five string-01 excerpts (56, 57, 58, 60, 61) favor the note four semitones higher, which equals the next annotation. The three remaining non-octave cases favor the string's open pitch (string-04:57, string-08:63, string-08:66). This supports a source/annotation disagreement; a shifted performance or excerpt boundary remains a hypothesis because the intervals between excerpts were not measured. In string-01:56 the periodic estimate is 64 while the strongest peak is 76, demonstrating why the peak alone cannot determine pitch.

Five upward-octave cases contain at most 0.035% median power in odd harmonics of the label. A lower note with only even harmonics and an upper octave can be observationally indistinguishable. The two downward-octave cases (string-01:53 and :54) show a lower periodic component and strong support for the lower-note harmonic pattern, but do not justify an automatic replacement label either. The string-06 controls both have a strongest peak at 52 while periodicity agrees with their label 40; a strong second harmonic alone is insufficient evidence of a wrong label.

The 25 controls cover 525 short windows and 380 distinct long-window contexts; the flagged group covers 283 short windows and 203 distinct contexts. No selected short window was silent or unresolved. The agreeing calibration control for string-08:63 is unavailable and remains explicitly missing. Every selected take and its full trajectory is retained in the small report. These windows overlap; neither their count nor repeated spectral contexts constitute independent examples or unique audio duration. The systematic scan covers each available excerpt, not the complete original performance.

## What changes for development

The selected test data include sustained source-content disagreement, so forcing a learner to reproduce these intended labels can reward the wrong acoustic evidence. That is a concrete evaluation limitation, not permission to remove difficult examples. The earlier spectral dictionary also recovered no complete three-to-five-note sets even on training mixtures; source disagreement does not explain that failure or establish a working tracker.

Next design: preserve the original benchmark and add explicit source-consistency metadata keyed by take, with these observations and unresolved octave cases visible. Before any alternate training or evaluation manifest, determine whether the eight non-octave discrepancies arise from excerpt alignment or the performed notes using source provenance and, only if necessary, a separately specified bounded observation. Acceptance requires an explicit provenance-backed mapping; no nearest-pitch relabeling or silent exclusion. A future model still has to recover complete three-to-five-note mixtures, transfer to untouched takes and satisfy continuous per-label/false-output gates. No further run, refit or policy change is queued by this result.

## Verification and provenance

- Source: `f06303acaad412b8c35902d1954193ea3c62b5e3`; worker: `161098abbaa98c67689ee7f3a85fd88981fabc75`.
- Eight synthetic checks, workflow parsing and the focused review passed. Source Portable offline replay CI [44951599483](https://github.com/Ajuntanaga/polyphonic-audio-to-midi/actions/runs/44951599483) passed native tests, replay comparison contracts and synthetic buffer parity. This does not measure live guitar/device delivery.
- All 555 expected-cents rows and the frozen 40-take selection reproduced. Existing authorized input archives were verified. Measurement took 10.08 CPU seconds on GitHub; no local recorded-audio processing.
- Small artifact `m3-source-pitch-verification-report-44951646663-1`, id `14724839590`, 50,837 bytes, collected once. Server/archive SHA-256: `463e2849c36b30f3554d435e024b3e92fd6ee7064e789b7aeb42e90d04b986c3`.
- Report: `build/github-results/source-pitch-verification-44951646663/artifact/source-pitch-verification-result/report/report.json`. Report SHA-256: `2bc94036c01e6b71723c4601a0987af5d2b22e574e207a6a5b0da4f28a0c1e52`.
- Compact all-take summary: `docs/recovery/source-pitch-verification-summary-20261121.json`; checkpoint: `docs/recovery/github-source-pitch-verification-20261121.json`.
- Per-window spectral evidence remains remote in `m3-source-pitch-verification-evidence-44951646663-1`, id `14726165320`, 686,083-byte archive, expiring 2026-12-05. Server digest `dc852bd063fe642f2bad404aa34aba0ab472e9837b929cbc78caa3c600f6ff06`. No download or repeat processing is needed for this conclusion.

Claude's existing analyses remain credited and published; his paused session supplies no new review of this result. Reliable live use and overall completion remain unmeasured.
