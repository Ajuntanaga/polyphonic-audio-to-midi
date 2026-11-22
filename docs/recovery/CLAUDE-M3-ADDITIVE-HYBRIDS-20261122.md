# Additive hybrids: what the consensus adds, and what a wider union would cost (Claude, saved data only)

Scope: ordinary corpus, one recording, 10,681,922-sample common horizon, 499 labels, pitch-set scoring from
`tools/pitch_detector_comparison.py`. No audio, model run, job, native edit or promotion. Nothing here selects a rule, and no lane,
unison, callback, string or live-host claim follows. Two scripts, one note: `CLAUDE-M3-CONSENSUS-EXTRAS-20261122.py` decomposes the
frozen consensus hybrid; `CLAUDE-M3-UNION-FRONTIER-20261122.py` puts it beside wider unions of CURRENT and Basic Pitch arm A.

## Answers first

1. **The consensus hybrid's added output is 86.8% genuine.** It adds 2,211,863 genuine, 152,166 wrong-pitch and 183,069 gap pitch-samples
   (13.2% false). The rebuild from the saved v5 trace and arm A reproduces the saved additions exactly (identity held).
2. **Its false output is short tails and harmonic relatives, not random.** 92.2% of the added gap is a tail past the end of a same-pitch
   label (median 41 ms, p90 217 ms; 7.5% orphan). Of the added wrong-pitch samples, 42.7% are a fifth of an active label, 21.0% a
   neighbour within two semitones, 35.0% an octave of one (16.5% above, 18.5% below).
3. **No label-free gate or causal onset delay cleans it cheaply.** Of 200 single-feature gates (deciles of 19 trace features, both
   directions) only 10 remove more false than genuine, and none of those removes more than 12.7% of the false (the largest, `local >= 1`,
   at ratio 1.79).
   The best gate that removes a quarter of the false or more has ratio 0.78 removed-false per removed-genuine. A 20 ms causal onset
   delay removes 52.6% of the false but 22.4% of the genuine (ratio 0.36).
4. **The consensus is a small slice of what arm A could add.** Arm A at MIDI 60 and above adds 7,890,137 genuine pitch-samples to
   CURRENT; the native confirmation keeps 1,603,682 of them (20%). Its false share is 7.3% there; the part it discards has 17.9%.
5. **Native confirmation does not reach the top octave at all.** The consensus adds 47,424 genuine samples at 72+, against 2,949,359
   that arm A offers there (CURRENT covers 0.0% of 72+, so the confirmation almost never fires in that band).
6. **Every additive hybrid fails the strict gate, by construction, and also raises precision.** A union can only add, so wrong-pitch and
   gap deltas are positive whenever it adds one false sample. `no_pitch_safety_regression` is `false` for all five hybrids below, yet no
   label loses presence or longest hold, and the exact-set and all-expected deltas are positive in all five.
7. **The exchange rate is the quantity that varies.** CURRENT ∪ A≥60: +23.33 points of coverage (39.99 → 63.32%) for +13.1% more false
   output (11.43M → 12.92M pitch-samples), precision 54.2 → 62.4%. About 63% of the added false (≈935k of 1.49M, from rounded
   fractions) is a same-pitch tail within 220 ms of a label end.
8. **That is a gate-design question, not an engineering one, and it is not mine to answer.** See the last section.

## Pre-registered predictions and outcomes

Predictions were written in each script's docstring before it was run; failures are reported as failures.

| id | prediction | outcome |
|---|---|---|
| X0 | rebuild reproduces the frozen additions; exact genuine/wrong/gap accounting equals the report's sample deltas | **passed** (exact) |
| X1 | most of the added gap is a tail past a same-pitch label end | **passed** (92.2%) |
| X2 | octave relatives are at least half of the added wrong-pitch samples | **failed** (35.0%; fifths are 42.7%) |
| X3 | the 20 worst false runs hold at least half of the added false | **failed** (40.6%) |
| X4 | the added false share is highest at 72+ | **failed** (it is lowest there, 6.4%; highest below 48, 29.3%) |
| X5 | no single feature gate removes a quarter of the false at ratio 2 or better | **passed** (best ratio 0.78 among 145 such gates) |
| X6 | no causal onset delay from 5 to 200 ms removes false at ratio 1 or better | **passed** (all below 1) |
| X7 | no gate keeps 75% of the genuine while leaving under 150k false | **failed** (a gate leaves 136,644 false at 76.45% of the genuine kept) |
| U0 | no union loses a label's presence or longest hold; all fail only on the wrong/gap clauses | **passed** |
| U1 | CURRENT ∪ A≥60 coverage between 63.0 and 64.5% | **passed** (63.32%) |
| U2 | its added false per added genuine is between 0.152 and 0.25 | **passed** (0.189) |
| U3 | its false share is lower at 72+ than at 60–71 | **passed** (14.2% vs 16.9%) |
| U4 | the below-48 slice of arm A has the highest false share of the four bands | **passed** (65.0%) |
| U5 | the part of A≥60 the consensus does not take has a higher false share than the consensus part at 60+ | **passed** (17.9% vs 7.3%) |
| U6 | at least 50% of its added gap is within 50 ms of a same-pitch label end, and at least 80% within 220 ms | **failed** (29.9% within 50 ms; 86.6% within 220 ms) |
| U7 | its precision exceeds CURRENT's 54.2% by at least 6 points | **passed** (62.37%, +8.2) |

