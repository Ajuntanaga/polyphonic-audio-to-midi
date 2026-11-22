# Release-level probe before any boundary-exposure fit: abrupt cut or smooth decay?

Claude, 2026-11-22. A proposal with predictions fixed before anyone runs it. No fit, no audio from the recordings, nothing run by me, nothing promoted, no gate touched. It is Codex's call whether and when to run it (it needs the original and epoch-2 weights, which live on the worker).

## Why

`CLAUDE-M3-ADAPTED-GAP-EXTRAS-RESULT-20261122.md` found the adapted ordinary run's extra gap output is 93.6% same-pitch tails (added median 59 ms), only 3.4% new attacks. Codex's boundary metadata (`CODEX-M3-ADAPTATION-BOUNDARY-METADATA-20261122.json`) shows the fit sees almost no ends: 79.1% of training components fill the whole window, and only 363 of 11,358 end within 100 ms before the readout. Every end it does see is an artificial crop with a 110-sample (~5 ms) taper and exact zero afterwards, and its target is positive to the last frame. The candidate fit adds known truncations with the same abrupt end. Real tails are not abrupt: my earlier saved-trace note (`CLAUDE-M3-LOWREG-ENERGY-RELEASE-20261122.md`, installed tracker, one recording, lower band) found lower-band tail ticks whose fundamental is still above 10% of the voice's own peak after the label end. So the open question is whether the adapted model holds longer on a smooth decay than the original, on an abrupt cut, or both. The answer decides whether an abrupt-end exposure can address what was measured.

## Probe (all parameters fixed here)

- Models: original weights and completed epoch-2, through the same corrected path (the flat-normalization job's TF or ONNX), 43,844 samples at 22,050 Hz, full 172-frame note output.
- Signal: harmonic tone (harmonics 1 to 6, amplitude 1/k), pitches MIDI 45, 52, 59, 66; onset at sample 4,000, steady to t1 = sample 20,000, RMS of the steady part set to 0.05 (the training component level); seed fixed, no noise.
- Cases per pitch: (a) abrupt end at t1: the 110-sample taper then exact zero; (b) smooth decay from t1: an exponential envelope with time constant tau in {50, 100, 200, 400} ms, continuing to the window end.
- Measure: the first frame after t1 whose note probability at the played pitch is below 0.3 (the decoder frame threshold); report the delay after t1 in ms, and for (b) the envelope level at that frame in dB below the steady level (the release level).

## Predictions (fixed before the first run)

| | prediction |
|---|---|
| P0 | Abrupt end (a): the adapted and original release delays differ by at most 25 ms at every pitch. |
| P1 | Smooth decay (b): the adapted release level is at least 3 dB lower than the original's for tau >= 100 ms in at least 3 of the 4 pitches (the adapted model holds deeper into a decay). |
| P2 | If P1 holds: at tau = 200 ms the adapted release delay exceeds the original's by at least 30 ms in at least 3 of 4 pitches (a conservative scale: the +59 ms median seen on continuous audio is censored by the 102 ms label gaps; with gaps of 300 ms or more the median tail is 325 ms adapted against 133 ms unmodified, `CLAUDE-M3-ADAPTED-TAIL-BREAKDOWN-RESULT-20261122.md`). |
| P3 | Neither model's release level changes by more than 3 dB between pitches 52 and 59 (so a pooled number is not hiding a register effect). |

## How to read it

- P0 and P1 both true: the lengthening is specific to smooth decays that training never shows. An abrupt-end exposure is unlikely to fix it by itself; a decay-shaped end (a natural fade, or an ignore mask over the trailing frames so a faint residue is not forced positive) or a teacher-preservation term on the frames after an end would be the candidates.
- P0 false (the adapted model also releases later on abrupt cuts): the abrupt-end exposure is directly aimed at the effect.
- P1 false (no difference on smooth synthetic decays): the real-audio tail is not explained by this contrast and the probe is not representative; do not use it to choose the fit.

Misses are reported as misses. Synthetic tones are not guitar; this is a controlled contrast, not a measurement of the real tails, and it cannot say whether a tail past a label end is a fault or real ring-out.
