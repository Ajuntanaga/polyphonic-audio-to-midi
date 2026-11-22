# An onset grace is cheap but does not clear labels 263 and 364: result and a rule inconsistency

Claude, 2026-11-22. Pre-registration: `CLAUDE-M3-ONNX-ONSET-GRACE-PREREGISTRATION-20261122.md` (commit `25dc971`, before the run). Post hoc candidate on saved events, emitted clock; no audio, model run, job or native edit; nothing promoted.

## Answer

**The grace is cheap and does recover small head losses, but it cannot clear the two labels that fail the frozen budget, so reading C stands:** no grace from 0 to 100 ms, at D = 220 or 260, passes the 25 ms / 5% label budget or the strict gate, for either support. Labels 263 (pitch 33) and 364 (pitch 42) lose the same 34.83 ms (10.18%) and 50.57 ms (6.76%) at every G.

Cropped adapted, ordinary, D = 220 (CURRENT coverage 39.9932%):

| G (ms) | 0 | 10 | 30 | 50 | 100 |
|---|---:|---:|---:|---:|---:|
| Coverage | 39.966 | 39.968 | 39.968 | 39.968 | 39.968 |
| Wrong-pitch removed | 22.28% | 22.02% | 21.56% | 21.14% | 20.16% |
| Gap delta (samples) | -344,176 | -343,216 | -341,296 | -337,829 | -329,739 |
| Labels losing | 5 | 3 | 3 | 3 | 3 |
| Over the budget | 263, 364 | 263, 364 | 263, 364 | 263, 364 | 263, 364 |

- **Cost is small.** A 30 ms grace gives back 0.7 points of wrong-pitch removal and about 3,000 gap samples; even G = 100 keeps 20.16%, so the cleanup is still retained by the earlier rule across the whole grid at D = 220. At D = 260 (adapted) it is retained at G = 0 only (19.96% at G = 10).
- **What it recovers:** labels 389 (0.68 ms) and 398 (5.34 ms) in both supports, and for the unmodified events label 229's 151.99 ms loss, all gone by G = 10. Losing labels fall from 5 to 3 (adapted) and from 6 to 3 (unmodified), leaving 42 (a 3.32 ms tail loss that D = 260 removes), 263 and 364.
- **Extended-middle:** 0 labels losing and the strict flag True in every cell (a safety check only; the output stays a subset of CURRENT).

## Why 263 and 364 do not move (post hoc diagnostic, not registered)

I expected their head loss to be CURRENT starting the note late. It is not. `CLAUDE-M3-ONNX-ONSET-GRACE-DIAGNOSTIC-20261122.py` lists, relative to each label's start, the spans of the label's own pitch:

| Label | CURRENT spans of the pitch (ms) | Cropped-adapted model spans | Native confirmation starts |
|---|---|---|---|
| 263 (pitch 33, 348 ms) | -1073.8 to 34.8, then 40.8 to 968.8 (and -2078.5 to -1076.5 before) | none | 36.2 |
| 364 (pitch 42, 749 ms) | -480.1 to 1044.6 (and -1572.1 to -523.4 before) | 95.8 to 882.4 | 50.6 |

CURRENT is already outputting the pitch for 0.5 to 2 s before the labeled start (the previous label of that pitch ends 1.8 s and 10.5 s earlier, so the scorer counts that output as wrong or gap output, which the filter removes), and its span runs on through the onset, so there is no span start inside the head for a grace to attach to. The filtered note can only begin when a support does: the native confirmation arrives 36.2 and 50.6 ms after the labeled start, and the lost time is CURRENT's output before that point (34.83 ms for label 263, whose CURRENT span has a 6 ms break at 34.8 to 40.8; 50.57 ms for label 364). The loss is the support's confirmation latency, and a causal filter has no way to tell "this leftover pitch becomes real now" from "this leftover pitch is wrong" until the support appears. Labels 389, 398 and 229 behave differently because CURRENT's own spans start inside their heads (389: CURRENT spans at 11.5, 64.8 and 226.8 ms), which is where a grace can reach. I did not split label 229's recovery further.

## A rule inconsistency I introduced

My frozen budget (`CLAUDE-M3-LABEL-RULE-DECISION-20261122.md`) says first-present delay is "reported per label, not gated" and also gates present-time loss at 25 ms and 5%. For a note whose output is already running when its true onset arrives, those are the same samples: the 34.83 and 50.57 ms are first-present delays, and the present-time clause gates them. So as written, a filter that waits for confirmation (about 36 to 51 ms here) cannot pass the budget on these labels however it is tuned, and the "not gated" clause is not true for head time. I have not changed the rule: any head-delay threshold set now would be chosen with these two labels in view, which is the fitting Codex warned against, and the rule's own text says to change numbers before the next held-out run. This is the user's call to make (and a candidate choice is between gating head delay on its own limit, or leaving it as is and accepting that confirmation-based filters fail it). The strict and budget results are unchanged and are both still reported.

## Predictions, scored

| Id | Claim | Odds | Result |
|---|---|---:|---|
| G0 | G = 0 reproduces committed D = 220 and 260 rows | 97% | hit |
| G1 | Monotone in G | 99% | hit |
| G2 | Adapted D = 220 passes the budget at some G | 88% | **miss** |
| G3 | Smallest such G at most 30 | 60% | miss (none passes) |
| G4 | At that G wrong removed at least 20% | 35% | miss (vacuous) |
| G5 | At that G gap delta at most -250,000 | 60% | miss (vacuous) |
| G6 | Unmodified D = 220 never passes the budget | 90% | hit |
| G7 | Adapted D = 260 strict gate True at some G | 65% | **miss** |

Three of eight. The same premise failed twice in a row (that the remaining losses are about when CURRENT or the model ends or starts a note): I read 263 and 364 as onset latency of the model, and the span listing shows they are latency of the confirmation of an output that CURRENT was already producing. I gave the grace 88% to clear the budget; it was the more confident of the two wrong calls.

## Limits

Post hoc grid and diagnostic, chosen after the losers were known; two recordings, both seen. Emitted-clock reconstruction of saved events: a real grace would put short false notes into live MIDI, which this scores only as samples. Two labels are the whole obstacle, so this says nothing about how often the pattern occurs on other recordings. No lane, string or MIDI-lifecycle claim. Nothing promoted.

## Provenance

`CLAUDE-M3-ONNX-ONSET-GRACE-20261122.py` (sha256 `8d79c3a05989`), output `CLAUDE-M3-ONNX-ONSET-GRACE-20261122.json`; `CLAUDE-M3-ONNX-ONSET-GRACE-DIAGNOSTIC-20261122.py` (`2dc286519b8d`) and its JSON. Same four hash-verified event members as the earlier results. No change after the pre-registration commit.
