# Ordinary stable-note attack observation — frozen before audio

Codex takes execution of this unfinished observation on 2026-11-23. The
existing Claude desktop session reports idle, no ordinary58 result or run is
recorded, and the worker queue contains no active job. This is coordination,
not a pause or an approval gate for Claude. Files owned for this observation:
`tools/portable_ordinary_attack_envelope.py`, its metadata-contract tests,
`ordinary-attack-envelope-20261123.json`, and the new worker workflow
`m3-ordinary-attack-envelope.yml`. Claude's seven-event workflow stays intact.

## Question and fixed inputs

Do the 58 ordinary-recording NoteOns suppressed by stable-note identity near
annotated same-pitch starts show an acoustic rise, compared with the 262 such
NoteOns retained by that path? These controls are retained events, **not**
verified acoustic attacks. The ordinary recording is constructed stress audio,
not an independent free-playing validation set.

Use ledger run 44079653692, the original corpus-20261108 ordinary recording and
labels, and the exact hashes in the adjacent JSON. Before opening audio,
reproduce 11,851 source events, 8,623 callbacks, 1,614 reciprocal suppressed
Off/On pairs, 499 labels, and 320 unique NoteOns in the inclusive same-pitch
window [label start -25 ms, label start +100 ms]: 58 suppressed, 262 retained.
Count an event once even when several labels refer to it. Retain every event
and all referring labels.

## Measurement fixed in advance

Reuse Claude's seven-event method exactly: an event-centred excerpt extending
2 s before and 1 s after (clipped only at recording edges), fourth-order
Butterworth bandpass at 0.96..1.04 times the nominal equal-tempered frequency,
forward/backward filtering, Hilbert amplitude, and a 5 ms moving average.
Report envelope at -50, 0, +50 and +300 ms; largest 20 ms rise whose starting
sample is within +/-40 ms of the event on the excerpt's 5 ms grid; and the
largest rise over the excerpt with its midpoint offset. Floor only ratio
division at 1e-12, exactly as in Claude's workflow. Edge-unavailable samples
are null, never copied from another time. No input gain change.

Additional descriptive context, without changing that measurement: envelope
level in dB relative to full scale, raw excerpt RMS, annotation onset offsets,
and other annotated pitches whose harmonics 1..6 enter the nominal band during
the local rise window [-40,+60 ms]. Same-pitch concurrent annotations are
reported separately. This flags possible overlap; annotations cannot prove
absence of an unlabelled contaminant. Store 5 ms envelope curves remotely.

The compact report includes all 320 event rows and separate suppressed/retained
distributions (minimum, P10, median, P90, maximum), plus counts in the fixed
descriptive rise bins <=1, (1,2), >=2. Summaries also separate annotated overlap
from no annotated overlap. Bins are descriptions, **not** an acoustic detector
or acceptance threshold. No significance or independent-sample claim: events
can share a note, passage, excerpt and annotation.

## Reading rule and limits

An identity failure stops interpretation. A suppressed event with a local rise
is a counterexample to the blanket statement that all removed ordinary events
occur on a flat/decaying nominal envelope; it requires contextual interpretation.
No rise, weak level or annotation overlap is not proof that a real re-pluck was
preserved. Compare controls before claiming the method can see attacks at these
pitches. A full comparison completes this observation even if it is inconclusive.

Filtering is noncausal and especially broad in time at bass pitches. Exact
annotated starts are not acoustic attack truth. Neither this observation nor
the earlier seven-event result establishes `acoustic_repluck_preservation`;
that field remains `not measured`. No relabelling, exclusions, policy, threshold
tuning, replay, promotion, installed changes, or scoreboard changes follow.

One CPU GitHub job, under the existing standing authorization. Record source
and worker SHAs, job ID and collection receipt. Download only the compact report
locally; keep audio and envelope curves on the worker/remote artifact. No local
audio access or execution. No duplicate dispatch or automatic rerun.
