# Erratum: the saved v5 trace carries no per-pitch evidence inside a rapid-mute run, so the "run-interior census" I proposed is withdrawn

Claude, 2026-11-22. Corrects item 7 of `CLAUDE-M3-RESTART-EVIDENCE-CENSUS-RESULT-20261122.md` (commit `7aa79a1`); that item now carries a pointer here. Saved data only: the two pinned v5 traces, no
audio, model run, job, native edit or promotion. Script `CLAUDE-M3-EVIDENCE-AVAILABILITY-TALLY-20261122.py` (sha256 prefix `c89e1d7899d9`) and its output `CLAUDE-M3-EVIDENCE-AVAILABILITY-TALLY-20261122.json`
(`f578f1c5b601`). The tally has no labels and no class: it counts fields by the decision's quiet code. It was written and run after the census result was published; the first look at these counts came from
a scratch copy without the pin check, and the committed form reproduces every count exactly.

## Answer

1. **The inference was wrong.** I wrote that the candidate records exist inside the removed parts ("100% carry a record for their pitch"), so a run-interior onset/energy census was the next check. A record
   is a state snapshot, not evidence. The detector runs its per-candidate spectral scoring only when a decision is not quiet (`if (!quiet || capture_floor_reentry)` in
   `native/src/polyphonic_pitch_detector.cpp`), and the header says the pre-selection energy fields are valid only when the spectrum was evaluated.
2. **Measured: inside a marked run there is no per-pitch evidence at all.** Every decision of quiet code 5 (`rapid_mute_ratio`, the code that marks a run) has candidate records, and not one has
   `energy_observed` or `onset_observed` set: ordinary 10,949 decisions, 24,729 records (24,565 of them CURRENT-active), 0 observed; extended-middle 888 decisions, 1,289 records (all active), 0 observed.
   Where the detector does evaluate (code 0), every active record has its energy observed (366,116 of 366,116 on ordinary) and 73.6% have the onset evidence observed (28.3% with a positive value).
3. **So the run-interior census is withdrawn,** and with it the sentence naming it as the next check in the census note, in my message to Codex (queue `01a2056c`), in phone update 48 and in my memory note. The census
   result itself is unaffected. Its cues L, E and A read ordinary-disposition decisions only, which is why Answer 6 says they cannot see inside a run; this tally is the reason, not a change to any number.
4. **What the trace can offer instead.** Pitch-specific evidence exists only before a run (the last evaluated decision) and after it (the first evaluated decision). `input_power` is the decision's fast input
   energy (`previous_decision_energy_`, set at every decision before the quiet branch), so it is saved inside runs too, but it is global, not per pitch. All 23 positive labels begin inside a run or within 25 ms
   after it, so the attack's own per-pitch evidence is not in saved data; only its aftermath at the run boundary is. My next check is therefore a boundary-evidence census, pre-registered separately before any run.
5. **For Codex, an option, not a request.** The detector already has an observation-only capture for the floor re-entry path (`capture_floor_reentry`: "without advancing selection, candidate evidence, or
   fine-frequency history"). A matching capture for rapid-mute decisions would, I expect, put the in-run per-pitch evidence into a new trace without changing any output. That is native lane and a new
   dispatch; I am not starting it, and nothing here argues for or against a native behaviour change.

## Counts by quiet code (ordinary; extended-middle and the other codes are in the JSON)

| Code | Disposition | Decisions | Records | Active records | Records with energy observed | Records with onset observed |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 0 | not quiet | 150,917 | 1,254,060 | 366,116 | 1,186,391 | 349,419 |
| 1 | minimum evidence, startup | 62 | 590 | 0 | 0 | 0 |
| 2 | minimum evidence after signal floor | 4,783 | 27,685 | 4,238 | 25,359 | 0 |
| **5** | **rapid mute ratio (marks a run)** | **10,949** | **24,729** | **24,565** | **0** | **0** |
| 7 | multi-voice evidence | 314 | 3,230 | 376 | 3,033 | 0 |

Codes 2 and 7 show energy because the detector does evaluate the spectrum there (the observation-only floor re-entry capture, and the multi-voice path); onset evidence needs the posterior update, which only code 0 reaches.
Extended-middle code 5: 888 decisions, 1,289 records, 1,289 active, 0 energy observed, 0 onset observed; its code 0 has 32,470 decisions with 40,522 active records, all with energy observed and 36,942 (91.2%) with onset observed.

## What stands

The census result, its identity gates, its predictions and its POST HOC sections are unchanged; so is Answer 6 (the positive labels begin where the cues cannot look). What changes is only the statement of what
could be checked next from saved data, and who would have to change something to see the attack itself.

## Provenance

Traces: ordinary `b664c7ff0ce8...` and extended-middle `78929974b9cc...` (SHA-256 of the decompressed pinned v5 traces, the rapid-mute check's pins, verified by the script after each pass). Detector reading is of the
committed source at `7aa79a1`. Both recordings remain seen design data.
