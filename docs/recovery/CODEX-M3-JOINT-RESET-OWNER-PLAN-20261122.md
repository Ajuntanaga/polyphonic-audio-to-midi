# Saved joint-reset owner attribution

Codex owns this bounded analysis of the already rejected run 45075475603.
Claude keeps the separate CURRENT boundary-evidence census. No new processing,
policy, threshold, gate, installed change or rerun is proposed here.

Question: do the five newly wholly pitch-missed ordinary labels follow a
period with no raw MIDI owner, as the last-active-candidate/shared-history
explanation would require? The source path exists; its role in these misses
has not been measured. A continuously emitted other owner can contradict the
simple last-owner explanation. An empty output set is only an opportunity:
suppressed active candidates and signal/floor history are not in this log.

Inputs fixed before collecting the events: the saved report (SHA256
3bedd04bd9b1cccc60faed718fcbdbf15e855d86a8d968b6aeb6fe3237773b8a),
and only the current/trial block-512 raw MIDI members for ordinary and
extended-middle. Evidence artifact 14775825950 is 14,516,243 bytes with digest
89bf2a5ee13e13aef7d890227997bd9ec24a4a1a98a4934a5d72ab76578d10dd.
Collect once, verify its digest and each member against the report, and leave
all other members compressed. No audio or model is opened.

For every label, reconstruct pitch-present time and longest contiguous hold
from the complete raw events and require agreement with the saved report.
Use half-open sample intervals, retain EOF owners to the recording horizon,
and process all events at a sample before measuring duration: a same-sample
lane hand-off cannot create a positive-duration empty interval.

Select labels with CURRENT present time > 0 and trial present time = 0, without
further exclusions (expected ordinary 42,70,200,306,364; extended-middle none).
For each arm and label report the last target-pitch disappearance before its
start, next target appearance, other emitted owners immediately after that
disappearance, and all empty-output intervals from that disappearance through
the label end. If the target has no earlier appearance, use recording start
and mark the anchor unavailable. Also report the owner set at label start,
minimum other-owner count during the label, and total empty duration there.

This is descriptive attribution, not a new acceptance test. The absence of a
rendered-owner gap rules out the simple output-owner route only; it does not
measure candidate activity or identify which NoteOff the diagnostic emitted.
The trial remains rejected whatever this analysis finds. The resulting table
will decide whether a shared-reset fix is supported or whether the next
design must address candidate-specific re-entry instead.
