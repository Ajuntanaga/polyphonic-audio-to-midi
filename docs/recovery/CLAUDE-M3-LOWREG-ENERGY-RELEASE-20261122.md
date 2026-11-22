# CLAUDE-M3-LOWREG-ENERGY-RELEASE-20261122: a voice's own energy decay separates tails well, but no single feature removes more than about 5% of the false output at near-zero label loss

Claude to Codex, 2026-11-22. Follow-up to `CLAUDE-M3-LOWREG-TAIL-STATE-20261122`. Same saved trace (run 44835727027, ordinary corpus, CURRENT ON, block 512, v5): no audio, no model run, no job, no native edit, nothing promoted, installed scoreboard unchanged. Tick-level bounds, not native results; one corpus only.

## 1. Answer first

1. **The voice's fundamental energy relative to its own running peak (`R = fund_energy / peak since the voice appeared`) separates lower-band tail ticks from true ticks better than I predicted.** On selected ticks, `R < 0.1` flags 41% of tail ticks and 2.5% of true ticks; where a direct fundamental peak exists (the part the unsupported-run rule cannot reach) it flags 22% against 1.5%.
2. **That does not turn into a safe release.** Per label, the true output a release on `R` destroys is spread over many labels. The safest grid point, `R < 0.05` for 100 ms, removes about 0.56M false samples (4.9% of CURRENT's 11.43M) and cuts two labels by 50 ms and 13 ms; `R < 0.1` for 50 ms removes about 1.5M (13%) and cuts 14 labels (924 ms in total). None reaches zero label loss, so none passes the strict gate on this corpus.
3. **The exchange is far better than the tail clip's, but still an exchange.** At about 3.2M to 3.7M lower-band false samples removed, the tail clip with a 100 ms grace costs 10.2 s of true output over 38 labels (3.3:1, scored on spans); R1 at 50 ms costs 1.3 s over 8 labels and `R < 0.1` for one tick costs 4.1 s over 68 labels (voice-tick estimates, 9:1 to 30:1). At the conservative end removed-per-true-lost is 17:1 to 93:1. The two units differ (scored span samples versus voice-ticks times 64), so read the factor as large, not as exact. The project's gate allows no exchange; whether a 17:1 or 47:1 trade is acceptable is the author's call, and this corpus cannot choose a threshold.
4. **No single voice-state feature I have found removes more than about 5% of CURRENT's false output at near-zero label loss on this recording.** The part that remains is tail ticks where the string is still ringing at more than 10% of its own peak after the label has ended; no release rule on the voice's own state can clip those without cutting true notes.

## 2. Energy-decay separation (pre-registered E1 to E3)

Selected lower-band ticks only, `energy_observed == 1`. Flag = feature below threshold. `W` = `fund_energy` over its maximum in the previous 150 ms.

| feature | selected tail, direct peak present | selected true, direct peak present | selected tail, all | selected true, all |
|---|---:|---:|---:|---:|
| R < 0.5 | 0.701 | 0.433 | 0.814 | 0.449 |
| R < 0.25 | 0.458 | 0.135 | 0.626 | 0.153 |
| R < 0.1 | 0.223 | 0.015 | 0.410 | 0.025 |
| R < 0.05 | 0.106 | 0.003 | 0.285 | 0.008 |
| W < 0.5 | 0.475 | 0.171 | 0.631 | 0.196 |
| W < 0.25 | 0.237 | 0.014 | 0.354 | 0.030 |
| W < 0.1 | 0.054 | 0.001 | 0.149 | 0.005 |
| W < 0.05 | 0.026 | 0.000 | 0.086 | 0.002 |

Selected tail ticks with a direct peak: 36,993 (all with energy observed); selected true ticks with a direct peak: 209,317.

| | prediction | measured | verdict |
|---|---|---|---|
| E1 | at least 90% of selected tail ticks with a direct peak have energy observed | 100% | passed |
| E2 | W < 0.25 flags at least 20% of those tail ticks and at most 5% of true ones | 23.7% vs 1.4% | passed |
| E3 | no R threshold on the grid has TPR at least 30% with FPR at most 10% (direct-peak ticks) | `R < 0.1`: 22.3% / 1.5%; `R < 0.25`: 45.8% / 13.5% | passed on the grid only: the grid has a hole between 0.1 and 0.25, and the curve shows R separates well, so my reasoning that natural decay confounds R was wrong |

## 3. Energy-release bound (pre-registered X1 to X5)

Rule E(thr, T): suppress a lower-band voice once it has had T consecutive ticks with `energy_observed == 1` and `R < thr` (selected or not); it returns when `R >= thr`, energy is unobserved, or the voice disappears. The running peak resets only when the voice is absent (no re-onset reset, which can only make this rule release earlier, so true loss is an upper bound on that account). "approx false removed" is (tail + other suppressed ticks) times 64 samples, voice-ticks not pitch-samples, against CURRENT's 11.43M false (all bands).

| rule | tail suppressed | approx false removed | true lost (ms) | labels with loss (over 100 ms) | removed per true lost |
|---|---:|---:|---:|---:|---:|
| E(0.05, 100 ms) | 6.1% | 0.56M (4.9%) | 63 | 2 (0) | 93.5 |
| E(0.05, 50 ms) | 9.2% | 0.87M (7.6%) | 193 | 6 (0) | 47.1 |
| E(0.1, 100 ms) | 10.0% | 1.05M (9.2%) | 403 | 6 (2) | 27.1 |
| E(0.1, 50 ms) | 15.1% | 1.53M (13.4%) | 924 | 14 (3) | 17.3 |
| E(0.05, 1 tick) | 25.1% | 2.55M (22.3%) | 1,379 | 42 (5) | 19.3 |
| E(0.1, 1 tick) | 35.4% | 3.67M (32.1%) | 4,085 | 68 (12) | 9.4 |
| E(0.25, 100 ms) | 19.4% | 2.04M (17.9%) | 5,356 | 45 (21) | 4.0 |
| E(0.25, 50 ms) | 26.6% | 2.78M (24.3%) | 8,383 | 58 (36) | 3.5 |
| E(0.25, 1 tick) | 53.1% | 5.82M (50.9%) | 23,681 | 139 (85) | 2.6 |
| R1: selected, direct == 0, 50 ms (earlier bound) | 26.7% | 3.73M (32.6%) | 1,299 | 8 (4) | 29.9 |
| U: R1(50 ms) or E(0.1, 50 ms) | 31.0% | 4.16M (36.4%) | 2,177 | 17 (7) | 19.9 |

| | prediction | measured | verdict |
|---|---|---|---|
| X1 | E(0.1, 50 ms) suppresses at least 20% of tail ticks | 15.1% | **failed** |
| X2 | E(0.1, 50 ms) loses at least 1 label but fewer than R1(50 ms) (8) | 14 labels | **failed** (more labels than R1) |
| X3 | E(0.05, 100 ms) loses at most 5 labels | 2 | passed |
| X4 | at every grid point with true loss, (tail + other) per true tick at least 10 | 2.6 to 93.5 (the E(0.25, *) points and E(0.1, 1 tick) at 9.4 miss it) | **failed** |
| X5 | the union suppresses at least 5 points more tail than the larger of its two parts | +4.3 points (31.0% vs 26.7%) | **failed** (narrowly) |

Worst labels at the conservative end: E(0.05, 100 ms) cuts label 82 (MIDI 51) by 50 ms of 733 and label 472 (MIDI 53) by 13 ms of 603.

## 4. Reading

- A release keyed on the voice's own fundamental decay is a genuine signal (E2), and a far better exchange than clipping on Arm A's note-offs.
- It still cuts true notes near their own end, because a labelled note also decays; across 260 labels that spreads a few percent of true ticks over many labels, so the label-level gate fails even where the tick-level rates look excellent (2.5% FPR at `R < 0.1` became 14 labels at 50 ms).
- The union does not add much (+4.3 points of tail), so the unsupported-run and energy-decay rules overlap on the same tail ticks.
- **The tails that survive every rule here are ringing strings:** direct peak present and energy still above 10% of the voice's own peak after the label has ended. Clipping them means guessing the note-off, which no feature of the voice's own state does without cutting true notes. This is a limit of voice-state rules on this recording, not of every possible rule.

## 5. Caveats

- One recording and one corpus; any threshold picked from this table is tuned on its own evidence. The saved trace is ordinary / CURRENT ON only; there is no extended-middle trace, so no held-out check exists until a native job produces one.
- Counts are voice-ticks at decision-tick resolution (64 samples at 96 kHz), not scored pitch-samples; a replay on a trace cannot reproduce how a real release changes later state or whether the candidate is re-selected on the next tick.
- The `other` class (voice sounding, no same-pitch label within 1.5 s) is counted as false output removed; I have not analysed what it is. It is 97,485 voice-ticks, 44% of the lower-band false voice-ticks, and the unsupported-run rule suppresses 15% to 26% of it.
- Not claimed: a lane, unison-multiplicity, callback-deadline or live-host claim; a note-level score; that any rule passes the project's gate on a held-out corpus.

## 6. What this changes

- A native release-hold trial would, at best on this evidence, remove about 5% of the false output at the cost of one or two short label cuts (E(0.05, 100 ms) or the R2 variant), or 10% to 13% at 6 to 14 label cuts. That is a small lever, and I do not think it justifies a GitHub job on its own. I am not starting one on this evidence.
- The larger unexplained mass is the `other` class and the ringing tails. The next saved-trace step is the anatomy of `other`: what pitch relation its ticks have to the labels sounding at that moment (octave and harmonic ghosts, near-semitone neighbours, or unrelated), because that decides whether the lower-band overhang is a release problem at all.

## 7. Pins and timing

| item | sha256 (first 12) | mtime (PST, 2026-11-22) |
|---|---|---|
| energy-decay script / result | 5da992208715 / e7614de47b5d | 02:32:33 / 02:32:49 |
| energy-release script / result | a595db5d8ce3 / 4ef4b5856336 | 02:33:36 / 02:33:54 |

Run each as `python3 -P -E <script> TRACE.tsv.gz` with the saved ordinary v5 outcome trace of run 44835727027. Both import the tail-state script, which imports the activation-fate script (published in `b229213`). The docstrings give no clock time on purpose; the predictions were written before each run.

## 8. Coordination

My files here are `CLAUDE-M3-LOWREG-ENERGY-*` only. No native edit, no claim on `native/src/polyphonic_pitch_detector.cpp`, and no job started or planned from this evidence.
