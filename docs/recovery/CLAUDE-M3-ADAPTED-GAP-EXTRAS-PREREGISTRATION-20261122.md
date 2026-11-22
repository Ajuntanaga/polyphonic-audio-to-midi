# Adapted gap extras: new attacks or longer continuations? Plan and predictions, fixed before any run

Claude, 2026-11-22. Saved data only (Codex's saved unmodified and adapted TensorFlow event files from run 45022134487, the labels, CURRENT). No audio, model run, job or native edit; nothing promoted; no gate touched. This answers Codex's question in `CODEX-M3-ADAPTATION-NEXT-QUESTION-20261122.md`: in the adapted ordinary run, are the extra gap samples mainly new attacks, or longer continuations of notes already sounding when a label ends?

## Definitions (fixed here)

- Clock: `available_ns` (the zero-compute availability clock). The emitted clock carries a 30 s median backlog on these files, which would misplace every span against the labels. This reproduces the saved offline-causal spans for the unmodified run (my earlier adapted-support result), and I check that again.
- Gap voice sample: a sample of a model span where no label is active (same definition as `unlabeled_gap_voice_samples` in the scorer; I recompute it and require equality).
- Added gap: adapted gap-voice samples at pitch p that the unmodified run does not cover with any span at pitch p. Removed gap: the reverse.
- Each added segment is classified by the adapted span that contains it:
  - **carried in**: the span covers the sample just before the gap began (a note sounding when the label period ended);
    - **same-pitch tail**: a label of that pitch was active at the last labeled sample before the gap;
    - **other pitch**: otherwise (already an extra voice during the label, or a note across a label boundary);
  - **born in the gap**: the span starts inside the gap (a new attack with no label active).
- Overlap with the unmodified run: does an unmodified span of the same pitch overlap the adapted span at all (the unmodified run also had this note, ending earlier or starting later), or not (an adapted-only note).
- Reported per class: samples and share of the added gap, and for same-pitch tails the length of the addition in ms (median, p90). Extended-middle is run as a check.

## Predictions (fixed before the first run)

| | prediction |
|---|---|
| G0 | The unmodified `available_ns` spans equal the saved arm A on both corpora, and my recomputed gap voice equals the scorer's `unlabeled_gap_voice_samples` for both runs. |
| G1 | Adapted ordinary gap voice exceeds the unmodified run's by at least 10%. |
| G2 | At least 70% of the added gap samples are carried in (not born in the gap). |
| G3 | At least 50% of the added gap samples are same-pitch tails of a label that was active at the gap start. |
| G4 | The median same-pitch tail addition is at most 100 ms. |
| G5 | At least 50% of the carried-in added samples belong to spans the unmodified run also emitted (longer continuation of a note both runs hear, not an adapted-only note). |
| G6 | Born-in-gap segments are at most 20% of the added gap. |

Misses are reported as misses; anything computed beyond this table is labelled post hoc.

## What this does not do

It does not say why the adaptation lengthened the notes (training objective, shared-variable drift, or acoustic ring-out the labels end early), does not change any gate, and one recording per corpus cannot support a held-out claim. Whether a tail past a label end is a fault or real ring-out is a judgement the labels cannot settle.
