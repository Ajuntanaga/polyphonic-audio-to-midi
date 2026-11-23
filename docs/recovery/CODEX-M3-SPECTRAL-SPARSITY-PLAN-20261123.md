# Spectral-sparsity attack spike — frozen before waveform processing

Codex owns the new `tools/spectral_sparsity_attack.py`, its portable runner,
contract tests, this plan/spec/checkpoint and `m3-spectral-sparsity-attack.yml`.
Claude's ordinary suppressed-attack acoustic study is separate and independently
authorized. No peer acknowledgement is needed. This is a bounded CPU GHA spike,
not a plugin change. No new inputs, local audio, native replay or installed edit.

The closed adjacent-onset guard retained the first repeat but restored false
retriggers in both single-copy controls. A separate attack identity therefore
needs an observable beyond that guard. Here we test spectral sparsity, using
weak spectral bins rather than the previous complex-domain difference feature.

Source: Mounir, Karsmakers and van Waterschoot,
[Musical note onset detection based on a spectral sparsity measure](https://link.springer.com/article/10.1186/s13636-021-00214-7),
equation 13 and sections 3.4/4.4. The feature combines energy with inverse
sparsity of the low-magnitude log spectrum. The paper tunes its threshold;
it does not supply a numeric default suitable for this run.

## Frozen construction

- Existing six SHA-pinned WAVs and response deadlines from run 45155740922.
  No regeneration or input gain change. Three layouts per pitch: single,
  overlapping copy and separated copy. These are constructed-copy controls,
  not new physical plucks or an independent acoustic validation set.
- NINOS2 l2/l4 equation 13, log1p magnitude, lowest 95.5% of eligible bins.
  Float64, symmetric Hann, unnormalised FFT4096, hop410, 96 kHz.
  Eligible bins: strictly positive frequency through 22,050 Hz, below Nyquist.
  This 96 kHz adaptation is explicit, not an exact paper reproduction.
- Causal trailing frames, startup zero padding. Trailing-max history 30 ms,
  trailing-mean history 100 ms (both rounded up to whole hops); future history
  zero. Mean includes the current frame and missing startup history is zero.
  Require positive excess above the mean, including at threshold zero.
  Refractory is strictly more than ceil(4096/410)=10 frames.
- Event time is the exclusive end of the necessary input hop. No backdating,
  alignment credit or inferred onset time. Final partial hop is zero-padded
  and reported. Python feature timing is not realtime plugin evidence.

## Calibration and transfer rule

Only delta is fitted. Calibrate on all three **physical-highmid / note56**
fixtures. For every distinct positive peak strength, inspect the exact event
regime immediately above it, plus delta zero. Choose the **smallest delta**
that passes all three fixtures: exactly one cue per inserted copy, no later
than its saved per-voice response, and no additional cues anywhere.
This finite threshold fit is disclosed; no other parameter is fitted.

If no delta passes all three, stop and report REJECTED_CALIBRATION. Do not
process transfer waveforms and do not choose a fallback. Otherwise freeze
delta and process the three **physical-high / note60** fixtures once.
All three must pass the identical rule for BOUNDED_CUE_SUPPORTED; any failure
is REJECTED_TRANSFER. No retune, extra dispatch, integration or promotion.
Calibrated fit and transfer are reported separately; neither is corpus accuracy.

Integrity first: source/archive/member hashes, waveform shape/finiteness,
and exact feature identity on the unchanged prefix before the second copy.
Local tests exercise vector arithmetic, causal clocks and threshold selection
on made-up metadata only; waveform/FFT execution is GHA-only. The small report
is collected once with server digest verification; feature tables remain remote.

A pass would justify designing a pitch-attributed articulation observation.
It cannot by itself prove preservation of guitar re-plucks, chord behavior,
installed improvement, processing allocations or native callback deadlines.
Failure closes this fixed representation/setting without a rescue by tuning.
