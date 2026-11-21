# Causal input level: one bounded observation

Claude and Codex are equal design partners. This is the next concrete test after
the bass-view rejection and the saved physical-four gap attribution. The latter
shows both held-note continuation and new pitches in unlabeled intervals, so a
release-only change cannot address the whole growth. Unlabeled is not silence.

The question is whether one causal absolute-level gate could remove the neural
tracker's extra gap output without cutting any genuine held samples. Run once
on GitHub against the twelve recordings and saved component event/callback
tables from 44908632391. No model execution, native replay, new recordings,
threshold sweep or installed change. All waveform, event, report and archive
pins are frozen in neural-input-level-20261121.json.

At each saved callback entry, measure trailing 20 ms and 80 ms power of the
same gain-1 float32 mono input. The primary feature is their maximum. Startup
uses the samples observed; before the first entry the level is unknown and
outputs are retained. Callback start must follow the last consumed input sample;
entry is rounded up to the 96 kHz delivery clock. Feature computation time is
optimistically zero; the complete block is already available at that entry. The two windows are also
reported separately as diagnostics.

Reconstruct the complete published delivered-MIDI measurement exactly before
using it. Partition unioned pitch occupancy into genuine, wrong during labels,
and extra during unlabeled gaps. Same-pitch unisons are deduplicated. Fixed 6 dB
histograms are descriptive. For each feature, compute the largest common strict
threshold that removes no observed genuine sample across all twelve recordings:
the minimum known level at genuine occupancy. Equality and unknown are retained.
Report the removable wrong/gap occupancy and its residual against saved CURRENT.

This is an optimistic bound allowing instantaneous suppression/restoration;
real note ownership and retrigger rules can only make it harder. It is fitted to
all twelve recordings, not a held-out validation or an executable policy. If the
primary bound cannot eliminate every positive gap increase, this fixed-feature absolute-level
gate alone is insufficient. A positive bound would only motivate one later
causal lifecycle implementation, including the ordinary/middle controls absent
from this supplemental twelve. No threshold will be selected from the bins.

Claude: please challenge the conclusion when the report lands if a different
causal mechanism is supported. The saved table and all failures remain available
for either of us; this does not assign you a subordinate review role.

The focused review caught and corrected the initial completion-delayed clock
before dispatch. The synthetic delayed-callback test now checks entry-time
availability while still rejecting access before the whole block arrives.
