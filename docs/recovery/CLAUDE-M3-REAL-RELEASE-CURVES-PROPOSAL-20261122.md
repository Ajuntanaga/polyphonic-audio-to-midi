# Real-audio release curves: ownership and pre-registration (written before any tape is read)

Claude, 2026-11-22. Nothing below has been run. I have not opened a stream tape from run 45029161409; the only things I know about them are the file names, the array names (`note`, `onset`, `frames`) and the writer code in `tools/portable_basic_pitch_streaming.py` and `tools/basic_pitch_streaming.py`.

## Ownership (so we do not overlap)

- **Mine:** the real-audio release-curve read on the saved ONNX stream tapes of Codex's run 45029161409 (`unmodified_onnx` and `adapted_onnx`, corpora `ordinary` and `extended-middle`). Saved-array arithmetic only: numpy on the downloaded evidence artifact, no model, no audio, no GitHub job, nothing promoted.
- **Codex's (not touched):** the unchanged-model operator profile (run 45032406856), the training/adaptation lane, the graph-optimization investigation, every frozen gate.
- **Not started and not claimed:** the fixed-noise-floor synthetic probe (floor variant). If I later dispatch it I will record ownership and register it before the job.

## Question

The synthetic probe showed the adapted model does not release later than the original on clean tones, but its output is a saturated switch (0.99 against 0.80 at the plateau, then a short fall). On real audio the adapted run keeps notes sounding past label ends far more often (still sounding at gap end 59.2% against 21.5%, earlier saved-data result). This read asks, on the real tapes, where that difference sits: plateau height at the end, the time to release, or the shape of the fall.

## Mapping check (stop rule)

Before any reading: for each arm and corpus,
- C0a: `frames[:,0]` is `0..N-1` contiguous and `frames[:,1] == 256*frames[:,0]`;
- C0b: replaying `ForwardDecoder` (frame threshold 0.3, onset 0.5, attack 3, release 3) over the saved `(note, onset)` rows reproduces every `(kind, note, frame)` triple in that arm's `<corpus>-events.json` exactly (if the events file is absent from the artifact, C0a only, and I say so).
If C0a or C0b fails for any arm or corpus, I report that and stop: no curve is read from a tape whose frame clock I cannot reproduce.

## Definitions (mechanical; the script implements exactly these)

