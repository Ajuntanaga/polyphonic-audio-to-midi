# Signal-observation cost breakdown — final diagnostic

Run **45106622018** completed successfully on source **7a5dc05**, worker
**818b51e**. The three saved tracking snapshots are bit-identical, all four
fixed controls are present, and all processing allocation/free counters are
zero. Both native test targets, 25 focused contracts and both source checks pass.
No policy, installed/default behavior, score or acceptance gate changed.

## What the measurements show

Pitch-measuring cell updates are the largest measured substage: **48.10–49.23%**
of reconstructed signal-observation time. The table divides each substage's
nanoseconds by residual observation plus all four new signal substages.

| Fixed replay | Cells | Residual observation | Spectral + group trackers |
|---|---:|---:|---:|
| ordinary / current-on | 48.95% | 37.26% | 13.79% |
| ordinary / completion-midi-retention-on | 48.10% | 37.87% | 14.03% |
| physical-long / completion-midi-retention-on | 49.23% | 39.04% | 11.72% |

The narrow-range stage has zero calls in this fixed max-fret-24 configuration.
All thirteen stage counters and the four control callbacks are retained in the
companion JSON and collected report. Ordinary counts remain 145400/528632
matches, 164263 wrong-note, 92638 wrong-string and 62856 gap outputs;
physical-long remains 41452/68441, with 67769/2709/5403 respectively.
Gap outputs are extra notes during unlabeled gaps.

These are **instrumented costs**, not production CPU proportions or a speedup.
Clock calls add substantial overhead and can dominate short intervals. The
four named controls' nonrecurrence does not clear the saved native deadline
failures. No timing acceptance or live-use claim follows from this observation.
The production allocation gate also stays false by design: timing_gates requires
an uninstrumented run even when all four observed allocation/free counters are
zero. MIDI lifecycle was not remeasured.

## Collection and next decision

The 37,813-byte small report archive was collected once; its SHA-256 equals
the server digest. Receipt: `build/github-results/signal-observation-stages-45106622018/collection.json`.
Report SHA-256: `9ddc86b04ceda2522c8876432d94a4d7f359ce605182576d079dd2d5c49d6018`.
Bulk artifact **14787534480**, 3,353,450 bytes, stays remote. No repoll,
redownload, rerun or broader replay is needed for this completed diagnostic.

The result locates a candidate area for a distinct CPU optimization. Any such
change still needs paired uninstrumented evidence; the rejected sharing,
packed-arithmetic and narrow-clearing screens stay rejected. Stable-note
re-pluck preservation remains a separate unresolved player-facing question.
