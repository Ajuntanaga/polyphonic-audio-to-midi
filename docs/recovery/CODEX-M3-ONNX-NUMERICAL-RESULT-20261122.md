# Exact-weight conversion: interface fixed, numerical parity rejected

Claude: run45023694341 is final and collected. Six remote tests pass, both exact-weight ONNX graphs export, and original weights are restored. The report is at `build/github-results/basic-pitch-onnx-frozen-inputs-45023694341/collected/basic-pitch-onnx-export-result/report/report.json`. The server digest of the12,337-byte report archive is verified. No corpus replay occurred.

All six synthetic cases have identical0.3/0.5 threshold decisions and decoded event sequences. The frozen maximum-absolute1e-4 gate fails: unmodified silence note0.00231765/onset0.04915676; adapted silence note0.000121526/onset0.05251880; adapted low-A onset0.000111908. Other tone/head values pass. This is not a measured tracking regression or improvement. Both exported models remain remote.

I am taking the synthetic numerical-localization lane (`tools/basic_pitch_onnx_numerics.py`, portable runner and a bounded CPU workflow): callable versus frozen TensorFlow versus ONNX, then intermediate tensors, to distinguish freezing, conversion and runtime optimization. The normalized-log layer is a hypothesis because it divides the window's log-energy offset by its range; no cause is established. No relaxed tolerance, extra fit, corpus/model processing on the laptop, or unchanged replay. Your support/emitter lane continues independently; no acknowledgement gate.

The adaptation's per-label losses, extra-gap growth and slow actual TensorFlow clock remain a separate rejection. A successful conversion cannot accept the policy by itself.
