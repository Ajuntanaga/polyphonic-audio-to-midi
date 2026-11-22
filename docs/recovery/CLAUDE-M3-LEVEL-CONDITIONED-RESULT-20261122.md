# Result: quiet-end loss is detect-then-drop for the adapted model; the 166 loss is not at label ends

Claude, 2026-11-22. Scores `CLAUDE-M3-LEVEL-CONDITIONED-PREREGISTRATION-20261122.md` (Parts A and B) and `CLAUDE-M3-LEVEL-CONDITIONED-PARTC-PREREGISTRATION-20261122.md` (Part C). Saved tapes only: no new job, no audio, no policy, no promotion, no gate change. Everything below is frame-level posterior (>= 0.3 at the label pitch), not decoder events.

## Answer

1. **My prediction about the shorter lookahead held (A1, A2 pass).** Removing 23.22 ms of right context changes label-end presence in the silent-after subset by -0.60 pp (199 to 197 of 334; 9 ends lost, 7 gained) and in the other 94 ends by -5.32 pp. So the 166 contrast is **not** an end-of-note effect. Where it does lose frames is the onset and the body of the label (section "Where the 166 contrast loses frames", post hoc): -17.5 pp in the first 50 ms, about -6 pp across the body, -2.75 pp in the last 50 ms.
2. **For the adapted model, quiet label ends are mostly notes that were detected and then dropped, not notes that were never detected.** 367 of 428 ends are detected 150 to 197 ms before the end; 266 of those are still present at the end. Among the 60 early-detected ends below -60 dB, 20% are present at the end (B4 pass). The level effect survives conditioning on early detection (AUC 0.845 to 0.817; B1 pass, B3 miss). My expectation that quiet ends were mostly never detected (B2) was wrong for the adapted model: 40% were not early-detected, against 77% for the unmodified model.
3. **For the unmodified model the picture is the opposite**: 174 of 428 ends are never early-detected, and quiet ends are mostly that (B2 pass, 77%).
4. **Absolute and relative level cannot be separated on this corpus** (C3 miss: Spearman -0.66 adapted, -0.63 unmodified). Corpus notes barely decay: the median whole-note drop is 5.7 dB. C1 and C2 are therefore not evaluable and I do not claim either reading.

## Scorecard against what I registered

| Id | Claim | Odds | Result | Verdict |
|---|---|---:|---|---|
| A1 | silent-after presence changes by at most 3 pp (166 vs 164, adapted) | 65% | -0.60 pp | **pass** |
| A2 | other-subset absolute change exceeds the silent-after change | (part of the 65%) | 5.32 pp vs 0.60 pp | **pass** |
| B1 | AUC of level among early-detected >= 0.65 | 60% | 0.817 (bootstrap 95% 0.766 to 0.862), 266 present / 101 absent | **pass** |
| B2 | >= 70% of ends below -60 dB not early-detected | 65% | 40% of 100 (unmodified: 77%) | **miss** |
| B3 | conditioning lowers the AUC by >= 0.05 | 50% | 0.845 to 0.817 = 0.028 (unmodified: 0.072) | **miss** (adapted) |
| B4 | <= half of early-detected sub -60 dB ends are present | 55% | 20% of 60 (unmodified: 4.3% of 23) | **pass** |
| C3 | |Spearman(pre, drop)| <= 0.6 | 70% | -0.664 (unmodified -0.627) | **miss** |
| C1, C2 | relative / absolute level beyond the other | 50% / 60% | not evaluable because C3 missed (descriptive: C1-stratum AUC 0.599, C2-stratum AUC 0.813) | **not evaluable** |

Three of my four Part B odds were above 50% and one of those (B2) missed; B3 at 50% missed too. I had expected conditioning on early detection to remove a bigger share of the level effect than it did; it removed 3 points of AUC on the adapted model.

## Part A detail (adapted, `control164` vs `candidate166`, 428 ordinary ends)

| Subset | n | present at end, 164 | present at end, 166 | change | lost / gained |
|---|---:|---:|---:|---:|---:|
| all | 428 | 62.15% | 60.51% | -1.64 pp | 15 / 8 |
| silent-after (80 ms of exact silence after the end) | 334 | 59.58% | 58.98% | -0.60 pp | 9 / 7 |
| other | 94 | 71.28% | 65.96% | -5.32 pp | 6 / 1 |

