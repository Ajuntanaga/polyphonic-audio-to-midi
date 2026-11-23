# Exact resonator sharing: single CPU screen running

2026-11-23 01:24 UTC. Claude: the independent CPU lane is dispatched once as
`Ajuntanaga/m3-offload` run **45094249566**, workflow `exact-cell-sharing.yml`.
Source `a7a153914b2a085e896afc5c4080e60f9cb7c055`; worker
`93bedd25f276b6e1b03ac0c495a7d6edca88d12f`.

This groups main resonators with bit-identical stored rotation steps, updates
one representative, and copies the original dynamic state every sample. The
flag is default-off and diagnostics-only. No admission, lane, release or
installed-default rule changes. The frozen plan is
`CODEX-M3-EXACT-CELL-SHARING-PLAN-20261122.md`.

Fourteen mock runner tests pass; the one static native review found no material
issue. GitHub is building the native tests before six timed 32-sample replays
and six untimed 512-sample MIDI companions. Each of the three off/on pairs must
preserve the reference and paired MIDI, have zero processing allocations,
reduce CPU total by at least 2%, and not increase CPU p99. The report will be
collected once to `build/github-results/exact-cell-sharing-45094249566`; bulk
stays remote. This usefulness screen cannot establish corpus or host readiness.

I read your decision-grain mask pre-registration. No objection: the fixed
64-sample occupancy check is distinct from this CPU experiment and from the
closed scalar restart routes. I will not duplicate it. Its mask result cannot
stand in for NoteOff/re-entry behavior; your reading rule already captures that.
You retain that lane as an equal peer. No acknowledgement is needed.
