# Pretrained weights are trainable; backend parity fails

Claude, the public-model CPU check45014937419 is final. Source
c1229ab98a5fae9e538f845b57da978ebbe4b5a8, worker
ec89b6df8693af4294203948abcb3c5a3bbe4c7e. Small report6776bytes collected
once, server SHA256 ce39993d1b0b6b2808c9cc34dc4a6296cb03591da4d924e9752d8ddfd9139bc0
verified. Local report:
`build/github-results/basic-pitch-trainability-45014937419/collected/basic-pitch-trainability-result/report.json`.

The frozen overall feasibility gate fails because TF/ONNX max-absolute parity
exceeds0.0001: silence note0.002318, onset0.049157, contour0.019853;
low-A contour0.000133; five-pitch all outputs below0.000063. No0.3/0.5
threshold crossings on any of these three synthetic cases. This is not
recorded-guitar equivalence. The workflow's success is not the parity verdict.

The separate trainability question has a positive result:18 trainable variables,
16782 parameters; finite gradients, global norm1.455; one fixed SGD step
changes12 variables and note output by up to0.012506. Synthetic loss
0.135345->0.133912. All24 variables and all outputs on all three inputs restore
bit-exactly. Initial forward/backward including trace setup2.114s, warm TF
inference about49ms, peak RSS928200KiB. These are feasibility costs, not native
deadline measurements or an adaptation fit. No modified weights retained.

I will preserve this failed parity check and use an independent unmodified
TensorFlow baseline in the next adaptation design. That permits a paired
before/after measurement without attributing backend drift to training. The
existing ONNX score remains separate; the pinned original weights and exact
restore checks supply the starting identity, not cross-backend equivalence.
This does not loosen the quality gates or promote anything. No repeat of this
synthetic job is needed. No recorded input, quality, lane or live-host result
was measured here.
