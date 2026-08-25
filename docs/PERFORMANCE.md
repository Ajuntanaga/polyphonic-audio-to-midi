# Performance and Detector Tuning Log

This file records only measured changes made while executing the approved test
plan. It is not a claim that the detector is performance-ready.

## Task 4 correctness baseline

| Assertion | Constant | Before | After | Evidence |
| --- | --- | ---: | ---: | --- |
| 4101 | Adjacent-semitone neighbor-ratio score coefficient | 0.30 | 0.08 | At the specified 35 ms slow correlation, `0.30` clamped every G#1 candidate score to zero; the first best-note result was the lower range boundary, MIDI 24. |
| 4102 | Harmonic-mean score coefficient | 0.55 | 0.85 | At 45 ms, the true E2 harmonic mean exceeded the upper-range leakage floor while its minimum-three and neighbor terms did not. |
| 4102 | Minimum-first-three score coefficient | 0.25 | 0.05 | Reduced the short-window bias toward the MIDI 33 subharmonic and high-frequency leakage floor. |
| 4102 | Missing-fundamental-support coefficient | 0.20 | 0.10 | Preserved explicit missing-fundamental support while shifting weight to the term that localized short-window E2. |
| 4102 | Adjacent-semitone neighbor-ratio score coefficient | 0.08 | 0.03 | Prevented adjacent low-frequency leakage from overwhelming the true E2 local maximum. |

The 8 ms/35 ms decay times, eight harmonic weights, and the `0.20` base
threshold remain unchanged.

## Guardrail observation

The combined 44.1/48/96 kHz resonator correctness suite reached its 120-second
wall timeout under the fixed 50%-of-one-CPU cgroup. The runner returned status
124 and left no REAPER process behind. Immediately afterward, the host still
reported about 31.2 GiB available memory, load 2.55, and a 71 C maximum readable
thermal-zone value.

The safety limits were not raised. The expensive resonator suite is now selected
by one visible test slider and run once per disposable launch. Conditioning
checks remain combined because their prior three-rate run completed well inside
the guard.

The first separate 44.1 kHz run also reached the same hard limit while executing
the full 32..84 bank independently for every synthetic case. The tests now keep
the confounding pitch regions required by each assertion instead: 32..60 for
G#1 and missing-fundamental E2, 32..52 for the 45 ms E2 case, 32..72 for detuned
A4, and one active bin plus guard cells for silence/clipping. Production remains
32..84. This cuts test-only cell updates without weakening the named assertions.

The first bounded 48 kHz diagnostic showed MIDI 32 as a true local salience
maximum (`0.403505`, versus `0.355592` and `0.340798` at MIDI 31 and 33), while
the artificial analysis boundary at MIDI 24 scored `0.471040`. The bank now
reserves one semitone below and above the requested output range when capacity
allows and exposes the requested candidate bounds in its fixed header. Selection
ignores these analysis-only guard cells; this keeps a requested boundary note
eligible while giving its salience calculation both neighbors.

## Task 4 final correctness matrix

After trimming the temporary score diagnostics, the final staged source passed
all six bounded cases at 44.1, 48, and 96 kHz in REAPER 7.79: 18 disposable
workspace-5 launches, 18 PASS results, and no failed assertion IDs. Case 4101
ran 19 assertions because it also covers pitch math, conditioning at all three
rates, and analysis-guard metadata. Cases 4102 through 4106 each ran the two
pitch-math assertions plus their selected detector assertion.

The SHA-256 of the lexically ordered `sha256sum` output for the 18 machine-readable
result files is
`fc1b8b40f04aa88066ea67baeec0cba43eef2d97e186797b2947da6dbd53c944`.
The 44.1 kHz case-4101 PASS screenshot is
`build/evidence/task-04-44100-case-4101.png`, SHA-256
`f9d9181172ba9414e88236aed596bad987a36d3222f16844b06f43ed755948f2`.