By pitch band (silent / other): 0-48: +1.94 / 0.00 pp; 48-60: -2.88 / -6.67; 60-72: -1.15 / **-16.67 (n = 18, 3 lost)**; 72-100: 0.00 / 0.00. The only visible end effect sits in 18 contested ends in the 60-71 band; with 3 ends it is a lead, not a finding.

## Part B detail (early detection = mean posterior over frames g-17..g-13 >= 0.3)

Presence at the end by level of the 80 ms before the end (`pre`), adapted model:

| `pre` (dB) | n | early-detected | present at end, all | present at end, given early |
|---|---:|---:|---:|---:|
| below -70 | 29 | 8 | 0.0% | 0.0% |
| -70 to -60 | 71 | 52 | 16.9% | 23.1% |
| -60 to -50 | 56 | 49 | 60.7% | 69.4% |
| -50 to -40 | 144 | 131 | 70.1% | 77.1% |
| above -40 | 128 | 127 | 93.0% | 93.7% |

None of the 61 adapted ends that were not early-detected is present at the end. Unmodified model: -70 to -60 dB is 1.4% present (21 of 71 early-detected); above -40 dB it is 48.4% present, 62.9% given early. In the uncontested stratum (n = 67, 60 early-detected) the adapted AUC is 0.919 unconditioned and 0.913 conditioned; the unmodified one drops 0.882 to 0.759.

## Part C and the whole-note drop (post hoc, no bar)

Part C could not separate absolute from relative level (C3). The post hoc whole-note drop (level just after the onset, [S+20 ms, S+100 ms), minus `pre`) shows why: median 5.7 dB, 10th to 90th percentile 2.1 to 10.9 dB, only 4.9% of adapted early-detected notes drop 12 dB or more. Notes in this corpus are about as loud at their end as just after their onset, within a few dB, so a note that is quiet at its end was quiet at its start.

Adapted, early-detected, present at the end by `pre` and whole-note drop (cells under 10 ends are noisy):

| `pre` | drop < 6 dB | 6 to 12 dB | 12 dB or more |
|---|---|---|---|
| below -60 dB | 12.5% (n = 8) | 26.8% (n = 41) | 0.0% (n = 11) |
| -60 to -50 | 85.7% (7) | 72.2% (36) | 33.3% (6) |
| -50 to -40 | 79.7% (64) | 74.2% (66) | 100% (1) |
| above -40 | 94.9% (117) | 80.0% (10) | none |

Within a level band, a bigger drop goes with somewhat lower presence in most cells, but the differences are small next to the level effect and the cells are small. I do not read a mechanism from this table.

## Where the 166 contrast loses frames (post hoc, `control164` vs `candidate166`, 428 labels)

Frame-level presence at the label pitch, by position inside the label (frames can fall into more than one bin for short labels):

| Position | frames | 164 | 166 | change |
|---|---:|---:|---:|---:|
| whole label | 25,805 | 81.62% | 74.46% | -7.16 pp |
| first 0-50 ms | 1,828 | 56.78% | 39.28% | **-17.51 pp** |
| 50-100 ms | 1,858 | 80.25% | 69.91% | -10.33 pp |
| 100-200 ms | 3,680 | 86.25% | 80.08% | -6.17 pp |
| 200-400 ms | 7,278 | 86.47% | 80.37% | -6.10 pp |
| middle (beyond 400 ms and the last 200 ms) | 4,411 | 85.51% | 79.48% | -6.03 pp |
| last 100-200 ms | 3,685 | 84.45% | 76.93% | -7.52 pp |
| last 50-100 ms | 1,838 | 81.23% | 74.37% | -6.86 pp |
| last 0-50 ms | 1,857 | 64.08% | 61.34% | **-2.75 pp** |

The shorter lookahead costs the most at the first 100 ms of a note and about 6 pp everywhere else; the last 50 ms, where right context is silence, costs the least. This frame-weighted whole-label change (-7.16 pp) is not Codex's whole-label figure (-4.6 pp, label-weighted present samples, FIFO decoder path): different quantity, same direction.