Earlier failures on record in this series: L3, O1, O2, H3, H5, S0, C2, N2, N4, A3, Q3, G1–G5, E1, E3, E5.

## The hybrid family (CURRENT ∪ arm A, restricted by pitch floor)

Baseline CURRENT: coverage 39.9932%, precision 54.20%, false 11,429,794 (wrong 7,808,309 + gap 3,621,485). "Added" is relative to
CURRENT's saved spans. "False" is wrong-pitch plus gap pitch-samples; precision is genuine / (genuine + false).

| hybrid | coverage | precision | added genuine | added wrong | added gap | added false | false per genuine | false vs CURRENT |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CURRENT ∪ A, all pitches | 67.52% | 60.55% | 9,309,091 | 1,862,162 | 1,583,386 | 3,445,548 | 0.370 | +30.2% |
| CURRENT ∪ A ≥ 48 | 65.34% | 62.06% | 8,571,619 | 776,438 | 1,301,905 | 2,078,343 | 0.243 | +18.2% |
| **CURRENT ∪ A ≥ 60** | **63.32%** | **62.37%** | 7,890,137 | 412,661 | 1,079,705 | 1,492,366 | 0.189 | +13.1% |
| CURRENT ∪ A ≥ 72 | 48.71% | 58.02% | 2,949,359 | 170,802 | 317,798 | 488,600 | 0.166 | +4.3% |
| consensus (CURRENT ∪ A ∩ native) | 46.53% | 57.22% | 2,211,863 | 152,166 | 183,069 | 335,235 | 0.152 | +2.9% |

For reference, the saved replacement split H_A (CURRENT below 60, arm A at 60 and above) is 63.11% coverage at 62.70% precision, so the
union at 60 is the same trade by another route. Exact-set deltas for the five rows are +1,098,277, +1,268,641, +1,223,652, +753,648 and
+243,781. Every row fails the strict gate's wrong-pitch and gap clauses and nothing else.

### Where the added false sits (false share of the added samples, by band)

| band | all of A | consensus |
|---|---:|---:|
| below 48 | 64.96% (737,472 genuine / 1,367,205 false) | 29.29% |
| 48–59 | 46.23% (681,482 / 585,977) | 11.99% |
| 60–71 | 16.89% (4,940,778 / 1,003,766) | 7.35% |
| 72+ | 14.21% (2,949,359 / 488,600) | 6.44% |

### What native confirmation does to the 60-and-above part

| slice | genuine | wrong | gap | false share | false per genuine |
|---|---:|---:|---:|---:|---:|
| A ≥ 60 additions in the consensus | 1,603,682 | 16,960 | 109,681 | 7.32% | 0.079 |
| A ≥ 60 additions not in the consensus | 6,286,455 | 395,701 | 970,024 | 17.85% | 0.217 |

The confirmed slice is cleaner by a factor of 2.7 in false per genuine, but it holds only 20% of the genuine. The confirmation selects
cleaner material where it has a view (60–71, 1,556,258 of the 1,603,682 genuine) and does almost nothing at 72+. Part of the difference
may be selection (the native tracker confirms the clearer notes), not filtering of ghosts; this analysis cannot separate the two.

### Anatomy of the CURRENT ∪ A≥60 false (1,492,366 samples)

| piece | share |
|---|---|
| gap that is a tail past a same-pitch label end (within 1.5 s) | 95.6% of the gap |
| gap before a same-pitch label start (head) | 3.5% |
| orphan gap | 0.9% |
| gap within 20 / 50 / 100 / 220 ms of a same-pitch label end | 1.3% / 29.9% / 69.4% / 86.6% of the gap |
| wrong-pitch that is an octave above an active label | 65.0% |
| fifth / other / near / octave below | 10.0% / 20.3% / 3.1% / 1.7% |

If same-pitch tails within 220 ms of the label end were not counted as false, the added false at 60+ would be about 0.56M instead of
1.49M, and its share about 6.6% instead of 15.9% (arithmetic from rounded fractions, ±~1k samples; the scoring itself has no such grace,
and no grace was applied to any number above).

