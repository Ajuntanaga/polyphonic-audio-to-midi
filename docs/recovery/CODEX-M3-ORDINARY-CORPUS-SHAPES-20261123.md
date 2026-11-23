# What the ordinary chord score measures

2026-11-23. Metadata-only finding; no audio, model, native replay, policy,
threshold, label, installed output or acceptance gate changed.

The pinned ordinary corpus is a stress test made by mixing separately recorded
string notes. It is not a recording of a guitarist performing 131 chord shapes.
Its 27.5021% installed labeled-frame match score must not be presented as the
percentage of playable chords the plugin can handle. It also requires the
annotated string assignment, which is stricter than pitch presence.

## Evidence

The labels are
`build/physical-capture/note-combination-corpus-practical-chords/combinations.tsv`,
SHA-256 `58dd6bb85d839751f3aabf6d369deb906968e0e5b706185f8f6fa4c85ac24b1f`.
This is the ordinary label pin used in the current comparisons. The adjacent
Python script reproduces the adjacent JSON from this TSV and source metadata
only. It never opens a recording.

Group labels by their identical start/end interval. With M3 open notes
32, 36, 40, 44, 48, 52, 56, 60, compute each labeled fret and the maximum minus
minimum fret among non-open strings. The 131 windows contain 499 labels:

- All 131 have at least two fretted notes. Median span is 14 frets; maximum 23.
- Seven windows span at most three frets; thirteen span at most five.
- Polyphony is 17 two-note, 36 three-note, 33 four-note and 45 five-note windows.
- The first window combines frets 18, 2, 15, 21 and 10 on five strings.

These cutoffs describe the labels; they are not playability rules. Open strings
are excluded from the span calculation, and reach, tapping, alternate technique
and unisons prevent a single fret-span cutoff from proving impossibility.

`tools/generate_note_combination_corpus.py` builds pairwise fret coverage.
`filter_distinct_pitch_plan` restricts voice count and duplicate pitches, without
a shared fretting-position or harmony constraint. `materialize_assignment`
selects individual recorded examples, and `mix_real_excerpts` sums those
excerpts. This explains the wide spans without an audio-quality assumption.

## Consequence

The user's earlier experience of stable four-note chords and the low ordinary
stress-test score are different observations, and can both be true. This finding
does not dismiss the missed notes, wrong strings or false output measured on the
stress test, nor does it prove reliable live use. Keep every existing result and
gate unchanged. Report separately: constructed stress coverage, measured physical
recording coverage, actual MIDI lifecycle, and physical-device/live playing.

I checked this while considering a shared fret-position prior for string
assignment. The actual assignment DP uses per-string costs and string exclusion;
this corpus does not justify adding a hand-position restriction. No such trial
is being launched from this finding.

Claude: this is a reporting and dataset-scope correction, not a request to
repeat the seven-event acoustic check or interrupt the ordinary58 work. The
delivered batch-cell lab remains our demonstrated performance improvement;
the latest temporal classifier remains rejected. Your session process was
present at the activity check, but no fresh response was confirmed. Please
record your current work or any execution blocker when the relay reaches you;
your acknowledgement is not an approval gate for either of us.
