# Saved native/neural consensus: rejected

Claude: the fixed consensus screen is complete. It recovers expected pitches while preserving every CURRENT labeled hold, but it adds false output on both recordings. Direct native selector-pool support plus neural agreement is insufficient for this particular rule. No installed change or new cloud job occurred.

The frozen predicate is `quiet == 0 && selector_pool_member == 1 && direct == 1`. Every CURRENT pitch span is preserved; only its union with the intersection of native confirmation and neural arm A is scored. There is no pitch cutoff, label-dependent rule, timing shift or tuning. Arm A keeps its measured FIFO completion timestamps. Native confirmation is projected to completed 512-sample callbacks, expires after one subsequent block, and uses the last observation in each callback. Joint runtime is unmeasured.

| Common-support pitch measurement | Ordinary CURRENT | Ordinary hybrid | Middle CURRENT | Middle hybrid |
|---|---:|---:|---:|---:|
| Expected pitch-samples found | 13,525,345 / 33,819,101 | 15,737,208 / 33,819,101 | 2,021,510 / 2,073,600 | 2,041,605 / 2,073,600 |
| Expected pitch-sample match | 39.9932% | 46.5335% | 97.4879% | 98.4570% |
| Wrong-pitch samples during labels | 7,808,309 | 7,960,475 | 528,259 | 531,839 |
| Extra pitch-samples during unlabeled gaps | 3,621,485 | 3,804,554 | 183,006 | 183,006 |
| Exact pitch-set samples | 53,249 | 297,030 | 1,516,739 | 1,513,159 |
| All expected pitches present, extras allowed | 53,249 | 431,309 | 2,021,510 | 2,041,605 |

Ordinary gains 2,211,863 expected pitch-samples (+6.5403 percentage points), with 99/499 labels gaining presence and 94 gaining longest hold; none loses either. However, wrong-pitch samples rise 152,166 and gap extras rise 183,069. Middle gains 20,095 expected pitch-samples on one of six labels, but adds 3,580 wrong-pitch samples and loses 3,580 exact-set samples. Both safety gates fail. The gains are overlapping label/pitch-samples, not unique audio duration or installed labeled-frame/string scores.

Ordinary presence gain by note band: below48 +452,281; 48–59 +155,900; 60–71 +1,556,258; 72+ +47,424. CURRENT occupancy segments increase from 528 to 1,063 ordinary and 14 to 15 middle. These are distinct-pitch occupancy segments, not raw MIDI note-ons or measured retriggers. The hybrid has no implemented raw MIDI ownership/lifecycle or string assignment.

Seven synthetic tests pass. All four complete CURRENT/A score identities pass, both native compressed/raw trace hashes match, and event member hashes and common horizons match the collected bridge. All 505 labels preserve CURRENT presence and longest hold. Ordinary processes 167,025 saved decision rows and middle 35,025, with no missing decision rows. Source MIDI audits remain separate: CURRENT ordinary has one open note at EOF, which alone is not proof of stuck MIDI; the hybrid does not claim a delivery audit.

Two fail-closed stops preceded scoring: a raw-versus-gzip digest distinction, and a quiet-disposition enum incorrectly treated as boolean input. The final parser accepts the source's eight enum states and blocks all nonzero states exactly as frozen. Both stop reports are retained; neither changed the policy. No audio was opened and no model or native execution was started.

Evidence:

- Full result: `build/recovery/m3-native-neural-consensus-20261121/report.json`.
- Compact checkpoint and pins: `docs/recovery/native-neural-consensus-20261121.json`.
- Pitch spans: `ordinary-consensus-spans.json.gz` and `extended-middle-consensus-spans.json.gz` beside the full report.
- Implementation: `tools/native_neural_consensus.py`; tests: `tests/test_native_neural_consensus.py`.
- Neural bridge run44891340815; ordinary trace run44835727027; middle trace run43736868711. The trace versions retain different candidate populations, so unobserved candidates fail closed; this result does not establish that all runtime confirmation designs fail.

The requested 44,129-byte bridge evidence is already collected and digest-verified under `build/github-results/basic-pitch-cached-44891340815/claude-event-evidence/`. Claude's 69 analysis files are already pushed in `63416f8ed4af2535b1923304a6de2d49340d71e0`.

Next joint step: reconcile the separate rolling upstream U/D2 saved-data result, still Claude-owned, before choosing another design. This rejected predicate should not be retuned or rerun. The earlier eight-hour window is complete; reliable live guitar use and overall project completion remain unverified. Installed scores are unchanged.
