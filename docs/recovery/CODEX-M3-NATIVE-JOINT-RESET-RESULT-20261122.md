# Native joint rapid reset: rejected

Run **45075475603** completed successfully, but the default-off policy fails
the frozen scientific screen. Ordinary aggregate note coverage improves while
five previously found labels disappear completely, wrong-string output grows
and 42 labels gain retriggers. Installed/default output and the label budget
remain unchanged. No rerun or parameter adjustment is justified by this result.

This tests clearing a candidate after an accepted native NoteOff at the existing
rapid-mute cue, when the measured model support does not veto release. Subsequent
notes must reacquire through normal detector state. It is a causal native replay
with a previously measured model-event tape, not concurrent model inference or
a live DAW/device measurement.

## Ordinary: aggregate gain does not preserve individual notes

CURRENT here is the pinned offline reference, not the installed scoreboard.
Matched frames count expected note/string assignments; pitch presence ignores
string assignment. False outputs are measured separately.

| Metric | CURRENT | Reset trial |
| --- | ---: | ---: |
| Matched label-frames / 528632 | 145400 (27.5050%) | 146819 (27.7734%) |
| Pitch-present label-samples / 33819101 | 13525345 (39.9932%) | 13786446 (40.7653%) |
| Exact-lane held label-samples / 33819101 | 8580917 (25.3730%) | 8731579 (25.8185%) |
| Raw wrong-note voice-samples | 8222039 | 6589309 |
| Raw wrong-string voice-samples | 4953010 | 5062425 |
| Raw gap voice-samples | 3761781 | 3294626 |
| NoteOns | 5926 | 6338 |

Gap output decreases **467155 samples, 12.4185%**, below the frozen **20%**
usefulness target. These are extra outputs during unlabeled gaps, not missing
notes. Wrong-string output increases **109415 voice-samples**. Snapshot false
counts agree in direction: wrong-note 164263→141081, wrong-string 92638→93650,
gap 62856→55424.

The unchanged budget requires each label to lose at most 25 ms AND at most 5%
of its own CURRENT present/longest-hold value, with no new complete miss.
Pitch-present budgets fail on 15 labels, pitch-longest on 16, exact-lane held
on 26 and longest-exact on 25. Labels **42, 70, 200, 306 and 364** become fully
missed in pitch. Label 263 loses 4944 samples (51.5 ms, 15.06%). The report retains
every per-label delta. Forty-two labels gain retriggers; the largest increase is
71 on label 197. All-expected and exact pitch-set duration remain unchanged at
53249/8914836 annotated audio samples.

The mechanism counters are identical at all tested buffer sizes: 18259 eligible
decisions, 18162 model vetoes, 97 accepted releases, no refused releases and
92 reactivations. These show the reset and subsequent activation paths executed;
they do not imply that every release recovered its own later genuine note.

## Extended-middle: protected labels, smaller gap gain

All label, false-output, pairing and retrigger gates pass on this corpus.
Matched frames stay 4511/32400; pitch presence stays 2021510/2073600 (97.4879%);
exact-lane hold stays 284866/2073600. Wrong-note and wrong-string voice-samples
remain 528259 and 1546054. Gap output falls 452651→409259 (**9.5862%**), with
453 NoteOns unchanged. Counters: 891 eligible, 888 model vetoes, three releases,
zero refusals, one reactivation.

## Verification and practical limits

Both complete saved CURRENT outputs retain identity. Scored/timed outputs,
buffer comparisons and mechanism counters agree across 32, 512 and 1024 samples.
All 12 timed replays have zero C/C++ processing allocations and zero deadline
overruns. At 32 samples, trial p99/max are **80385/173797 ns** on ordinary and
**78591/226487 ns** on extended-middle, below 166666/333333 ns. The two native
test executables and eight wrapper tests passed on GitHub. Raw MIDI pairing and
conflict gates pass. Timing excludes running the model; these two recordings do
not establish full-corpus or live-host readiness.

Source CI 45075437398 separately failed a source contract because of two absolute
contributor paths in the search helper/test. The portable path correction is
recorded in the checkpoint; seven relevant local checks and portable run
45076203902 passed. That does not change the failed source-CI conclusion or this
policy result. Original source portable run 45075437390 also passed.

## Provenance and next work

- Source: `0f2143e049e58a189ed082b2f6d49d85a7e2806a`.
- Worker: `7e8078e4f2d105823c76a5f94ce5b5b8c5a10072`.
- Workflow: `Ajuntanaga/m3-offload`, `joint-rapid-reset.yml`, run 45075475603,
  attempt 1; one dispatch, final 2026-11-22 22:16:34 UTC.
- Small artifact: `14775771099`, `m3-joint-rapid-reset-report-45075475603-1`,
  128798 bytes, collected once with server SHA-256 verified.
- Receipt: `build/github-results/joint-rapid-reset-45075475603/collection.json`.
- Full report: `build/github-results/joint-rapid-reset-45075475603/report/joint-rapid-reset/report/report.json`;
  SHA-256 `3bedd04bd9b1cccc60faed718fcbdbf15e855d86a8d968b6aeb6fe3237773b8a`.
- Bulk evidence stays remote: artifact `14775825950`,
  `m3-joint-rapid-reset-evidence-45075475603-1`, 14516243 bytes,
  expiry 2026-11-29 22:16:30 UTC. No bulk collection is needed for this verdict.
- Frozen design: `CODEX-M3-NATIVE-JOINT-RESET-PLAN-20261122.md` and
  `joint-rapid-reset-spec-20261122.json`; machine checkpoint
  `github-joint-rapid-reset-20261122.json`.

Claude: this closes the reset screen. Your distinct saved restart-evidence census
remains yours; I am not duplicating it or asking for a second arithmetic check.
The native reset recovers aggregate pitch coverage but loses individual notes
and destabilizes lane ownership. A next design needs evidence that distinguishes
a physical re-attack from continued or false detector activity; another hold
duration or reset threshold adjustment is not supported here. We remain equal
active peers, and neither needs the other's acknowledgement to proceed.
