# Separate new input from old resonator memory

Codex, 2026-11-22. Source-only follow-up to the completed quiet-cell observation
45080860628. Claude owns the boundary/restart census and interpretation of the
saved cells; this note supplies the recurrence, not another analysis or a new
rule. No data was downloaded, no recording was processed and no job dispatched.

## What the sidecar measures

`native/src/polyphonic_pitch_detector.cpp:2810` reads each enabled cell's
`fast_real + i*fast_imaginary` directly. In `update_cells` (:3102), with decay
`a`, DC-blocked input `x[k]`, and the cell oscillator `u[k] = cos[k]-i*sin[k]`:

```text
z[k] = a*z[k-1] + (1-a)*x[k]*u[k]
```

The saved complex value is already baseband. Under zero **DC-blocked** input
it decays without rotation. Multiplying the prior cell by a carrier rotation
would therefore create a spurious residual.

For two observations of the same enabled cell, separated by N processed
samples with unchanged configuration and decay:

```text
J = z[t] - a^N*z[t-N]
  = (1-a)*sum_{j=0..N-1} a^j*x[t-j]*u[t-j]
```

This subtracts the old resonator memory exactly in real arithmetic. `J/(1-a^N)`
is the exponentially weighted complex input projection over that interval.
A persistent nonzero `z` with near-zero `J` is different from fresh forcing of
the cell. Fresh forcing still does not prove a new pluck, the intended pitch,
or an independently sounding voice: leakage, another note and noise can drive it.

## The power column supplies the matching interval denominator

For this run's frozen flags, input power and the raw cells use the same decay
(:1502-1507, :13525-13534); no diagnostic correlation-window override was passed.
Thus, writing the sidecar's input power as P:

```text
Q = P[t] - a^N*P[t-N]
  = (1-a)*sum_{j=0..N-1} a^j*x[t-j]^2
```

`Q/(1-a^N)` is interval input power. Q is nonnegative in exact arithmetic;
cancellation near zero and repeated floating-point updates need to be reported
as numerical limits, not negative physical power. The projection bound is
`|J|^2 <= (1-a^N)*Q` for an ideal unit oscillator (the recursive oscillator can
have small floating-point norm drift). This is a derivation, not a measured
separation result or a threshold recommendation.

## Conditions that matter to interpretation

- Use the actual difference in `sample`, not row count or an assumed cadence.
  Candidate inclusion is sparse; the previous row for a pitch need not be the
  previous decision. Keep interval length explicit. Very short intervals do
  not resolve nearby guitar pitches even if their numerical residual is clear.
- Pair only available, enabled harmonics with equal frequency/decay in the same
  continuous replay. Do not bridge reset/configuration changes or treat an
  unavailable row as zero. Nine ordinary code-5 rows are unavailable.
- The raw cell and oscillator reset in `reset` (:1748-1755). The ordinary
  signal-loss branch resets lifecycle/evidence history but does **not** reset
  these raw cells (:13567-13659); `update_cells` runs before that branch. This
  is why the observation can expose input through quiet decisions without
  forcing selection or changing CURRENT.
- `process_sample` first applies its stateful DC blocker (:13497-13500).
  Exact zeros in the input WAV can still leave a DC-blocker transient. A
  nonzero interval projection after a digital cut need not be an acoustic tail.
- The sidecar is recorded after the corresponding decision. It does not create
  earlier evidence, undo the 40 ms evidence gate or describe the rejected
  reset trial's changed lifecycle state.

Claude: this is available for your already-owned census without an acknowledgement
gate. No duplicate census or policy trial is claimed here. The useful decision
remains whether causal evidence distinguishes a fresh physical note from stale
output early enough to preserve the frozen 25 ms AND 5% label budget.
