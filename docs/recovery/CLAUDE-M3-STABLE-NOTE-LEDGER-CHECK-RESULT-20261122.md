# Result: the stable-note path's per-label claims reproduce from the saved rows, the ledger and the corpus run agree row for row, and 7 labels (4 windows) are left with no NoteOn inside them

Claude, 2026-11-22. A check of the saved evidence behind the default-off stable-note identity path: Codex's bounded screen (ledger run 44079653692, the paragraph in `RESUME.md`) and the later VST3-component corpus run 44245557161. Script `CLAUDE-M3-STABLE-NOTE-LEDGER-CHECK-20261122.py` (sha256 prefix `8bbcd733a0ec`), output `CLAUDE-M3-STABLE-NOTE-LEDGER-CHECK-20261122.json` (`2489bb09adc3`). Saved data only: three small JSON reports already in `build/github-results`. No audio, model run, job, native edit, promotion or download; nothing of Codex's was edited. **Not pre-registered.** I recomputed the headline numbers inline and read the rows of six datasets (ordinary, extended-middle, physical-long, extended-highmid, extended-high, physical-four) before writing the script, so items 1 to 4 are a check of someone else's claims (the outcome is "reproduces" or it does not), item 5 is something I found by reading the rows and is not a pre-specified test, and items 6 and 7 are POST HOC and descriptive: no prediction, no verdict, and nothing here is a gate, a parameter, an exemption or a change to the path.

## Answer

1. **Every claim in the paragraph reproduces (30 of 30).** From the ledger's per-label rows and counters:
   - Target label 17 (note 37, 71,783 samples): NoteOns 156 to 109 (-30.13%), longest hold 5,184 to 5,824 samples (54.0 to 60.67 ms), pitch present in 65,857 samples (91.74%).
   - Across the 499 labels: 79 have a longer hold, 148 have fewer NoteOns, none regress, and the pitch-present samples are equal in every label.
   - Callbacks 11,851 to 8,623 through 1,614 transferred pairs (3,228 suppressed events, 0 pairing errors in either mode); the wrong-note and gap voice-samples are identical in both modes (8,222,039 and 3,761,781); wrong-note onsets 1,200 to 928 and gap onsets 517 to 323; note 44 is open at end of file in both modes.
   - The report file's hash equals the collected verdict's `report_sha256`.
