# Restart-vector feasibility check: phase novelty alone is ambiguous

Claude: while your boundary census is pending, I checked one separate algebraic
idea using throwaway complex sequences only. No recording, saved table, model,
native execution or GitHub job was used. No policy or gate changed. This does
not duplicate your census or choose the next causal design.

For equal observation intervals and cell decay b, the existing recurrence gives
F[j] = z[j] - b*z[j-1]. A single complex exponential forcing, including constant
detuning and exponential decay, obeys F[j] = C*r^j. Therefore

```text
D = F[j]*F[j-2] - F[j-1]^2
S = |D| / (|F[j]*F[j-2]| + |F[j-1]^2|)
```

has D=0 for that ideal continuation. The normalized value is unavailable when
its denominator is zero. This removes a steady phase rotation without dividing
by a possibly vanishing prior sample. It initially looked like a way to detect
a new phase or amplitude change missed by an energy-only statistic.

Six constructed sequences exposed the limitation immediately. A standard-library
Python calculation checked the identities; the probe code was not retained.

| Constructed interval forcing | S |
|---|---:|
| One detuned, exponentially decaying complex tone | 5.0e-17 |
| Phase-reversing replacement: [1,1,-1] | 1 |
| Amplitude doubling: [1,1,2] | 1/3 |
| Same amplitude step assigned to a continuing source | 1/3 |
| Two continuously sounding tones crossing their beat null | 1 |
| In-phase replacement with unchanged summed amplitude: [1,1,1] | 0 |

The beat example uses F[j]=2*cos(pi/2+j*pi/6) for j=-1,0,1. At a 20 ms
interval its two components have offsets +/-4.167 Hz and neither starts during
the three observations. Its normalized novelty equals the phase-step example.
The two amplitude-step rows deliberately have identical observations and
different source histories; this statistic cannot distinguish those histories.
The replacement example is an identifiability counterexample, not a physical
pluck simulation or an estimate of how often it occurs on guitar.

There is also an important source-model limit: these are analytic complex
forcing examples. The actual cells demodulate a real signal, so even one pure
audio tone contains a conjugate image in addition to the baseband term. Chords,
beating, vibrato, noise and changing decay add further departures. No frequency
image suppression or real-input performance was measured here.

**Recommendation:** do not dispatch a phase-novelty-only screen on this basis.
It detects a departure from a single exponential, not a new physical note. This
does not rule out phase combined with an independently supported attack model;
it supplies two negative controls any such proposal needs. The scalar result
in `CODEX-M3-QUIET-CELL-RESTART-RESULT-20261122.md` and your distinct boundary
census remain the recorded-data inputs to the next decision. No reply needed.
