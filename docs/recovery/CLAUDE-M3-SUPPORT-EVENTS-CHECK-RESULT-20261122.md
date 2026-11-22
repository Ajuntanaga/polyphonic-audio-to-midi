# Codex's L/E/A screen reproduces exactly; E brings back mostly orphan notes and A takes back almost everything the filter removed: result

Claude, 2026-11-22. Pre-registration: `CLAUDE-M3-SUPPORT-EVENTS-CHECK-PREREGISTRATION-20261122.md` (commit `eb8c167`, before the run). Saved data only (pinned v5 traces, the adapted cropped ONNX events, Codex's saved spans and result); no audio, model run, job or native edit; nothing promoted. The script did not change after the pre-registration commit.

## Answer

**Every number in Codex's frozen L/E/A screen reproduces from my own derivation of the three support arms: support spans, filtered spans, full scorer comparisons, per-label deltas and budget verdicts, on both recordings, equal to the sample.** The class split then says why E and A behave as they do. The false output E brings back over L is 84% orphan notes (173,074 samples for 4,864 present). A takes back 92.5% of everything the filter removed (1,928,065 false samples for 9,096 present), including 95% of the orphan pool and 86% of the tail pool, and ends at CURRENT's precision. Neither added source is a usable cue: before the hold, the extra direct observations (E_add) cover present and false output alike (lift 0.90), and the onset-only source that lets A clear labels 263 and 364 covers 6.6 times more of CURRENT's false output than of its present output (lift 0.15).

## Identity: the screen reproduces

All of the following hold for L, E and A on both recordings (ordinary 499 labels, extended-middle 6 labels):

- Trace audit equal (ordinary 167,025 rows, 1,310,294 candidate rows, 16,108 quiet rows; extended-middle 35,025, 95,436 and 2,555; raw hash and the 64-sample tick grid checked). My L support equals the saved native confirmation.
- My L, E and A support spans equal Codex's saved spans, also span for span without merging (ordinary 4,964, 5,291 and 5,309 spans).
- My filtered spans equal Codex's saved filtered spans (ordinary 521, 530 and 526 runs), also span for span; my L filter equals the committed cropped-adapted filter.
- The full `compare` output, including the five per-label fields Codex records, equals Codex's stored comparison; so do the budget verdicts. Ordinary: L fails labels 263 and 364, E fails 364, A passes; wrong-pitch output removed 22.275%, 20.214% and 1.985%. Extended-middle: all three pass; 25.999%, 25.902% and 0.012%.
- Class volumes equal the scorer's present, extra and gap totals for CURRENT, L, E and A, and the three filtered outputs nest per pitch (L inside E inside A).

The limit is the one I registered: this is a second derivation from the same trace, scorer and plan wording, written after I had read Codex's code. It catches slips and mis-wired inputs, not a misreading we share, and it does not re-test the shared scorer.

## What E and A bring back (ordinary, all pitches, voice samples)

| | False re-admitted | Present | False per present | Orphan | Tail | Head |
|---|---:|---:|---:|---:|---:|---:|
| E over L | 173,074 | 4,864 | 35.6 | 145,560 (84.1%) | 13,305 (7.7%) | 14,209 (8.2%) |
| A over E | 1,754,991 | 4,232 | 414.7 | 1,044,083 (59.5%) | 575,939 (32.8%) | 134,969 (7.7%) |
| A over L | 1,928,065 | 9,096 | 212.0 | 1,189,643 (61.7%) | 589,244 (30.6%) | 149,178 (7.7%) |

Share of the pool L removed from CURRENT (orphan 1,247,630, tail 686,673, head 149,178, between 0) that each arm takes back: E 11.7% of the orphan pool, 1.9% of the tail pool, 9.5% of the head pool; A 95.4%, 85.8% and 100%. Precision (present over present plus false): CURRENT 54.20%, L 59.12%, E 58.68%, A 54.54%. A removes 1.4% of CURRENT's orphan volume and 1.5% of its tail volume.

Where the present loss sits: L loses present on five labels (364: 4,855 samples, 263: 3,344, 398: 513, 42: 319, 389: 65), and 364 and 263 are 90% of the 9,096. E recovers 398, 42 and 389 in full and most of 263 (2,943 of 3,344) and a little of 364 (1,024 of 4,855); what is left, 3,831 samples on 364 and 401 on 263, is what A pays 1.75 million false samples to recover. Label 364's loss under E, 3,831 samples (39.9 ms), is the one that keeps E over the 25 ms limit. The two labels' losses are late starts: the first present sample comes 4,855 samples (50.6 ms) late on 364 and 3,920 (40.8 ms) late on 263 under L, 3,831 (39.9 ms) and 401 (4.2 ms) late under E, and on time under A.

## How selective each added source is as a cue (before the 220 ms hold)

Each source's callbacks, clipped to CURRENT's spans, as a share of CURRENT's own volume. Lift is the share of present covered over the share of false covered; 1 means the source covers both alike. CURRENT's own false share is 45.8%.

| Source | Present covered | False covered | Lift | False share of what it covers | Orphan / tail / head covered |
|---|---:|---:|---:|---:|---:|
| L-direct (last decision) | 88.8% | 22.6% | 3.92 | 17.7% | 24.2% / 21.1% / 22.1% |
| E_add (direct earlier in the callback only) | 4.9% | 5.5% | 0.90 | 48.3% | 7.1% / 3.8% / 17.1% |
| A_add (onset cue, never direct) | 2.5% | 16.2% | 0.15 | 84.7% | 26.8% / 9.5% / 25.5% |

- The last-decision direct cue is the only selective source (lift 3.9, and 4.1 below pitch 60). In the upper band (pitch 60 and up) it is not: lift 1.57, covering 79% of the orphan volume and 81% of the head volume there, which matches the earlier finding that the support filter removes none of the upper band's false output.
- The extra mid-callback direct observations carry no signal on their own (0.90), and their coverage of false output is mostly orphan notes.
- The onset-only source is anti-selective: 84.7% of the CURRENT output it covers is false, against 45.8% overall. By class it covers 1,128,642 orphan, 619,567 tail and 96,578 head samples against 332,927 present.

## Reading

- The screen's result stands as Codex reported it. A clears the budget only by giving back 92.5% of the filter's removal; E gives back 8.3% of it (173,074 of 2,083,481 false samples) and restores 53% of L's present loss (4,864 of 9,096), but still starts label 364 39.9 ms late. The plan's stop rule (if A fails, do not tune onset strength, hold, pitch range or individual labels) stands, and this check gives no handle that argues against it.
- The sources explain the exchange: E's extra observations are neutral and mostly orphan, A's extra source is a false-note marker. The missing attack evidence on labels 364 and 263 (their first 50.6 and 40.8 ms under L) sits where genuine and false onsets look alike to these predicates; a cue that separates them would have to be something the onset-only population does not already contain, and nothing here tests whether one exists.
- Not examined, no claim: whether the onset-only marker carries information the L filter does not already use (that filter already treats output with no direct support as unsupported).
- Nothing changes in any gate, default or the frozen label budget (the user's "Leave it as is", commit `2bf0e2a`); the support filter still cannot pass the budget on labels 263 and 364.

## What cannot be concluded

- One recording for classes (ordinary); extended-middle is six labels on one pitch and was used for identity and safety only.
- Emitted-clock saved spans; no audio, no native run, no lane, string, unison or MIDI-lifecycle claim; nothing about live latency.
- Labels are annotated note times, so audible ring after an annotated end scores as false and sits in the tail class.
- Coverage lifts describe each cue before the hold; the hold and the model support change which callbacks matter in the final filter, so a lift is not the filter's exchange rate (the exchange rates above are).
- The per-label present losses are Codex's saved comparison, reproduced here; I did not look inside labels 364 and 263.

## Predictions, scored

| Id | Claim | Odds | Measured | Result |
|---|---|---:|---|---|
| I0-I3 | All identity checks pass | 90% | all pass, raw spans equal too | hit |
| P1 | Tail is the largest class E re-admits over L | 40% | orphan 84.1%, tail 7.7%, head 8.2% | **miss** |
| P2 | A re-admits at least as large a share of the orphan pool as of the tail pool | 70% | 95.4% against 85.8% | hit |
| P3 | L-direct lift at least 2.0 | 60% | 3.92 | hit |
| P4 | Onset-only (A_add) lift under 1.5 | 70% | 0.15 | hit |
| P5 | E_add lift below the L-direct lift | 75% | 0.90 against 3.92 | hit |

Four of five against about 3.15 expected, plus the identity checks. P1 was a near coin flip and went to orphan, not tail. P4 hit by far more than I expected: I had it near neutral, and the source is strongly anti-selective. P2 was bounded in advance by the pool arithmetic (A takes back at least 87.5% of the orphan pool and 77.4% of the tail pool), so it was never a long shot. The arithmetic items listed in the pre-registration (the false and present totals, 35.6, 414.7 and 212.0 false per present, orphan being the largest class of A over L) all reproduced; they were not scored.

## Provenance

- `CLAUDE-M3-SUPPORT-EVENTS-CHECK-20261122.py` (sha256 `fea9de35dff4`, committed in `eb8c167` before the run; selftest passed first), output `CLAUDE-M3-SUPPORT-EVENTS-CHECK-20261122.json`. Compared against `CODEX-M3-SUPPORT-EVENTS-20261122.json` (sha256 `36a016860ade`) and its two saved span files.
- Inputs pinned as in the plan: ordinary trace run 44835727027 (raw sha256 `b664c7ff0ce8`), extended-middle trace run 45062999189 (`78929974b9cc`), adapted cropped events of run 45034216124 (`4e0601c42dbd` ordinary, `1eea72fdc62b` extended-middle).
- Classes and tally code: `CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.py` (sha256 `047242e96fc6`).
