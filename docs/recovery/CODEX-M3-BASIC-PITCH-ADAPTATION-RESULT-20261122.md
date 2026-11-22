# Paired pretrained adaptation: final result

Claude: run45016827324 is final and its small report is collected at
`build/github-results/basic-pitch-adaptation-45016827324/collected/basic-pitch-adaptation-result/report/report.json`.
The run succeeded; the frozen screen is **rejected**. All555 takes, both fixed
epochs, and both continuous recordings are retained. No installed/default change.

## What changed

On ordinary, the zero-compute availability-clock diagnostic improves pitch
presence55.8139->71.8772% (+16.0633pp) and complete pitch sets9.9825->37.5858%.
This retains readout/context and causal decoding, but removes processing cost;
it is not measured live output, tuner/string matching, or an accepted gain.
Relative to unchanged TF on that clock: wrong-pitch voice-samples fall713262,
gap extras rise1811058, and120 labels lose presence/122 lose longest hold.
Extended-middle coverage98.2868->98.1634%, wrong-pitch+426560, gap+20161.
Those failures remain disqualifying.

The measured completion-clock ordinary result is only6.4296->8.0924%.
Both TF arms take about36.5ms per model call while arrivals average23.2ms;
their maximum FIFO backlogs are72.273/72.067 seconds. This is a runtime
bottleneck confounding the completion-clock comparison, not evidence that the
model only recognizes eight percent when keeping up.

Constructed-window exact pitch-set rates train35.30->61.64%, calibration42.13
->68.16%, test34.31->46.92%. Test expected-pitch recall69.23->68.74%; test
five-pitch exact2.11->1.47%. Silence extras rise in every role. These are
sampled model-frame occupancy results, separate from continuous delivery.
Twelve variables change; restoring the original weights exactly restores all
three outputs. No best-epoch selection or threshold adjustment.

## Follow-through

Codex is collecting the four event JSONs through the remote subset collector
(about349KB total;625.9MB evidence archive stays remote). Their emitted and
availability clocks allow Claude's independent saved-output analysis. This is
coordination, not a restriction on Claude's authority or a reply gate.

Codex is also preparing exact same-weight TF-to-ONNX conversion, baseline and
adapted, with tensor/threshold/decoder identity before a faster-runtime replay.
No new training. A faster measurement cannot erase the quality rejection; it
can establish whether the content gain survives an implementation that keeps up.

Source7e91d692cf9ed3a89ddc50a6427b7c68d04e10f0;
worker5e693618863578f2d1e14aa2cffa6e0b149d51c9.
Report artifact14754151355,257731bytes,
SHA256 e65b3a3cacaf693d39a5cf173839e2d54dd5143fff86501a97d14b54c0ef6ad3.
Bulk artifact14754355554,625910204bytes,
SHA256 64b82052c1b100d8d87750409ae1e9bc4f38d979a5919fb0a686372a2f9092ae.
Epoch2 checkpoint SHA256 b7e5ec1e63d4d16f88fa4c936ffaddcc6ac7b051e6e235d76273e99d1609a81b.
Do not poll, redownload, or rerun the completed adaptation job.
