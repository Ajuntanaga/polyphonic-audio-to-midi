# Unchanged-model operator profile

Codex owns the new operator-profile runner, tests, specification, checkpoint and worker workflow. Claude retains independent release-probe ownership; no acknowledgement or approval gate. Full graph optimization45031644965 is final/rejected; no unchanged retry.

One bounded GitHub CPU observation of the exact two corrected ONNX files from45029161409. ORT1.20.1, optimizations disabled, sequential2 intra/1 inter threads. Three existing fixed synthetic signals per model,16 calls after one zero warmup. A fresh unprofiled session must be bit-identical on all outputs. No recordings, training or graph rewrite.

Question: which named operators and tensor shapes account for runtime? Save all node/operator duration shares and graph metadata, excluding the warmup and fence events. This decides whether temporal caching or a smaller dependency slice can remove repeated work. Profiled timings include overhead and cannot pass the corpus deadline gate.

Official profiling API: https://onnxruntime.ai/docs/performance/tune-performance/profiling-tools.html .

Local parser tests:3 passed. Model execution and environment verification occur on GitHub only. Source/worker pins and run are added to github-basic-pitch-operator-profile-20261122.json at dispatch. No installed/default changes or promotion.
