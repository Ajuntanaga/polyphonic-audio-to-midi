# Claude: saved-report assessment of streaming run 44889388628 — 2026-11-21

Source: only the collected `report.json` (SHA-256 `a56b822b…ebec32`, verified) plus the saved offline reference and the saved CURRENT baseline, all per-label tables with the same fields (present, longest hold, segments, first-present delay). Scripts and outputs: `CLAUDE-M3-STREAMING-ASSESSMENT-20261121.py/.json` (part 1) and `…-PART2-20261121.py/.json` (part 2); both predeclared in the docstring, each run once. No audio, no model, no download, no dispatch. The zero-compute result is used as a diagnostic only. All 499 labels and 6 labels are kept.

Cross-checks against your summary all match: 226 gain / 197 lose / 76 unchanged, gross 9,201,236 gained and 4,143,292 lost, 34 labels to zero, 195 longest-hold declines, 55.8064% zero-compute coverage, gap extras 3,341,707 vs 3,568,575. The per-label present sums equal the distinct-pitch totals exactly (S 18,583,289, O 22,831,126, C 13,525,345), so label sums do not double count in this corpus. The identity A = D + P + G (annotated = first-presence delay + present + non-present after first presence) holds on every label (0 violations), so everything below is exact arithmetic, not a fit.

## 1. Streaming vs the offline model: it is a late-onset result, not a dropout result

379 of 499 labels lose present time against offline (380 lose the longest hold), 28 gain (552,774 samples), 92 unchanged. Gross loss 4,800,611 label-samples.

| Class (labels losing vs offline) | Labels | Lost samples | Share of gross |
| --- | ---: | ---: | ---: |
| Complete dropout (offline present, streaming zero) | 18 | 596,155 | 12.4% |
| Fragmented (more pieces than offline) | 41 | 822,391 | 17.1% |
| Shorter, same or fewer pieces | 320 | 3,382,065 | 70.5% |

The 18 dropouts are not notes shorter than the lag: offline presence on them is 139–643 ms (median 302 ms), none at or under 95 ms (context budget plus median compute), and all 18 are also absent under the zero-compute clock. By band (below 48 / 48–59 / 60–71 / 72+): 6 / 10 / 2 / 0.

For the 361 labels present in both, the loss splits exactly into an onset-delay term and a non-present-after-onset term: **4,193,124 of 4,204,456 samples (99.7%) is the onset-delay term**; the after-onset term nets to +11,332. Its two parts cancel: the 320 single-piece losers end *later* than offline (−341,921), the 41 fragmented ones add 353,253 of internal gaps. The single-piece labels do not lose their tails; they lose their first ~120 ms.

- First-present shift streaming − offline, all 370 labels present in both: median +106.6 ms, quartiles +86 / +145 ms, 5–95%: +66 / +212 ms. Only 14 labels are at or before offline; 1 is within 35 ms; 143 are 35–100 ms later; 212 are more than 100 ms later.
- The shift explains the coverage gap by arithmetic: mean shift 119.8 ms on a mean label of 706 ms predicts 17.0% of present time lost; observed sum(Ps)/sum(Po) on the same labels is 18.8% lost.
- Scheduling is a thin slice: S − Z first-present delay is 11.03–11.24 ms (IQR), equal to the median inference-block service time. The compute-free shift versus offline is still a median 96.5 ms (8.3 model frames; quartiles 74.6 / 134.3 ms). That agrees with your reading that removing service delay alone cannot restore the offline number; it adds that what is left is overwhelmingly time shift, not missing content.
- What the shift is made of is only partly identifiable from the tables. Only 35% of labels sit inside [72.7 ms, 84.35 ms + 2 frames] (the context budgets plus two frames of attack rule); 21% are below the minimum context budget and 43% are above it. First-present delay is label-relative and offline places onsets by backward traversal and Melodia, so context lag, the forward attack rule and offline's own onset placement are mixed. A same-clock comparison is needed (section 5).

## 2. Streaming vs CURRENT: what the 197 losses and 34 zeros are

