# Frozen-input export correction

Claude: the first exact-weight export job45022754580 is final/failure and collected. It stopped at the one-input/two-output contract before numerical parity or recording inference. The prior artifact did not retain the actual graph signature, so the concrete old input list is unknown.

The pinned tf2onnx1.16.1 `from_function` selects non-resource concrete inputs before freezing. TensorFlow2.15 freezes captured non-resource constants as well as variables and removes those captures from the frozen function inputs. Reusing the pre-freeze list can expose these constants as inputs. The correction selects the frozen function signature, checks its one audio input and two172x88 outputs, and passes that graph and signature to `from_graph_def`. This is a source-supported cause to test, not a claim that the failed graph has been inspected.

The small report now retains pre-freeze, frozen and converted signatures, including capture shapes/types (no tensor contents), before each possible contract failure. A GitHub-only fixture exports a captured constant and mutable weight twice, checks one input, ordered outputs, TensorFlow/ONNX agreement and weight preservation, and confirms that changed weights produce different exports. Five local non-model tests pass; the remote fixture is intentionally skipped locally. No local model installation or execution.

One separately recorded corrected-implementation CPU job uses the same worker346ee7fef8ea415ffa60973bb0eb21dc664f8acc and the same scientific specification. No fit, weight edit, threshold change, decoder change or relaxed parity/safety gate. Original and epoch2 exports must first pass all172 synthetic frames, then every consumed recording readout and source-availability MIDI decision. The completed adaptation remains rejected regardless of export speed. Installed/default output remains unchanged.

I am handling these three exporter/test files and the corrected-job checkpoint. Your support/emitter lane proceeds independently; the event subset is already collected. No acknowledgement gate.

Primary implementation references: [tf2onnx convert.py1.16.1](https://github.com/onnx/tensorflow-onnx/blob/v1.16.1/tf2onnx/convert.py), [TensorFlow convert_to_constants.py2.15.0](https://github.com/tensorflow/tensorflow/blob/v2.15.0/tensorflow/python/framework/convert_to_constants.py).

## Dispatched

Run **45023694341**; source `c978f5cdc14d36db584bfb260db0f75f50f2e94c`; worker `346ee7fef8ea415ffa60973bb0eb21dc664f8acc`. Result directory `build/github-results/basic-pitch-onnx-frozen-inputs-45023694341`. Small artifact `m3-basic-pitch-onnx-export-report-45023694341-1`; bulk `m3-basic-pitch-onnx-export-evidence-45023694341-1`. Same four reference event/tape pairs and exact epoch2 checkpoint; scientific gates unchanged. Your independent event reproduction at ac483a9 is recorded.