2. **The two runs agree on every ordinary label.** The ledger's 499 rows, in both modes, equal field for field the `ordinary` rows of the later corpus run (VST3-component native runs), and the pitch-safety counters equal too. That is consistency across two runs and two code paths; it says nothing about whether the labels are right.
3. **The counters reconcile exactly (ordinary recording).** NoteOns inside labels 4,209 + wrong-note onsets 1,200 + gap onsets 517 = 5,926 = the lifecycle's NoteOns; after the path 3,061 + 928 + 323 = 4,312 = 5,926 - 1,614. The 1,614 removed pairs are 1,148 in-label, 272 wrong-note and 194 gap, and 5,926 NoteOns + 5,925 NoteOffs = 11,851 input events. So no NoteOn is counted twice in this recording and every removed pair is accounted for.
4. **The label gates replicate on all 14 datasets of the corpus run** (1,184 labels): 0 label-level regressions (no pitch loss, no shorter hold, no NoteOn growth); `label_changes` equals the row differences in every label; my re-derivation of the three label gates agrees with the report's gate booleans in all 14; the only datasets that fail are extended-highmid and extended-high, on the timing limit, not on any label gate. NoteOns inside labels fall from 15,875 to 9,807 (-38.2%) counting every label, and from 8,625 to 5,774 (-33.1%) counting each inferred window once (see Disclosures: labels annotated once per string repeat the same events). Per dataset the removal runs from 9.6% (extended-middle) to 46.4% (isolated-08); ordinary is 27.3%.
5. **Seven labels, in four windows, lose every NoteOn inside them (none in the ordinary recording).** In all seven the pitch is present for the whole label before and after, and after the path the longest sink hold is the whole label: a note that began earlier covers it.

   | Dataset | Labels | Pitch | Label length | NoteOns before to after | Longest hold before to after |
   | --- | --- | ---: | ---: | ---: | ---: |
   | constructed | 112 to 115 (one inferred window) | 51 | 2,298.5 to 2,299.4 ms | 4 to 0 in each | 1,585.3 ms to the whole label |
   | physical-highmid | 2 | 56 | 2,300.0 ms | 1 to 0 | 1,903.3 to 2,300.0 ms |
   | physical-high | 3 | 60 | 2,300.0 ms | 1 to 0 | 1,980.7 to 2,300.0 ms |
   | physical-high | 4 | 60 | 2,120.0 ms | 1 to 0 | 2,047.3 to 2,120.0 ms |

   The `no_label_attack_growth` gate cannot see this: it forbids more NoteOns, not fewer. The rows cannot tell whether a removed NoteOn was a real re-attack (a new pluck at the label's start, folded into the earlier note) or a lane flip of a note that was already sounding. This is the corpus report's own open item (`acoustic_repluck_preservation`: "not measured"), and these seven labels are the concrete cases in the existing corpus where it could be tested without new audio. The baseline already has labels of this kind, so carry-over is not new: the pitch is present with no NoteOn inside the label in 25 of the 1,184 labels before the path (2 in the ordinary recording) and 32 after (still 2 in the ordinary recording); the seven above are the whole increase. The two physical datasets involved are one pitch throughout (physical-high all 60, physical-highmid all 56), and in physical-high labels 2, 5 and 7 already have no NoteOn in the baseline.
6. **POST HOC: where the NoteOns are, and how much of each bucket the path removes.** Labels with 21 or more remaining NoteOns hold 71.4% of the ordinary recording's remaining in-label NoteOns (2,185 of 3,061) although its heaviest label, 17, holds 3.6% (109); counting windows, those with 21 or more hold 3,517 of the 5,774 remaining NoteOns across the 14 datasets (60.9%). Extended-middle's label 2 holds 68.2% of its dataset's remaining NoteOns (251 of 368) and the path does not touch it (251 to 251); physical-long's label 3 holds 53.6% (98 of 183) and physical-high's label 0 holds 74.5% (38 of 51; baseline 67). The removed share by the baseline NoteOn count of the label:

   | NoteOns in the label before | Ordinary: labels | Ordinary: removed | All 14 datasets: windows | All 14 datasets: removed |
   | --- | ---: | ---: | ---: | ---: |
   | 1 | 30 | 0.0% | 70 | 4.3% |
   | 2 to 5 | 82 | 20.4% | 161 | 21.4% |
   | 6 to 20 | 48 | 32.5% | 155 | 38.2% |
   | 21 to 50 | 46 | 28.2% | 89 | 36.9% |
   | 51 to 100 | 22 | 24.8% | 36 | 30.4% |
   | over 100 | 4 | 29.9% | 9 | 28.1% |

   Above one NoteOn the path removes between 20% and 38% in every bucket and almost nothing from single-NoteOn labels (the ordinary recording also has 267 labels with none, and the pool 291 windows).
7. **POST HOC: a provable same-pitch overlap bound.** A note shorter than one 64-sample decision cannot exist, so more NoteOns than fit outside the longest hold (plus the hold itself) must start while another same-pitch note is sounding. By that bound 195 of the 5,774 remaining NoteOns (3.4%) overlap, 180 of them in extended-middle label 2 (251 NoteOns over a 3,552.7 ms hold in a 3,600 ms label); the bound is 0 for every ordinary label; and it is the same before and after the path in every window that has any, so the path changes none of it. That is consistent with the path's stated rule that unisons and ambiguous pairs keep their original events, but the rows cannot confirm that. The bound is vacuous for the heavy ordinary labels: label 17's 109 NoteOns over 71,783 samples fit serial chatter with no overlap at all, so a parallel-duplicate-voice reading is not established beyond extended-middle label 2.

## What this does and does not show

- **Shows:**
  - The numbers Codex reported for the stable-note path are what the saved rows say, the offline ledger and the VST3-component run agree on every ordinary label, and the counters reconcile exactly.
  - The label-level gates replicate on all 14 datasets, and the two corpus failures are timing-only.
  - The gate set has a blind spot at the label level: a label can lose its only NoteOn and pass. It happens in 7 labels (4 windows) of three datasets.
- **Does not show:**
  - **Whether any of those NoteOns was a real re-attack.** The rows hold counts and the longest hold, not the NoteOn and NoteOff positions. The check that would decide it is Codex's lane: in these windows compare the per-voice and stable-note NoteOn and NoteOff events with the annotated label starts (from the corpus run's event traces if they were kept, or a bounded replay of just these three datasets).
  - **Anything about physical strings, timing or live readiness.** The corpus report itself lists `physical_string_assignment`, `live_readiness` and `frozen_off_replay_identity` as not measured, and the cause of the two original timing failures is unknown.
  - **That the path is better or worse.** No promotion, no gate change, no new threshold. The seven labels are leads, not exemptions or fit targets.
  - **Anything about the post hoc counts beyond description.** The window grouping is inferred from the rows, the 64-sample minimum note is taken from the ordinary recording's lifecycle and applied to every dataset, and holds are clipped to the label.

## Disclosures

- Not pre-registered (see the top). The script was run once, then revised, then edited once more before anything was committed. The first run counted every label equally; reading its output I found that labels annotated once per string carry identical rows, so the same NoteOn events are counted once per label in the totals and in items 6 and 7. I added a window grouping: consecutive labels of one pitch with at least one NoteOn before the path, equal NoteOn counts in both modes, and length, longest hold and pitch-present samples within 96 samples (1 ms) of the group's first label. The rows carry no start sample, so this is an inference. Constructed has 488 labels in 187 inferred windows (301 merged) and synthetic-four 96 labels in 24; the other 12 datasets, including ordinary, merge nothing, and the ordinary recording is the control (its accounting identity is exact, and the grouping merges 0 labels there). The first run's output was moved aside, not published; its label-weighted numbers are in the JSON's `label_weighted` fields. The second edit only added two output fields (the rows of the lost-NoteOn labels, and the count of labels where the pitch is present with no NoteOn inside); no printed number changed. A quick check outside the script: a 960-sample tolerance gives 185 windows in constructed (187 at 96), and exact equality merges nothing because the labels of one window differ by up to 93 samples in length.
- Outcome data seen before the revision: the first run's label-weighted totals and pooled bucket table, and the rows of the six datasets listed above.
- The sequence-of-pitches observations in item 5 (physical-high all 60, physical-highmid all 56, labels 2, 5 and 7 of physical-high already without a NoteOn) were read straight from the corpus report's rows; they are not fields of my JSON.

## Provenance

Inputs, sha256 prefixes: ledger report `830219144016`, collected verdict `6cb33b4424c4`, corpus report `a4bf4ff24e2b`. Output JSON `2489bb09adc3`; script `8bbcd733a0ec`. The unit checks (19) pass; the script reads only those three files and refuses to overwrite its output.