| Class (labels losing vs CURRENT) | Labels | Lost samples | Share of gross | Also lose longest hold |
| --- | ---: | ---: | ---: | ---: |
| Complete dropout | 34 | 1,893,433 | 45.7% | 34 |
| Fragmented | 24 | 645,689 | 15.6% | 24 |
| Shorter | 139 | 1,604,170 | 38.7% | 136 |

Of the 163 labels present in both, the onset-delay term is 59.7% of their loss (1,342,901 of 2,249,859) and the after-onset term 40.3%.

The 34 dropouts are the largest single block, and they are not a latency artefact: CURRENT holds them for a median 658 ms of a median 748 ms label, neither the zero-compute replay nor the offline model rescues them (offline is zero on 22; on the other 12 it is present for longer than any lag budget, and still below CURRENT), and 33 of the 34 are below MIDI 60 (18 below 48, 15 at 48–59).

Mutually exclusive attribution of the 4,143,292 gross loss (sums checked):

| Part | Samples | Share | Labels |
| --- | ---: | ---: | ---: |
| Model-level: offline Basic Pitch is itself below CURRENT on the label | 2,236,095 | 54.0% | 96 |
| Streaming-added on those same labels (offline minus streaming) | 1,180,216 | 28.5% | 96 |
| Streaming-only: offline is at or above CURRENT, streaming falls below | 726,981 | 17.5% | 101 |

Streaming accounts for 1,907,197 (46.0%) of the loss; more than half would remain even for a perfect causal copy of the offline model, which is why the offline run itself failed the clause on 99 labels. By band (model-level / streaming-added / streaming-only): below 48: 1.214M / 0.731M / 0.389M; 48–59: 0.975M / 0.443M / 0.327M; 60–71: 47k / 6k / 11k; 72+: none.

## 3. Fragmentation is a two-piece split in the bass

41 labels have more pieces than offline (offline has exactly one piece on every present label, 388 of 388). Median 2 pieces, 95th percentile 3, maximum 4. 21 of the 41 are below MIDI 48, and every below-48 label with more pieces than offline is among the losers; 11 are at 60–71. Mean pieces per present label: streaming 1.15 (below 48: 1.28), CURRENT 1.39 (below 48: 1.72), so streaming is not more chopped than CURRENT, only more than a Melodia-merged offline result. Their loss is 57% onset (469,138) and 43% gap (353,253).

## 4. Extended-middle: the five failures are all onset-time

Five of six labels lose 17.3 to 34.7 ms of a 3,600 ms note against CURRENT (0.48–0.96% of the label), and **each loss equals S first-present − C first-present to within rounding** (label 0: 34.74 vs 34.74 ms; 1: 17.30 vs 17.30; 2: 21.07 vs 21.07; 3: 19.76 vs 19.76; 5: 21.09 vs 21.09). Streaming first presence is 65–81 ms, CURRENT 47–57 ms; both then hold to the end of the label. The sixth label gains 218 ms because CURRENT splits that note in two. On this set the frozen per-label clause is a 17–35 ms onset-latency comparison against CURRENT. I am not proposing to relax it; I am recording that it measures latency here.

## 5. The one follow-up I recommend: decoder swap on the saved activation tape

The tables fix how the loss is distributed (late onset: dominant; two-piece fragments in the bass; 18 content dropouts; 34 CURRENT-held bass labels no model recovers) but cannot say whether the 18 dropouts and 41 splits are readout or decoder, nor split the ~96 ms compute-free shift between context lag and the forward attack rule. One experiment separates all three using only evidence the completed job already produced: `ordinary-stream.npz` (6,040,965 bytes, SHA-256 `c363e954…c840c548e`). I have not opened it. I assume (from your prototype note, "every consumed activation pair") that it holds note and onset activations for the 9,584 consumed frames, which are contiguous. No model call, no audio, no parameter change, no dispatch; the decoding is NumPy on a 9,584 × 88 array, seconds of CPU.

Decode the *same* tape three ways with fixed, already-frozen definitions, and score each with the frozen label metrics (present, longest hold, segments, first-present delay):

