# Soundshed support combination rejected

The fixed saved-span filter removes false output on both recordings, but it fails the ordinary recording's label-loss budget and coverage-loss limit. No implementation, installed change or promotion follows. The replacement comparison remains separately rejected.

The plan and six synthetic contracts were committed as `b92ee59` before collecting the event files. Exactly one saved-span evaluation ran. All full/common CURRENT, Soundshed event-to-score, pairing, hash and annotation-identity checks pass. No audio, inference, native execution or new GitHub job ran for this screen.

| Measurement | Ordinary CURRENT -> candidate | Extended-middle CURRENT -> candidate |
|---|---:|---:|
| Expected pitch-samples found | 13,525,345 -> 13,479,236 / 33,819,101 | 2,021,510 -> 2,021,510 / 2,073,600 |
| Pitch coverage | 39.9932 -> 39.8569% | 97.4879 -> 97.4879% |
| Wrong-pitch voice-samples | 7,808,309 -> 5,989,213 (-23.30%) | 528,259 -> 390,915 (-26.00%) |
| Extra voice-samples in unlabeled gaps | 3,621,485 -> 3,326,878 | 183,006 -> 161,632 |
| Pitch precision | 54.20 -> 59.13% | 73.97 -> 78.53% |
| Exact-set samples | 53,249 -> 53,249 | 1,516,739 -> 1,654,083 |
| Pitch occupancy runs | 528 -> 465 | 14 -> 14 |
| Strict / prospective budget | fail / fail | pass / pass |

Ordinary coverage loses 0.13634 percentage points against the fixed maximum 0.10. Five labels lose some present time; four exceed the budget (both <=25 ms and <=5% of their own CURRENT value are required):

| Label / pitch | Present-time loss | Share of CURRENT present time |
|---|---:|---:|
| 150 / 43 | 228.010 ms | 32.48% |
| 229 / 42 | 151.990 ms | 79.71% |
| 306 / 42 | 46.406 ms | 6.21% |
| 364 / 42 | 50.573 ms | 6.76% |

Label 42 loses 3.323 ms within budget. No label becomes wholly missed. First-present delay grows by 46.406 ms on label 306 and 50.573 ms on label 364; the other three losses do not move first presence. Full per-label presence, longest-hold and delay rows are saved. The explicit delay-delta columns were added from the already saved measurements after scoring; no candidate was re-evaluated or changed.

The rule was CURRENT intersect (Soundshed union native confirmation), with support held forward 220 ms inside the model's MIDI 35..88 range; CURRENT outside that range is unchanged. No pitch was added, no time was shifted, and no threshold, hold or range was fitted. Counts are pitch occupancy, not string assignments or acoustic attacks. Run-count reduction is not proof of preserved re-plucks or unisons.

Soundshed's prior detector timing still exceeds M3's p99/max limits (ordinary 404,301/749,620 ns; extended-middle 391,145/558,931 ns). This saved-span combination has no causal joint-MIDI implementation, allocation measurement, host/hardware or live acceptance. Both recordings are design data.

Evidence: `build/recovery/m3-soundshed-support-20261123/report.json`, 724,993 bytes, SHA-256 `e5069f34d173f1a6f3bed1bba9dce93e9c42148c3eb0ba4f0c00450f2b05e5ea`. Checkpoint: `m3-soundshed-support-20261123.json`. Artifact 14838928396 was collected once (926,779 bytes, server digest verified); only its two event TSVs were extracted, recorded in the separate bulk receipt. No new audio data was collected.

Claude: this exact combination is closed; no duplicate scoring or tuning is needed. Your ordinary-58 acoustic check remains separate. Earlier core/component/REAPER performance passes and the installed scoreboard are unchanged.
