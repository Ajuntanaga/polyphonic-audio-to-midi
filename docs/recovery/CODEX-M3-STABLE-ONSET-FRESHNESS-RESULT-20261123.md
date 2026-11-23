# Fixed adjacent-onset continuation guard: rejected

Run [45181144376](https://github.com/Ajuntanaga/m3-offload/actions/runs/45181144376)
completed successfully as a workflow; its scientific verdict is
**REJECTED_FIXED_SCREEN**. The guard restores all four repeated-copy first
responses at their original samples, but reintroduces two Off/On pairs in the
physical-highmid single-copy control and one in physical-high. Both violate
the frozen requirement to preserve the saved single-copy stable output.
The exact rule is closed: no retuning, repeat screen or full-corpus follow-up.
The installed plugin, production defaults and scoreboard are unchanged.

## Behavioral result

All 4/4 repeated first responses are retained. In physical-high/overlap, the
first response moves from the old stable path's 171.323 ms to the per-voice
reference's 47.323 ms after the approximate rise marker, recovering the known
124 ms delay. Single-copy initial responses also retain their original times.
The cost is extra retriggers after those initial responses. Callback counts
include both NoteOn and NoteOff events:

| Fixture | Per-voice reference | Saved stable | Candidate stable |
|---|---:|---:|---:|
| physical-highmid/single | 8 | 2 | 6 |
| physical-highmid/overlap | 154 | 86 | 116 |
| physical-highmid/separated | 16 | 4 | 12 |
| physical-high/single | 10 | 2 | 4 |
| physical-high/overlap | 32 | 14 | 22 |
| physical-high/separated | 20 | 4 | 8 |

The candidate still suppresses 36 reciprocal pairs across six fixtures.
It passes 95/97 gates; the two failed gates are the single-copy saved-stable
identities. That gate ratio is not a project-completion measure. These are
constructed waveform controls; acoustic re-pluck preservation remains
**not measured**. Claude's seven nominal-band acoustic checks support lane
flicker in those seven original windows, not the unmeasured ordinary attacks
or a general re-pluck guarantee.

## Integrity and realtime result

Both native suites and 14 Python contracts pass. Saved per-voice output,
traced/untraced snapshots and MIDI, block-32/512 output, pitch occupancy,
EOF state and ledger provenance checks pass. All six trace-free timing runs
explicitly enable stable identity. Across 81,000 timed blocks: zero processing
allocations/frees and zero deadline overruns; worst p99 65,758 ns and maximum
173,361 ns, inside the 166,666 ns p99 / 333,333 ns maximum gates. One callback
exceeds the half-budget threshold; this does not fail either timing gate.
No live-device or acoustic acceptance follows from these checks.

The earlier run 45179941790 failed only at the trace-only CLI check before a
complete screen. This recovery repairs that offline timing plumbing without
changing the guard, fixtures or acceptance rules. It does not override this
completed behavioral rejection.

## Provenance and next work

Source `d0d5cc5efda659f55b1b60a794a6bc2a0d2873ae`; worker
`8fa28bab7cf2c4063791cc5fb09a55db57b43bff`; frozen spec
`55ab8bc9b6ad2eb3bd7fb37f0ddfb1b07622e66b20099d659d5bf6f9e2b42eaf`.
Report artifact 14821391858, 52,826 bytes, collected once with server digest
verified. Archive SHA-256
`b462d08c12934b6534d8572066a943c24f5568f12224d14ae125fa758d927649`;
report SHA-256
`44ad78cdc8c5e11cb4b2f18cc9eb100d9b1b211cbf56a9d0a87628cda2ff9b0a`.
Receipt and report are under
`build/github-results/stable-onset-timing-recovery-45181144376/`.
Bulk traces and audio remain remote; no further collection is needed for this
verdict.

The immediate problem is selective articulation: the existing onset signal
responds to both a repeated attack and single-note lane flicker. This result
closes the exact one-decision-history rule; it does not establish that every
pitch-specific attack design must fail. The completed batch-cell CPU gains
remain separate. Claude's ordinary acoustic lane remains independently open;
this result does not pause or gate that work.
