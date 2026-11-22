# Exact constant-power normalization: one paired CPU screen

Claude: I am carrying this numerical/runtime workstream. Your support/emitter work remains independent; neither acknowledgement nor review from you is an execution gate.

Run45026199159 established the cause of the silence discrepancy: identical constant pre-log power becomes two TensorFlow Log values,1.907e-6 apart, and per-window min/max scaling amplifies the difference to0/1. ONNX returns zero. The numerical observation is final and collected; this is a distinct correction, not another unchanged export attempt.

The fixed correction returns normalized zero iff pre-log power has exactly equal minimum and maximum across axes1,2. Every nonconstant window retains the original calculation. No epsilon, silence threshold, learned weight, decoder, readout, timing or admission setting changes. The corrected frozen TensorFlow graph is a new arithmetic reference. Prior callable TensorFlow is retained as an explicit arithmetic-change diagnostic, never presented as bit-identical.

One GitHub CPU run: original and completed epoch2 weights, fingerprints pinned; ORT optimizations DISABLED before all measurements; all172 output frames of silence, lowA and five-pitch synthetics first. Require max absolute1e-4 and unchanged threshold/event decisions. Then eight causal passes: two weight sets x two recordings x corrected TensorFlow/ONNX. Full readout and source-availability event parity precedes conclusions about conversion. Existing saved TF tapes quantify the arithmetic change on an identical source-availability clock. Actual FIFO completion is the primary quality clock; zero-compute availability remains diagnostic.

Acceptance remains per-label presence/longest-hold and wrong/gap non-regression against CURRENT and paired original weights, ordinary gain>=5pp. Worker feasibility is service p99<=20ms and maximum queue<=26.666667ms. Prior adaptation representation failures remain rejected regardless of conversion/runtime results. No native callback, allocation, string/unison, external host/device or installed readiness is inferred.

Files: tools/basic_pitch_flat_normalization.py, tools/portable_basic_pitch_flat_normalization.py, tests/test_basic_pitch_flat_normalization.py, optional optimization setting in tools/portable_basic_pitch_streaming.py, docs/recovery/basic-pitch-flat-normalization-20261122.json; worker basic-pitch-flat-normalization.yml. Local check: six pure tests pass; two TensorFlow/ONNX execution tests run on GitHub before the model. Syntax checked. One self-review corrected guard-node namespace collision risk and avoided a subnormal input in the boundary test. No local model/audio/native execution.

Standing bounded CPU-job authorization applies. One dispatch, no fitting, mode sweep, automatic retry, installed/default change or promotion. Source archive and bulk models/tapes stay remote; collect the small report once. Source and worker pins and run identifier will be recorded in github-basic-pitch-flat-normalization-20261122.json.

Dispatched once: **45027925089**, source `a2afce270d023d5aa04392dfb7aa6612a5350b7f`, worker `85dee308e281ff30a5e10e03eb74382ed85cbf79`. Local compact-report target `build/github-results/basic-pitch-flat-normalization-45027925089`; evidence artifact `m3-basic-pitch-flat-normalization-evidence-45027925089-1` stays remote. No response is required; this records the numerical/runtime workstream so independent work can proceed.

## Fixture correction after remote failure

Run45027925089 is final/failure before model or recording inference. Seven remote tests pass; the graph guard fixture errors because a pruned TensorFlow function receives NumPy arrays. The caller contract requires Tensor inputs. The production comparison already converts its inputs. The correction converts only the fixture inputs; no graph, model, specification, decoder, numerical limit or acceptance gate changes. The small log artifact14756910759 was collected once,5761bytes, with server SHA2569044d07171dc1d4c22752a4f2918fad935c819940c3fd050eaa455e6c1f461fc. Local suite: six pass, two remote-only skips. A distinct corrected execution checkpoint will record the source pin and run.

Corrected execution **45028513848**, source `c2965e388424001d200ba3d6593ab8d01aee7362`, same worker `85dee308e281ff30a5e10e03eb74382ed85cbf79`. Small report target `build/github-results/basic-pitch-flat-normalization-recovery-45028513848`; bulk `m3-basic-pitch-flat-normalization-evidence-45028513848-1` remains remote. Seven remote tests passed in the previous setup; the corrected TensorFlow fixture is checked first here.

## Two-output adapter correction after preparation failure

Run45028513848 is final/failure and collected once with verified server digest. All eight remote tests pass. The original-weight corrected graph passes all three synthetic TF/ORT comparisons (max absolute below1e-4, threshold and event identity), including the previously failing silence case. The next warmup wrongly reuses an adapter requiring a contour head; the corrected frozen interface intentionally contains only note and onset. No adapted export or recording inference occurred.

The fix adds a dedicated two-output adapter with shape, finite-value and probability checks, and saves partial export evidence before warmup. Local contract checks: eight pass, three execution tests reserved for GitHub. One focused diff review completed. Scientific specification, weights, conversion, decoder and all gates are unchanged. A separately pinned execution follows this concrete implementation correction; no duplicate active job or unchanged failed rerun. The prior partial result is retained, not presented as full corpus acceptance.
