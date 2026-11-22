# Synthetic numerical localization, frozen before dispatch

Claude: I am taking the numerical conversion path in `tools/basic_pitch_onnx_numerics.py`, its focused test, the frozen JSON specification and worker `basic-pitch-onnx-numerics.yml`. Your support/emitter work can continue independently; no peer approval or acknowledgement gate.

Run45023694341 completed with correct model interfaces and preserved variables, but numerical parity failed, especially on silence. This distinct observation compares the original callable TensorFlow model, the frozen function, exposed TensorFlow intermediates, and optimized/unoptimized ONNX with and without intermediate outputs. Only the same three synthetic inputs are used. No recording, fit, updated weight, cutoff change or relaxed tolerance is allowed. All eligible exact-name float32 intermediate tensors are retained up to the frozen256-tensor/20M-element bounds; exceeding bounds fails instead of sampling. Shapes that differ are reported unavailable rather than permuted by guess.

Exposing outputs may inhibit fusion, so final-output perturbation is measured separately. Graphs, maps and bounded intermediate arrays stay in the remote evidence artifact. The compact report is collected once. An intermediate observed pass cannot certify the unobserved model. This job locates a conversion discrepancy; it does not measure note quality or live readiness.

Local direct verification: seven comparison/export checks pass, one TensorFlow/ONNX fixture correctly skipped locally and required on GitHub. The JSON-serialization index defect was fixed before dispatch. One source/workflow review completed. Twenty-minute CPU job with fifteen-minute process cap; one dispatch under standing authorization. Source and worker SHAs plus run and artifact names will be recorded in the checkpoint.

The unchanged numerical limit is maximum absolute1e-4 with no0.3/0.5 decision crossing and identical decoded events. Further implementation follows the first measured divergence, not a tolerance change. The adaptation safety rejection remains separate from conversion feasibility. Installed/default output unchanged.
