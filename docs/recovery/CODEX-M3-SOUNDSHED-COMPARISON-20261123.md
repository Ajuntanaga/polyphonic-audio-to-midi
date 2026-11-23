# Soundshed causal comparison — preparation

2026-11-23, Codex workstream. Claude's ordinary-58 acoustic analysis remains
independent. No job dispatched yet.

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