## What this bears on, and what it does not

- **Release-context adaptation fit (Codex's run 45037966575, not mine to rerun).** The adapted model already holds quiet notes through detection and then lets go at about -60 to -70 dB (20% present at the end when quiet and detected earlier). A release-context fit aimed at those ends has something to reach, which the unmodified model's never-detected quiet notes would not have. When that result is read, splitting its end-presence gain by the `pre` bands above (below -60, -60 to -50, -50 to -40, above -40) would show whether the gain lands where the loss is. I propose that split; I do not set a gate.
- **The 166/167 contrast** should be diagnosed at onsets and across the label body, not at ends. That is what the position table says; it is not a statement about the quality screen, which stays rejected on Codex's frozen gate.
- **Not supported by this data:** any claim that the lever is absolute or relative level (C3 miss), any decoder-level claim (tape posterior only), any claim about other recordings.

## Pins and integrity

- `CLAUDE-M3-AUDIO-RELEASE-ENDS-20261122.json` sha256 `3465031b7b6c90da94d658c933116b161550e87648330d70fc8d412b96df3784`; curves file `CLAUDE-M3-AUDIO-RELEASE-CURVES-20261122.json.gz` sha256 `0e8a80aa51ae07a6...` (file in the repo).
- Tapes: unmodified `085d0b9dc284a38863f775f841e9eb8324448541b931ffac3f22652743617ea6`; adapted `cb24925d06ec9700c9aee81f247135d2450afc9669b2275064158eba2dcf4bea`; `candidate166` `d23914d816a5c1352a8ecdb352ae86c2878eb6bf75b8b08a335b0727db0013b1` (matches the `bulk` entry of run 45036257574's report). Evidence artifact 14759539384, downloaded read-only, zip sha256 `daee380c2c5d9ffacd8cfbef2805102eca10df75eea0d31215071ab9b813d881` equal to the artifact digest.
- Integrity checks registered in Part A all passed: `c0a` frame clock on all three tapes (`frames[:,0] == arange`, `frames[:,1] == 256 * frames[:,0]`); the control tapes reproduce all 428 saved groups (0 mismatches); 0 ends excluded for short or unmapped spans.
- Scripts: `CLAUDE-M3-LEVEL-CONDITIONED-20261122.py` (registered scorer, Parts A/B/C), `CLAUDE-M3-LEVEL-CONDITIONED-POSTHOC-20261122.py` and `CLAUDE-M3-LOOKAHEAD-LOSS-POSITION-20261122.py` (post hoc). Result files: `CLAUDE-M3-LEVEL-CONDITIONED-RESULT-20261122.json` (sha256 `4636dc47...`), `...-POSTHOC-RESULT-20261122.json` (`cbcc4a15...`), `CLAUDE-M3-LOOKAHEAD-LOSS-POSITION-RESULT-20261122.json` (`e486b912...`). Bootstrap: 2000 resamples over ends, seed 20261122.

## Limits

One recording; ends within a take are not independent, so every interval is narrower than the real uncertainty (no bootstrap over takes is possible from these files). Presence at the end is a 3-frame mean of a posterior, not a decoder event; the decoder's hold and onset logic can still change which ends count. "Early detected" uses the decoder's frame threshold but no onset logic. `pre` is a spectral level at the pitch's first harmonics and includes other pitches' harmonics where the end is contested. The sub -60 dB cells hold 60 ends and the 60-71 band `other` cell holds 18. The position table covers the 428 labels of the ends file, which is the evaluable subset of the ordinary corpus, not every label.

## Reproduce

```bash
python3 docs/recovery/CLAUDE-M3-LEVEL-CONDITIONED-20261122.py \
  docs/recovery/CLAUDE-M3-AUDIO-RELEASE-ENDS-20261122.json \
  docs/recovery/CLAUDE-M3-AUDIO-RELEASE-CURVES-20261122.json.gz \
  UNMODIFIED_TAPE_DIR ADAPTED_TAPE_DIR CANDIDATE166_TAPE_DIR OUT.json
```

Tape directories are the unzipped `ordinary-stream.npz` directories of the control tapes of run 45029161409 and of the `candidate166` evidence of run 45036257574. The post hoc scripts take the usage lines in their headers.
