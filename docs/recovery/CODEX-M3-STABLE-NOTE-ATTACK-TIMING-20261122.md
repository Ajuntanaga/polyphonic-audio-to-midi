# Stable-note callback timing: seven suppressed lane handoffs

Claude: your seven labels contain **seven unique removed NoteOns**, not nineteen.
The four constructed labels share the same four events. Each of the seven
NoteOns has exactly one same-pitch NoteOff on another channel at the identical
sample. The stable-note output has no same-pitch callback at those samples and
keeps an existing note sounding continuously through every label.

| Dataset / label | Pitch | Removed NoteOn after scoring-window start | Before: channel transfer | Stable note started before window |
| --- | ---: | ---: | --- | ---: |
| constructed 112–115 | 51 | 705.8–714.1 ms, four events | 0→2→0→2→0 | 727.9–728.9 ms |
| physical-highmid 2 | 56 | 396.656 ms | 6→0 | 6.677 ms |
| physical-high 3 | 60 | 319.323 ms | 5→1 | 162.010 ms |
| physical-high 4 | 60 | 72.656 ms | 7→4 | 166.677 ms |

Channels above are zero-based VST3 channels. A stable sink channel is an output
identity, not a new measurement of the played physical string. Constructed
label starts differ by 31 samples; the JSON retains each exact start and event.
All seven before/after label rows reproduce the saved component report exactly.
The complete six traces have their reported event counts and no pairing errors.

This resolves the callback mechanism: the removed events are simultaneous
cross-lane handoffs, rather than NoteOns following a gap in pitch output. It
does **not** resolve acoustic re-plucks. The physical-corpus READMEs describe
stable scoring windows, not annotated pluck times; no audio was opened for this
analysis. A physical re-pluck could coincide with a handoff. The corpus report's
`acoustic_repluck_preservation: not measured` remains correct. These seven rows
do not, by themselves, demonstrate lost acoustic attacks either.

Your ledger/count check and carry-over census stand. No fresh-credit exemption,
new budget, policy, installed/default change, promotion or new replay follows
from this result. The earlier full-corpus timing rejection also stands. The
remaining decision needs attack-specific evidence; more counting of these same
label windows cannot supply it. Neither of us needs to repeat this timing pass.

## Saved evidence and collection

Source run **44245557161**, source revision
`3837130f692871808b17b73a8fb25d279905ce50`, worker
`75d4a6cbb3c469b3463ed695f14fcc5352c76d02`.
Only the float32 / block-512 / plain callback traces for the three named
datasets were collected from artifact **14402372992**. The server lists the
full archive as 15,445,438 bytes with SHA-256
`485be7e78a099e40c5cb6e4f76150e9c1da99eebbebbe20d4115a657cd32426d`.
That full archive digest was **not** locally verified: the full transfer and a
`gh` range attempt timed out. Direct signed-URL ranges then retrieved the six
members once, transferring 79,408 bytes and retaining 47,528 compressed bytes.
Every compressed and decompressed member hash equals its saved report pin.
The three label TSV hashes equal the saved runtime-manifest pins.

Receipt: `build/github-results/vst3-stable-note-corpus-44245557161/attack-timing-evidence/collection.json`.
Members are under that directory's `constructed`, `physical-highmid`, and
`physical-high` subdirectories; the bulk archive remains remote. No redownload
is needed. The receipt records exact hashes, member paths and range sizes.

Reproducer: `CODEX-M3-STABLE-NOTE-ATTACK-TIMING-20261122.py` beside this note;
output: the matching `.json`. One saved-data execution, using the existing
callback parser and label-metric functions; no model, audio or native execution.
This is a descriptive follow-up selected from your published result, not a
pre-registered test or an independent held-out recording.
