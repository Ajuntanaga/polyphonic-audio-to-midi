# Soundshed causal comparison — preparation

2026-11-23, Codex workstream. Claude's ordinary-58 acoustic analysis remains
independent. The single job is final; see `CODEX-M3-SOUNDSHED-RESULT-20261123.md`.

I am preparing one isolated GitHub CPU comparison of the public Soundshed
polyphonic detector against saved M3 CURRENT on ordinary and extended-middle.
The public model and implementation exist at upstream revision
`ca0329840d4bbf3b3b782333afe8dc89fc32fbb6`. Upstream reported results are a reason
to compare, not our measurements. This work does not integrate upstream code
into M3 or change installed output. Upstream is AGPL-3.0; preserve its notices
and keep any comparison harness separate from the production plugin.

Temporary ownership: this note; a new standalone replay adapter, portable
comparison runner, tests/spec/checkpoint under Soundshed-specific names; and
one new worker workflow. Existing scorers and previous verdicts remain intact.
Before dispatch, freeze input/source pins, causal event clock, upstream default
settings, note-range handling, unchanged label/false-output gates, and report
artifacts. No threshold sweep or second configuration.

Audio, native compilation and detector execution stay on GitHub Actions. The
local intake contains source text and API metadata only, under
`build/recovery/soundshed-intake-20261123`. No recording/model inference or
installed build runs locally. No duplicate public-dataset experiment is queued.

Sources:
- https://github.com/webprofusion/soundshed-guitar
- https://github.com/webprofusion/soundshed-guitar/blob/ca0329840d4bbf3b3b782333afe8dc89fc32fbb6/docs/fx-library.md#polyphonic
- https://github.com/webprofusion/soundshed-guitar/blob/ca0329840d4bbf3b3b782333afe8dc89fc32fbb6/LICENSE

## Frozen comparison before dispatch

The specification is `soundshed-comparison-20261123.json`. Primary is the range-preserving arm: CURRENT outside MIDI 35..88, Soundshed inside. All annotations stay in the denominators. Lowest 35 is the detector/reference-test default, while the GUI host defaults to 38; this run explicitly chooses the full trained range. Threshold -50 dB, trained Settings, follow-pitch off, block512 and -9 dB input trim are fixed. Native emitted sample offsets receive no correction.

The full unchanged upstream test executable must pass before the two corpus replays. The adapter retains events before scoring and reports callback timing separately. The fixed label budget remains 25 ms AND 5% for present and longest hold, with no new missed label or wrong-pitch/gap growth on either recording. Ordinary needs at least 5 pp of pitch-coverage gain. Standalone, literal union and the existing pitch-60 split are descriptive arms only. No tuning, second configuration or installed change.

The source and embedded weights total 855,860 bytes across 18 pinned files. The CPU worker fetches them directly; no model or audio execution on the laptop. Native tests and replay still unexecuted until GitHub.

## Dispatch receipt

Run **45218379585** was dispatched once at 2026-11-23T16:36:19Z.
Source `1a00073578ba8296ff0415cc99ce77fd1f5918ef`; worker
`638f5bb6292f1c293205a17e19828a99ebe9656d`. Source CI **45218053120**
passed. The 58 pure local checks pass; native tests and corpus results await
the worker. Small report: `m3-soundshed-report-45218379585-1`; bulk stays
remote under `m3-soundshed-evidence-45218379585-1`.
Local collection target: `build/github-results/soundshed-comparison-45218379585`.

## Final result

Run **45218379585** completed successfully. The causal pitch screen is **REJECTED**. All 71 unchanged upstream and 58 comparison checks pass; both CURRENT measurements reproduce. Primary ordinary pitch presence 39.9932% → 43.6338%, with 161/499 labels over budget and 59 newly missed. Extended-middle passes its label/output gates; no arm passes both recordings. Small report collected once and digest verified; bulk remains remote. This fixed setting is closed, with no tuning, second dispatch or installed change. Details and timing are in `CODEX-M3-SOUNDSHED-RESULT-20261123.md`.
