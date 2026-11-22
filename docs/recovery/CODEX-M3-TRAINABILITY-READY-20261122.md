# Pretrained Basic Pitch trainability: frozen public-model check

2026-11-22. One bounded GitHub CPU job, separate from active recorded-input
training recovery45012604509. Standing M3 CPU-job authorization applies equally
to both peers. Codex owns these new files for coordination; no Claude reply gate.

Question: can the exact published pretrained TensorFlow SavedModel receive
finite nonzero gradients, change through one update and recover its original
outputs exactly? The model is pinned at fa5997af0a8210982619003269994a1be25eddf3;
all three SavedModel files have exact git blob/size pins. ONNX also retains our
existing SHA256. No recorded input, calibration file or private artifact is used.

Spec: basic-pitch-trainability-20261122.json. Runtime: Python3.11,
tensorflow-cpu2.15.0, ONNX Runtime1.20.1, NumPy1.26.4, one CPU thread,
deterministic TensorFlow, oneDNN disabled. Three fixed inputs: silence, MIDI45
harmonic decay and five-pitch40/47/52/56/59 harmonic decay. No inference or model
dependency installation runs locally.

All172 frames and note/onset/contour outputs must be finite probabilities with
the pinned shape. TF/ONNX maximum absolute difference must be<=0.0001 for each
output/input; threshold crossings at0.3/0.5 remain visible. Require inference
not to change stored variables. One note-BCE step uses fixed SGD0.001 and global
gradient clipping1.0 in the SavedModel's inference mode, keeping BN statistics
fixed. Record every connected/unconnected variable, gradient norm, before/after
loss, changed weights and changed note output. Restore *all* variables in a
finally block and require bit-identical variables and all three outputs on all
three inputs. No updated weights are retained or published.

Forward and forward/backward wall time plus peak resident memory size a possible
later fit; they are not callback or live-host timing. The fixed synthetic labels
are a gradient probe, not training-quality evidence. A feasibility pass neither
accepts a guitar detector nor changes any quality gate. A failed parity/gradient
or restoration result remains recorded; no automatic retry or tuning.

Implementation: tools/portable_basic_pitch_trainability.py; three local guard,
integrity and path tests pass. Python syntax/spec pins checked. One direct source
review found no blocking issue; actual backend and gradient behavior remains for
GitHub. Workflow basic-pitch-trainability.yml:20-minute job,10-minute execution,
public-only concurrency group. Collect only its small report/log artifact once.
Modified model weights and original model binaries are not uploaded as evidence.

The current full recovery fit remains selected at the top of RESUME.md. Its
source/worker pins and scientific gates are unaffected by this independent check.
