# Copied-excerpt attack count remains ambiguous

The bounded observation is complete. It does **not** establish that each
physical-unison excerpt contains exactly one acoustic attack. Both late cues
coincide with small changes across more than the nominal fundamental, but the
saved plots cannot distinguish a quiet additional excitation from the evolution
of overlapping strings. The predeclared reading is **AMBIGUOUS; stop this
observation**. No new threshold, detector setting or follow-up feature survey.

Run **45188221519** completed successfully. Source
`18a5806029bd84e9489b1b0c33d19eba55e88c19`, worker
`65cd3018b14bd71f385438a1e090e36794522038`. All five integrity checks and six
observation-contract tests passed. All audio, filtering and FFT work ran on
GitHub; only the small report and two figures were collected locally.

## Fixed measurements

Numbers are the largest adjacent-20-ms power rise in each saved cue's frozen
neighborhood, in dB. Each band has its own maximizing time: these columns do
not describe simultaneous band maxima or count pick contacts.

| Excerpt and cue | Broadband | Nominal fundamental | 0–500 Hz | 500–2,000 Hz | 2–8 kHz | 8–20 kHz |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Note 56 first | 30.39 | 13.61 | 29.70 | 42.44 | 30.85 | 8.02 |
| Note 56 late | 1.50 | 0.78 | 1.78 | 1.97 | 4.00 | 1.68 |
| Note 60 first | 36.89 | 15.70 | 35.69 | 51.52 | 40.51 | 24.20 |
| Note 60 late | 0.99 | 0.37 | 0.99 | 0.77 | 4.46 | 7.68 |

The first attacks produce large steps and a clear harmonic pattern. Around
320–330 ms in note 56 and 260–265 ms in note 60, the figures show smaller
envelope steps and changes in the harmonic pattern. The middle-band envelope
also oscillates later. This is visual description, not a physical-source
identification. In particular, note 60's 7.68 dB high-band rise ends at only
−95.11 dBFS; note 56's corresponding band ends at −102.49 dBFS. A large ratio
near the noise floor is not proof of another pick. Conversely, a much smaller
rise than the first attack does not rule out a quiet additional string pluck.

These are centered, noncausal observations. Their times are not implementable
MIDI deadlines. Neither source has independently annotated pick contacts.

## Consequence for the project

The positive-spectral screen remains **0/6 against its fixed copy-marker
expectation**. Its ten extra cues are extra relative to those markers; this
observation does not justify calling all ten false acoustic attacks. The
complex, sparsity and adjacent-onset screens remain closed with their recorded
verdicts. No result is promoted or retrospectively retuned.

Claude's GHA check of seven removed NoteOns remains a separate useful result:
the nominal band was flat or decaying at those events, with the observed strong
rise earlier. It does not label every excitation in these excerpts and does
not cover the ordinary recording's 58 suppressed attack-zone NoteOns. That
independent ordinary-recording lane is already coordinated in
`CODEX-M3-PEER-ACOUSTIC-NEXT-20261123.md`; this result requests no duplicate job.

Before another articulation policy trial, the deciding evidence must distinguish
a new physical attack from continued pitch activity. These two excerpts cannot
provide that ground truth. The existing repeated-copy observation still records
a delayed response; it is not an acoustic re-pluck acceptance test.
`acoustic_repluck_preservation` remains **not measured**. Installed output,
defaults, scores, label budgets and prior batch-cell performance passes are
unchanged.

## Retained evidence

- Checkpoint: `github-fixture-attack-anatomy-20261123.json`.
- Receipt: `build/github-results/fixture-attack-anatomy-45188221519/collection.json`.
- Report: `build/github-results/fixture-attack-anatomy-45188221519/report/fixture-attack-anatomy/report.json`, SHA-256 `31f3ec5cecd954f8963a5a20e75c17ce955ae1808847cf34e8b9f6cf78f789ce`.
- Figures in the same directory: `physical-highmid.png`, SHA-256 `aee3827f29340d9c0a5bdec3d7f696a080daaa73e0e622c76bd5110ec44abd1a`; `physical-high.png`, SHA-256 `8a7c2afa189e5f77ad4421066ee2fd2720f35f28bf251472363e16dfb4807fb2`.
- Report artifact `14823639512`, 370,814 bytes, server/local archive SHA-256 `3de4256c3737a90ccfc30bc5e84892efee5a3fd03ec2ba8dbab4ffd2a8b3b777`.
- Curves artifact `14824657133`, 54,302 bytes, remains remote; SHA-256 `abe99fa004d0847eb58098dda40782a38c68a23a12e27bafae9f916d3f939106`.

Collected once; do not repoll, rerun or redownload this completed job.
