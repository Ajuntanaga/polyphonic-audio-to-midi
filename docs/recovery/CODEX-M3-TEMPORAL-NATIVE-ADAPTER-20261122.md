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

Native execution remains on GitHub. The first synthetic job is recorded below.
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

## First adapter attempt and bounded correction

Run45039213332 is final/failure; source d879bf871dbab4cc5aaa17b5562631c0e3c33078, worker6fec38cc392bc3086db88d19412ca6ac530633de. The 2,170-byte log artifact14760464234 was collected once and its server SHA256 verified. ONNX fixture validation failed before any native compilation or test: NumPy1.x promoted division by the Python integer65536 to float64. The graph requires float32. All fixture arithmetic operands are now explicitly float32; local array-only checks confirm the three shapes and every expected value exactly. No model/native/audio work ran locally. A separate corrected execution will retain the same specification, worker and checks; the failed job will not be rerun. Release-training45037966575 remains active and sourceCI45037917689 passed.

## Corrected adapter result

Run45039587086 is final/success at source85d2d9fd7dac62d47a1a53a5bba522d6187d776e and worker6fec38cc392bc3086db88d19412ca6ac530633de. Both `neural_core` and `neural_model_adapter` pass. The four accepted layouts and invalid-interface rejection cases ran on GitHub; legacy and temporal worker modes compiled. Artifact14760967857 (3,778 bytes) was collected once; SHA2561d24a708587b2fc787eeefdc5d5cbeb508685f44d6c15def0e1a2205068283a1 matches the server. Result: `build/github-results/neural-adapter-contract-45039587086/artifact/report.json`. No corpus quality or runtime timing claim follows from these synthetic tests.

Claude: I am preparing the model-specific native runner on top of the existing delivery/timing harness while the release fit runs. It will require the exact new model and probability-tape pins, preserve164/165, compare corrected full/cropped outputs and cached probabilities/events, and score measured component delivery separately from worker-ready and zero-compute clocks. I will not dispatch it solely to re-prove a rejected quality result; the completed fit will determine whether a useful native comparison exists. Your saved-data level analysis remains independent.
