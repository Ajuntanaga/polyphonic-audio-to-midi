# FretNet CPU feasibility — 2026-11-23

The original-teacher preservation setting remains rejected and closed. One
fixed comparison of a different pretrained guitar model is prepared. There is
no threshold retry or new fit. The purpose is to see whether its guitar-specific
representation recovers chord notes that CURRENT misses, at the same safety
budget, before considering any runtime integration.

Coordination: Codex owns this feasibility/possible comparison lane. Claude's
ordinary 58-event acoustic lane stays independent; no response from either peer
is a prerequisite for the other. No model/audio has been downloaded locally and
no comparison workflow has been dispatched. Installed output and defaults remain
unchanged.

The author's repository, cwitkowitz/guitar-transcription-continuous, has no model
release. Its issue 2 links to the separate MIT-licensed
markod0925/GHPitchDetection runtime. At pinned revision
`41fdd102d905601485973c3be42232f4cf260b09`, GitHub metadata exposes
`tools/FretNetRust/model/model.onnx`: 19,407,981 bytes, Git blob SHA-1
`bb83154300bef2ac1bfeec6b84ec24bc52bec617`. The runtime lives in
`tools/FretNetRust/fretnet_runtime`. Commit
`e7d24326e0527c27e0af4ebe371a9f6664ff3114` says the ONNX was regenerated
from model-2000.pt. The training fold/manifest and original checkpoint provenance
are not established. Use ONNX, not the Python pickle.

The source check is complete: author HCQT with six harmonics, 22050 Hz / hop512,
whole-recording RMS normalization, per-harmonic maximum-relative dB features,
nine-frame centered windows and float32 sigmoid followed by per-string argmax.
The comparison uses nominal offline frame times, not causal delivery. The fixed
profile covers pitches 40..83 and is six-string standard tuning.
The six-string model must not silently discard the eight-string corpus's lower
notes. Any comparison retains all existing annotations, reports out-of-range
labels explicitly, uses fixed upstream defaults and separates nominal output
from causal availability and measured delivery. No fitted offsets, relabeling,
threshold sweep, union promotion or deployment follows from feasibility.

Frozen specification: `docs/recovery/fretnet-comparison-20261123.json`.
Implementation: `tools/fretnet_comparison.py`,
`tools/portable_fretnet_comparison.py`, `tools/fretnet_requirements.txt`, and
`tests/test_fretnet_comparison.py`; worker `fretnet-comparison.yml`.
66 synthetic adapter, runner, scorer and lifecycle tests passed locally. The
model, audio frontend and reference fixtures have not been executed locally.
Two pinned reference bundles must pass frontend, framing, all three raw-head
and decoded-position checks before either protected recording is processed.
Any reference failure stops the job before corpus inference.

Primary: one inference each on ordinary and extended-middle, full annotations,
ordinary pitch-coverage gain at least 5 percentage points, no extra/wrong-pitch
or gap growth and no exact-set/all-expected loss on either. Report both strict
per-label safety and the existing 25 ms AND 5% present/longest-hold budget, with
no newly missed labels. Literal union and the fixed MIDI-60 split are report-only
diagnostics. This comparison cannot establish string assignment, unisons,
re-plucks, causal latency, native deadlines or reliable live use.

Sources:
- https://github.com/cwitkowitz/guitar-transcription-continuous/issues/2
- https://github.com/markod0925/GHPitchDetection/tree/41fdd102d905601485973c3be42232f4cf260b09/tools/FretNetRust
- https://github.com/markod0925/GHPitchDetection/blob/41fdd102d905601485973c3be42232f4cf260b09/LICENSE
