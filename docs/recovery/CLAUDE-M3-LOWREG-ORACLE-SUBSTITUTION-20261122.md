# CLAUDE-M3-LOWREG-ORACLE-SUBSTITUTION-20261122: a label-aware corrector of orphan lower output would add up to 5.06 coverage points; 3.58 of them when the target is unambiguous

Claude to Codex, 2026-11-22. Saved spans and labels only (the pinned report and baseline of run 44835727027): no audio, no model run, no job, no native edit, nothing promoted, installed scoreboard unchanged. Pitch occupancy; ordinary corpus; CURRENT spans below MIDI 60. **Every number here is an ORACLE upper bound that uses the labels. It is not an implementable rule and not a result about any detector.**

## 1. Answer first

Most of CURRENT's lower orphan output (a sounded pitch that overlaps no label of its own pitch) stands in a relation to a label that CURRENT does not otherwise cover. The oracle reassigns each orphan stretch (a stretch of constant active-label set) to an uncovered related label's pitch: octave first, then twelfth-like, then near, ties by smaller interval. A related label is "uncovered" when CURRENT's same-pitch spans do not cover every sample of the stretch. Only orphan stretches change, so no label can lose present samples and the strict gate `no_pitch_safety_regression` is met by construction.

| ordinary corpus | coverage | gain | exact-pitch-set | wrong-pitch delta | gap delta | strict gate | labels lost |
|---|---:|---:|---:|---:|---:|---|---:|
| CURRENT | 39.99% | | 53,249 | | | | |
| oracle `all` | 45.05% | **+5.06 points** | 136,578 (2.56 times) | -2,470,491 | 0 | true | 0 |
| oracle `unique` (substitute only if exactly one uncovered related label) | 43.57% | **+3.58** | 114,434 (2.15 times) | -1,720,168 | 0 | true | 0 |
| oracle `octave_unique` (only if that one is an octave) | 41.20% | **+1.20** | 112,578 (2.11 times) | -554,900 | 0 | true | 0 |

Extended-middle: no change in any mode (zero uncovered related labels in any orphan stretch).

1. **The unambiguous part keeps 71% of the gain.** 69.6% of the orphan stretch samples that have an uncovered related label have exactly one (1,720,168 of 2,470,491; the 2,470,491 equals the `all` oracle's wrong-pitch reduction), so the target is not a pick among several chord notes.
2. **The octave-only unique part is small** (+1.20 points) but gives 2.11 times the exact-pitch-set samples: 59,329 of the 61,185 exact-set samples that `unique` adds (97%) come from these octave stretches. I have not looked at why.
3. **Per-class substitution shares** (consistent denominator: samples in stretches where some active label stands in that class's relation to the orphan pitch): octave 1,171,286 of 1,574,151 (74.4%); twelfth-like 599,457 of 1,064,850 (56.3%); near 699,748 of 1,758,282 (39.8%). The earlier printout of 1.045 for `near` was a denominator artefact (the first script counted a stretch only under its first-priority class); nothing was above 1 once each class has its own denominator.
4. **Count of uncovered related labels per stretch (samples):** none 463,789; exactly one 1,720,168; two 545,129; three or more 205,194.

## 2. Pre-registered predictions

Substitution script (`CLAUDE-M3-LOWREG-ORACLE-SUBSTITUTION-20261122.py`):

| | prediction | measured | verdict |
|---|---|---|---|
| Q1 | at least 30% of octave-class orphan samples are substitutions | 74.4% | passed |
| Q2 | at least 30% of twelfth-class | 86.8% (first denominator); 56.3% (consistent) | passed either way |
| Q3 | at least 50% of near-class | 104.5% (artefact); 39.8% (consistent) | passed only on the artefact; **fails on the consistent denominator** |
| Q4 | oracle raises ordinary coverage by at least 3 points | +5.06 | passed |
| Q5 | oracle at least doubles exact-pitch-set samples | 2.56 times | passed |
| Q6 | oracle passes the strict gate | true | passed (by construction) |

Ambiguity script (`CLAUDE-M3-LOWREG-ORACLE-AMBIGUITY-20261122.py`):

| | prediction | measured | verdict |
|---|---|---|---|
| A0 | `all` reproduces the oracle (+5.06, exact-set 136,578) | 5.06; 136,578 | passed |
| A1 | at least 60% of stretch samples with an uncovered related label have exactly one | 69.6% | passed |
| A2 | `unique` keeps at least half the gain (2.53 points) | 3.58 | passed |
| A3 | `octave_unique` gains at least 1.5 points | 1.20 | **failed** |
| A4 | every per-class share is at most 1 | 0.744, 0.563, 0.398 | passed |

## 3. Reading and caveats

- **What this says:** the orphan output mostly sits where a label that CURRENT misses is sounding, within an octave, twelfth or neighbour interval of it. If a corrector could name the right pitch, ordinary coverage could rise by up to about 3.6 points (unambiguous) or 5.1 (all), at a lower wrong-pitch output and no gap or label loss.
- **What this does not say:** that the detector "heard the note and rendered it at the wrong pitch". The orphan-null control (`CLAUDE-M3-LOWREG-ORPHAN-NULL-20261122`) shows 69% of orphan stretch samples have some related active label by chance, and only the octave tie survives that control (+20 points); so the oracle gain mixes real substitutions with the fact that nearly any orphan has some uncovered related label to be pointed at. It is evidence of where recall is missing, not of a mechanism.
- **The oracle knows the labels.** A label-free corrector must find the uncovered pitch from audio evidence. The ghost-separation result shows no single trace feature separates ghosts from true partnered notes cleanly (best AUC 0.83).
- The strict gate is met here by construction. The same gate is the brittle one for any real rule (any cut a few milliseconds before a label ends loses present samples); that is the author's call to relax, not mine.
- Next saved-trace question (not started): at the ticks where an orphan sits on an uncovered related label, does the trace show a candidate or evidence for that label's own pitch (selected or not)? If it does, a rule has something to select; if not, the recall gap is upstream of selection.
- One recording and one corpus. Not claimed: a lane, unison-multiplicity, callback-deadline or live-host claim; nothing selects a native rule.

## 4. Pins and timing

| item | sha256 (first 12) | mtime (PST, 2026-11-22) |
|---|---|---|
| substitution script / result | fdfddfd13209 / 816c903f3388 | 02:39:33 / 02:39:36 |
| ambiguity script / result | 44ec43b78fbb / 7f376a5126e5 | 02:42:51 / 02:42:54 |

Run each script from `docs/recovery` with `python3 -P -E`; they read the pinned report and baseline JSONs and import the frozen tail-clip audit script (and through it the split script); the ambiguity script also imports the substitution script. The docstrings give no clock time on purpose; the predictions were written before each run.

## 5. Coordination

My files here are `CLAUDE-M3-LOWREG-ORACLE-SUBSTITUTION-20261122.*` and `CLAUDE-M3-LOWREG-ORACLE-AMBIGUITY-20261122.*` only. No native edit and no job.
