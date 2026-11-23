# A short practical guitar capture

2026-11-23. Prepared, not recorded or scored. No software, settings or acceptance
gate changes. The faster **M3 Batch Cell Lab** package is already staged under
`build/deliverables/m3-batch-cell-lab-20261123/`; it is not installed.

## Why this is the next missing performance check

The retained recordings establish real three-string unisons. They do not
establish exact membership of a real four-string chord: the recording named
`physical-four` has changing fingering and pitch-only labels. The ordinary
chord benchmark mixes individual recorded notes, often across widely separated
frets. It remains a useful stress test, but it is not a recording of ordinary
chord playing. Neither fact contradicts the player's earlier stable four-note
experience. That particular performance and its exact settings were not retained
as a reproducible comparison.

The existing stress scores and rejected trials stay as recorded. This capture
adds a practical performance check; it does not replace difficult examples.

## Record about three minutes, when convenient

Use the guitar's existing major-thirds tuning and A4 reference. The shapes
below assume the recorded tuning: strings 8 through 1 open at MIDI
32, 36, 40, 44, 48, 52, 56, 60. If the guitar has changed, record its actual
tuning instead of retuning for this guide. String 8 is the lowest string.

Record a continuous **dry DI** at the interface's current rate, preferably the
existing 96 kHz setup. Keep the raw take, including attacks, gaps and decay:
do not gate, normalize, pitch-shift, trim into artificial holds or join takes.
Keep effects and a click out of the recorded DI. A separate spoken/video cue
can identify the fingering and actual plucks; intended times alone are not
ground truth. Video is optional. Avoid changing a live REAPER session solely
for this capture.

These are compact suggested shapes, not a constraint on the detector. Use them
only if comfortable; log any different fingering before playing it.

| Case | Strings, lowest first | Frets in that order | Expected MIDI pitches | Purpose |
| --- | --- | --- | --- | --- |
| Low four-note E major | 8, 7, 6, 5 | 8, 8, 7, 8 | 40, 44, 47, 52 | Lower-register chord |
| Middle four-note C major | 5, 4, 3, 2 | 4, 4, 3, 4 | 48, 52, 55, 60 | Familiar compact chord |
| High four-note C major | 4, 3, 2, 1 | 12, 12, 11, 12 | 60, 64, 67, 72 | Upper notes currently difficult in mixtures |
| Existing three-string E2 unison | 8, 7, 6 | 8, 4, 0 | 40, 40, 40 | Same pitch on three strings |

For each case, take roughly 12 seconds:

1. Sound the intended strings separately once so their identity is clear.
2. Play the chord together and hold for about two seconds.
3. Pluck the held chord twice more, about one second apart, without first
   muting it. Let it ring briefly, then deliberately mute and leave a gap.

Make three **separate performances** of that sequence. They need not follow a
metronome. A missed string or unintended attack stays in the recording and is
annotated as played. If possible, append a short example of the four-note
playing that originally felt stable, with its actual settings written down.
Do not attempt a stretched four-string same-pitch unison for this guide: the
four-note major chords above and the three-string unison answer different
questions.

Record sample rate, pickup selection, input gain, tuning, calibration state,
plugin build and settings once. The dry recording is enough to begin; a
simultaneous MIDI capture and note of what the player heard are useful if an
existing setup already records them. No lab installation is required to make
the dry take.

## What happens afterward

Raw inputs remain in the authorized private `m3-offload` route, outside the
public source repository. Processing and listening/measurement by agents stay
on GitHub Actions. Sample labels are derived from the actual recording and
confirmed string membership; this plan contains no invented sample timestamps.
Keep uncertain attacks or ends marked uncertain rather than forcing an answer.

Assign complete performances to development, calibration and held-out test
before comparing output. Do not split copies or adjacent fragments of one
performance across roles. The reserved test performance is not used to choose
settings or tune a rule. It is a same-player practical check, not a claim about
all guitars or players.

Replay the fixed CURRENT reference and the exact staged batch-cell lab with
the same calibration/settings first. Report note presence, exact string and
whole-chord matches, false notes/gap outputs, correct hold duration, real
re-plucks preserved, extra retriggers and delivery latency separately. Existing
per-label, false-output, allocation and deadline requirements remain intact;
the performance build is expected to preserve output, not increase tracking
scores. Actual live device behavior still needs the player's host check.

## Peer coordination and provenance

Claude's seven-event acoustic check remains useful: none of those removed
events coincided with an attack in the nominal-pitch envelope. The ordinary
58-event acoustic task is separate, already offered in
`CODEX-M3-PEER-ACOUSTIC-NEXT-20261123.md`; this guide does not duplicate it or
restrict either peer's authority. The existing Claude session reported `idle`
when checked on 2026-11-23, with its last recorded reply at 10:03:59 UTC. That
is an activity observation, not a user pause instruction or evidence of ongoing
analysis.

Evidence: `CODEX-M3-ORDINARY-CORPUS-SHAPES-20261123.md`,
`build/physical-capture/unison-08-07-06/README.md`,
`build/physical-capture/unison-08-07-06-05-04/README.md`,
`CODEX-M3-BATCH-CELL-LAB-DELIVERY-20261123.md`, and
`CLAUDE-M3-AUDIO-ENVELOPE-GHA-RESULT-20261122.md`.

The companion `m3-practical-capture-plan-20261123.json` records the proposed
notes and lane masks. Its state is `awaiting_new_performance`, not a measured
result or a dispatched job.
