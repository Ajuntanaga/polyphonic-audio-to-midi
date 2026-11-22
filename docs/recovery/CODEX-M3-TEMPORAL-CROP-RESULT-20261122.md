# Temporal crop: runtime screen passed, tracking quality still rejected

Run45034216124 finished2026-11-22 14:48:28 UTC, source8647d92400bf4049a1f5010de40a2f3016b8e72d, worker1dcfc41a4d2bafa62702a49a44fa3b5bf319f0b7. Small report collected once; server SHA2564413524ff8f72b5d5359dc7c67e04bb7a68a7b05a93453aac0f76b1de61d6257 verified. Bulk artifact14759705414 remains remote.

All six synthetic pairs and all four recording/model pairs are bit-identical at every consumed note/onset probability and source frame. Original graphs reproduce the prior disabled-ORT tapes. Source-availability events, cleanup notes and measurements are identical. The crop retains all original initializers (102 unmodified,100 adapted).

| Recording / weights | Original p99 ms | Cropped p99 ms | Cropped queue max ms |
|---|---:|---:|---:|
| ordinary / unmodified |19.562209|11.158296|17.614712|
| ordinary / adapted |19.339976|11.202313|8.497971|
| middle / unmodified |19.340345|10.880618|4.914696|
| middle / adapted |19.373951|11.160454|5.137533|

All four cropped pairs pass p99<=20ms and queue<=26.666667ms. Median service falls from18.48–18.50ms to10.39–10.43ms. This is an exact-output implementation improvement on this GitHub CPU, not native callback, allocation, hardware or DAW certification.

Measured FIFO completion changes because compute is faster. Ordinary adapted pitch-present samples rise23615657->23914086/33819101; extra pitch-voice samples2642286->2455533; gap voice-samples5434706->5326057. The source-availability content is identical, so these are delivery-clock effects, not new detections or installed tuner/string gains. Prior adaptation label losses, held-out failures and gap growth remain rejected. Prior corrected-TensorFlow/ORT numerical failures remain unresolved; this ORT-only result does not erase them. No promotion or installed/default change.

Next is the separately frozen frame166/167 causal readout against164/165, keeping weights and decoder fixed; see CODEX-M3-SHORTER-LOOKAHEAD-20261122.md. Claude's acoustic-support observation remains independent and equally authorized. Do not poll, redownload or rerun45034216124.
