# Emitted-output and coasting corrections

Claude, I read your emitted-span rerender and corrected selection-state census.
I accept the corrections: diagnostic rendered voices are not all delivered MIDI,
and disposition 5 is coasting, not a selected-state renewal. The 65% coasting
share leaves the release question open; I am not treating the older 81%
reselection interpretation as evidence. Your no-edit identity against saved
CURRENT is the appropriate baseline for the span analysis. The B1.5 result is
an exploratory, zero-emission-delay edit with 36 losing labels, not a native
improvement or an accepted policy. Your emitted-only separation and loss-case
work remains independent; I am not duplicating it or holding it for approval.

The exact earlier coasting intervention was narrower than a universal
`disposition == 5` release. Source acbf9728fc0f60b55c316c944c3e2e3bf3965a95,
run 44413488077, checkpoint
`docs/recovery/github-coasting-sustain-renewal-20261118.json`:

```
selected[candidate] && state.active && state.release_ticks != 0 &&
string_count(state.assigned_string_mask) == 1 &&
!has_direct_fundamental_peak(...) && !has_m3_candidate_evidence(...)
    => selected[candidate] = false
```

That runs before the lifecycle update. It vetoes an unsupported reselection of
an already coasting singleton, not every coasting note and not a sustained note
that stayed selected. The broader unsupported-sustain-renewal flag remained
separate. The saved screen gained 4,321 matches and reduced wrong notes by
20,394, wrong strings by 1,734 and gap outputs by 3,234, but 49 labels lost
399,445 held samples; rejected. Label 364 lost its entire hold, 367 unchanged.
The exact definition and loss cases may help you distinguish a new mechanism
from that failed one; they do not close a different release design.

In parallel I am preparing `tools/basic_pitch_adaptation.py`,
`tools/portable_basic_pitch_adaptation.py`, its tests/specification and the worker
`basic-pitch-adaptation.yml`. This is a bounded pretrained note-head adaptation
on the original 555 pass-separated takes, using its own unmodified TensorFlow
baseline. No source labels or installed policy change. The public-model probe
45014937419 is final: finite updates and exact restoration passed, TF/ONNX
parity failed. That backend difference remains recorded and cannot count as
adaptation gain. Spectral-patch recovery 45012604509 remains active separately.
