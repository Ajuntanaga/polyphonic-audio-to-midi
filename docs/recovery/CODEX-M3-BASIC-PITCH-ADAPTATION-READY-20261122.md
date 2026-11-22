# Frozen pretrained adaptation: one CPU comparison

2026-11-22. Codex owns this prepared workstream; Claude remains an equal, independently active collaborator. No acknowledgement or new approval gate is needed under the standing M3 CPU-job authorization.

Question: can two fixed epochs of note-only adaptation on the retained guitar takes improve pitch presence while preserving lower notes, holds and false-output safety? This is a different representation from the concurrently running harmonic-patch model (45012604509); neither job is duplicated.

## Frozen experiment

- Specification: `basic-pitch-adaptation-20261122.json`, SHA256 `fa70689affcb0bd964ad0f2e81890ef23f840387a1f5ebbd7c896c2e11c6240c`.
- Pinned pretrained TensorFlow model from Spotify Basic Pitch commit `fa5997af0a8210982619003269994a1be25eddf3`. All public model files have pinned git-blob hashes and sizes.
- All 555 original takes remain: pass1 train200, pass2 calibration200, pass3 test155. Every take is anchored before random mixtures. Same instrument/session and previously examined labels; this is not independent-player or blind validation.
- 4096/1024/1024 fixed windows, 1-5 distinct strings, frozen gains and seeds. Crop or zero-pad, never repeat or stretch short takes. Nominal-frame labels cover the retained component, including the taper. Same-pitch sources count as one pitch, not verified unison multiplicity.
- Two epochs, batch4, Adam1e-4, global gradient clip1. SavedModel inference graph, fixed normalization statistics; note BCE only. No fabricated onset or contour labels. No sweep, early stopping, threshold selection or automatic retry.
- Unchanged TensorFlow and epoch2 TensorFlow are paired. The trainability probe 45014937419 proved finite gradients and exact restoration but FAILED TensorFlow/ONNX numerical parity; a backend difference cannot count as adaptation gain.
- Train precision99%, held-role precision95%, recall80%, exact set70% overall and at3/4/5 pitches, silence extras0. Each source occurrence must preserve presence and longest hold. Every failure and delta remains reported.
- After a completed fit, BOTH models run on ordinary and extended-middle even if these gates fail. Same existing causal decoder, raw recording amplitude, all88 model pitches, one CPU thread. Measured FIFO completion is primary; zero-compute availability is diagnostic. Paired timing includes machine noise.
- Existing per-label presence/hold, false-note/gap, exact-set and all-expected gates apply against unchanged TensorFlow and saved CURRENT; ordinary must gain at least5pp. Report rejection without hiding complementary gains or lost labels. Native deadlines/allocations, strings, bends/replucks and live host/device delivery remain unmeasured.

## Execution and collection

Files: `tools/basic_pitch_adaptation.py`, `tools/portable_basic_pitch_adaptation.py`, `tests/test_basic_pitch_adaptation.py`, frozen specification. Worker: `basic-pitch-adaptation.yml`, 105-minute process/120-minute job, one thread, existing private input releases only. Epoch model/optimizer states are atomic, bulk evidence stays remote.

Six synthetic tests pass, covering retained-source coverage, actual short-note frame masks and silence, unison counting, per-occurrence losses, false-silence/chord gates and the pre-I/O remote guard. Python compilation passes. No local recorded audio, model load, fit or native execution. Model execution is first verified on GitHub.

Expected artifacts: `m3-basic-pitch-adaptation-report-RUN-1` (collect once with server-digest verification) and `m3-basic-pitch-adaptation-evidence-RUN-1` (remote model/checkpoint/window/stream evidence). Source/worker revisions and run ID will be recorded after the single dispatch. Installed output and scoreboard remain unchanged.
