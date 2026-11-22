# Pre-registration: scoring Codex's original/adapted Basic Pitch events as the filter's support

Claude, 2026-11-22. Written and committed BEFORE the adaptation run 45016827324 has produced any event file, so the plan and the predictions cannot be fitted to what arrives. The commit is the record. Nothing here is a result.

## What will be scored

Codex's frozen adaptation run (spec SHA256 `fa70689a...`) runs unchanged TensorFlow and epoch-2 adapted TensorFlow, with the existing causal decoder, on `ordinary` and `extended-middle`, and pins four compact event files (original and adapted, two corpora). Codex owns the run, the monitor and the collection; this note only fixes how I will use the events once Codex sends their paths and hashes.

Support under test, the same model-supported filter already scored with arm A:

- CURRENT intersected with (model spans union the native confirmation), the support held forward D ms, D in {50, 220}, both corpora, filter only (no lane, no persistence rule). Same scorer (`tools/pitch_detector_comparison.py`), same labels, same CURRENT, same clipping as `CLAUDE-M3-SUPPORT-DILATION-20261122.py`; only the span source changes.
- Four supports per corpus: arm A (saved ONNX offline causal run, the existing reference), the unchanged-TF events, the adapted-TF events, and arm A union adapted events.
- The events are read at their measured emitted clock (FIFO completion), not at zero-compute availability. If the event files carry only the zero-compute clock I will say so and not use it as a causal support.

## What cannot be concluded

This scores the events as a support for the existing filter on two recordings that were examined before. It is not the adaptation's acceptance (Codex's frozen gates decide that), not a tracking result, and says nothing about native deadlines, strings or live delivery. A rejected adaptation is scored too and reported as rejected-run evidence. Any grid value other than D in {50, 220} and any lane variant would be post hoc and labelled.

## Predictions, each can fail (reasons are from saved arm A numbers, ordinary D = 220 unless stated)

- R0 format and identity: the unchanged-TF events, used as the support, give a filter within a few labels of arm A's: 4 to 8 labels losing present or longest hold (arm A: 6) and a wrong-pitch removal share between 18% and 26% (arm A: 22.1%). The TF/ONNX backends differ numerically, so exact identity is not expected.
- R1 the adapted support loses no more labels than the unchanged-TF support.
- R2 the adapted support loses no larger a share of CURRENT's present time than the unchanged-TF support.
- R3 the adapted support removes at least as large a share of CURRENT's wrong-pitch output as the unchanged-TF support (a more precise model rejects more false notes).
- R4 label 229 (pitch 42, the largest arm-A loss) stays lost under both supports: at least half of its CURRENT present time is removed in each.
- R5 extended-middle, D = 220: both model supports keep 0 labels losing and the safety flag True (arm A did).
- R6 the filter precision with the adapted support is at least the unchanged-TF support's at D = 220 on ordinary.
- R7 arm A union adapted events as the support loses fewer labels than arm A alone (below 6) on ordinary at D = 220.

Report all eight whatever they show, including failed predictions, with the sha256 of every input file.
