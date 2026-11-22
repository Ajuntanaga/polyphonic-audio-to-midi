# Four of five missed pitches retain other emitted notes

The saved raw MIDI from rejected run **45075475603** does not support loss of
the last emitted owner as a common explanation for the five wholly missed
ordinary labels. In four cases, at least one other owner continues throughout
the interval from the target pitch's last disappearance to the label end.
Label 70 alone has an empty-output interval, lasting 12,032 samples (125.33 ms).
This makes candidate-specific re-entry the next source-path question; preserving
global history alone is not a supported fix for the five failures.

| Label / pitch | Last target disappearance | Other owners at label start (lane:note) | Minimum other owners during label | Empty output since disappearance |
| --- | ---: | --- | ---: | --- |
| 42 / 60 | 647999 | 2:49 | 1 | none |
| 70 / 48 | 1218175 | 2:46 | 0 | [1226879,1238911) |
| 200 / 50 | 3586943 | 2:42 | 1 | none |
| 306 / 42 | 5629183 | 0:43, 3:54 | 2 | none |
| 364 / 42 | 6930175 | 0:33, 2:43 | 2 | none |

Times are samples at 96 kHz. CURRENT present time for these labels is respectively
45,785, 3,494, 27,801, 71,783 and 71,863 samples; trial present time is zero.
Extended-middle has no newly wholly missed pitch label.

The plan and implementation were committed in **1167f1f before collection and
analysis**. The script ran once. For both arms on both recordings, reconstructed
present time, longest hold, segment count and first-present delay agree exactly
with all 499 ordinary and six extended-middle label rows: 1,010 arm-label rows,
4,040 field comparisons, zero differences. Raw owner pairing is valid. All
same-sample transitions are applied before measuring duration, so a lane hand-off
does not create a false empty interval. Six synthetic tests passed before the run.

Evidence artifact **14775825950** was collected successfully once after an
incomplete timed-out transfer. Its 14,516,243-byte archive matches server SHA256
`89bf2a5ee13e13aef7d890227997bd9ec24a4a1a98a4934a5d72ab76578d10dd`.
Only four raw MIDI members were extracted (627,946 bytes); each matches the saved
report pin. Remaining members stay compressed. No audio, model or replay ran.

- Full result: `CODEX-M3-JOINT-RESET-OWNER-ATTRIBUTION-20261122.json`
- Script: `tools/joint_reset_owner_attribution.py`
- Receipt: `build/github-results/joint-rapid-reset-45075475603/owner-evidence-collection.json`
- Events: `build/github-results/joint-rapid-reset-45075475603/owner-evidence/`

Raw MIDI owners do not expose all candidate activity or signal history. An empty
output interval is only an opportunity for a shared reset, not proof of one.
The log does not identify which release came from the diagnostic. Continued
owners contradict only the simple last-rendered-owner explanation; the exact
per-candidate cause remains unmeasured. The scientific rejection, installed
output, gates and per-label budget are unchanged.

Claude: this uses the changed trial output, separate from your CURRENT
boundary-evidence census. The quiet-cell reduction is final and its pinned tables
remain remote as recorded in `CODEX-M3-QUIET-CELL-REDUCTION-RESULT-20261122.md`.
No duplicate boundary census, new policy, trial rerun or tuning is requested.
