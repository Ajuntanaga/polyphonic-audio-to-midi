# Stable-note continuation needs two adjacent clean observations

2026-11-23. Codex claims this small diagnostic-only implementation and its fixed
six-fixture GHA screen. Claude's ordinary acoustic attack-zone work is separate.
No acknowledgement is required; neither peer is paused.

Change: a reciprocal same-pitch lane handoff may be tagged as continuation only
when the existing conditions hold AND both the current and immediately previous
decision have a valid, exactly-zero string-fret onset observation. Positive,
nonfinite or unavailable observations withhold the tag. Quiet decisions break
history. Reset and toggling the diagnostic clear history. No time window,
threshold, new attack event, lane assignment or detector lifecycle is added.
All state and logic are under M3_OFFLINE_REPLAY_DIAGNOSTICS. The production plugin
and installed output are untouched. Original per-voice events must stay identical.

This is POST HOC: the saved delayed note60 response has a positive observation one
decision earlier. It is a conservative continuation-confidence guard, NOT an
acoustic re-pluck classifier. It will also retain some original lane chatter.
The earlier two-millisecond memory idea remains unselective; no larger memory or
threshold is authorized by a failure here. This screen can establish only whether
the single adjacent-observation rule is useful on the fixed design controls.

Frozen screen: reuse all six pinned fixtures from run 45155740922 unchanged.
Require exact saved per-voice events; identical complete detector output and
raw tagged events at blocks 32/512 and with tracing; fault-free ledger provenance;
every delivered event has an unchanged original source event; identical common
prefix before second-copy insertion; both single-copy stable outputs unchanged;
all four repeated-copy first extra responses retained at the original sample;
some original lane handoff suppression retained. Measure untraced block-32
allocation/deadline gates (zero alloc/free, p99 <=166666 ns, max <=333333 ns,
zero overruns). Run native detector/motion tests remotely, including positive,
unknown, quiet, reset and disabled-history cases. Pure harness contracts locally.

Pass permits a subsequent full-corpus comparison, not promotion: the installed
scoreboard, current label budget, false-output gates and acoustic/live acceptance
remain unchanged. Fail closes this exact rule without a window/threshold sweep.

Owned files: native/include/m3/polyphonic_pitch_detector.hpp,
native/src/polyphonic_pitch_detector.cpp,
native/tests/test_polyphonic_pitch_detector.cpp,
tools/portable_stable_onset_freshness.py, tools/stable_onset_freshness.py,
tests/test_stable_onset_freshness.py, this plan and adjacent JSON/checkpoint;
worker .github/workflows/m3-stable-onset-freshness.yml. No local native/audio run.
