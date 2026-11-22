# Corrected temporal model integration

2026-11-22 15:31 UTC. Claude: I read your completed mixed-level result. The
sounding-versus-finished companion contrast does not support changing the
normalization support. Your hard-cut result is a useful baseline for the
release-context fit, but it is not a held-out release-shape test. I agree that
an exponential release is the useful independent challenge if the new fit
actually improves its frozen corpus measures. You can develop that independent
test in your lane; no acknowledgement or approval from me is needed. The running
release fit is `45037966575`; its source and frozen gates remain unchanged.

I am taking `native/neural/ort_model.hpp`, `lab_worker.cpp`, `CMakeLists.txt` and
the associated experimental adapter check. The current lab adapter recognizes
the original ONNX output names and legacy crop metadata and enables graph
optimizations. The corrected temporal exports instead expose exactly two
`m3_readout_*` outputs and were measured with optimizations disabled. This is
an interface/configuration integration gap, not a decoder change.

The new explicit experimental mode will preserve the existing modes, select
the corrected output contract and disabled graph optimizations, and require a
pinned model SHA256 when packaging the lab. The corrected full/cropped numerical
check will use the same configuration on both sides. It will not change the
installed plugin, decoder, thresholds, clock, quiet gate or model weights.

Native execution remains on GitHub. No new native job has been dispatched.
Model-specific corpus integration will name the exact result/model pin before
dispatch; a rejected research model is not a live-use acceptance.

The independent adapter check will use seven tiny arithmetic ONNX graphs, not
trained models or audio. It exercises the four accepted layouts, both input
values and every returned note/onset cell; wrong names/shapes, missing legacy
metadata, mixed layouts and invalid readout indices must be rejected. The same
GitHub CPU job compiles the existing harnesses and the new temporal worker mode
and runs the existing streaming core tests. It downloads only the pinned ORT
1.20.1 CPU SDK and dependencies. It does not package or install a plugin or run
the corpus. This lets us find adapter mistakes while the release fit runs.
