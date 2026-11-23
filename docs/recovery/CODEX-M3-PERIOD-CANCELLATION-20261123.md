# Period cancellation: one bounded mechanism spike

Codex owns the new `tools/period_cancellation.py`,
`tools/portable_period_cancellation.py`, their pure contract test, the matching
JSON specification, and worker `period-cancellation.yml`. Claude's ordinary
attack-zone investigation stays independent. No acknowledgement is a gate.

## Question and fixed experiment

Can subtracting a delayed copy of a strong periodic source expose a quieter
upper pitch, without raising responses to the same pitch when its component is
removed? This is a mechanism screen, not a detector, MIDI or live-use screen.

Use the existing pinned source manifest and input releases. Generate exactly
1,024 mixtures in each existing pass role with the existing seeds, crops,
normalization and component gains. Anchor every source in its role; retain all
555 intended labels, including previously questioned ones. The train role is
descriptive only. No learned model or audio transfer to the laptop.

For every distinct intended pitch in a mixture, make a matched negative by
removing ALL components of that pitch. No additional normalization is applied
after removal. Same-pitch unisons count as one pitch. Exact component sums and
filter linearity must agree within 1e-12. Silence rows remain in the inventory.

Three fixed arms:

- RAW: unchanged waveform.
- MIXTURE_PERIOD (primary): `y[n] = x[n] - x[n-T]`, with linear interpolation at
  fractional delay T. Estimate T from the mixture only: a 4,096-sample YIN
  difference window, MIDI 32..84 lag range, first local trough below 0.1 or the
  global minimum if none, parabolic interpolation. No annotation or component
  information enters this arm. Re-estimate from each matched negative too.
- COMPONENT_PERIOD (diagnostic): the same filter, but estimate T from the
  loudest exact component, chosen by its final 8,192-sample power. This is an
  oracle source-isolation aid, not an implementable parent-selection result.

Score every intended query pitch on the last 8,192 past samples. Score is the
sum of six Hann-window partial peak powers weighted by 1/h, divided by waveform
power (floor 1e-12). Partial peaks use a fixed seven-point +/-35-cent grid and a
32,768-point zero-padded FFT. The same readout is used in all arms. It is not the
native detector and does not inherit its thresholds or acceptance claims.

Each arm gets ONE scalar cutoff from all of its calibration matched negatives:
the lowest nonnegative cutoff with at most floor(1% * N) false responses, ties
handled conservatively. No positive or test value chooses the cutoff. Apply it
unchanged to train and test. Keep calibration thresholds and all query rows.

Primary subset: intended MIDI >=60 whose strongest own component has at most
-12 dB RMS relative to the loudest component in the final readout window.
Strong notes, lower notes, harmonic-related targets, unisons and all other
queries remain reported. They are not silently excluded from totals. Interval
strata use {12,19,24,28,31,36}; no stratum picks a setting.

## Frozen decision

Continue to a separately designed raw-plus-residual tracker only if all hold
for MIXTURE_PERIOD on the test role:

1. All integrity checks pass and at least 100 primary positive queries exist.
2. Primary found count improves by at least 5 percentage points over RAW.
3. False-response counts do not rise either over ALL matched negatives or over
   primary matched negatives; no silence response appears.
4. In the primary subset the median exact-component target/interference power
   improvement is >=3 dB and at least 75% of targets retain >=-6 dB power.

Report COMPONENT_PERIOD under the same calculation, separately. Its pass alone
does not pass the primary screen or authorize integration. A failed fixed arm
is closed: no cutoff adjustment, alternative delay/window, corpus exclusion,
second dispatch or full replay just to rescue it. A harness failure before
measurement is recorded distinctly.

## Interpretation and limits

The filter removes the strong source too. It cannot replace the entire tracker
and is not scored as such. A successful spike would justify a joint raw and
residual design, which must then pass the existing cross-corpus label, false
output, hold, allocation and deadline gates. Installed defaults and scoreboard
remain unchanged. No latency or CPU improvement is claimed here; all readout
samples are past-only, but Python cost is only diagnostic worker cost.

These pass roles have been used in earlier development; the test is source-pass
separated within this experiment, not fresh external validation. Intended pitch
is not guaranteed audible. Finite-window pitch drift, fractional-delay error
and shared harmonics can defeat cancellation. Component-period and component
power accounting are oracle diagnostics. Matched negatives are synthetic
counterfactuals, not a substitute for physical negative corpora or live audio.

Primary sources: de Cheveigne (2021),
https://journals.sagepub.com/doi/10.1177/23312165211041422 ; de Cheveigne and
Baskind (2003), https://www.ee.columbia.edu/~dpwe/papers/deChevB03-muptrack.pdf .
This is distinct from the repository's existing stationary sinusoidal Gram
solver and per-cell detuning correction: it cancels periodic structure directly
in the waveform rather than estimating partial ownership from resonator cells.

## Execution pin

The worker pins the source commit as a literal and rejects a different dispatch
input before checkout or dependency installation. The run checkpoint records
that source commit, the separate worker commit, and the specification hash.
The runner also checks the checked-out HEAD against the dispatch input and
records both revisions in the report. This avoids a self-referential source
commit inside a specification committed in that same source revision.

Local verification: all 13 pure synthetic/accounting tests pass. One independent
read-only review found no blocking arithmetic, counterfactual, calibration or
dependency defect; its source-pin concern is addressed by the worker pin.
