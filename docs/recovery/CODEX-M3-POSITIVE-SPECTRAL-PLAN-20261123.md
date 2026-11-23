# One fixed positive spectral-difference attack baseline

Status: frozen before processing; Codex owns only the new positive_spectral_attack
module, portable runner, tests, spec and matching worker workflow. Claude's
ordinary acoustic suppression analysis remains independent. No native source,
installed tracker or model changes.

The missing capability is a causal distinction between a fresh physical attack
and continuation of a held pitch. The adjacent-onset rule restored lane chatter;
the complex-domain baseline missed initial responses; NINOS2 calibrated on note56
but produced five late extras on note60. This experiment tests a different
descriptor: retain positive log-band changes, with a maximum over neighbouring
past bands to suppress moving partials. A spectral decrease alone contributes
zero. A late harmonic bloom still can contribute: that is the named failure risk.

Source: [Boeck/Widmer DAFx 2013](https://www.cp.jku.at/research/papers/Boeck_Widmer_DAFx_2013.pdf)
and [CPJKU reference](https://github.com/CPJKU/SuperFlux/blob/master/SuperFlux.py).
This is a documented 96 kHz adaptation of the equations, not reference-binary
parity. Fixed 4096-sample symmetric Hann, 480-sample hop (200 fps), normalized
PCM with gain one; no recording normalization. Peak-one triangular bands at
24/octave aligned to A440, 30..17000 Hz with enclosing edges, rounded unique
FFT bins; exclude Nyquist. log10(1+magnitude); two-frame difference; three-band
past maximum; sum positive differences. The first two feature frames are zero.
No phase weighting or learned model.

Peak rule: current equals the maximum of current plus six past frames and is
at least their 21-frame trailing mean plus **1.1** (the upstream default delta).
Zero-padded history; no future. Strictly more than six frames since the last
emitted cue. This uses the paper's last-emitted-event rule, not the reference
program's post-hoc adjacent-detection combining. Availability is the exclusive
hop end, with no backdating or future audio. The 4096/96000 window is about
42.7 ms, near the paper's 2048/44100 duration. No parameter is selected from
these recordings and no threshold sweep is allowed.

One CPU GitHub job, six pinned copies from run 45155740922 (notes56/60,
single/overlap/separated). Reuse the established copy/deadline scorer. Pass only
if every copy has exactly one cue by the saved per-voice first-response deadline,
with no additional cue anywhere. Verify source/archive/member pins, finite
geometry, all samples accounted and feature/event prefix identity. Pure vector
and clock tests run locally and on the worker; all waveform/FFT work is remote.

A failure closes this fixed setting, without tuning or another dispatch. A pass
supports only this global cue on copied controls; actual independent re-plucks,
pitch attribution in chords, detector integration and native timing remain open.
Acoustic re-pluck preservation remains not measured. Keep only the small report
locally; feature evidence stays remote. No promotion or installed score change.