1. **D0, frozen forward decoder.** Must reproduce the 1,192 events and the S per-label table exactly (18,583,289 present). If it does not, stop: the tape is not the decoder's input.
2. **D1, no decoder.** Pitch present on frame f when note activation ≥ 0.3 (the existing frame threshold). No onset rule, no three-frame attack, no release hysteresis. Gives the readout view.
3. **D2, upstream decoder on the tape.** The pinned upstream `note_creation` defaults (onset 0.5, frame 0.3, 127.7 ms minimum, Melodia, inferred onsets) on the same frame sequence. Lookahead is allowed because this is a diagnostic ceiling, not a streaming candidate.

Score D0 and D1 on two clocks: emission (the primary clock) and each frame's own nominal source position (diagnostic, not a latency claim). D2 only on the nominal clock.

Then the three terms are read off one table: lag = D0 nominal minus D0 emission (clock only); decoder = D2 minus D0 on the nominal clock (and D1 as the decoder-free bound); readout = offline Basic Pitch minus D2 on the nominal clock (both use the upstream decoder, so the remaining difference is the causal resampler, the 73–84 ms context and per-window normalisation). Add per-class diagnostics for the 18 dropouts and 41 splits: peak note activation inside the label, and for splits the depth and length (frames) of the sub-0.3 dip. A dropout whose peak never reaches 0.3 is readout; one that reappears in D1 is the attack rule. A split whose dip is a few frames just under 0.3 is the single-threshold on/off rule; one that is deep is readout.

Reading rules I would fix now so the numbers cannot choose them: if D2 nominal is within a few points of offline's 67.5%, readout is adequate and the remaining work is a causal decoder plus a latency budget; if D2 stays near streaming's 55% and the 18 dropouts persist in D1, the loss is readout and the context/normalisation design is what to change. I would not pre-set the cut points beyond saying they are the table's to show, since three-way arithmetic here is exact and does not need a threshold.

I can write D1 and D2 and the scoring join as my own `CLAUDE-*` script as soon as the tape is on disk, as an independent check on yours. I have not downloaded anything; collecting the 6 MB artifact is yours.

## 6. Smaller requests

- Add two columns to the saved per-label reports from fields you already compute: onset-delay term (Ds − Dx) and after-onset term (Gs − Gx), with G = A − D − P. They are an exact identity of existing fields (no fitted timing offset), and they would have turned this analysis into a lookup.
- One orthogonal candidate, flagged as untested and not requested: the user's own framing is "each tuner locks to the string or pitch range it is set to". CURRENT is ahead of the causal Basic Pitch below MIDI 60 on aggregate (70.0% vs 52.5% below 48, 63.9% vs 52.9% at 48–59) and the causal Basic Pitch recovers 60+ (5.8% / 0% → 58.0% / 58.0%). A pitch-range partition, CURRENT below 60 and the causal Basic Pitch at 60+, would lose no label below 60 by construction; its present-time ceiling from the saved tables is 21,341,759 / 33,819,101 = 63.1% (CURRENT 6,690,873 + 6,292,681 below 60; streaming 5,408,846 + 2,949,359 above), against 40.0% now. That is coverage only. Whether it passes the false-output gates depends on how each detector's extras split by pitch band, which the saved report does not give (extras are aggregate). The 166 KB `ordinary-events.json` plus the saved v5 table would answer it without a model. I would rather do that after the decoder swap, and it also needs your decision on whether a pitch-range arbiter is in scope.

## 7. Limits

First-present delay is label-relative: a note carried over from a preceding same-pitch label reads as an early or zero delay (this can account for part of the 21% below the minimum context budget and for the negative shifts). The ordinary labels are nearly uniform (about 747.5 ms for most), so the length-quartile split I predeclared in part 2 collapses and says nothing; I report it only as a null. Everything is one corpus, one run and offline replay of the causal path; nothing here concerns string identity, unisons, bends, re-plucks, native timing or the host. If any figure disagrees with the JSON, the JSON wins.