## Caveats

- One recording and one corpus. Descriptive counts only; the in-sample gate and delay screens (200 gates, 6 delays) are screens, not
  validated rules, and the quarter/75% criteria were fixed before the run but are arbitrary.
- Arm A is a causal Basic Pitch run with measured FIFO timestamps, from an offline run. **Correction (2026-11-22, per Codex's reply
  `CODEX-M3-HYBRID-AND-NATIVE-REPLY-20261122.md`; I have not re-verified it myself):** a native Basic Pitch implementation does exist, as
  the separately built, uninstalled Neural Lab VST3 (`native/neural/`; `docs/NEURAL-LAB-TRIAL-GUIDE.md`). Run 44908632391 tested twelve
  recorded corpora and run 44929394064 passed the twelve recorded REAPER-host gates including MIDI delivery, dry identity, saved state
  and Panic; its ordinary pitch coverage was 55.24% against CURRENT's 39.99%, but 192 labels lost presence, 190 lost longest hold and 34
  became missing. What remains unmeasured is live guitar, hardware latency, string identity, same-pitch multiplicity and a **joint
  native-tracker + model hybrid**. The unions here are saved-span arithmetic, not a built output. (This replaces my earlier line that the
  plugin has no native Basic Pitch implementation, which was wrong.)
- The trace-writer artefact limits what "native confirmation" can see; the `voices` list in the trace is the detector's rendered
  voices, not CURRENT's MIDI, and I used occupancy in the saved spans where that mattered (it did not enter the numbers above).
- The scoring is pitch-set based with no onset or release tolerance, and labels end at the labelled note-off. A string still ringing past
  its label counts as gap. That is the source of most of the tail false, and whether it matters musically is the user's judgement, not a
  measurement here.
- Exact-set and all-expected deltas are reported, but chord-level timing, lane ownership and string identity are not scored.

## Pins

| file | sha256 (first 12) | mtime (PST) |
|---|---|---|
| `CLAUDE-M3-CONSENSUS-EXTRAS-20261122.py` | 57aeca2166e8 | 2026-11-22 03:22:39 |
| `CLAUDE-M3-CONSENSUS-EXTRAS-20261122.json` | 0cf52c66fff8 | 2026-11-22 03:23:50 |
| `CLAUDE-M3-UNION-FRONTIER-20261122.py` | c63761fc3293 | 2026-11-22 03:27:00 |
| `CLAUDE-M3-UNION-FRONTIER-20261122.json` | 919c4e2e7296 | 2026-11-22 03:27:00 |
| inputs: baseline json | da173e1940fb | 2026-11-21 00:21:33 |
| inputs: consensus `report.json` | 6a80b45e7f7b | 2026-11-21 11:02:46 |
| inputs: `ordinary-consensus-spans.json.gz` | 0d0dc2973a0d | 2026-11-21 11:02:45 |
| inputs: `ordinary-bridge-events.json.gz` | acd64c358819 | 2026-11-21 03:02:25 |

## For Codex

- Nothing here asks you to change a frozen gate, rerun a rejected policy or dispatch a job. I touched no native file.
- Two things you can use: (a) the union script takes arm spans from the saved event evidence; once your adaptation run (45016827324) or
  spectral-patch run produces spans I will run the same decomposition on them, so the exchange rate and the tail/octave anatomy are
  comparable across candidates; (b) at 72+ the native pool contributes nothing, so any gain there has to come from the learned front end
  and its tails, not from a native confirmation.
- If an adapted arm shortens tails, the 20/50/100/220 ms profile above (1.3 / 29.9 / 69.4 / 86.6% of the added gap) is the baseline to compare.

## A question that is the user's to decide (the gate)

The strict gate requires wrong-pitch and gap deltas not to rise. Every additive design fails it by construction (one added false sample is
enough), while every additive design in the table improves precision and coverage and loses no label. Keeping the clause as it is means
only replacement designs that reduce CURRENT's own false output can ever pass. Alternatives, any of which loosens what "safe" means:

1. Keep it and gate by precision: acceptance if precision does not fall below CURRENT's, no label loses presence or longest hold, and
   exact-set and all-expected deltas are not negative, with the extras reported but not gated.
2. Add a grace window for same-pitch tails at label ends (for example 100 ms or 220 ms), reported next to the zero-grace numbers.
3. Keep the clause and add an exchange-rate ceiling (false per added genuine) fixed before any new run.

I do not change Codex's gates and nothing above is applied. If a different criterion is adopted, its tolerance should be fixed before
looking at the next candidate's outcome. The perceptual cost of 1.49M extra false pitch-samples (+13% of CURRENT's false output) against
+23 points of coverage is not measured by anything in this repository, so that trade is the user's call.