- Frame `g` sits at source time `256*g/22050` s (global frame index; frame 0 at sample 0, from `FIRST_END` and `readout_frames[0]`). Absolute offsets of up to about one frame (11.6 ms) are possible, and cancel in paired adapted-minus-original comparisons.
- Labels and horizon `H` come from the existing `dataset_context` (labels clipped to the common support), as in every earlier analysis. Per MIDI note the labels are merged into union spans (any string). An **end** is a union-span end `E` before `H`. Next start `S` is the next union-span start at that pitch, or `H`. Window end `W = min(S, E + 1000 ms, H)`.
- An end is **evaluable** if its span is at least 100 ms long and `W - E >= 120 ms`.
- `g(E) = floor(E * 22050 / (96000 * 256))`. Plateau `P` = mean of the note probability at the label pitch over frames `g-2..g`. An arm **detects** the end if `P >= 0.3`.
- **Release frame** = first `f` in `[g+1, g(W)-2]` with the note probability below 0.3 on `f, f+1, f+2` (the decoder's own release rule). Delay = `256f/22050 - E/96000` in ms. If there is no such `f` the end is **censored** with bound `>= (256*g(W)/22050 - E/96000)`.
- **Fall time** = release frame minus the first `f >= g+1` with probability below `0.9*P` (frames); defined only when the arm detects the end and both frames exist.
- **Paired** = evaluable ends that both arms detect. Pair counting follows the probe's rule: both uncensored gives a difference; adapted censored with bound at or above the original's delay counts as "adapted later"; original censored with bound at or above the adapted delay counts as "adapted earlier"; otherwise not evaluable. Ties count for neither side.
- **Others sounding at E** = number of union spans at other pitches with `start <= E < end`. Groups: 0, 1 or 2, 3 or more.

## Predictions (registered; judged as registered, misses reported as misses)

- **H1, plateau.** At paired ends the adapted plateau `P` is higher than the original's in at least 70% of non-tied ends, and the median adapted `P` is at least 0.9 while the original's median is at most 0.85. (Synthetic result: 0.99 against 0.80.)
- **H2, hold.** Adapted is later in at least 60% of non-tied evaluable pairs, and the median paired difference over uncensored pairs is at least +23.2 ms (two frames). I expect this to hold on real audio, which is the contrast with the synthetic probe.
- **H3, shape.** The adapted fall time is shorter than the original's in at least 60% of non-tied pairs where both are defined. (Synthetic: 5 to 7 frames against 17 to 21 at tau 0.05.)
- **H4, polyphony.** The median paired hold difference (adapted minus original, uncensored pairs) is at least 20 ms larger for ends with three or more other sounding labels than for ends with none. Not evaluated if either group has fewer than 15 pairs.
- **C1, consistency with the earlier span-based figure.** Among ends with `W - E >= 300 ms`, the censored share is at least 20 percentage points higher for adapted than for original (earlier saved-data figure: 59.2% against 21.5% for gaps of 300 ms or more: 47.8% against 15.2%).
- Verdicts are from `ordinary`. `extended-middle` is a replication read, reported separately and never pooled; it can only confirm or fail to confirm the direction of each hypothesis.

## Reading rules

- H1, H2 and H3 all true: the lengthening on real audio is a level effect, not a slower decay. The adapted output sits near saturation and takes the 0.3 crossing later because it starts higher, and then falls fast. That supports testing the window-floor normalization hypothesis next (floor variant) and says a decay-shaped teacher term would not target the observed difference, while a level or calibration term would. It does not by itself decide the boundary fit.
- H2 true, H1 or H3 false: the hold is a different mechanism from the synthetic switch; I would not extrapolate from the probe at all.
- H2 false: the earlier span-based tail figure comes from something the tapes do not show (note birth in gaps, the decoder, or the event clock), and I re-check that figure before saying anything else about tails.
- H4 true: polyphony at the end explains part of it, which points at competition among sounding pitches rather than a plain per-pitch level effect.

## Caveats stated in advance

- No audio is read, so whether the string was still physically sounding after a label end (post-label audibility, which Codex rightly keeps open) cannot be separated here. A longer hold could be the model being right about the audio. This read characterizes the model output only.
- `ordinary` is one recording; ends inside one take are not independent. Counts are descriptive: I will give exact sign-test p-values but they gate nothing.
- Post hoc readings, if any, are labelled as such.

## Amendment 1 (written before any tape was read; the tapes are still downloading)

I re-read `stream_blocks` and found a contamination I missed in the definitions. A readout at frame 164 of a window ending at `next_end` sits `1860` model samples (84.4 ms) before the window's last sample, so the output at a frame's nominal time can already reflect up to about 84 ms of audio after it. A note that starts at the next same-pitch label start `S` can therefore raise the probability at frames up to about 84 ms before `S`, and I would count that as a held tail. Change, applied before any reading:

- Window end becomes `W = min(S - 100 ms, E + 1000 ms, H)` where `S` is a next same-pitch label start. When there is no next start the window end is `min(E + 1000 ms, H)` as before. Everything else in "Definitions" is unchanged, including the evaluable rule `W - E >= 120 ms` (now with the amended `W`), so ends whose next same-pitch note begins within 220 ms are not evaluable.
- The plateau is kept as registered (frames `g-2..g`). The same lookahead means those frames see up to 84 ms past the end, so I will also print an **early plateau** (frames `g-10..g-8`, which see audio only up to about the end). It is labelled post hoc and gates nothing.
- C1 uses the amended window: "ends with `W - E >= 300 ms`".
