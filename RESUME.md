## 2026-11-09 — trace the cross-sample MIDI lane replacement

- Added the bounded `midi-lane-trace` worker task. It observes candidates 47 and 48 separately around samples 202752–204288 of the ordinary recording, using the existing routing and calibrated-output recorder. Both complete OFF replays must match the saved reference, and their complete MIDI and outcome streams must match each other.
- The report retains each raw note-on still outstanding at the window start and each subsequent lane transition without overwriting an earlier pitch. This preserves the prior note 48 when note 47 arrives at sample 203519, before the recorded note-48 release at 203583. Raw transitions do not establish host-delivered ownership; stage observations do not always identify an emission call site.
- The sole diagnostic run is `42604663479`, pinned to source `fc60011805791cac98530cf2e594c4da6e1a563f` and worker `0a0de1990cafca29cf33569bcebb8f3f35c6e5e6`. It is running on GitHub; do not dispatch another. Source run `42604608951` passed native tests, Python contracts and synthetic buffer parity. Collect the small report into `build/github-results/midi-lane-trace-42604663479`; checkpoint: `docs/recovery/github-midi-lane-trace-20261109.json`.

- Six lightweight Python contracts pass, including out-of-window stream drift and missing-conflict rejection. Native compilation and the real recording trace run only on GitHub Actions. No runtime policy, installed output or acceptance limit changes. Next: collect the pinned cloud result, identify the responsible stage, and choose a bounded correction only from the observed cause.

## 2026-11-09 — reduced MIDI ledger cases pass on GitHub

- Source `eca0d03a3e69546f71514205d4d2b4e87b201119` adds two native ledger cases from the saved ordinary MIDI report. CI `42602154059` passed the native tests and production VST3 build/package; portable run `42602154464` passed its replay tests, Python contracts and synthetic buffer parity. No local native execution or installed setting change occurred. Checkpoint: `docs/recovery/github-midi-ledger-reproduction-20261109.json`.
- In both single-channel and per-voice routing, the same-sample replacement delivers note 48 off before note 47 on. The cross-sample replacement instead blocks delivery, suppresses the new note and releases the old note on the next callback. These are reduced fixtures with a seeded old note, not a full-recording or live-host reproduction. They explain why raw event pairing cannot be treated as delivered MIDI duration.
- Next: trace the producer and prior lane ownership at the recorded cross-sample replacement before changing runtime policy. Keep the preview disabled and the installed scoreboard unchanged. The previous corpus still passes label/error, allocation and buffer checks but fails three native timing gates; host delivery and held-duration acceptance remain unmeasured.
- Cleanup is complete: about 5.75 GB net recovered during its measured window, including 618 older session logs compressed losslessly, saving 747 MB. The latest drive check found 92.3 GB available; that later total also reflects other activity. Source, recordings, final plugins, installed tools, credentials, checkpoints and active conversations are preserved.

## 2026-11-09 — protected labels pass; timing and MIDI holds remain open

- GitHub corpus run `42592853316` completed at source `01cfb12d8b3b59a8635b26749059113d5768708e`. All 42 label/error comparisons pass, all 42 OFF references match the preceding corpus, all 56 buffer comparisons match, and all 28 timed modes report zero allocations/frees and identical scored output. Thirteen of fourteen datasets are bit-identical OFF/ON. Ordinary matches rise 145385 to 145395/528632 (27.502119% to 27.504010%); wrong-note outputs fall by 74 and wrong-string outputs by 2, with gap extras unchanged.
- The candidate remains rejected: only 11/14 paired native timing gates pass. Constructed OFF reaches 375700 ns, physical-highmid OFF 352144 ns, and extended-high ON 333649 ns, each with one deadline overrun against the unchanged 333333 ns maximum. All p99 gates pass. A successful workflow is not acceptance. Do not repeat the unchanged job to seek a cleaner timing result. Checkpoint: `docs/recovery/github-projection-preview-corpus-20261109.json`.
- GitHub ordinary MIDI screen `42598238121` also completed. Its full OFF/ON replay hashes match the preceding trial, preserving the ten-frame gain. The raw streams contain 11903 OFF transitions and 11895 ON transitions. Each has 617 note-ons before lane release and 617 unmatched note-offs, so held-duration comparisons are suppressed. The one open note at EOF in each stream is not proof of a stuck note. Host delivery and duration acceptance remain unmeasured. Checkpoint: `docs/recovery/github-ordinary-midi-lifecycle-20261109.json`.
- Same-sample event ordering can be repaired by the host ledger, but the saved report also contains cross-sample lane conflicts. Next: reproduce one such conflict against the native ledger, then trace its producer before choosing a runtime correction. Keep the preview disabled, the installed scoreboard unchanged and the fixed label/error, allocation, buffer, timing and host gates intact. Both small reports are retained locally; larger evidence stays on GitHub. A bounded attempt to retrieve the two small MIDI streams timed out without retaining an archive.

## 2026-11-09 — retain complete MIDI streams in the ordinary screen

- The ordinary preview screen now accepts the same optional `--capture-midi-lifecycle` switch as the corpus runner. It pairs the full OFF and ON detector event streams before cropping the diagnostic traces, then retains both complete MIDI streams as compressed artifacts. A note that starts before the diagnostic window can therefore contribute its actual held duration inside a label.
- The report compares raw held samples, longest holds and retriggers. Pairing anomalies suppress duration comparisons; incomplete event capture fails the run. These are detector events before host delivery. Labeled-frame screen eligibility remains separate from MIDI duration, and neither promotes the plugin for live use.
- Added contracts for notes crossing the diagnostic window, incomplete streams and pairing anomalies. GitHub run `42597330722` passed at source `d51b71afaaeb38d4eb5b7020b7dbb8e254ae20f5`. The first run found that the fixture supplied candidate rows outside its requested window; the fixture now honors those bounds. Native tests, replay contracts and the synthetic buffer smoke passed on GitHub. Capture remains off by default, with no native algorithm or installed setting change. No full MIDI hold measurement has been collected yet. Checkpoint: `docs/recovery/github-ordinary-midi-lifecycle-20261109.json`.
- GitHub screen `42598238121` is pending behind the sole corpus run `42592853316`. The screen pins source `d51b71afaaeb38d4eb5b7020b7dbb8e254ae20f5` and worker `cd72acf856a61022d8f44d303533ca148e1546df`, with `midi_lifecycle=true`. Both jobs share the existing serialized queue. Do not dispatch duplicates.
- Collect each small report once after completion. The duration screen must retain the preceding ordinary OFF and ON replay hashes before its hold and retrigger measurements can be attributed to the same trial. Pairing anomalies invalidate duration comparisons. Protected corpus, allocation, buffer, native timing and live-host gates remain separate; the installed plugin is unchanged.
- Storage cleanup is complete. The latest check found 89.11 GB free (83.0 GiB). The cleanup record reports about 5.75 GB net recovered, including 618 older session logs compressed. Source, recordings, installed plugins, recovery checkpoints and active conversations are preserved.

## 2026-11-09 — measure detector MIDI holds separately from tuner matches

- Added optional `--capture-midi-lifecycle` to the corpus runner and `midi_lifecycle` to the worker dispatch. It captures the full detector event stream only on untimed 512-sample references. The timed 32-sample and buffer-comparison 1024-sample runs remain uninstrumented. Capture is off by default; no native algorithm or installed setting changes.
- The reducer uses the recording's sample clock and half-open label intervals. It reports simultaneous expected routing lanes, raw hold duration, retriggers, event-pairing anomalies and notes open at the recording boundary. It validates native event order and completeness. Unassigned voices remain pitch-keyed and cannot establish a nonzero string mask. These are detector events before host delivery, not tuner frame scores or proof of stuck notes.
- GitHub Actions run `42594962318` passed at source `3daccb2726e4f38558250e41112951d5e5712766`: 97 Python contracts, both native suites and the synthetic buffer-parity smoke. The canonical workflow is synced to worker commit `a96a95786ce9faed97b9aa8b62ee4049a8fc5832`. No MIDI lifecycle corpus measurement has been collected yet; onset/release tolerances and live acceptance remain unmeasured. Existing label/error, allocation, buffer and timing gates are unchanged.
- Protected corpus run `42592853316` remains the sole active corpus job at its original source. Do not replace or duplicate it. Collect its small report first; any later lifecycle capture must have its own pinned provenance.

## 2026-11-09 — preview correction enters the protected corpus

- GitHub run `42592853316` was dispatched once at source `01cfb12d8b3b59a8635b26749059113d5768708e`, worker `6ab8d23234ba1509f4674543977a4d5740f9553b`. It screens the preview correction across fourteen datasets at buffer sizes 32, 512 and 1024. The ON run enables only `--diagnostic-projection-preview-admission`; frozen-cue and reset corrections remain off. The trial stays disabled in the installed plugin.
- The corpus runner retains its label/error, allocation, buffer and native timing gates. Both timed modes must meet p99 <=166666 ns, maximum <=333333 ns and zero deadline overruns. The new contracts also check that a timing failure in either mode rejects the native gate. Python and workflow shell syntax pass locally; runtime tests and replay run on GitHub.
- Results are pending. Collect the small report once into `build/github-results/assignment-context-corpus-42592853316` and compare OFF hashes with the saved references. Keep the larger evidence artifact in GitHub. Do not launch another run. Source portable tests are recorded as `42592792294`.
- The ordinary screen already gained ten matched frames with no label loss and fewer false outputs. This wider job does not establish acceptance merely by completing: any label/error, allocation, buffer or timing failure keeps the candidate rejected, and live host/MIDI checks remain separate. Installed scores are unchanged. Checkpoint: `docs/recovery/github-projection-preview-corpus-20261109.json`.

## 2026-11-09 — preserve physical context in the preview trial

- The default-off preview-admission trial now passes the original selection into physical string assignment. Preview filtering still applies to downstream unison and calibrated-note ownership. This changes one call site; onset thresholds and collision guards are unchanged.
- The completed routing trace showed spectral support disappearing before the first wrong-string output. Filtering the physical assignment can relocate an active peer and change spectral ownership, but the saved report does not identify the exact proposal rejection. This trial tests that interaction; it does not claim a verified cause or improvement.
- GitHub run `42591352851` passed the ordinary screen at source `a0737ff41ac9ace594c4dc2741752bb4382c068f`: matches rose from 145385 to 145395/528632 (27.502119% to 27.504010%), with no lost labels. Wrong-note outputs fell by 74, wrong-string outputs by 2, and extra outputs during gaps were unchanged. The OFF replay was bit-identical to its saved reference. The earlier nine-frame loss on label 54 did not recur.
- All 72 worker Python contracts, the native onset-boundary test and the trace-identity test passed. Source replay run `42591312155` and native/VST3 build run `42591311929` also passed. This is an offline screen, not promotion: protected corpus, allocation, buffer, native timing and live-host acceptance remain pending for this candidate. The installed scoreboard is unchanged.
- Full provenance and counts are in `docs/recovery/github-projection-preview-context-20261109.json`. Only the small report artifact was downloaded; the larger trace archive remains in GitHub.
- The runner records the trial revision as `full_physical_assignment_context`. Earlier preview and routing reports remain historical results from their pinned source commits. Do not dispatch the historical routing task against this changed trial and expect its rejected ON hash to match.
- Cleanup is complete: about 5.75 GB net recovered, including 618 old session logs compressed. The fresh check found 87.53 GB available. Source, recordings, installed tools, checkpoints and active conversations remain preserved.

## 2026-11-09 — routing trace identifies lost spectral support

- GitHub diagnostic `42589153942` completed at source `2073028474c48fb7af39ea52486184ce4dcd4d40` and worker `64e2bcb4a9e0f0ce1afcb6089cb575a4975f10ae`. Both complete ordinary OFF and rejected ON replay outputs are bit-identical to their recorded references. The 72 worker Python contracts, focused native trace test, source CI `42589112388` and portable CI `42589112295` passed. Checkpoint: `docs/recovery/github-routing-trace-20261109.json`. This completed job needs no rerun or repeat download.
- At sample 945215, note 52 has the same assigned mask 1 and pre-render continuity mask 2 in both runs. Its spectral mask is 2 in OFF but 0 in ON. ON therefore renders mask 1 and moves MIDI from lane 1 to lane 0. Continuity changes to mask 1 afterward. At 945343, spectral mask 2 returns and MIDI returns to lane 1. Prior continuity-mask loss is ruled out as the immediate cause of this first episode; the upstream reason spectral support disappears still needs a source-level explanation.
- The earlier trial remains rejected: whole-recording matches improve by 44, but label 54 loses 9. Installed scores and runtime policy are unchanged. The recorder is disabled by default and excluded from production builds. Other protected corpora, allocation, native timing and live-host gates were not rerun for this diagnostic.
- Next: inspect spectral proposal admission at the first transfer, then make a default-off correction only if it yields a full-recording gain with zero per-label loss and no increased wrong-note, wrong-string or extra gap outputs. Follow with protected corpus, buffer, allocation, timing and host checks before promotion.
- Storage: only the small report artifact was downloaded; the larger trace artifact remains on GitHub. The earlier cleanup recovered about 5.75 GB net and compressed 618 old session logs. Source, recordings, checkpoints and active conversations remain preserved.

## 2026-11-09 — preview ownership trial rejected; routing regression isolated

- GitHub run `42586000548` completed successfully at source `d0646b8c70f2e674c5b9f158222575c49bf2e2a9` and worker `18cfddfbcdb80c7d93ba4cc74093fd07d1a51835`. The runtime trial is rejected. Its report and bounded traces are final; do not poll, download or repeat this completed job. Checkpoint: `docs/recovery/github-projection-preview-20261109.json`.
- Ordinary matches rose from 145385/528632 (27.5021%) to 145429/528632 (27.5104%), a gain of 44 frames. Wrong-note outputs fell by 112, wrong-string outputs by 34, and extra outputs during unlabeled gaps stayed at 62856. Label 54 nevertheless fell from 467/1122 to 458/1122: ten lost frames and one gained frame. Aggregate gains do not offset that regression. Installed output and the scoreboard are unchanged.
- The retained traces identify actual MIDI lane transfers. Logical note 52 remains selected and active with the same assigned mask in every lost frame, but ON moves its output from the expected lane 1 to lane 0. In the first episode, note 41 changes lanes at sample 945151, note 52 moves at 945215, and returns at 945343. The one-decision delay is consistent with the continuity update after rendering; the deciding spectral/continuity masks are not captured, so that internal mechanism remains an inference. Diagnosis: `docs/recovery/github-projection-preview-diagnosis-20261109.json`.
- Target label 55 improves from 267/1122 to 290/1122. Active-source matched snapshots rise from 12 to 46 while preview-only matches fall from 255 to 244; logical note 42 never activates. The trial records six calibrated apply/revert cycles and actual transient note-42 MIDI. This does not establish stable held notes or live readiness.
- The full ordinary OFF replay is bit-identical to its reference. All 68 worker Python contracts and both focused native suites passed. Source CI `42585948467` and portable run `42585948562` passed. Other protected datasets, buffer, allocation, native timing and host gates were not rerun for this trial. The diagnostic flag remains default off and unavailable in production builds.
- Next: capture note 52's spectral, continuity, cached group and desired output masks around the first transfer in one default-off GitHub diagnostic, retaining exact OFF identity. Any later runtime fix must gain whole-recording matches with zero per-label losses and no increased wrong-note, wrong-string or extra gap outputs, then pass the protected corpus, allocation, buffer, timing and host gates. Do not rerun the rejected trial unchanged.
- Storage cleanup is complete: about 5.75 GB net recovered, including 618 older session logs compressed; the fresh check found 84.58 GB available. Keep reports and the three small compressed traces; the verified redundant evidence ZIP is removed. Recordings, source, checkpoints and active conversations are preserved.
- The earlier notification attempt at `2026-11-09T08:27:28.856346Z` remains ambiguous: publication success was reported without a confirmed inline receipt. Its captured output is retained and that message was not retried. Reliable live use and overall completion remain unmeasured.

## 2026-11-09 — calibrated retunes traced; baseline preserved

- GitHub diagnostic `42583044596` completed successfully at source `4064cf15c1841f725512b4e408e2337670b50464` and worker `d72570b88c93367366058b5cd3a3c8af91dbecdb`. The report is collected once and final. Summary: `docs/recovery/github-calibrated-output-trace-20261109.json`. Do not rerun it.
- The full ordinary recording is bit-identical to the retained OFF reference both without and with tracing: 145385/528632 matches (27.5021%), wrong-note/wrong-string/gap-extra counts 164263/92653/62856. Label 55 remains 267/1122 (23.7968%). No runtime rule or installed output changed.
- All seven returns from output note 42 to 41 execute the untrusted-projection branch after two eligible ticks. Each application uses assigned-string mask 1 and each return mask 4, while phase changes by less than 0.42 cents. None of the 250 collision-reset observations changes output. Changing string assignment and its calibration are the next suspect; this does not yet establish why assignment moved or justify holding an unsupported note.
- The baseline now has actual MIDI capture. Its 14 note-42 ons and 14 offs match the earlier evidence-retention trial exactly in sample, kind and lane. That trial remains rejected: its 49 lost target matches came from previews, and the full recording lost matches on 26 labels and added 659 extra outputs during unlabeled gaps.
- All 66 worker Python contracts and both focused native tests passed. Source CI `42583014795` passed and packaged the production VST3; portable run `42583014584` passed, including 69 Python tests and both native suites. The package remains uninstalled. Other protected corpora, native timing and live-host acceptance were not rerun for this diagnostic.
- Next: reconcile string assignment and calibrated projection at the captured lane transfers before choosing a runtime change. A default-off trial needs positive labeled gain, zero per-label loss and no increased wrong-note, wrong-string or gap-extra output, followed by corpus, allocation, buffer, native timing and live-host gates. Reliable live use and overall completion remain unmeasured.

## 2026-11-09 — transient MIDI attributed; preview regression separated

- The retained traces from final GitHub trial `42578776712` are collected. The complete evidence ZIP matched its published digest; the three small compressed traces are retained and the redundant 4,683,530-byte ZIP is removed. Provenance: `docs/recovery/github-evidence-retention-result-20261109.json`.
- Label 55 still falls from 267/1122 matches (23.7968%) to 218/1122 (19.4296%). Inactive-preview matches account for the entire loss: 255 to 206. Matched snapshots with an active logical source remain 12, and logical note 42 never activates. A snapshot is not a held-MIDI measurement; the voice `cents_valid` field indicates pitch-bend validity, not activity.
- All 14 captured note-42 ons match an active logical note-41 source at the same sample and lane. Seven short cycles retune 41 to 42, move it from lane 0 to lane 2, then return to 41. The 14 paired lifetimes last 64–192 samples at 96 kHz. The baseline lacks an actual MIDI-event trace, so no before/after MIDI improvement is claimed. Diagnosis: `docs/recovery/github-evidence-retention-lifecycle-20261109.json`.
- The Python summary now separates preview matches, logical candidate activity and actual MIDI events. Six focused tests pass, including invalid pitch-bend/activity assumptions, retuned neighboring sources, ambiguous sources and missing event capture. This is saved-trace analysis; no native replay or build ran locally.
- The calibrated-output eligibility gate clears pending consensus but leaves the current output note. A later untrusted projection can revert after two eligible ticks; a collision can revert immediately. The post-lifecycle trace does not identify the executed reset branch, so longer hysteresis is not yet justified. Next: expose that branch with default-off diagnostics before changing calibrated-note stability, retaining full OFF identity on GitHub Actions. Do not repeat the rejected collision rule or change onset thresholds from preview matches alone.
- Evidence retention remains rejected: 26 labels regress and gap-extra output rises by 659. Installed output, default-off behavior and the scoreboard remain unchanged. Every later runtime screen still needs a labeled gain without label loss or increased false outputs, then protected corpus, allocation, buffer, native timing and live-host checks. Reliable live use and overall completion remain unmeasured.

## 2026-11-09 — direct evidence retention rejected; cleanup complete

- Existing GitHub trial `42578776712` completed at source `c5268d309e729aad7611d6d33172a10a18a13080` and worker `c6e46816fa646b7a24d5504a5c4325234ffea92f`. The small report is collected; do not rerun this screen. Result and artifact provenance: `docs/recovery/github-evidence-retention-result-20261109.json`.
- Ordinary matches rose from 145385/528632 (27.5021%) to 147156/528632 (27.8371%), a gain of 1771 frames (1.2181% relative). Wrong-note outputs fell 164263 to 163119 and wrong-string outputs fell 92653 to 91807, but extra outputs during unlabeled gaps rose 62856 to 63515. Matches fell on 26 labels. The trial is rejected; aggregate gains do not offset these failures. Installed output and the scoreboard remain unchanged.
- The target label 55 fell from 267/1122 to 218/1122 matches. Retaining direct evidence removed the selected/direct/inactive zero-evidence observations and raised peak evidence from 44 to 112, but the candidate state still recorded no active decisions. Actual MIDI transitions are present in the new trace. Candidate state alone does not prove absence of MIDI, correct string identity, stable note locking or freedom from stuck notes. Do not repeat the earlier broad inference that this label produced no MIDI onset.
- The diagnostic switch remains off by default and is excluded from production builds. It retains direct evidence during energy dips while blocking onset and preserving the existing evidence threshold, fresh attack delay and assignment rules. The OFF full-recording replay is bit-identical to the retained reference. The trial passed 61 Python contracts and both native lifecycle tests. Other protected datasets, allocation, buffer parity, native timing and live-host acceptance were not measured for this trial.
- Next: inspect the retained event/reset window to explain transient MIDI and label losses before another implementation. A new screen needs an identical OFF reference, a positive labeled gain, no per-label loss and no increase in wrong-note, wrong-string or gap-extra output. The compressed trace artifact remains on GitHub; its identifier and digest are in the result summary.
- Portable replay run `42578754392` passed. In source CI run `42578754471`, the native C++ job passed; the source contract rejected machine-specific paths in this checkpoint. Commit `9562317` corrected those paths, and the failing contract passed locally. No native build or replay ran locally.
- Storage cleanup is complete: about 5.75 GB was recovered, including compression of 618 older session logs. Source, recordings, final plugins, installed tools and active sessions remain. Cleanup receipt: `~/.local/state/researchos/space-cleanup-20261109/summary.json`. Reliable live use is unverified; overall completion is not measured.

## 2026-11-09 — ordinary assignment diagnosed; trace archives reduced

- GitHub run `42573296579` completed at source `a5853d68774611c5cc93deeee73317d072c127ac`. The traced and untraced full ordinary replay are bit-identical: 145385/528632 labeled matches, with wrong-note/wrong-string/gap-extra counts 164263/92653/62856. The small report is final and collected; do not repeat the job or resume the full-artifact download. Summary: `docs/recovery/github-ordinary-assignment-20261109.json`.
- Original label 54, note 52, matches 467/1122 frames (41.6221%); its pitch is selected in 1078/1122 (96.0784%). Pitch selection is not correct string assignment. Of 67 sampled assignment rows, 30 render the correct string. Among the 37 misses, 16 reserve the expected string for a coasting voice, 20 prefer another available string, and one has no valid joint assignment.
- Reconstructing the frozen assignment states reproduces all 66 valid native decisions. Removing adjacent note 41 changes 20 assignments but recovers none: correct target assignments remain 3/66. This label-informed probe keeps costs and reservations fixed; it is neither a runtime rule nor an audio replay. Removing that note alone is rejected as the next fix.
- The retained 205-row excerpt is `docs/recovery/github-ordinary-label54-assignment-20261109.json.gz` (122451 bytes), verified against its uncompressed local source. It came from a partial download: the full remote ZIP and member hash were not verified. Removing the partial ZIP and replacing the plain excerpt saved 3842384 bytes net. Future traces retain the requested sample window, all competing notes and exact row bytes only after full replay identity and selection-coverage checks. Separate hashes describe the full capture and retained window. All 13 focused Python tests pass; no native processing ran locally.
- Next: inspect which coasting voice reserves the expected string and how that ownership relates to the rendered MIDI mask. Any later cloud trial must improve labeled matches without lost protected labels or increased false outputs, then pass allocation, buffer, native timing and live-host gates. Installed output, default-off behavior and the scoreboard remain unchanged. Live readiness and overall completion are not measured.

## 2026-11-09 — protected outputs retained; timing and identity screen rejected

- GitHub corpus run `42566960267` completed at source `7bd8e8a42360b9bc1adc8c0c52d8c7ddfa2dc396`. All 84 saved replay files are bit-identical to the previous corpus run. All 42 label/error comparisons and 56 buffer-parity checks pass. Both timed modes preserve output and report zero C/C++ processing allocations or frees. Summary: `docs/recovery/github-guard-cell-corpus-20261109.json`.
- Paired native gates pass on 9/14 datasets. Ordinary OFF/ON maxima are 451280/691478 ns, constructed 669937/576562 ns, physical-long OFF 592727 ns, extended-high ON 375662 ns and physical-four ON 437678 ns; each exceeds the unchanged 333333 ns maximum and has deadline misses. All p99 measurements pass the 166666 ns limit. Physical-high now passes timing but still matches 0/28043 labeled frames. A successful recovery job does not mean acceptance; promotion remains rejected.
- Isolated identity run `42571625288` completed at source `642eaaacbc45fac19b59f4a20937862685d68695`. Only 2/6 feasible strings supply usable training prototypes. The screen admits 0/22 held-out attacks, wrongly admits none and abstains on all 22. These are attacks, not labeled frames. The fixed screen is rejected; do not bypass unknown competitors or integrate these features. Summary: `docs/recovery/github-partial-identity-20261109.json`.
- Both small reports were collected once. Do not poll, download or repeat these completed jobs. Installed output and the scoreboard remain unchanged. Reliable live use and overall completion are not measured.
- The original-label diagnostic is complete in run `42573296579`; see the newer ordinary-assignment entry above. Full replay identity passes and original label 54 matches 467/1122 frames. The earlier preparation checks passed; no duplicate run is needed.
- Storage cleanup is complete: disposable downloads, caches and old C++ intermediates were removed; 618 older session logs were compressed. Source, recordings, final binaries and active sessions are retained. Restore instructions: `~/.codex/session-archives/m3-20261109/README.md`.

## 2026-11-09 — isolated string identity screen prepared

- `tools/portable_partial_identity.py` tests whether upper-harmonic offsets distinguish all six strings that can play MIDI note 52. It uses 28 recorded attacks: one ascending attack per string supplies six training prototypes; 22 descending and checkpoint attacks are held out. Measurements use the existing harmonic audit. Weak or search-edge partials remain unknown; every feasible competitor must have a measured prototype before any assignment is admitted.
- The exploratory screen requires at least three valid windows and 75% valid coverage, upper-partial power ratios of at least 0.001, and offsets within 35 cents. Held-out assignment requires RMS distance at most 3 cents and a nearest-rival margin of at least 1 cent. It passes only if all 22 held-out attacks are admitted to the correct string. These are diagnostic limits, not plugin acceptance thresholds; same-session isolated attacks do not establish unison separation, labeled-frame gains or live readiness.
- The five focused tests pass. YAML parsing, workflow shell syntax and the synchronized worker copy pass. The GitHub task `partial-identity` runs the audio measurement on the standard CPU runner and shares the existing serialized processing queue. Existing corpus run `42566960267` continues without restart.
- Input release `partial-identity-note52-20261109` contains cropped recordings and provenance. Bundle size is 20,164,031 bytes; SHA-256 is `4f7efa2ea0ba4d9025ff35c22d2bc48c9a5199a1ebb9b83c422c1bf10038829e`. Original recordings and labels are retained. The source and worker repositories are public as authorized.
- Collect the isolated screen report once its recorded GitHub job completes. A failed screen rejects these features under the fixed limits; a pass requires a later real-unison and absent-string control. Installed output, default-off behavior and the scoreboard remain unchanged. The protected corpus, native timing and live-host gates remain separate.

## 2026-11-09 — GitHub worker is public

- `Ajuntanaga/m3-offload` is public and stays public between runs, as requested. An unauthenticated GitHub API read confirms public visibility. Recording bundles, calibration, release assets, Actions logs and published artifacts are now public. The source repository was already public.
- Worker `2b102bf853cdc8f7aa157a38a7e0dca01c2c5278` updates the public-repository guard and keeps the existing concurrency group, standard Ubuntu CPU runner, read-only token permissions and acceptance limits. The canonical workflow is synchronized, YAML and shell syntax checks pass, and the guard passes against the live repository. Documentation commands and acceptance requirements are preserved.
- Existing corpus run `42566960267` remains in progress at source `7bd8e8a42360b9bc1adc8c0c52d8c7ddfa2dc396`, using its original worker commit. It was not restarted. Its billing treatment after a mid-run visibility change is unverified. Collect the small report once when complete; keep the installed scoreboard and default-off unchanged.

## 2026-11-09 — boundary guard controls passed; protected corpus running

- Source `7bd8e8a42360b9bc1adc8c0c52d8c7ddfa2dc396` is pushed. It precomputes the enabled lower/upper boundary guard cells during configuration, retains their update order and arithmetic, and adds a native regression against the former enabled scan across reset and sample-rate reconfiguration, including no enabled guards.
- Private acceptance run `42566485639` passed and its small report was collected once. All 60 replay hashes match the previous source, all 30 label/error comparisons and 40 buffer-parity checks pass, and all ten paired native gates pass with zero processing allocations/frees and zero deadline misses. Worst p99 is 115,130 ns against 166,666 ns; worst maximum is 315,587 ns against 333,333 ns. Summary: `docs/recovery/github-guard-cell-controls-20261109.json`. Do not poll, download or repeat this completed job.
- Public CI `42566471834` passed native tests, production VST3 build and packaging. Portable run `42566471807` also passed. Shared-runner variation prevents attributing the timing change solely to this optimization; no new note gain is claimed.
- Existing private full-corpus run `42566960267` is processing the same source. Collect its small report once to `build/github-results/guard-cell-corpus-42566960267`. Require prior OFF/ON output hashes, no lost labels or increased false outputs, buffers 32/512/1024 parity, zero C/C++ allocations/frees and both modes within p99 <=166,666 ns, maximum <=333,333 ns, zero misses on all fourteen datasets. Do not launch duplicates. The installed plugin and default-off remain unchanged; primary match gains and live host/MIDI gates remain open.

- Notification attempt at `2026-11-09T05:24:15.375183Z` was unconfirmed: the helper reported publication success but could not confirm an inline receipt. The 3,398-byte preview and captured output are retained locally; no retry was made. Do not resend this message. Capture: `build/modal/notification-publisher-20261109T052415375183Z.json`.

## 2026-11-09 — quiet-octave spike did not recur in CPU diagnosis

- Private GitHub run `42565379726` completed at source `c83242badc31305ff62b5b21a38db425473f0640`, worker `7a5a9da2e21ff07ee7fad6fb363b62966243677a`. All 52 contracts and the replay build passed. Public portable run `42565225081` passed. Small report collected once; do not poll, download or repeat these jobs. Summary: `docs/recovery/github-quiet-octave-timing-20261109.json`.
- Quiet-octave OFF/ON retain their exact saved hashes and 2,070/2,079 of 6,900 labeled matches (30.000%/30.130%). Wrong-note, wrong-string and gap-extra counts remain 841/1,314/318 OFF and 841/1,305/318 ON. Both modes have zero observed C/C++ processing allocations/frees. The upper note remains 0/3,450; the existing gain is nine lower-note matches, not an optimization gain.
- Diagnostic OFF wall p99/max are 96,494/157,208 ns; CPU 96,840/157,693 ns. ON wall p99/max are 92,213/219,278 ns; CPU 92,409/219,812 ns. Each mode has 10,650 blocks and no wall or CPU misses. CPU resolution passes. The earlier uninstrumented ON 604,791 ns spike did not recur; its cause remains unresolved and its acceptance failure remains in force. Diagnostic timing cannot establish a production speedup or live readiness.
- Next: select one output-preserving work reduction from the retained signal-observation/fine-frequency stage evidence before further acceptance testing. Require all 60 held-out output hashes, unchanged label/error safety, buffers 32/512/1024, zero allocations/frees, and both uninstrumented modes below p99 166,666 ns and maximum 333,333 ns with no misses. Then check the affected protected corpus. Do not chase a pass with unchanged timing reruns. Physical-high timing, primary match gains and live host/MIDI gates remain open; installed output and default-off are unchanged.

## 2026-11-09 — conditional activity scan preserves every held-out output

- Source `75be07aad00fae8b98b23a336e13d371f089eefb` is pushed. Private run `42564733545` is final FAILURE solely at native timing acceptance; collection and all 50 contracts passed. Public CI `42564718747` and portable replay `42564718685` passed. The small report was collected once; do not poll, download or repeat these jobs. Summary: `docs/recovery/github-activity-scan-controls-20261109.json`.
- All 60 OFF/ON replay files at buffers 32/512/1024 are bit-identical to the prior held-out run. All 30 label/error comparisons and 40 buffer-parity checks passed. All 20 measured modes preserve output with zero processing allocations/frees and passing p99. Nearby target matches remain 815 to 835/3,450 OFF/ON; the scan optimization adds no note gain.
- Equal-level octave OFF/ON p99 are 130,464/128,029 ns and maxima are 200,424/204,935 ns, with no misses. Quiet-octave ON p99 is 106,178 ns, but maximum is 604,791 ns with one miss in 10,650 blocks, exceeding 333,333 ns by 271,458 ns. Nine of ten paired native gates pass; promotion is rejected. Shared-runner variation prevents attributing timing differences solely to the scan optimization.
- Prepared selection of either retained octave pair for the existing bounded CPU diagnostic. The next run must select `control=octave_-12dB`, preserve the new full OFF/ON hashes and explain CPU work versus wall delay. Nineteen focused Python contracts pass. Do not run another unchanged acceptance sweep. Full protected-corpus/physical-high timing, primary match gains and live host/MIDI gates remain open. Installed output and default-off behavior stay unchanged.

## 2026-11-09 — stage diagnosis collected; conditional activity scan prepared

- Private stage diagnostic `42558357302` is final SUCCESS at source `2351dd721a1cffb14a535a0fca7b6d7d29f85655`, worker `0c80fa8230e73b9248b65bc32deb4ce1883145df`. All 50 contracts passed. Public CI `42558343299` passed native tests and production VST3 packaging; portable run `42558343532` passed. Small report collected once; do not rerun or download these jobs. Summary: `docs/recovery/github-octave-stages-20261109.json`.
- Both octave modes retain the complete saved replay hash, 2,439/6,900 matches (35.348%), and wrong-note/wrong-string/gap-extra counts 1,370/4,311/630. Every processing allocation/free count is zero. Instrumented OFF wall p99/max are 193,867/261,137 ns; ON is 243,660/358,681 ns with one deadline miss. ON CPU maximum is 359,545 ns. These clock-heavy diagnostic numbers cannot pass native acceptance or establish a production speed change.
- The slowest ON block includes signal observation 64,729 ns, fine-frequency work 57,726 ns, voice lifecycle 40,560 ns, and activity/reset bookkeeping 29,124 ns. Multiple stages contribute; no single cause for the earlier spike is established. The ordinary per-sample activity scan is unnecessary when energy already decides signal presence.
- Prepared a semantics-preserving short circuit: scan activity only above the absolute floor and below the decay ratio; stop at the first active voice. No cached state, thresholds or assignment rules change. Next: push this source and run the existing uninstrumented held-out controls on GitHub once. Require all saved OFF/ON output hashes, unchanged labels/errors, buffers 32/512/1024, zero allocations/frees, p99 <=166666 ns, maximum <=333333 ns and zero misses. Only then check the affected protected corpus. Installed output stays unchanged; physical-high, primary match gains and live host/MIDI gates remain open.

## 2026-11-09 — octave CPU spike measured; timing remains open

- Private GitHub diagnostic `42557095189` completed at source `f16eea70cabfe50de9576750123fa4849112a44c` and worker `15ebda95b633a4cfaa3f7184cd3f8ecbf16ed1f8`. All 48 Python contracts and the replay build passed; public portable workflow `42557057874` passed at the same source. The small report was collected once into `build/github-results/octave-timing-42557095189`. Both jobs are final; do not poll, download or repeat them. Summary: `docs/recovery/github-octave-timing-20261109.json`.
- Equal-level octave OFF and ON both match their saved full replay hash. Matches remain 2,439/6,900 (35.348%); wrong notes, wrong strings and extra outputs during unlabeled gaps remain 1,370, 4,311 and 630. All observed processing allocation/free counts are zero. These are offline measurements; installed output and default-off behavior are unchanged.
- OFF wall p99/max are 138,785/212,623 ns and CPU p99/max are 139,289/213,412 ns, with no deadline misses. ON wall p99/max are 128,092/377,130 ns and CPU p99/max are 128,333/377,591 ns, with one wall and one CPU deadline miss in 10,650 blocks. The unchanged maximum is 333,333 ns; ON exceeds it by 43,797 ns in wall time and 44,258 ns in CPU time. The CPU clock passes its resolution check, although its bracket includes wall-clock-read overhead.
- The ON slow block ends at sample 225,600 and records a scheduled fine-frequency update, two active candidates and 15 selection transitions. That state does not identify the expensive operation. The CPU miss cannot be dismissed as solely runner descheduling. Diagnostic collection passed; native acceptance did not. The prior uninstrumented octave OFF maximum of 373,987 ns and physical-high ON maximum of 469,120 ns remain failed acceptance evidence.
- Next: isolate detector, fine-frequency and cue stage costs on this saved octave OFF/ON pair with one bounded GitHub Actions diagnostic. Require retained full replay hashes, unchanged labels/errors and zero observed allocations/frees. Then optimize an identified stage and check both modes without instrumentation against p99 <=166666 ns, maximum <=333333 ns and zero misses. Keep physical-high, match-improvement, live host and MIDI lifecycle gates open. Do not lower string-admission thresholds or repeat unchanged timing runs to seek a pass. Reliable live use and overall completion are not measured.

## 2026-11-09 — held-out control gains reproduced; timing still rejects promotion

- Private GitHub run `42555591900` is final at source `77fa7dcca2b79000fffe23c9b9afe77bfa8b0519` and worker `072c764eccdf9976006df04b2fe235e4d05810d7`. Compilation and all 44 Python contracts passed. Public portable run `42555532390` passed at the same source. The small result artifact was collected once into `build/github-results/heldout-controls-42555591900`; do not poll, download or rerun these completed jobs. Summary: `docs/recovery/github-heldout-controls-20261109.json`.
- All four original input hashes and ten regenerated mixture sample hashes match the retained held-out reference. The four-input bundle is 1,962,867 bytes, SHA-256 `692b6bdd8b78fb2193489c6597ca413630c11ab9f3f835569e7f55eacbbf1b3d`, retained at `build/recovery/heldout-controls-20261109.tar.gz` and verified in the private release. The redundant upload copy was removed only after the server digest matched. This restores inputs, not the missing historical binary or feature sidecars. These are independently plucked crops from the same session, not new-session coverage.
- With calibration and no spectral templates, the nearby-note target improved from 815/3,450 (23.623%) OFF to 835/3,450 (24.203%) ON: +20 frames, +0.580 percentage points, +2.454% relative. Whole-mixture matches rose from 2,987 to 3,007/6,900; wrong-string outputs fell from 1,548 to 1,528. Wrong-note outputs stayed at 3,178 and extra outputs during unlabeled gaps at 668. Solo gained 17 target frames (3,219 to 3,236/3,450); the quiet-octave target gained 9 (2,070 to 2,079/3,450). Both gains also removed wrong-string outputs.
- All ten controls preserved labels and error limits at buffers 32, 512 and 1,024; the other seven were OFF/ON bit-identical at each buffer. All buffer parity checks passed. All twenty timed modes preserved output identity with zero processing allocations/frees and passing p99. Paired native gates passed on 9/10 controls (90% of this test gate, not project completion). Equal-level octave OFF reached 373,987 ns against the 333,333 ns maximum, with one missed deadline in 10,650 blocks. ON reached 255,627 ns with no miss. This report has no CPU diagnosis for that OFF miss; its cause is unverified. The earlier physical-high ON maximum of 469,120 ns and its deadline miss also remain failed acceptance evidence.
- Collection succeeded, but promotion is rejected. The installed plugin and default-off behavior remain unchanged. No native build or replay ran on the laptop. Next: prepare a bounded CPU-versus-wall diagnostic for the failed equal-level octave control using its retained OFF/ON output hashes, only on GitHub Actions. Keep native wall-time limits, protected labels/errors, physical-long and exact-three improvement targets, and live host/MIDI lifecycle gates. Do not repeat unchanged acceptance runs to obtain a passing result or treat diagnostic timing as acceptance. Overall completion and reliable live readiness are not measured.

## 2026-11-09 — physical-high timing diagnosis is final

- Private GitHub run `42553868181` completed at source `43c04270019d362c67113017058e184dd1af38ff` and worker `48b0aa16f23771f91a3334289ad21eb806752989`. The small report was collected once into `build/github-results/physical-high-timing-42553868181`; do not rerun or download it again. Summary: `docs/recovery/github-physical-high-timing-20261109.json`.
- Both modes match their retained full replay hashes and report zero processing allocations or frees. OFF wall p99/max are 129513/494617 ns with one missed deadline; ON is 135484/256291 ns with none. The slow OFF block used 147566 ns of thread CPU time, leaving a 347051 ns wall-minus-CPU difference consistent with runner interruption. CPU maxima are 259995 ns OFF and 257872 ns ON, with no CPU deadline misses and usable clock resolution.
- These instrumented results are diagnostic only. They do not explain or erase the earlier uninstrumented ON maximum of 469120 ns and one missed deadline in corpus run `42545080876`. Promotion remains rejected. Public portable workflow `42553839841` passed at the same source. Installed output and recorded scores are unchanged.
- Next: recover the controlled overlap cases from retained inputs on GitHub Actions and measure the current native cue's target-note effect with unchanged labels and false-output gates. Preserve any retained historical input hashes; regenerated outputs get new provenance. Keep native timing and live host/MIDI gates separate. Do not lower string-admission thresholds on the exhausted upper-unison trace.

## 2026-11-09 — target the remaining physical-high timing failure

- The core/timing runner now honors its selected dataset; previously it always ran physical-long. Both OFF and ON require retained block-32 references before processing starts. References for all fourteen recordings were extracted from final GitHub corpus run `42545080876`, with its source and report hash preserved in `docs/recovery/github-core-references-20261109.json`. This adds no new measured score or acceptance claim.
- Seventeen focused Python contracts pass, including selected recording paths, paired references, output identity, allocation failures and diagnostic-only timing. No native processing ran locally.
- Next: dispatch one private GitHub `timing-diagnosis` for physical-high at this source. Collect CPU time, phase and slow-block state to distinguish computation from runner interruption. The earlier ON maximum of 469120 ns and one deadline miss remain failures; diagnostic timing cannot replace acceptance. Record the exact run under `portable_compute.github_worker` in `build/modal/current-status.json`. Installed output remains unchanged.

## 2026-11-09 — corpus recovery complete; one timing gate still fails

- The reported native CI failure is fixed. Two tests expected 90 trace columns after the format expanded to 93; source `996596e4f03826f0243631e7e7bde52b43fd3e19` passed public CI `42547835491` and portable replay workflow `42547835417`. The NumPy dependency is installed before Python comparison tests. The separate Node.js warning is addressed by updating the artifact uploader to `actions/upload-artifact@v7` in the public workflows and private worker template; source `e50210d67472f1a1ab03983866025bee9d62a9f0` passed CI `42550704499`, portable replay `42550704442` and Linux configuration `42550704358`. The production VST3 and diagnostics uploaded successfully, and the native CI check has no annotations. The private worker template is synchronized; no private job was launched for this uploader-only change.
- Full-corpus run `42545080876` completed at source `96509a4c8c212f2587865f5cd9d78164da0f0167`. All fourteen OFF references match retained hashes. OFF/ON comparisons preserve label and error counts on all fourteen datasets, with buffer parity and zero processing allocations or frees. Thirteen datasets have bit-identical OFF/ON output; physical-high differs without a count regression. Summary: `docs/recovery/github-full-corpus-20261109.json`.
- Paired native gates pass on 13/14 datasets. Physical-high ON reaches 469120 ns against a 333333 ns maximum and misses one of 154176 deadlines; zero misses is required. All p99 checks pass. Recovery succeeded, but promotion is rejected. This test-gate ratio is not project completion. The original report is preserved and its saved OFF/ON measurements were reassessed with the corrected paired acceptance check; no native replay was repeated.
- Diagnostic `42548007356`, at source `996596e4f03826f0243631e7e7bde52b43fd3e19`, completed with bit-identical traced and untraced physical-middle output. Expected string 3 is never chosen as the first addition in label 0 despite a correct primary string 5 in all 216 sampled rows. In labels 3–5, expected string 4 fails the profile-distance gate in 480/487 sampled rows. These counts describe sampled decisions, not frame-match gains. Summary and compressed trace provenance: `docs/recovery/github-profile-rejection-20261109.json`.
- Saved calibration also bounds the possible gain for the note-52 string-4/5 pair. Its squared profile distance is 0.0023852874737265374; a convex two-template fit can improve on its best member by at most one quarter of that, 0.0005963218684316344. This is below the 0.010 first-addition gain floor. Lowering only the 0.0025 distance threshold cannot admit this pair. The finding concerns this rule and calibration, not a physical impossibility or a validated correction.
- Both cloud jobs are final and their reports have been collected; do not poll, download or launch them again. Next, use the saved observations to assess independent string evidence before choosing a default-off correction. Any native trial runs on GitHub Actions. Keep original labels, protected-output checks and timing limits. Physical-high maximum/deadline, match-improvement, live host and MIDI lifecycle gates remain open. Installed scores are unchanged; reliable live use and overall completion are not measured.

## 2026-11-09 — native tests and VST3 build verified

- Source `996596e4f03826f0243631e7e7bde52b43fd3e19` fixes the two replay tests that still expected 90 trace columns after the format expanded to 93. Public CI `42547835491` passed source contracts, all native tests, the production VST3 build and packaging. Portable workflow `42547835417` also passed native tests, Python contracts and buffer parity. No binary was installed.
- At 01:58 UTC, full-corpus run `42545080876` was still recovering OFF and ON references at measured source `96509a4c8c212f2587865f5cd9d78164da0f0167`. Focused physical-middle, note-52 diagnostic `42548007356` was pending behind it at the corrected source. The private concurrency group serializes processing. Cancelled trace `42547542721` never ran. Do not duplicate either active job.
- Collect the corpus report into `build/github-results/corpus-recovery-42545080876` and the diagnostic into `build/github-results/profile-rejection-trace-42548007356` once each finishes. The corpus source predates the paired timing acceptance fix: preserve its original report and apply the corrected check to its saved OFF and ON measurements. Require complete traced/untraced output identity before interpreting the diagnostic's first-pass rejection counts. Keep the two source provenances separate in `build/modal/current-status.json`.
- The older NumPy import failure is resolved in the current workflows, which install `numpy>=2,<3` before the Python contracts. Installed scores remain unchanged. Corpus acceptance, assignment improvement and live-host verification remain open; overall completion is not measured. The next tuner change depends on the recorded results.

## 2026-11-09 — trace the missing secondary string before changing assignment

- The saved physical-middle note-52 trace localizes the missing string before proposal formation. For label 0, primary string 5 is valid for expected strings 3 and 5 in all 216 sampled rows, but string 3 never enters the proposal. Of 211 observed profile fits, string 3 has the best single-string fit in 100 rows, including 65 with beat support. This rules out primary commitment and the no-beat independent-resolution gate as complete explanations. Keep the original labels and calibration.
- Added offline-only first-pass profile diagnostics: the rejecting branch, computed mixture fraction and candidate fit error for each string. Later passes do not overwrite the first pass. Unreached values use -1 and are reported as not measured. All acceptance predicates, thresholds and installed output are unchanged. The assignment report retains older trace support and rejects partial or invalid diagnostic columns.
- Five focused Python contracts and whitespace checks passed locally. Native regression tests now cover accepted pairs, retained-component rejection, absent templates, reset state, scale invariance and allocation-free observation; those tests await GitHub Actions. Do not compile or replay locally.
- Next: push this source and queue one private GitHub `assignment-trace` task for physical-middle, note 52. Require native tests and bit-identical traced/untraced replay before interpreting the rejection counts. Record its exact run separately from the active full-corpus run `42545080876`; the worker concurrency group serializes heavy processing. Do not duplicate the corpus job.
- The source acceptance correction passed public portable workflow `42546145719` at `3d800465d5fd24aaccb1eb54ecfc377cb0393dac`. Full-corpus acceptance still needs both OFF and ON timing under the corrected measurement scope. No assignment gain or live readiness is claimed. Installed scores remain unchanged; ntfy updates continue.

## 2026-11-09 — paired corpus timing acceptance corrected

- Corpus acceptance now requires both OFF and ON block-32 timing to pass. The previous summary checked ON only and could overlook an OFF deadline failure. Allocation and timing acceptance also require the current measurement scope, which excludes offline frequency reporting. Detector output and installed settings are unchanged.
- Fifteen focused Python contract tests passed locally. The new corpus test completes all six mocked replays and rejects either mode exceeding the timing limits; absent or old measurement scope is rejected. No native processing ran locally.
- The existing full-corpus GitHub run `42545080876` remains active at measured source `96509a4c8c212f2587865f5cd9d78164da0f0167`. It already passed compilation and comparison contracts. Do not duplicate it. Once its report arrives, apply the corrected acceptance calculation to its saved OFF and ON measurements, preserving the original report; no native rerun is needed for this reporting correction.
- The earlier physical-long core check passed output identity, allocation and timing gates. This is limited to that recorded dataset and runner. The full corpus, actual match-improvement targets and live host/MIDI lifecycle checks remain open. Installed scores and overall readiness are unchanged.

## 2026-11-09 — GitHub core check passes; full corpus check running

- All new heavy/offloaded processing uses GitHub Actions, with inline ntfy progress updates. Private worker run `42545080876` is running the full `corpus-recovery` task at measured source `96509a4c8c212f2587865f5cd9d78164da0f0167`, worker `0f5adddcfeb418833294b11500b84e4ad7adb9d3`. Collect its small reports once terminal into `build/github-results/corpus-recovery-42545080876`. Do not launch a duplicate, compile or replay locally, or poll legacy Modal/Kaggle jobs.
- The paired physical-long core check `42544649533` passed and is final. Both OFF and ON match the complete retained TSV and the scored fingerprint, with zero C/C++ processing allocations or frees and zero missed deadlines across 176,464 blocks per mode. OFF p99/max: 112340/282348 ns. ON: 128685/284609 ns. Limits remain p99 <=166666 ns and max <=333333 ns. Summary: `docs/recovery/github-frequency-report-core-check-20261109.json`; report: `build/github-results/frequency-report-core-check-42544649533/core-check/report.json`. Collected once; do not repeat.
- Timing now excludes optional offline frequency report calculations and their observer. Admission and unison state remain active, and explicit diagnostic pruning retains its required calculations. This corrects measurement scope; it does not establish a production speed or note-accuracy gain. The six focused local Python contracts and all 34 cloud comparison contracts passed. Source CI `42544621467` passed native tests, production VST3 build and packaging; portable workflow `42544621385` passed. No binary was installed.
- Installed scores remain 41,452/68,441 physical-long matches and 25,219/39,378 exact-three matches. False outputs remain 67,769 wrong notes, 2,709 wrong strings and 5,403 extra outputs during unlabeled gaps. The gap statistic is not missing notes. The primary match improvement targets remain unmet; reliable live use and overall completion are not measured.
- Next: collect the existing full-corpus job and assess all fourteen datasets for passage matches and false outputs, buffer parity at 32/512/1024, zero processing allocations/frees and native timing limits. Compare the retained OFF hashes. Its safety pass is separate from live host/MIDI lifecycle verification and from an actual note-assignment improvement. Keep the installed default-off behavior unchanged.
- Earlier timing diagnosis `42543367917` remains final and preserved in `docs/recovery/github-timing-diagnosis-20261109.json`. Instrumented timings were diagnostic-only; the latest uninstrumented core check supplies the acceptance evidence.

## 2026-11-09 — corrected core measurement passes allocation and output gates

- Private GitHub core check `42542306099` is final at source `ade8175cf8362001691774f866da701508cbf1b8` and worker `e509ea1e34f2456132e847a1cab4887872e89627`. Native compilation and all 32 comparison contracts passed. The paired check deliberately failed the workflow because worst-block and deadline gates remain unmet. Summary: `docs/recovery/github-core-check-20261109.json`; detailed report: `build/github-results/core-check-42542306099/core-check/report.json`. Collected once; do not rerun or download again.
- Physical-long OFF and ON at block 32 match their retained full TSV hashes. Both retain 41,452/68,441 labeled matches, 25,219/39,378 exact-three matches, and false-output counts 67,769 wrong notes, 2,709 wrong strings and 5,403 extra outputs during unlabeled gaps. No labeled passage or false-output count regressed. Installed output remains unchanged.
- Both modes now report zero C++ and C processing allocations and frees, down from the previous 3,053 allocations and 3,050 frees per overlapping hook set. The earlier counts included an offline reporting observer. Excluding that observer corrects measurement scope; it does not establish a production speed gain.
- OFF p99/max are 118894/399070 ns with 115 deadline overruns in 176,464 blocks. ON p99/max are 144818/429119 ns with 117 overruns. Both p99 values pass the 166666 ns ceiling; maxima exceed the 333333 ns ceiling by 65,737 and 95,786 ns. Zero overruns is required. Shared-runner results do not establish live-host performance.
- Next: a bounded GitHub timing diagnosis of the remaining slow detector/cue blocks, preserving complete output identity and zero allocations. Keep native limits unchanged and do not widen corpus testing before this timing screen passes. Block 1024, the wider ON corpus, lifecycle/routing and live instrument/DAW checks remain open. The primary long/exact-three improvement targets are still unmet; live readiness and overall completion are not measured.
- Source `ade8175` also passed the portable replay workflow `42542241912`. In CI `42542244513`, native tests, VST3 build and artifact packaging passed; these do not verify the plugin in a live host.
- All new offloaded processing uses GitHub Actions. The private worker holds recordings; GitHub keeps reports and build artifacts, and ntfy carries inline updates. No new Modal or Kaggle work is permitted. Original inputs and current evidence remain local; previously verified duplicate upload files have already been removed.

## 2026-11-09 — allocation failure isolated to offline diagnostics

- Private GitHub allocation trace `42541481679` passed at source `58b55840abd51de27f4a7f9dc5f031cee247f992`. Every one of 3,053 C++ allocations (13,289,192 bytes) comes from `FrequencyRefinementMask` vector growth in the offline scoring observer. Full physical-long OFF output matches the retained reference. C and C++ hook counts overlap; do not add them. The instrumented timing is diagnostic-only. Summary: `docs/recovery/github-allocation-trace-20261109.json`.
- The timed pass reused the scored detector without detaching that observer. The correction now detaches it after scoring, leaving detector settings and scored diagnostics intact. This removes report bookkeeping from the measurement; it does not establish a production speed gain. Installed output and the default-off feature remain unchanged.
- Next: run the new private GitHub `core-check` task once at the pushed source commit. It measures physical-long OFF and ON at block 32 without allocation tracing. Require complete retained TSV identity, timed/scored fingerprint identity, zero C/C++ processing allocations and frees, p99 <=166666 ns, maximum <=333333 ns and zero deadline overruns. Report timing failure even if output and allocation checks pass. The runner contract tests passed locally; no native code ran locally.
- All new offloaded work uses GitHub Actions. Record the exact run and output path under `portable_compute.github_worker` in `build/modal/current-status.json`, then collect its small report once. Continue ntfy updates. Wider corpus, buffer and host/MIDI lifecycle gates remain open; reliable live use and overall completion are not measured.

## 2026-11-09 — references recovered; real-time gates still fail

- Legacy Kaggle corpus version 2 is final COMPLETE. All fourteen OFF references were recovered; physical-long also has ON results at blocks 512 and 32. Seventeen saved replay files, totaling 22,357,948 bytes, match the report hashes. The final result is preserved in `docs/recovery/recovered-corpus-v2-20261109.json`; detailed files and the collection receipt are in `build/kaggle-results/recovered-corpus-v2`. Do not poll or relaunch this terminal job. All new processing runs on GitHub Actions.
- Physical-long OFF and ON are bit-identical at both measured block sizes: 41,452/68,441 labeled matches and 25,219/39,378 exact three-string matches. False outputs remain 67,769 wrong notes, 2,709 wrong strings and 5,403 extra outputs during unlabeled gaps. The gap statistic is not a missing-note count. Buffer 32/512 parity passes; block 1024 and the remaining thirteen ON comparisons were not measured.
- Promotion is rejected. Both OFF and ON report 3,053 processing allocations and 3,050 frees in each hook set; C and C++ hook counts may overlap and must not be added together. At block 32, OFF p99/max are 286367/22452618 ns with 918 deadline overruns; ON is 309024/21107564 ns with 1,227 overruns. Required limits remain p99 <=166666 ns, maximum <=333333 ns, zero overruns and zero processing allocations/frees. Shared-runner timing does not establish live-host timing. The report's `stopped_on_regression` field names physical-long, but the stop was the allocation gate, not lost labels or added false outputs.
- The GitHub assignment trace independently shows pitch selection without correct string assignment on physical-middle. Early candidate rows remain in fine-frequency history collection; that status is not an admission rejection. Later rows can accept an incorrect string group. The trace does not yet isolate why history is insufficient. Keep the existing labels and calibration unchanged.
- Next: dispatch the prepared `allocation-trace` task on the private GitHub worker. It runs physical-long OFF at block 32 once, records C++ allocation callers in fixed storage, and resolves addresses after processing. Require the complete retained replay hash and full allocation accounting. Instrumented timings are diagnostic-only and cannot pass real-time acceptance. The normal build keeps tracing off.
- Broader acceptance still requires unchanged passage matches and false-output counts, zero processing allocations/frees, full buffer parity and the native timing limits. Installed output remains unchanged. Reliable live use and overall completion are not measured.

## 2026-11-09 — GitHub-only execution route

- User instruction: all new offloaded processing goes through GitHub Actions; continue ntfy updates. The public source repository retains ordinary CI, VST3 packaging and Linux configuration workflows. Real recordings and detailed results use the private `Ajuntanaga/m3-offload` worker repository. Canonical workflow and dispatch instructions: `cloud/github/`.
- The private input release contains the same 30 recovered inputs, compressed to 176,719,420 bytes. The archive SHA-256 is `adf6e36f2883538cfa3b0500ca0d936ed64fc6a1e12aeae3bd89e40dbf7c4254`; the private worker verifies it and each selected input before replay. No secret is copied to the worker.
- First GitHub task: physical-middle note 52 OFF reference plus assignment trace, using one pinned source commit and unchanged labels/settings. Require traced/untraced output identity. This isolates pitch-selection and string-assignment failures; it is not an accepted detector change. The candidate trace explicitly covers later labels and rejects an overlong capture.
- Private worker run `42538733620` passed the native build, 24 contract tests and assignment diagnostic at source `42c42d0d0ed99c46a89e23eb43f026e7c6be56f3`, worker `dd5b80f91d41815794bfa504c1a0de7ac845435e`. Public portable tests passed at the same source in run `42538709808`. The earlier missing-NumPy failure in run `42538530330` is resolved; its logs remain preserved. The private release server confirms the exact input archive bytes and SHA-256.
- Fresh untraced and traced OFF outputs are bit-identical: both match 0/24,139 labeled frames, with 4,516 wrong-note outputs, 17,921 wrong-string outputs and 94,413 extra outputs during unlabeled gaps. The latter are not missing-note counts. Pitch 52 is selected in 23,084/24,139 frames (95.63% pitch selection, not assignment-match percentage); the remaining frames include 1,004 coasting and 51 spectral rejections. None of 1,443 sampled assignment rows renders the expected string mask. The failure therefore persists after pitch selection in the sampled rows; the particular support, fit or admission rule is not yet established.
- Final report: `build/github-results/assignment-middle-42538733620/trace/report.json`. Public result and provenance: `docs/recovery/github-assignment-trace-20261109.json`. Next, inspect the saved assignment evidence for missing expected strings and extra lanes; keep labels and installed output unchanged. Any processing needed for the next test runs on GitHub Actions.
- GitHub run IDs, artifact names, output locations and collection state belong in `build/modal/current-status.json` under `portable_compute.github_worker`. The existing ten-minute heartbeat now follows this route. It must never dispatch work itself.
- Legacy Kaggle corpus version 2 was already running when this instruction arrived. Collect its terminal report once; do not submit a new version or duplicate the full recovery while it runs. Modal endpoints must not be probed.
- Both older Kaggle upload staging directories have had their 30 duplicate inputs removed after hash verification. Original inputs, evidence and launch manifests remain. The verified private GitHub upload archive has also been removed, reclaiming 176,719,420 bytes; the private release and all original inputs remain.
- Installed scores, default-off settings and live-readiness status remain unchanged. All previous label/error, allocation, buffer, p99/max/deadline, host and MIDI lifecycle gates still apply. No local native build or replay is permitted for this migration.

## 2026-11-08 23:49 UTC — corrected corpus recovery running

- Private Kaggle corpus recovery `anthovargas/m3-recovered-corpus/2` is RUNNING, observed at 23:49 UTC. Dataset version 2 is ready and contains the same 30 recovered inputs plus source from `6cb88d5011c6170371bd82c59091dbc5d162f192`. The float64 WAV-reader fix passed GitHub native tests before submission. No installed output changed.
- This is one replacement run with an 11,400-second timeout. Do not launch another version while it is pending or running. Local launch records are in `build/kaggle-recovery-20261108T2352Z`; collect its report, bootstrap report and stage logs into `build/kaggle-results/recovered-corpus-v2`. The launch provenance is also recorded in `docs/recovery/corpus-recovery-v2-launch.json`.
- Version 1 is final ERROR after ten of fourteen OFF references and no ON references. Its reports remain in `build/kaggle-results/recovered-corpus-v1`, and its status is preserved under `portable_compute.recovery_history` in `build/modal/current-status.json`. Do not poll it again. Version 2 measurements are not available yet; do not carry version 1 counts forward as new results.
- The upper-unison labels fit the configured note, fret and polyphony limits. Their zero-match results predate migration. The next diagnostic is a physical-middle OFF replay with the existing assignment trace, using unchanged labels and settings. It will show whether the expected strings lack calibrated support or lose to other feasible assignments. This is a diagnostic plan, not an established cause or an accepted tuner change.
- After collection, require all fourteen OFF references, no lost passage matches or added false outputs in OFF/ON comparisons, zero processing allocations and frees, buffer parity, p99 <=166666 ns, maximum <=333333 ns and zero deadline overruns. Host and MIDI lifecycle checks remain separate. Installed physical-long and exact-three targets are still unmet; reliable live use is unverified and overall completion is not measured.
- After this checkpoint is pushed, remove only duplicate upload-staging inputs whose hashes match the retained originals. Keep recordings, labels, calibration, reports, source archives and launch records.

## 2026-11-08 — upper-unison reference comparison and disk cleanup

- The three zero-match upper-unison cases predate the migration. November 4 Modal OFF summaries and November 8 Kaggle OFF summaries agree on every count and output fingerprint: middle 0/24,139, high-middle 0/23,452, high 0/28,043. Audio, label and calibration hashes match the recovered input inventory. Evidence: `docs/recovery/upper-unison-reference-comparison-20261108.json`.
- This removes a suspected migration regression; it does not establish correct annotations, successful string assignment or full historical TSV identity. The matcher requires the expected note/string assignment, so zero matches must not be described as no detected audio. Installed scores remain unchanged.
- Removed 30 duplicate upload-staging inputs from `build/kaggle-recovery-20261108T2010Z/dataset`, reclaiming 307,122,490 bytes (292.9 MiB). Each staged file and retained source was hashed against the recovery inventory before removal. Original recordings, labels, calibration, reports and launch metadata remain. Local manifest: `build/recovery/duplicate-cleanup-20261108.json`. Recreate staging from retained inputs before any future upload.
- Next: resume bounded reference recovery with the cloud-tested float64 reader; retain upper-unison zero scores as known baseline limitations. Diagnose assignment separately without changing labels to raise scores. No new cloud run or local build was launched by this checkpoint; timing, false-output and host gates still apply.

## 2026-11-08 23:06 UTC — replacement execution routes verified

- Modal remains unavailable. Oracle signup was rejected, so no OCI VM is configured. GitHub Actions and private Kaggle are the active execution routes; no local gateway, native build or render was started.
- GitHub run `42533147556` at `0576d612d6e5290d702fd60b97d6e90543536116` passed source contracts, native tests, production VST3 compilation and artifact packaging. The dependency check now distinguishes model-file extensions from C++ pointer members. The downloaded bundle and provenance are in `build/cloud-artifacts/0576d61`; no plugin was installed.
- Portable replay run `42533147507` passed at `0576d61`. Linux sandbox run `42532741071` passed at `ea2e1cc`. The latter checks shell and systemd configuration in a disposable runner; it does not establish kernel, driver, resource-limit or audio-host behavior. Production VST3 archives, SHA-256 and source provenance are retained for seven days.
- Private static binary triage smoke `anthovargas/m3-static-triage-smoke`, version 1, completed: all four file/binutils inspection tools passed on a generated fixture. Reports and logs are in `build/kaggle-results/triage-smoke-v1`. The runner bounds time and output and checks input hashes. No user binary was uploaded or executed, and no LLM inference was tested.
- Corpus recovery version 1 is terminal ERROR: ten of fourteen OFF references, no ON references, no native corpus acceptance. The `extended-highmid-off-512.stderr` failure was `unsupported_wave` on valid mono float64 audio at 96 kHz. Float64 reader regressions now pass in the cloud without converting the recording. Bootstrap and replay failures preserve their final reports and diagnosis. No replacement corpus run was launched.
- Nine focused Python contracts and the dependency-check regression passed locally. The existing ten-minute `m3-modal-heartbeat` follows recorded replacement jobs and retains inline ntfy summaries. It does not poll terminal recovery version 1 or launch duplicate work.
- Next: check the three zero-match recordings against labels and calibration before wider reference recovery. The input checklist remains 30/30; historical control crops, OFF/ON TSVs and the final Modal report are still missing. Installed scores and acceptance gates are unchanged; reliable live use and overall completion remain unmeasured.

## 2026-11-08 20:13 UTC — private corpus recovery running

- Recovery source is committed and pushed as `82a683030149f72ba229641811368f58392ab53f`. GitHub Actions run `42518745279` passed the native build, native tests, Python comparison contracts and synthetic buffer checks at 20:11 UTC. No production C++ or installed output changed.
- All 30 declared replay inputs are recovered and hashed, totaling 307,122,490 bytes. The private dataset `anthovargas/m3-recovered-corpus-20261108` is ready. Original control crops, historical OFF/ON TSVs and the final Modal split-search report remain unavailable; recovered measurements have new provenance.
- Private Kaggle kernel `anthovargas/m3-recovered-corpus`, version 1, was submitted once and observed RUNNING at approximately 20:12 UTC. It uses CPU for the native C++ replay, with internet disabled. Preparation and launch records are in `build/kaggle-recovery-20261108T2010Z`. Do not launch another version while this run is pending or active.
- The runner saves fourteen OFF references first, then screens physical-long with the actual correction flags. Wider ON recovery requires the physical safety checks. Acceptance additionally requires no lost passage matches or added false outputs, zero processing allocations and frees, buffer parity, p99 <=166666 ns, maximum <=333333 ns and zero deadline overruns. A completed reference-recovery job is not promotion; timing failures remain failures even if reference recovery continues.
- The ten-minute `m3-modal-heartbeat` automation now follows this specific kernel version. Once outputs exist, it collects reports and stage logs to `build/kaggle-results/recovered-corpus-v1`, updates local recovery status and sends the inline summary. It must preserve installed scores and must not launch duplicate work or repeat inaccessible Modal probes.
- Earlier Kaggle GPU probe `anthovargas/m3-portable-gpu-spectra` completed on Tesla T4: 266 generated-audio windows passed numerical comparison. That small probe was slower than CPU and does not establish labeled-note gains, native cue parity or live readiness. Local comparison/recovery tests passed: 17 tests, no failures.
- Next: collect the existing recovery job's report and assess its measured safety and timing results before changing the implementation. Host/MIDI lifecycle checks and the physical-long and exact-three targets remain open. Reliable live use is unverified; overall completion is not measured.
- Modal access remains unavailable, last checked November 8 at 18:57 UTC. Older checkpoints describe historical evidence. Precise prose mode remains selected; research and inactive-log compression are complete. Last confirmed inline ntfy: 20:09 UTC, 3192 bytes, HTTP 200, no attachment, receipt `ky1rj66Suv5R`; full receipt is in `build/modal/latest-notification-receipt.json`.

## 2026-11-08 18:55 UTC — split-search result recovery needs Modal access

- The same `research` profile resolves to workspace `snorkelai`; no token, profile, environment or configuration-path override is set in the parent environment. Modal denies both `app_get` and `volume_get` in `main`. The final state of app `ap-NDVgzocHRPf04mXeH56JE7` is unverified. The old local launcher handle is gone; this does not establish that its detached job stopped. Do not launch a replacement.
- Retrieve `results/cue-split-peaks-20261104T1415Z/report.json` from volume `m3-protected-replay-data` once access is restored. The authoritative local evidence available now is `build/modal/cue-split-peaks-20261104T1415Z-active.json`, saved from the report updated on November 4 at 14:19:11 UTC. It is partial, not final.
- That snapshot records 81 native tests with zero failures. Seven of ten cases have completed exact saved OFF/ON and buffer comparisons, with zero processing allocations or frees. Three of those seven pass both timing limits. Worst observed ON p99 is 203338 ns against 166666 ns, maximum is 1775391 ns against 333333 ns, with 19 deadline overruns. These failures already reject promotion; remaining results are unavailable, not assumed to pass or fail.
- The offline candidate splits alternating note searches between phases 224 and 256, preserving the audio window and fixed 256-sample publication. The empty-history reset switch is off. The new adjacent-note test checks that both groups become visible at the same deadline. No installed output changed.
- Next: recover the existing final report, then decide the next bounded cost change from its evidence. Wider native corpus checks still require exact saved outputs, buffer parity, zero processing allocations, p99 at most 166666 ns, maximum at most 333333 ns and zero overruns. Native corpus acceptance remains zero of fourteen; live readiness and overall completion are not measured.
- Sent one inline ntfy update at 18:54:28 UTC: 3721 bytes, HTTP 200, receipt `qU2ybI5fyclG`. Next attempt is due after 19:04:26 UTC. Precise prose mode remains selected. Research and inactive-log compression are complete.

## 2026-11-04 14:10 UTC — empty-reset optimization rejected

- Full trial `cue-empty-reset-20261104T1355Z`, app `ap-CdkfoEEZAptnrSYFpojgB4`, preserves all ten saved OFF/ON references, ON outputs at blocks 32/512/1024 and timed/scored fingerprints. All 80 tests pass, including nonempty history resets, with zero processing allocations or frees. Binary SHA-256: `f90f17ee37b513ea02b2628296fc01298faf17f0fc428ddbb2a70a157edba2a6`.
- Full timing fails: none of the ten recordings passes both limits. Worst ON p99 is 196470 ns against 166666 ns, maximum is 652129 ns against 333333 ns, with six deadline overruns. Cross-run differences do not isolate the switch or prove a timing regression.
- Paired cost run `cue-empty-reset-cost-20261104T1406Z`, app `ap-cDdy1WgUd4hIplXTzpRZKf`, completed at 14:06:16 UTC without a rebuild. It uses the same saved binary and solo recording in OFF/ON/ON/OFF order. All four outputs are exact with zero processing allocations. Total child CPU changes 1500 to 1490 ms and 1590 to 1500 ms: savings of 10 ms/0.6667% and 90 ms/5.6604%. Only one of two pairs meets both required savings, 5% and 50 ms. Reject the switch as an unproven optimization; it remains default-off and excluded from production builds. Child CPU includes startup, scoring and the timed replay pass; clock resolution is not measured.
- Next: separate cue transform and peak work across blocks while preserving the fixed 256-sample publication schedule. Require exact OFF/ON outputs, tested buffer parity, zero processing allocations, p99 at most 166666 ns, maximum at most 333333 ns and zero deadline overruns before wider native corpus checks. The previous cloud CPU timer and empty-reset investigations are complete; do not repeat them without new evidence.
- Controlled gains remain solo 3219 to 3236/3450, quiet octave 2070 to 2079/3450 and nearby 815 to 835/3450. Wrong strings fall 159 to 142, 1314 to 1305 and 1548 to 1528; wrong-note and extra-gap counts are unchanged. The other seven controls are bit-identical. Earlier undelayed corpus coverage is nine of fourteen; native corpus acceptance remains zero of fourteen.
- Installed output is unchanged. The measurement window remains 170.7 ms; 2.666667 ms is only added cue availability delay. Host performance, MIDI lifecycle/routing, remaining corpus coverage, physical-long and exact-three targets remain open. Reliable live use and overall completion are not measured.
- Last confirmed inline ntfy: 14:01:13 UTC, 3694 bytes, receipt `g7relNmLRFiT`. Continue the ten-minute cadence. Precise prose mode is selected. Research and inactive-log compression are complete.

## 2026-11-04 13:51 UTC — coarse CPU clock rejected; empty-history optimization next

- Final diagnostic `cue-state-clock-20261104T1344Z`, app `ap-3P8E65hW5KeXZEPDhK7FjH`, completed at 13:45:57 UTC. All 78 tests pass; solo, equal-level octave and equal-level nearby preserve exact paired OFF/ON outputs with zero processing allocations or frees. Binary SHA-256: `30e7ba2ecc0fd74e4fda7ebf1ed42b75d6248c1ecac729625d2bc0f29639a38f`.
- All six thread CPU clock resolution checks fail: the observed duration grid is 10000000 ns against a maximum of 3333 ns. Wall timing remains valid. All six diagnostic wall measurements pass, but this does not replace the rejected full screen or establish the cause of earlier spikes. Post-block snapshots do not make sample 58560 a repeatable worst block.
- Latest full candidate `cue-spaced-replay-20261104T1316Z` preserves all ten references, ON outputs at blocks 32/512/1024 and timed/scored fingerprints. All 78 tests pass with zero processing allocations or frees. All ten p99 measurements pass; six cases pass both timing limits. Worst p99 is 143700 ns against 166666 ns, maximum is 2345030 ns against 333333 ns, and ON has nine deadline overruns. This candidate remains rejected for native corpus screening.
- The fixed 256-sample reference is `cue-fixed-delay256-20261104T1311Z`, SHA-256 `5b67030ab795a9f204f22433b4d3b9b5087aa2b6f418e812d51f3743051437fa`. The native schedule transforms at phases 32/96/160/224 and publishes at phase 256. The added delay is 2.666667 ms; the measurement window remains 170.7 ms.
- Next: test an offline opt-in skip for redundant clears of already-empty fine-frequency histories. This is a code-level cost lead, not a measured bottleneck or speedup. Preserve nonempty reset behavior and require ten exact OFF/ON references, buffer parity, zero processing allocations, p99 at most 166666 ns, maximum at most 333333 ns and zero overruns before wider native corpus checks. No Modal job remained active at the checkpoint.
- Controlled gains remain solo 3219 to 3236/3450, quiet octave 2070 to 2079/3450 and nearby 815 to 835/3450. Wrong strings fall 159 to 142, 1314 to 1305 and 1548 to 1528; wrong-note and extra-gap counts are unchanged. The other seven controls are bit-identical. Earlier undelayed corpus coverage is nine of fourteen; this native binary has no full corpus acceptance yet. Installed output is unchanged. Host performance, MIDI lifecycle/routing, remaining corpus coverage, physical-long and exact-three targets remain open; reliable live use and overall completion are not measured.
- Last confirmed ntfy: 13:50:38 UTC, 3669 bytes, inline receipt `8QVMh8VgcNc5`. Continue the ten-minute cadence. Precise prose mode is selected. Research and inactive-log compression are complete.

## 2026-11-04 13:00 UTC — native cue replay preserved; combined timing rejected

- Final Modal run `cue-direct-power-replay-20261104T1257Z`, app `ap-KpmqzXtN5PvdsB2UYQdhYR`, reproduces all ten saved OFF and delayed ON outputs. ON agrees at blocks 32/512/1024; timed and scored fingerprints agree. All 78 tests pass, with zero C/C++ processing allocations or frees. Binary SHA-256: `37e74e44779271c80ce18635ce3846537b47659d4260311de6900f1d036c9616`.
- Solo matches remain 3219 to 3236/3450 (93.3043% to 93.7971%); quiet-octave target matches 2070 to 2079/3450 (60.0000% to 60.2609%); nearby-note target matches 815 to 835/3450 (23.6232% to 24.2029%). Wrong strings fall 159 to 142, 1314 to 1305 and 1548 to 1528 respectively. Wrong-note and extra-gap outputs are unchanged. The other seven cases are bit-identical to OFF. Extra-gap counts mean extra outputs during unlabeled gaps, not missing notes.
- Only solo passes both combined timing limits. Worst p99 is 202121 ns against 166666 ns; maximum is 2219376 ns against 333333 ns. The timer includes cue generation, trim and the detector, excluding scoring, hashing and reports. Timing is rejected; no wider native corpus screen is accepted.
- Standalone direct-power run `cue-direct-power-20261104T1251Z` preserves all ten cue files, passes six tests and reports zero processing allocations/frees. Worst p99 is 155090 ns and maximum 479739 ns; eight of ten recordings pass both timing limits. Probe SHA-256: `fde84f3dddd1fcd7074aaf205566869e53b653cfbe134eacb8fc049e8da4d909`. Earlier split-calculation run `cue-cooperative-corpus-20261104T1216Z` passed standalone timing; neither result establishes combined or live-host timing.
- Next: move the final transform and peak selection away from a detector decision boundary while keeping cue release exactly 128 samples late. This is an unmeasured scheduling change. Require all ten reference outputs, zero processing allocations, combined p99 at most 166666 ns and maximum at most 333333 ns. The last report is final; confirm its detached container has stopped before launching the next Modal job.
- Installed output is unchanged. Earlier nine undelayed corpus passes are separate evidence. The 170.7 ms measurement window remains; the fixed 128-sample delay adds 1.333333 ms. Physical-long and exact-three targets remain unmet. Native corpus coverage, lifecycle/routing and live-host checks remain open; reliable live use and overall completion are not measured.
- Last confirmed inline ntfy receipt: `OZ1MFsbXDUrT`, 12:57:16 UTC, 3600 bytes, HTTP 200, no attachment. Continue the ten-minute cadence. Precise prose is selected; research and inactive-log compression are complete.

## 2026-11-04 12:02 UTC — hybrid worker rejected; split calculation next

- Modal run `cue-worker-hybrid-trace-20261104T1158Z`, app `ap-jAD8xbuqRFpJZotmBK8GeI`, completed at 11:55:31 UTC. The fixed hybrid policy polls during the final 384 samples of each 1024-sample hop and sleeps otherwise. At block 32, its two repeats deliver 331/332 and 332/332 cues; process CPU is 65.16% and 69.37% of one core. Both exceed the diagnostic limit of 50%. The first repeat loses 1024 cue samples and has one callback overrun. Zero of two repeats passes all gates. The eleven native tests pass; callback allocations, extra cues, queue drops and stale outputs remain zero.
- The late nonempty cue exposes a calculation deadline failure: the worker starts 10.174 us after the input callback begins, but the step takes 3.348120 ms. The target callback begins after 1.133487 ms. Wall time includes possible descheduling, so this does not isolate arithmetic cost. In the sleeping controls, 42 of 59 missing cues have not started processing before the target callback finishes. Both wakeup delay and long calculation steps need attention; further polling alone is not the next route.
- Earlier uninstrumented hybrid run `cue-worker-hybrid-20261104T1150Z` is also rejected: one repeat misses an empty cue frame, despite process CPU of 44.38% and 48.87%. Timestamp stores and cloud scheduling can affect the later probe. Do not treat CPU differences between these runs as a controlled causal comparison. Trace binary SHA-256: `a8dd4c355c86376b8c2aa4dc0613a1db0c281d6dd97f25a62b111e1e6cc63aab`.
- Next: design a bounded split calculation preserving the symmetric Hann window, zero padding, cue thresholds and 128-sample delay. Before integration, require frozen cue parity, zero callback allocation, block-32 callback p99 at most 166.666 us and no callback above 333.333 us. Native builds remain on Modal; no M3 job remains active at this checkpoint. Do not widen corpus testing until the small timing screen passes.
- Installed output is unchanged. Earlier fixed-delay replay preserves all ten controlled results; nine undelayed corpus passes are separate evidence. Full delayed-corpus coverage, detector integration, lifecycle/routing and live-host checks remain open. The 170.7 ms measurement window remains; 1.333333 ms is only the additional cue delay. Physical-long and exact-three targets remain unmet. Overall completion is not measured.
- Last confirmed inline ntfy receipt: `94ko1JzpytQs`, 11:52:13 UTC, 3440 bytes, HTTP 200, no attachment. Continue the ten-minute cadence. Precise prose is selected; research and inactive-log compression are complete.

## 2026-11-04 11:14 UTC — short cue delay preserves controlled gains

- Modal run `cue-fixed-delay128-20261104T1108Z`, app `ap-TkoH25S1QtNaIxvt3nuX5I`, completed at 11:10:37 UTC. A fixed 128-sample delay (1.333333 ms) preserves the counts, false outputs and fingerprints of all ten undelayed cases. Fresh OFF and zero-delay ON reproduce every saved control; delayed ON agrees at blocks 32/512/1024. All 68 native tests pass, including causal renewal, reset, expiry clipping and overflow boundaries for the diagnostic delay.
- Solo matches remain 3236/3450 (93.7971%), against OFF 3219 (93.3043%); wrong strings remain 142 versus 159. Nearby matches remain 835/3450 (24.2029%), against OFF 815 (23.6232%); wrong strings remain 1528 versus 1548. Quiet-octave target matches remain 2079/3450 (60.2609%), against OFF 2070 (60.0000%); wrong strings remain 1305 versus 1314. Wrong-note and extra-gap outputs are unchanged in each case. The seven other cases are bit-identical to OFF.
- Replay SHA-256: `8126916ac76d07a4b00932d4c051633015a172f71b3655a7045de853f3a61889`. The nine earlier undelayed corpus passes use a different binary and do not cover this build or its delayed policy. Installed output is unchanged; physical-long and exact-three targets remain unmet.
- Next: measure bounded background delivery with the fixed 128-sample availability delay. Require no late or lost frames, exact cue masks, no callback allocation or waiting, bounded overflow/reset behavior and callback timing. A standalone scheduling probe will not establish detector integration or live-host readiness. No Modal job remains active.
- Last confirmed inline ntfy receipt: `RzZab92lSAMW`, 11:07:24 UTC, 3503 bytes, HTTP 200, no attachment. Continue the ten-minute cadence. Precise prose is selected. Research and inactive-log compression are complete. Overall completion is not measured.

## 2026-11-04 11:03 UTC — optimized native cues preserve parity but miss callback timing

- Modal run `native-frozen-cue-pffft-20261104T1051Z`, app `ap-lA4mqvgzBMe2Um1JT5y9WO`, completed at 10:53:31 UTC. The double-precision AVX transform preserves all ten cue files and all 175960 note observations within the frozen tolerances, with zero clock, reason, peak or numeric mismatches. All five boundary, reset and allocation tests pass; the allocation guard covers both C++ operators and linked C allocation functions.
- Timing still fails in every case. Worst block p99 is 0.291410 ms against 0.166666 ms; maximum is 0.730550 ms against 0.333333 ms. Compared with the earlier scalar run, these are reductions of 95.14% and 94.92% across separate cloud runs, not a controlled same-CPU comparison. The standalone probe excludes detector and plugin work, so it remains rejected for synchronous callback use. Probe SHA-256: `0d79fa79a32ceded79c2faf62bde932eb9b0823ad0a924b577cf15672bb4ad31`.
- PFFFT is vendored at upstream commit `7ae36e8c1d352cba66231de953cfa35f235b9e7a`, with license and file hashes retained. The optimized probe is optional and defaults off; it is not linked into the installed plugin. Fixed workspace is 2110416 bytes, excluding the FFT library's setup allocation. This result supplies neither host scheduling nor out-of-memory recovery evidence.
- Next: screen one fixed 128-sample (1.333333 ms) delay before implementing a worker. The saved cue reader only accepts times aligned to 1024 samples, so this needs a diagnostic-only delay option and a fresh Modal replay build. Keep the source cue file unchanged; first require exact OFF and zero-delay ON reproduction, then require all undelayed gains, no added false outputs or negative-control changes, and buffer parity at 32/512/1024. Do not implement a worker if this screen fails.
- The undelayed candidate still has nine earlier corpus passes on binary `7e6cd8b72b54a616195db5eb89fda9ee2d2ada1fe4c862f8dd39992cb2401f93`; they do not establish coverage for a rebuilt or delayed candidate. Installed output and the primary scoreboard are unchanged. Reliable live use and overall completion are not measured. No Modal job remains active.
- Inline ntfy receipt `m1nUJIAnV4ZB` was confirmed at 10:55:25 UTC: 3601 bytes, HTTP 200, no attachment. Continue the ten-minute cadence. Precise prose is selected. Research and inactive-log compression are complete.

## 2026-11-04 10:40 UTC — native timing and delayed cue routes rejected

- Standalone Modal run `native-frozen-cue-20261104T1023Z`, app `ap-q7vTAL1Qn4cA52sQKAwzcx`, completed at 10:27:53 UTC. All ten cases match the frozen reference: 175960 note observations have zero clock, reason, peak or numeric mismatches, and cue files are identical. All four boundary, reset and allocation tests pass. The component is offline and is not linked into the installed plugin.
- Timing fails in all ten cases. Worst block p99 is 5.991700 ms against 0.166666 ms; maximum is 14.391048 ms against 0.333333 ms. These measurements exclude the detector and the rest of the plugin. The synchronous FFT is rejected for the audio callback. Native probe SHA-256: `c6bab244c77a0e014b302b9afebb047cd54b5f73e93e5364db5fa593a34a511e`.
- The undelayed initial-settling candidate now passes nine of the fixed fourteen corpus screens on replay binary `7e6cd8b72b54a616195db5eb89fda9ee2d2ada1fe4c862f8dd39992cb2401f93`. Ordinary, constructed, isolated low/middle/high, physical-long, physical-middle and physical-highmid are bit-identical to their controls. Physical-high preserves all passage matches and false-output limits, but its output fingerprint changes from `0b868703201511e1` to `8fdf6bd9993365a1`; do not describe that corpus as bit-identical. ON agrees at blocks 32/512/1024 in all nine screens. Extended middle/highmid/high and physical/synthetic four-string screens remain open.
- Modal run `cue-fixed-delay-20261104T1034Z`, app `ap-QpTZRZkEgGxf694kzQWyQN`, completed at 10:34:50 UTC and is rejected. Shifting availability and expiry by 1024 samples (10.6667 ms) loses five solo matches: undelayed 3236 to delayed 3231/3450 (93.7971% to 93.6522%), with wrong-string outputs 142 to 147. OFF remains 3219 matches and 159 wrong strings; a smaller gain does not preserve the accepted undelayed result. Nearby 835/3450 and quiet octave 2079/3450 are unchanged, as are the remaining cases. Further buffer checks stopped. OFF and test evidence are reused from the source screen. The earlier corpus passes do not cover delayed cues. No incremental FFT was implemented; no Modal job remains active.
- Next: reduce native calculation cost without delaying cue availability. Preserve the frozen math and thresholds; require native reference parity, timing and allocation checks before detector integration. Installed output remains unchanged, the long/exact-three targets remain unmet, and live readiness and overall completion are not measured.
- Inline ntfy receipt `jSsGW0GCoNDK` was confirmed at 10:33:40 UTC: 3236 bytes, HTTP 200, no attachment. Continue the ten-minute cadence. Precise prose mode is selected. Research and inactive-log compression are complete.

## 2026-11-04 10:00 UTC — isolated strings and sustained unisons preserved

- The initial-settling candidate passes ordinary chords, constructed chords and representative low, middle and high isolated strings. ON, OFF and baseline are bit-identical in all five corpora, with no lost passage matches or added false outputs. ON agrees at blocks 32/512/1024. All use the saved binary `7e6cd8b72b54a616195db5eb89fda9ee2d2ada1fe4c862f8dd39992cb2401f93`.
- Middle-string run `cue-initial-assignment-isolated05-20261104T0945Z` completed at 09:46:37 UTC: 25681/31050 matches (82.7085%), wrong-note/wrong-string/extra-gap counts 12028/4037/3860, total false outputs 19925 and fingerprint `87edbea93db1fb35`.
- High-string run `cue-initial-assignment-isolated02-20261104T0949Z` completed at 09:52:21 UTC: 29240/35550 matches (82.2504%), errors 2491/1400/1840, total false outputs 5731 and fingerprint `e1436099f9cfb492`. Extra-gap counts mean extra outputs during unlabeled gaps, not missing notes.
- Long physical-unison run `cue-initial-assignment-physical-long-20261104T0953Z` passed at 09:59:10 UTC: 41452/68441 overall matches (60.5660%) and 25219/39378 exact-three matches (64.0434%). Errors remain 67769/2709/5403, total false outputs 75881; fingerprint `519bc0f9f4710566`. ON, OFF and baseline are bit-identical, and ON agrees at blocks 32/512/1024. Primary targets remain at least 42128 overall and 25604 exact-three matches, with wrong strings at most 2709; preserving the baseline alone does not reach them.
- Detached Modal run `cue-initial-assignment-physical-middle-20261104T1001Z`, app `ap-Jzek6Mn52fZlv2x7XV1Td0`, is checking middle physical unisons on the same binary. Do not launch a duplicate. Require no lost passage matches, no increased false-output count, exact OFF equality and ON buffer parity.
- Six of the fixed fourteen corpus screens pass on this binary. The earlier nearby gain remains 815→835/3450; installed output is unchanged. Remaining physical/synthetic unisons, native cue timing and MIDI lifecycle/host gates are open. Reliable live use and overall completion are not measured.
- Last inline ntfy receipt: 09:59:42 UTC, 3453 bytes. Continue the ten-minute cadence. GitHub includes the preceding checkpoint in `cb3b96368034ded16770793c468e6ccd2e61eae6`. Precise mode is selected; research and inactive-log compression are complete.

## 2026-11-04 09:45 UTC — ordinary chords and low strings preserved

- The initial-settling candidate now passes constructed chords, ordinary intervals/chords and isolated low strings. Every ON output in these corpora is bit-identical to OFF and the baseline; no passage loses matches, and all ON outputs agree at blocks 32/512/1024. The same saved binary is used throughout: `7e6cd8b72b54a616195db5eb89fda9ee2d2ada1fe4c862f8dd39992cb2401f93`.
- Ordinary run `cue-initial-assignment-ordinary-20261104T0933Z` completed at 09:38:30 UTC. Matches remain 145385/528632 (27.5021%); wrong-note/wrong-string/extra-gap counts remain 164263/92653/62856, total false outputs 319772 and fingerprint `bbed96f3be505756`.
- Low-string run `cue-initial-assignment-isolated08-20261104T0940Z` completed at 09:42:41 UTC. Matches remain 29816/31050 (96.0258%); wrong-note/wrong-string/extra-gap counts remain 2462/579/2928, total false outputs 5969 and fingerprint `06c4e7fdb2a739e4`. Extra-gap counts mean extra outputs during unlabeled gaps, not missing notes.
- The earlier small screen retains nearby matches 815→835/3450, solo gain 17 and quiet-octave gain nine. These gains are offline; installed output is unchanged. The correction remains limited to candidate age below 160 ms, with the other assignment guards intact.
- Detached Modal run `cue-initial-assignment-isolated05-20261104T0945Z`, app `ap-NXKSy9qBjGRpAVKayKfS9O`, is checking middle strings. Do not launch a duplicate. Require at least 25681/31050 matches, no passage loss, wrong-note/wrong-string/extra-gap counts at or below 12028/4037/3860, exact OFF equality and ON buffer parity. High strings and physical/synthetic unisons follow after this gate passes.
- GitHub includes the implementation and constructed-corpus checkpoint in `856cb21ea95a560a668a7f68d3aa3871fb9e8923`. Last inline ntfy receipt: 09:36:47 UTC, 3292 bytes; continue the ten-minute cadence. Precise mode is selected. Research and inactive-log compression are complete. Full corpus, realtime and MIDI lifecycle/host gates remain open; reliable live use and overall completion are not measured.

## 2026-11-04 09:33 UTC — initial-settling guard passes constructed chords

- Paired diagnostic `cue-mature-tuning-failure-20261104T0901Z` completed at 09:06:01 UTC. Both complete-history outputs exactly reproduce the saved results, and all traces are complete. The first changed output is sample 6317119: MIDI 51 moves from the correct string 2 to free string 4. Candidate age is 1258 decisions, about 838.7 ms; tuning is valid at +29.3153 cents after 1485 updates. Descriptor similarity favors the wrong string at 0.988216, and its tuning error is 14.5067 cents versus 41.7098 for the incumbent. Pitch detection is unchanged. Neither cue confirmation nor this descriptor/tuning preference justifies replacing an established string assignment.
- The offline candidate limits cue corrections to candidate age below the existing 160 ms evidence period. It retains occupancy, group, descriptor and tuning guards. The new regression covers the recorded late move, unavailable tuning on an established assignment, and the earlier useful correction. Installed output is unchanged.
- Small screen `cue-initial-assignment-20261104T0913Z` completed at 09:17:23 UTC. Nearby matches remain 815→835/3450 (23.62%→24.20%; +20 frames, +2.45% relative), while wrong-string outputs fall 1548→1528; wrong notes and extra outputs in unlabeled gaps remain 3178 and 668. Solo gains 17 matches and quiet octave nine; seven other cases are bit-identical. All ten OFF controls reproduce the baseline and all ON outputs agree at blocks 32/512/1024. All 66 focused native tests pass. Binary SHA-256: `7e6cd8b72b54a616195db5eb89fda9ee2d2ada1fe4c862f8dd39992cb2401f93`.
- Constructed run `cue-initial-assignment-constructed-20261104T0918Z`, app `ap-bNKzDkeFbLYJ00gfhu3GJQ`, completed at 09:32:02 UTC and passed. ON, OFF and baseline are bit-identical: 259074/1614601 matches (16.0457%), wrong-note/wrong-string/extra-gap counts 167722/103754/23176, total false outputs 294652 and fingerprint `199db8fd25ada73e`. No passage changes; ON agrees at blocks 32/512/1024. This clears the constructed regression while retaining the small-screen gain; it does not establish broader or live acceptance.
- Detached Modal run `cue-initial-assignment-ordinary-20261104T0933Z`, app `ap-8A2UQzXzCFhnGOvQqGDFQT`, is checking ordinary intervals and chords with the same binary and verified saved cue features. Do not launch a duplicate. Require at least 145385/528632 matches, no lost passage, wrong-note/wrong-string/extra-gap counts at or below 164263/92653/62856, exact OFF equality and ON buffer parity. Isolated strings and physical/synthetic unisons follow only after this gate passes.
- The installed state is unchanged. Last inline ntfy receipt: 09:26:20 UTC, 3127 bytes. Continue the ten-minute cadence. GitHub includes the implementation and preceding checkpoint in `cf20db140b5018b5784bae8a00d1abd1eea73b5a`. Precise mode is selected; research and inactive-log compression are complete. Reliable live use and overall completion remain unmeasured.

## 2026-11-04 09:01 UTC — mature-tuning guard rejected on remaining passages

- `cue-mature-tuning-constructed-20261104T0850Z` completed at 08:59:19 UTC and is rejected. Matches fall 259074→258558/1614601 (16.0457%→16.0137%; −516 frames, −0.1992% relative). Wrong-note/wrong-string/extra-gap counts change 167722/103754/23176→167046/103725/23176; total false outputs fall 294652→293947. Those reductions do not offset lost matches in eight passages. OFF exactly reproduces the baseline. Further ON buffer and corpus checks stopped; installed output is unchanged.
- The earlier MIDI-49 failure no longer changes any label score. The first remaining lost passage is label 98, MIDI 51 on string 2: 2305→584/3450. Paired diagnostic `cue-mature-tuning-failure-20261104T0901Z`, app `ap-4qeuG8fm8GQj8BpDnVW5wv`, is running against the saved binary and complete audio history. It must reproduce every saved score before its traces can guide the next change. Do not launch a duplicate or expand to ordinary chords while this gate fails.
- The small-screen gains and 65 focused tests below remain valid for this rejected candidate. Require a replacement to retain nearby matches at least 835/3450 without control regressions, preserve every constructed passage and at least 259074/1614601 matches, keep wrong-note/wrong-string/extra-gap counts at or below 167722/103754/23176, and pass exact OFF equality plus ON buffer parity before broader corpus checks.
- This checkpoint records an offline rejection, not a production improvement. Last confirmed inline ntfy receipt is 08:53:22 UTC, 3186 bytes; continue the ten-minute cadence. Precise prose is selected; research and inactive-log compression are complete. Reliable live use and overall completion remain unmeasured.

## 2026-11-04 08:52 UTC — mature-tuning guard passes the small screen

- `cue-mature-tuning-20261104T0847Z` completed at 08:49:16 UTC and is accepted for corpus screening. Nearby matches remain 815→835/3450 (23.62%→24.20%; +20 frames, +2.45% relative); wrong-string outputs fall 1548→1528, while wrong notes and extra outputs in unlabeled gaps remain 3178 and 668. Solo gains 17 matches; quiet octave gains nine. Seven other cases are bit-identical. All ten OFF controls match the baseline and all ten ON outputs agree at blocks 32/512/1024. All 65 focused native tests pass. Binary SHA-256: `e3d7ccafdb35d943f4b8f3d7f7280356d44663637f96a493fbaa7de49e69bba8`.
- The guard distinguishes early missing tuning from lost mature tuning. After the existing 160 ms phase-evidence threshold, a cue-driven string move requires valid output-projection tuning. Earlier corrections remain eligible under the other guards. Valid tuning retains the 0.75-cent contradiction veto. The new regression test covers early, valid mature and invalid mature estimates using the harmful decision inputs. This is opt-in replay code; installed output is unchanged.
- At this checkpoint, detached Modal run `cue-mature-tuning-constructed-20261104T0850Z`, app `ap-YB7jVi1ih84CunnoCXSp4w`, was active. It reused the completed constructed cue features from `cue-assignment-constructed-resume-20261104T0726Z` and recomputes all outputs and scores. Do not launch a duplicate. Require at least 259074/1614601 matches, no lost label, wrong-note/wrong-string/extra-gap ceilings 167722/103754/23176, exact OFF equality and ON parity at blocks 32/512/1024. Ordinary and the remaining protected recordings follow only after this gate passes.
- GitHub last pushed checkpoint is `c2ce175fea30a477eeab855e48dfc61e20eb9127`; the mature-tuning change and this checkpoint await the corpus result. Last confirmed inline ntfy receipt is 08:43:21 UTC, 3460 bytes. Continue the ten-minute cadence. Precise prose is selected; research and inactive-log compression are complete. Reliable live use and overall completion remain unmeasured.

## 2026-11-04 08:35 UTC — wider tuning veto rejected on constructed chords

- `cue-tuning-range-constructed-20261104T0824Z` completed at 08:28:31 UTC and is rejected. Matches fall 259074→257470/1614601 (16.0457%→15.9464%; −1604 frames, −0.6191% relative). Wrong-note/wrong-string/extra-gap counts change 167722/103754/23176→175058/102380/23627; total false outputs rise 294652→301065. Fewer wrong-string outputs do not offset the lost matches and added wrong notes and gap outputs. Sixteen labels lose matches. OFF exactly reproduces the baseline; further ON buffer and corpus checks stopped. Installed output is unchanged.
- Paired diagnostic `cue-tuning-range-failure-20261104T0832Z`, app `ap-3ZrmD9dFVfBhSFcOxSP7Oh`, completed at 08:38:43 UTC. Both complete-history replays reproduce every saved score, with complete traces. The first differing output is sample 4751807: MIDI 49 moves from string 2 to string 4 as phase reaches −60.7600 cents after 2284 accepted updates. Losing output-projection validity disables the veto despite a 32.2070-cent tuning advantage for the incumbent. The wider guard delayed the same harmful switch by four detector frames (256 samples, 2.667 ms). The next candidate requires valid tuning after the existing 160 ms evidence threshold, while preserving early correction.
- The small-screen gain and focused checks below remain valid for this rejected candidate. Any replacement must preserve those gains, at least 259074 constructed matches and every passage, error ceilings 167722/103754/23176, exact OFF equality and ON parity at blocks 32/512/1024. Full protected-corpus, realtime and MIDI lifecycle/host gates remain open.
- GitHub includes the candidate, instrumentation, feature reuse and earlier checkpoint in `c2ce175fea30a477eeab855e48dfc61e20eb9127`. The 08:29:36 UTC ntfy receipt confirms an inline 3279-byte rejection summary. Continue the ten-minute cadence. Precise prose is selected; research and inactive-log compression are complete. Overall completion and reliable live use remain unmeasured.

## 2026-11-04 08:26 UTC — wider tuning veto passes the small screen

- Active detached Modal run: `cue-tuning-range-constructed-20261104T0824Z`, app `ap-DepDvLyS2r37s4E0BL7m4w`. It checks the constructed recording with the new saved binary and previously completed cue features. All outputs and scores are recomputed. Do not launch a duplicate. Installed output is unchanged.
- Small screen `cue-tuning-range-20261104T0819Z` completed at 08:21:54 UTC and is accepted for corpus testing. Nearby matches rise 815→835/3450 (23.62%→24.20%; +20 frames, +2.45% relative), while wrong strings fall 1548→1528; wrong notes remain 3178 and extra outputs in unlabeled gaps remain 668. Solo gains 17 matches and quiet octave gains nine. Seven other cases are bit-identical. All ten OFF controls match the baseline, all ten ON outputs agree across blocks 32/512/1024, and all 64 focused native tests pass. Binary SHA-256: `ad6a6726124c44bf5da75097d433252f36f3a2a734f7fed83f2125a016c167a1`.
- Diagnostic `cue-decision-inputs-20261104T0806Z` completed at 08:10:11 UTC. Instrumentation reproduces every label score and output fingerprint for the helpful nearby case and the rejected constructed recording. Eight cue tests and 48 offline tests pass. The trace records actual cue inputs and every proposed move, including decisions between regularly sampled rows.
- At the first harmful move, sample 4751551, MIDI 49 moves from string 2 to string 4. The actual descriptor similarity is 0.98767, so the 0.97 guard works. Tuning has settled after 2280 updates but is −51.6409 cents: outside the narrow ±50-cent pitch bin, inside the existing ±60-cent output-projection range. Losing the narrow validity flag disabled the contradiction veto despite a 32.2070-cent tuning advantage for the incumbent. The helpful move at sample 44799 has only 181 updates and remains unsettled.
- The candidate uses settled output-projection validity for the existing 0.75-cent contradiction veto. It leaves early corrections without settled tuning eligible under the other guards. Pitch admission, tuning calculation and default MIDI behavior are unchanged. The small screen preserves the useful correction; the constructed-corpus safety result is pending.
- Thirteen Python checks pass for saved cue reuse. `--reuse-cue-features --cue-checkpoint-run RUN` permits a new native binary while requiring identical audio, annotations, calibration, settings, feature source and rules, clocks, cue hash and complete extraction. No replay or score is reused. The active constructed screen reuses completed cues from `cue-assignment-constructed-resume-20261104T0726Z`. Require at least 259074 matches, no lost passage, wrong-note/wrong-string/extra-gap ceilings 167722/103754/23176, exact OFF equality and ON parity at blocks 32/512/1024. If it passes, test ordinary chords with cues from `cue-assignment-ordinary-20261104T0643Z`, then the remaining protected corpora.
- The latest inline ntfy receipt is 08:18:32 UTC, 3311 bytes, attachment absent. Continue the ten-minute cadence from fresh evidence. Research and inactive-log compression are complete. Live readiness and overall completion remain unmeasured.

## 2026-11-04 07:56 UTC — constructed regression isolated to string assignment

- `cue-assignment-constructed-resume-20261104T0726Z` completed at 07:33:40 UTC and is rejected. Matches fall 259074→254400/1614601 (16.0457%→15.7562%; −4674 frames, −1.8041% relative). Wrong-note/wrong-string/extra-gap counts rise 167722/103754/23176→170861/104719/24077; total false outputs rise 294652→299657. Eighteen passages lose matches. OFF exactly reproduces the baseline and every label score. Further ON buffer and corpus checks stopped. The ordinary pass below remains valid for that recording; installed output is unchanged.
- Paired diagnostic `cue-assignment-failure-resume-20261104T0749Z`, app `ap-YoCHSm396HwqfBLUURdVXZ`, completed at 07:50:37 UTC. Both outputs and every label score reproduce the saved rejection. It reused the completed OFF traces after validating inputs, window, binary and scores, and replayed only ON. All trace row counts are complete. The summary now follows native exact-string-set scoring; eleven focused tests cover extra same-pitch strings, incomplete groups and unconstrained labels. Native scoring and detector code are unchanged.
- The saved-trace comparison, app `ap-zxkzowp2C7p0otV81VHrTe`, verified all four raw trace hashes. The first output difference and lost match occur at sample 4751551: MIDI 49 moves from string 2 to string 4 after identical earlier output. Label 69 falls 1455→507/3448. Pitch selection and admission evidence are unchanged at the first loss. Report: `build/modal/cue-assignment-failure-resume-20261104T0749Z-first-assignment-difference.json`.
- No Modal job is running. Next: capture the actual reassignment inputs. The existing descriptor snapshot precedes the phase-tuning update, while the move uses a recomputed descriptor; its earlier 0.938 similarity does not establish a bypass of the 0.97 guard. Any revised candidate must preserve constructed matches at least 259074, every passage, wrong-note/wrong-string/extra-gap ceilings 167722/103754/23176, exact OFF equality and ON parity at blocks 32/512/1024 before expanding coverage.
- The candidate remains offline-only. Reliable live use and overall completion are not measured. Precise prose and ten-minute inline ntfy updates remain in use; research and inactive-log compression are complete.

## 2026-11-04 07:26 UTC — constructed corpus resumes from saved cues

- Active detached Modal run: `cue-assignment-constructed-resume-20261104T0726Z`, app `ap-BTk31v3Lc3HqrR4BXFOgfK`. It uses the saved binary from `cue-assignment-only-20261104T0639Z` and the completed cue file from `cue-assignment-constructed-20261104T0653Z`. Do not launch a duplicate. Require at least 259074/1614601 matches, no lost label, wrong-note/wrong-string/extra-gap counts no higher than 167722/103754/23176, exact OFF equality and ON parity at blocks 32/512/1024. Isolated strings follow only after this gate passes.
- The first constructed app was canceled when its local client disconnected at 07:11:33 UTC; Modal records it stopped at 07:13:00. Cue extraction completed across 29491200 samples with 59536 intervals, but no replay verdict was saved. The continuation checks recording, calibration, source report, binary, frozen rules, cue hash and complete counts before reusing cues. It never reuses partial replay output. Eleven focused Python tests, runner syntax and whitespace checks pass. Use `modal run --detach` for subsequent long cloud checks.
- Ordinary corpus `cue-assignment-ordinary-20261104T0643Z` passed at 06:51:49 UTC. ON is bit-identical to OFF and the old baseline: 145385/528632 matches (27.50%), with wrong-note/wrong-string/extra-gap counts 164263/92653/62856 and total false outputs 319772. No passage loses matches. ON is identical at all three tested buffers. The earlier ordinary-corpus losses are absent; this proves safety on this recording, not a match gain or live readiness.
- The small screen completed at 06:42:02 UTC. Nearby target matches rise 815→835/3450 (23.62%→24.20%; +20 frames, +2.45% relative). Wrong strings fall 1548→1528; wrong notes remain 3178 and extra outputs in unlabeled gaps remain 668. Solo gains 17 matches and quiet octave gains nine. The other seven cases are bit-identical. All ten OFF controls match the old baseline, ON output matches across the tested buffers, and all 64 focused native tests pass. Final report: `build/modal/cue-assignment-only-20261104T0639Z.json`.
- The earlier ordinary failure first diverges in pitch selection at sample 3205247: OFF emits candidate 52, while ON suppresses it as a harmonic shadow of 71. Later slot loss on MIDI 54 does not prove a string correction caused it. Full saved outcome traces were hash-verified and compared on Modal without a new replay. Evidence: `build/modal/cue-veto-failure-20261104T0609Z-first-outcome-difference.json`.
- The free-lane experiment now uses frozen cues only to reassign already selected pitches. Explicit fundamental admission remains a separate opt-in diagnostic. The tuning contradiction, calibration, occupancy and unison guards are retained. Installed output and defaults are unchanged; full-corpus, unison, realtime and MIDI lifecycle/host gates remain open. Use Precise prose and ten-minute inline ntfy summaries within 4000 UTF-8 bytes. Research and inactive-log compression are complete.

## 2026-11-04 06:09 UTC — ordinary corpus rejects tuning veto; first loss under diagnosis

- `cue-veto-ordinary-20261104T0600Z` completed at 06:07:03 UTC and is rejected. Matches rise 145385→145596/528632 (27.502%→27.542%; +211 frames, +0.145% relative). Wrong notes fall 164263→163561, but wrong strings rise 92653→93192 and extra outputs in unlabeled gaps rise 62856→62947. Total false outputs fall 319772→319700; that does not offset the separate safety failures. Labels 187/188/192/196 lose 31/7/11/8 matches. The earlier 858-frame loss on label 243 is absent. OFF is exactly baseline; further ON buffer and corpus checks stopped.
- Active diagnostic: `cue-veto-failure-20261104T0609Z`, app `ap-tqYZOmNqXXeAxlt3QJLTFL`. It traces the first loss, label 187 (MIDI 54/string mask 8), using the saved binary and complete audio history. That passage falls 902→871/1122 matches. Do not launch a duplicate. Identify the wrong correction before another candidate; require no lost label or higher wrong-note/wrong-string/extra-gap count, exact OFF equality and ON buffer parity before expanding recordings.
- The small screen completed at 05:57:35 UTC. Nearby target matches rise 815→835/3450 (23.62%→24.20%; +20 frames, +2.45% relative), while wrong strings fall 1548→1528. Wrong notes remain 3178 and extra gap outputs 668. Solo gains 17 matches and quiet octave gains nine; the other seven cases are bit-identical. All ten OFF controls match the old baseline, and ON is identical across the tested buffers. All 63 focused native tests pass. Final report: `build/modal/cue-tuning-veto-20261104T0556Z.json`.
- Valid tuning vetoes a sound-based correction when it favors the incumbent by at least 0.75 cents. Missing tuning does not bypass pitch, sound, calibration, occupancy or unison guards. The full ordinary recording rejects this candidate despite the small-screen gain. Installed output and defaults are unchanged; full-corpus, unison, realtime and MIDI lifecycle/host gates remain open. GitHub/checkpoint prose uses Precise mode; research and inactive-log compression are complete.

## 2026-11-04 05:54 UTC — contradiction-only tuning guard on Modal

- Active run: `cue-tuning-veto-20261104T0556Z`, app `ap-RhosvE88lEw9GUILd7kq5m`. Do not launch a duplicate. The candidate vetoes a sound-based move when valid tuning favors the incumbent by at least 0.75 cents. Unavailable tuning leaves the independent pitch, sound, calibration, occupancy and unison guards in control. Installed output is unchanged.
- The focused tests cover the known harmful MIDI-48 move, the missing-tuning MIDI-36 opportunity, the tuning boundary and invalid measurements. Results are pending. The small screen must exceed 815/3450 nearby matches with no control/error regression, exact OFF and ON buffer parity before ordinary-corpus verification. Ordinary must preserve every labeled passage and all false-output ceilings.
- GitHub checkpoint `428c013` records the rejected strict guard. This candidate remains unaccepted until the Modal report is final. Use Precise prose and inline ntfy summaries of at most 4000 UTF-8 bytes. Research and inactive-log compression are complete.

## 2026-11-04 05:50 UTC — strict tuning guard rejected without a held-out gain

- Modal `cue-tuning-guard-20261104T0541Z`, app `ap-WBakhcGtZ9Pz5dSuYRrG5A`, completed at 05:45:40 UTC. All 62 focused native tests pass. Every one of the ten ON cases is bit-identical to OFF; OFF matches the saved baseline, and ON matches across blocks 32/512/1024. The nearby target stays 815/3450 (23.62%), so this candidate is rejected. No broad-corpus replay was started. Installed output and defaults are unchanged.
- The strict guard requires valid phase tuning and at least 0.75 cents lower tuning error on the preferred string. It removes the previous nearby gain of 20 frames, as well as the solo and quiet-octave gains. Final report: `build/modal/cue-tuning-guard-20261104T0541Z.json`.
- Saved target snapshots contain 20 sound-qualified decisions with the destination apparently free; all have invalid phase tuning. Five decisions with valid tuning have an occupied destination. This explains why requiring valid tuning can eliminate useful opportunities. Snapshot occupancy does not expose every internal reservation. Evidence: `build/modal/cue-tuning-guard-20261104T0541Z-target-diagnosis.json`; calibration hash matches the replay input.
- The earlier harmful MIDI-48 move at sample 4341823 has valid tuning: 1.163126 cents, versus learned values 1.04296875 on the original string and 6.19140625 on the competing string. Its errors are about 0.12 versus 5.03 cents. Evidence: `build/modal/cue-corpus-failure-20261104T0025Z-exact-move.json`. The wrong move later blocks MIDI 55, losing 858 matches in that passage.
- Next candidate: veto a sound-based string change when valid tuning favors the incumbent by at least 0.75 cents; treat unavailable tuning as unavailable. Preserve complete calibration, independent pitch cues, free-destination and unison guards. This is a hypothesis, not an accepted repair. Require nearby >815/3450 with no control/error regression, exact OFF and ON buffer parity before repeating ordinary. Ordinary requires >=145385 matches, no lost label or higher error count. Full-corpus, unison, realtime and MIDI lifecycle/host gates remain open.
- GitHub already has the causal diagnosis in `7903769e4657853db9f259cfa7fd68289a5bce42`; this checkpoint records the rejected strict guard. Use Precise prose and fresh evidence for inline ntfy summaries at most 4000 UTF-8 bytes. Never retry an ambiguous send. Research and inactive-log compression are complete.

## 2026-11-03 23:54 UTC — small string-correction trial passes; ordinary corpus running

- Modal `cue-free-lane-replay-20261103T2332Z`, app `ap-hVxZH1KTjz7dZpNUQwBEwy`, completed at 23:35:06 UTC. The offline candidate is accepted for corpus screening. Nearby-note target matches rise 815→835/3450 (23.62%→24.20%; +20 frames, +2.45% relative); aggregate matches rise 2987→3007/6900 (43.29%→43.58%). Wrong-string outputs fall 1548→1528; wrong-note and extra-gap outputs stay 3178 and 668. Installed output is unchanged.
- Solo and quiet-octave cases also gain 17 and 9 matches, respectively, with equal reductions in wrong-string outputs. The other seven cases are bit-identical. All ten old-baseline/new-OFF controls match, and every ON result is identical at blocks 32/512/1024. Sixty focused native tests pass. Final report: `build/modal/cue-free-lane-replay-20261103T2332Z.json`.
- Active run: `cue-corpus-ordinary-20261103T2350Z`, app `ap-8WBrg4VJWESiT6oBdQOi97`. Do not launch a duplicate. It reuses the accepted binary, measures the frozen cue for every playable pitch MIDI 32–84 without using labels to select cues, then compares baseline/OFF/ON output for each annotated passage. Final report will be `build/modal/cue-corpus-ordinary-20261103T2350Z.json`.
- The earlier `cue-corpus-ordinary-20261103T2346Z` attempt stopped before feature measurement because its reader accepted only float32 WAV files. The ordinary recording is PCM16. The reader now supports both formats, preserving the native PCM16 conversion of sample/32768. Seven corpus-reader/scoring tests and twenty related Python tests pass; compilation and whitespace checks pass.
- Corpus acceptance requires no lost matches in any labeled passage, no higher wrong-note/wrong-string/extra-gap/total false-output count, exact old-baseline/new-OFF equality, and ON parity at blocks 32/512/1024. The freshly measured ordinary baseline is 145385/528632, with errors 164263/92653/62856, matching the installed scoreboard. This replaces the older 145397 reference used when preparing this screen; compare the candidate against the current paired replay. Expand to protected recordings only after this gate passes.
- The correction remains default-off and replay-only. Frozen pitch evidence can redirect a selected single-string note only with complete calibration, similarity at least 0.97, margin at least 0.02 and an unused preferred string. Occupied strings, existing or emerging unisons and conflicting proposals are preserved. No pitch is removed. Timing/allocation, lifecycle/routing and actual-host gates remain open.
- The 23:38:21 and 23:50:49 UTC ntfy attempts have no confirmed receipt and must not be retried. The local sender now strips outer whitespace before byte counting and publishing, matching ntfy's receipt normalization. The next distinct ten-minute summary will check delivery. Use fresh status/report evidence and at most 4000 UTF-8 bytes. Research and inactive-log compression are complete; GitHub/checkpoint prose uses Precise mode.

## 2026-11-03 23:32 UTC — guarded string correction running on Modal

- Active run: `cue-free-lane-replay-20261103T2332Z`, app `ap-hVxZH1KTjz7dZpNUQwBEwy`. Do not launch a duplicate. It builds and tests the default-off replay path, then compares the ten held-out cases at blocks 32/512/1024. The report will be `build/modal/cue-free-lane-replay-20261103T2332Z.json`.
- The first build stopped on a test-only integer-conversion warning. Its final failure report is `build/modal/cue-free-lane-replay-20261103T2330Z.json`. Explicit byte-sized test inputs fix the warning; the detector policy is unchanged.
- The frozen pitch cue may correct a selected note's string only with complete playable-string calibration, similarity at least 0.97, a margin of at least 0.02, and an unused preferred string. Occupied strings and emerging or established unison groups are preserved. Proposals share a fixed occupancy snapshot; conflicting proposals are rejected together. No pitch is removed and no installed behavior changes.
- Accept only if nearby_0dB target matches exceed 815/3450, every control preserves target/aggregate matches and all error ceilings, old-baseline/new-OFF output is identical, and ON output is buffer invariant. The broader corpus and live gates remain required after this screen.
- The 23:27:29 UTC ntfy summary was confirmed inline: 3283 bytes, HTTP 200, receipt `HZSEu3UaGHWp`. Use fresh status evidence for the next ten-minute summary; do not retry an ambiguous send.

## 2026-11-03 23:14 UTC — frozen-cue replay rejected; wrong-string failures isolated

- Modal `frozen-cue-replay-20261103T2259Z`, app `ap-eOOpj5SiCoAPpXf684Oi3V`, completed at 23:02:07 UTC. The final report is `build/modal/frozen-cue-replay-20261103T2259Z.json`. The candidate is rejected for no strict target gain. Follow-up `frozen-cue-selection-20261103T2310Z`, app `ap-6bdpsEetQf7CRlyZ5q5uN3`, completed at 23:09:44 UTC with identical output and complete traces. No job from this slice remains running.
- All ten held-out cases have identical old-baseline, new-OFF and new-ON outputs. ON also matches at block sizes 32/512/1024. The hardest target remains 815/3450 (23.62%); aggregate matches remain 2987/6900 (43.29%). Wrong-note/wrong-string/extra-gap outputs remain 3178/1548/668, total 5394. No case loses matches or increases an error count.
- Cue-active decisions match 222/544 target frames (40.81%). Of the remaining 322, 210 emit MIDI 36 on the wrong string and 112 emit no target voice; none changes a detected MIDI 36 into another pitch. All 186 selected-but-unmatched frames are wrong-string outputs. The 97 below-admission frames all fail the direct-peak or fundamental-ratio prerequisite despite exceeding the scalar score threshold. Thirteen more are selector evictions and two are coasting without output. Do not lower a global threshold from this result.
- The expected string carries another note in 148/322 misses, MIDI 35 in 147. The descriptor prefers the expected string in 153/223 misses with a reported target candidate; 99 candidate entries are unreported, not zero evidence. Saved traces and cues match the cloud hashes. Detail: `build/modal/frozen-cue-selection-20261103T2310Z-output-diagnosis.json`.
- Fifty-six focused native tests and twenty-eight Python tests pass. The cue sidecar is causal, bounded and replay-only. Installed output and production defaults are unchanged; broader corpus and live-use checks have not run on this trial.
- Next: test whether the frozen pitch cue plus measured string evidence can resolve competing assignments. Require target matches >815/3450 in nearby_0dB, no target/aggregate loss or increased false counts in any control, and exact OFF equality before corpus expansion. Use one bounded Modal experiment; do not repeat the rejected admission matrix.
- The fresh 23:16:57 UTC ntfy summary was confirmed as inline text (3298 bytes, HTTP 200). The earlier ambiguous attempt was not retried. Continue distinct periodic summaries at ten-minute intervals, at most 4000 UTF-8 bytes each, with the saved-credential publisher. Read the latest receipt for current delivery state.

## 2026-11-03 22:41 UTC — frozen overtone screen passes on second plucks

- Modal `independent-partials-heldout-20261103T2239Z`, app `ap-y9qUIPMP9TxRFAquViIciT`, completed at 22:39:53 UTC. Final report: `build/modal/independent-partials-heldout-20261103T2239Z.json`. The diagnostic is accepted for the next replay step; installed output is unchanged.
- The rule was frozen before measuring pass 2: both third/fifth-overtone local contrasts strictly above `8.593275855114637` dB, with pitch agreement at most 25 cents. It gives 520/1080 target-present cues (48.15%), 0/3240 absent-note cues and 0/1700 clear-gap cues. Every target case has evidence; the equal-level nearby-note mixture gives 34/216 (15.74%). These are feature observations, not matched MIDI frames.
- The first pass-2 pluck of each source note was selected before spectral analysis. The pass-1 raw crops match the earlier training crops byte-for-byte; pass-2 spans are disjoint and have different sample hashes. This tests repeatability within one recording session, not another guitar/session. Silence is digital zero, not recorded room noise. Windows and reused mixtures are correlated.
- The first cue arrives 155.33–166.00 ms after the labeled crop starts. The causal window remains 16384 samples at 96 kHz (170.7 ms). No native MIDI replay, callback timing, allocation, lifecycle or live-use result is claimed. The accepted three-second unison evidence window is unchanged.
- Validation: 13 focused Python tests, compilation and whitespace checks pass. Boundary tests retain absent-note false cues, reject missing/nonfinite features, and separate window tails from clear gaps.
- Next: add a default-off offline replay path for the frozen cue. Require strict MIDI36/string-mask1 recovery in nearby_0dB, no target/aggregate loss or increased safety count in any control, and exact OFF equality. Only then expand to ordinary matches >145385 with preserved error ceilings and the protected/live gates. Preserve 3 seconds / 0.20 / 0.50 and -9/60/75/poly5/fret24.
- Research and inactive-log compression are complete. Continue ten-minute inline ntfy updates from current evidence, <=4000 UTF-8 bytes, with delivery state in `build/modal/latest-notification-receipt.json`; never retry an ambiguous send. GitHub/checkpoint prose uses Precise mode.

## 2026-11-03 22:32 UTC — local overtone reference measured; separate-take test next

- Modal `independent-partials-local-reference-20261103T2226Z`, app `ap-OSl5pMhurkBJzMeraAhu5J`, completed at 22:27:17 UTC. Final report: `build/modal/independent-partials-local-reference-20261103T2226Z.json`. No job from this slice is running. The installed plugin and MIDI policy are unchanged.
- The original third/fifth-overtone cue remains 0/1080 target-present frames: its 1% global power floor rejects every fifth overtone, including the solo low note. New measurements compare each overtone with fixed nearby frequency bands and record pitch agreement even when that floor rejects it. All nine original case metric groups are unchanged.
- In the equal-level nearby-note mixture, paired overtone contrast exceeds the measured negative-control maximum in 31/216 frames (14.35%); the fifth overtone alone does so in 0/216. Both peaks are target-dominated in all 31 by source-component power accounting. This is spectral separation within one take, not recovered MIDI, a proven independent source cue or a measured false-positive rate. Joint pitch-agreement acceptance has not yet been counted.
- Next: freeze the paired contrast threshold at strictly greater than `8.593275855114637` dB and retain the existing 25-cent agreement condition before testing separate low/upper-string recordings. Require useful target evidence and zero cues in source-only and absent-neighbor controls. A fitted control maximum cannot establish safety on new recordings. Only a passing result advances to the existing target-specific replay gate, then ordinary matches >145385 with preserved error ceilings and all protected/live gates.
- Validation: 11 focused Python tests and compilation pass; one focused review is complete. This diagnostic uses a causal 16384-sample window at 96 kHz (170.7 ms), with no native build, MIDI replay or installation. It does not shorten the accepted three-second evidence window. Preserve 3 seconds / 0.20 / 0.50 and -9/60/75/poly5/fret24.
- Research and inactive-log compression remain complete. Continue ten-minute inline ntfy updates from current evidence, <=4000 UTF-8 bytes. Read `build/modal/latest-notification-receipt.json` for delivery state; never retry an ambiguous send. Details and limits: `docs/PARTIAL-MOTION-RESEARCH.md`.

## 2026-11-03 15:06 UTC — fundamental-admission trial rejected; target scoring corrected

- Modal `controlled-admission-20261103T1457Z`, app `ap-IAhnUeIrJYnBEkFjBz9CCs`, completed at 14:59:37 UTC. Final report: `build/modal/controlled-admission-20261103T1457Z.json`. No job remains running from this slice; do not repeat the rejected trial or expand it to the corpus.
- Default-off, offline-only `--diagnostic-fundamental-admission` tests a strong direct fundamental above the unchanged threshold, with playable/non-narrow evidence and rejection of stronger eligible harmonic explanations. Equal-RMS nearby MIDI49 raised aggregate matches 3250→3507/6900 (47.10→50.83%), but wrong notes rose 149, wrong strings 1505, extra gap outputs 12 and total false outputs 1666. Quiet added octave also regressed: six fewer matches and 32 extra false outputs. All five same-binary OFF controls exactly match saved outputs. Installed output and defaults are unchanged.
- One focused review found that the original `target_improved` field counted both notes together. Target-note recovery is not measured by this completed report; its safety rejection still stands. `tools/controlled_admission_gate.py` now requires `--label-details`, unchanged target identity/labels, no target or aggregate match loss in any case, no higher error count, and a strict MIDI36/string-mask1 gain in nearby_0dB. Missing or inconsistent evidence fails closed. The original cloud report is preserved.
- Validation: 53 focused native tests passed in Modal (2 admission, 5 harmonic admission, 46 offline replay); six local gate/parser tests, Python compilation, source-contract check and whitespace check pass. One review completed and its scoring issue is fixed. This trial used block 512 only; the earlier control experiment's 32/512/1024 parity is separate. No new full native, realtime/allocation, production build, validator, lifecycle or live-use result; no installation.
- Next: seek an independent partial/reference that distinguishes a real low note from overlapping energy before another admission rule. Require target-specific improvement across the five saved controls with every safety count preserved, then ordinary matches >145385 and all protected/live gates. The present direct-peak rule is rejected, not a parameter-sweep starting point. Preserve 3 seconds / 0.20 / 0.50 and -9/60/75/poly5/fret24.
- Requested research and compression are finished: 835 inactive logs compressed and verified, reclaiming 3,668,400,185 bytes; active/recent histories preserved. Sources and results: `docs/PARTIAL-MOTION-RESEARCH.md`. Latest notification attempt at 15:00:05 UTC was ambiguous and must not be retried; use fresh evidence for the next scheduled update, no earlier than 15:10:05 UTC. Read `build/modal/latest-notification-receipt.json` for newer delivery state.

## 2026-11-03 14:38 UTC — saved-mixture admission failure located

- One diagnostic replay is complete; no new MIDI policy or installation. Modal `controlled-selection-20261103T1438Z`, app `ap-EdN3xo0azmWOcY5DHaerud`, report `build/modal/controlled-selection-20261103T1438Z.json`, finished at 14:38:07 UTC. No M3 job remains running from this slice.
- Same cached nearby_0dB audio, labels, calibration and exact native binary as the five-case control below. All seven output fields match: fingerprint `095d8d9a3e2d65ec`, matches 3250/6900, wrong notes 3383, wrong strings 1642, extra gap outputs 740, total false outputs 5765. This follow-up used block 512; earlier five-case 32/512/1024 parity remains separate.
- The 130 sampled absent MIDI-36 assignment rows split into 117 `below_threshold`, five quiet/startup, four coasting and four selector-pool evictions. All 117 have scores above the scalar threshold but active/local-peak/candidate-evidence flags false. All 1800 such full-rate ticks share that pattern (score ratio 2.840–5.096); 1273 have direct peaks. The disposition names a broader eligibility failure, not low amplitude. Saved trace SHA checked; supplemental `-threshold-breakdown.json` retains the calculation.
- Result narrows the next implementation to admission evidence before assignment. MIDI37 is selected/coasting on 93/117 sampled failed ticks alongside added MIDI49 on all117; causation of the local/evidence failure is still unresolved. Do not change global sensitivity, descriptor weights or selector capacity from this case. First design one offline guard distinguishing an independent low fundamental from neighboring harmonic candidates; require improved saved-mixture matching with no more wrong-note/string/gap outputs, then ordinary matches >145385 and all protected/live gates. Preserve 3 seconds / 0.20 / 0.50 and measured -9/60/75/poly5/fret24.
- Three focused tests, Python compilation, whitespace checks and one focused review PASS. No new full native, realtime/allocation, production build, validator or live-use claim. Details and sources: `docs/PARTIAL-MOTION-RESEARCH.md`.
- Requested research and log compression are complete: 835 inactive files verified and compressed, 3,668,400,185 bytes reclaimed; active/recent sessions preserved. Do not repeat completed captures or compression. Latest notification attempts at 14:24 and 14:37 had no confirmed receipt; do not retry them. Use fresh status and current receipt for the next scheduled ten-minute update, <=4000 UTF-8 bytes; the publisher wrapper now retains a safe HTTP failure code when provided.

## 2026-11-03 14:25 UTC — controlled overlap completed; broad descriptor explanation not reproduced

- Offline diagnostic complete. Modal `controlled-descriptor-overlap-20261103T1423Z`, app `ap-zrlKXf4xao0BqzCa6toH18`, finished at 14:24:59 UTC. Final report: `build/modal/controlled-descriptor-overlap-20261103T1423Z.json`. The installed plugin and native policy are unchanged.
- Five cases preserve one string-8 MIDI-36 waveform and onset: alone, plus string-5 MIDI 48 or 49 at -12/0 dB relative RMS. Source crops and annotations are hashed; all cases share gain and padding. No pitch correction, phase alignment or individual mixture normalization. Sources differ in tuning and envelope, so the nominal octave is not exact harmonic coincidence.
- Sustained descriptor margins favor the wrong competing string on 2/116, 0/142, 0/183 and 2/66 eligible mixture rows. The corresponding solo margins all favor the expected string. Short attacks can flip, but the earlier broad sustained descriptor degradation is not reproduced with the fixed waveform. No blanket weight change is justified.
- Important next failures: quiet added MIDI 49 leaves the target available on 211/216 sampled frames with correct pairwise descriptor preference, yet final replay matches 0/6900 expected voice frames. Equal-RMS added MIDI 49 omits the target from 130/216 sampled assignment frames versus 5/216 alone. Absence from this trace alone does not establish missing MIDI or its cause. Inspect saved candidate/ownership/rendering evidence next; do not repeat the five-case experiment.
- Validation: all five cases match untraced outputs and preserve output fingerprints plus trace bytes at 32/512/1024. Twenty focused Python tests, Python compilation and whitespace checks PASS; one focused review found no consequential issue. No new full native suite, production build, deadline/allocation, validator or live-use result is claimed for these Python diagnostics.
- Acceptance remains unchanged: ordinary matches must exceed 145385 with wrong notes <=164263, wrong strings <=92653 and extra gap outputs <=62856, followed by all physical-unison, isolated, constructed-chord and live gates. Preserve 3 seconds / 0.20 / 0.50 and -9/60/75/poly5/fret24.
- Research and log cleanup are complete: 835 inactive files compressed and verified, reclaiming 3,668,400,185 bytes; active/recent history preserved. Archive manifest and restore instructions: `~/.codex/session-archives/m3-20261103/`. Continue ten-minute inline ntfy summaries from fresh evidence and receipt state, <=4000 UTF-8 bytes. The 14:24:29 attempt had no confirmed receipt and must not be retried; next scheduled attempt is due no earlier than 14:34:29 UTC.

## 2026-11-03 14:07 UTC — matched descriptor comparison completed

- Saved-trace analysis only; no new native policy, audio replay or installation. Modal `descriptor-context-20261103T1407Z`, app `ap-HpS34OtwJINmvZ0iaWK3wi`, completed at 14:07:07 UTC. Report: `build/modal/descriptor-context-20261103T1407Z.json`.
- New `tools/string_descriptor_context.py` matches note/string/fret, competing playable string and annotation age; validates trace hashes and observation eligibility; retains missing rows as unavailable. Segment weighting prevents long notes dominating the comparison. The small cloud runner reuses the existing ordinary and isolated-08 captures.
- All 12 measured comparisons favor the wrong competing string more often in chords. Sustained note 36: isolated 0.00%, chord 98.65%; note 37: 13.66% to 85.61%; note 38: 55.19% to 85.46%; note 39: 4.37% to 72.97%; note 40 against string 7: 0.00% to 43.86%, against string 6: 0.00% to 7.89%. These are equal-segment pairwise descriptor statistics, not MIDI errors or independent performances. Coverage: 721 chord pairs, 1130 isolated pairs across five low-string pitches.
- Verdict: chord context is associated with degraded descriptor evidence. Different takes still confound causality; isolated note 38 also shows ambiguity. No production candidate is accepted and no held-out gain is claimed. Details and physical mechanism: `docs/PARTIAL-MOTION-RESEARCH.md`.
- Validation: 33 focused Python tests PASS; one focused review found no consequential issues. Earlier capture output/trace parity at 32/512/1024 remains as recorded below. No new production, deadline/allocation, validator or live-use verification.
- Next: controlled overlap using the exact same isolated target waveform, alone versus mixed with existing isolated notes. Keep onset/calibration fixed and compare colliding/noncolliding harmonics at declared levels. A signal-derived reliability rule must pass held-out correction-minus-spoil and downstream-recovery checks before causal MIDI replay; then all ordinary, unison, isolated, constructed-chord and live gates remain required. Preserve 3 seconds / 0.20 / 0.50.
- Research and inactive-log compression remain complete: 835 files verified and compressed; 3,668,400,185 bytes reclaimed; active/recent history preserved. Do not repeat completed compression/captures. Continue ten-minute inline ntfy updates from fresh reports and receipt state, <=4000 UTF-8 bytes, no retry of ambiguous sends.

## 2026-11-03 13:48 UTC — spectral likelihood failure isolated

- Offline diagnostic slice complete. Production state, defaults and installed output remain unchanged. Two appended assignment-trace fields record the exact weighted, centered detuning contribution and its validity mask; missing evidence is distinct from a measured zero.
- Modal `string-detuning-evidence-20261103T1340Z`, app `ap-LdI8x83nCynr8wvYrcSrK6`, completed at 13:48:45 UTC. Final report: `build/modal/string-detuning-evidence-20261103T1340Z.json`. Ordinary and isolated-08 counts/fingerprints match untraced controls at 32/512/1024; trace bytes are also identical across those blocks.
- Reproducible decomposition: `python3 -m tools.string_likelihood_decomposition --trace build/modal/string-detuning-evidence-20261103T1340Z-ordinary.tsv.gz --capture-report build/modal/string-detuning-evidence-20261103T1340Z.json --dataset ordinary --output build/modal/string-likelihood-components-20261103.json`. It verifies source trace identity, clock and row accounting; reserved/unplayable expected lanes are excluded.
- The rejected shadow still corrects 607 assignments and spoils 936. Of the spoiled pairs, spectral descriptor favors the wrong lane in 803 while cents favor the expected lane in 758. Descriptor reverses the sum of the other likelihood terms in 623 pairs; detuning does so in 95. Those comparisons overlap. Descriptor also rescues 350 corrected pairs, so wholesale removal is unsupported. These are frozen intermediate decisions, not causal MIDI gains.
- Checks: 46 native offline tests PASS, 57 Python checks PASS (including 32 source-contract checks), whitespace check PASS. One focused review complete. Its requested sign/weight assertion passes in targeted cloud app `ap-kV4C0V9nVM1HRWwCETeN9I`; report `build/modal/string-detuning-weight-test-20261103.json`. The initial packaging-only failure was stopped; no native test had run in it. No new production build, deadline/allocation, validator or install result.
- Next: compare isolated and overlapping-chord descriptor residuals at the same note/string, keeping attack/sustain and corpus identities separate. Distinguish overlap contamination from calibration bias before changing weights. Only a fixed signal-derived reliability rule with a positive corrected-minus-spoiled shadow result and protected downstream recoveries advances to causal replay. Require ordinary matched >145385, wrong notes <=164263, wrong strings <=92653 and extra gap outputs <=62856, then every protected/live gate. Preserve 3 seconds / 0.20 / 0.50.
- Requested research and log cleanup are complete: sources and measured route in `docs/PARTIAL-MOTION-RESEARCH.md`; 835 inactive files compressed and verified, 3,668,400,185 bytes reclaimed. Current/recent history preserved. Archive manifest and restore instructions: `~/.codex/session-archives/m3-20261103/`. Do not repeat compression or the completed captures.
- Notifications: use the latest receipt/status for the ten-minute cadence and fresh report evidence. Keep each inline message <=4000 UTF-8 bytes; do not retry an ambiguous send.

## 2026-11-03 13:26 UTC — observation-cost shadow rejected

- Compared one fixed observation-cost replacement on the saved ordinary-chord trace. No audio replay, native output change, new Modal job or installation. Current Modal capture `string-evidence-20261103T1258Z` remains completed and final.
- Result: REJECTED. Of 12,867 scored single-string targets, native intermediate assignment was correct in 7,636 (59.35%); shadow assignment in 7,307 (56.79%). It corrected 607 and spoiled 936, net -329 (-4.31%, -2.56 percentage points). These are sampled intermediate decisions, not full replay or MIDI counts. Another 1,125 changed decisions were unlabeled.
- The auditor exactly reconstructs native cost and packed assignment for 8,663 feasible frames; 746 native-infeasible frames remain unavailable. No reconstruction mismatches. Existing reservations are enforced and ineligible rows keep their native lanes. Missing pre-assignment selector/pending-group state prevents treating these eligibility checks as sufficient native guards.
- Reproduce with `python3 -m tools.string_observation_shadow --trace build/modal/string-evidence-20261103T1258Z-ordinary.tsv.gz --capture-report build/modal/string-evidence-20261103T1258Z.json --dataset ordinary --output build/modal/provisional-observation-cost-shadow-20261103.json`. The tool streams the trace and verifies its SHA-256 against the capture report.
- Checks: 20 focused Python tests PASS, including later frozen-lane contention; one focused review complete. Earlier capture/native checks remain as recorded below; no new production, real-time, validator or install result is claimed.
- Next: identify the likelihood components that reverse correct ordinary string choices using saved evidence and calibration inputs. No weight sweep or causal replay for the rejected formulation. A new candidate first needs positive corrected-minus-spoiled shadow results, then ordinary matches >145385 with wrong notes <=164263, wrong strings <=92653 and extra gap outputs <=62856, followed by all protected/live gates.
- Log cleanup remains complete: 835 inactive files, 3,668,400,185 bytes reclaimed; current/recent history preserved. Inline notification confirmed at 13:28:35 UTC: `kGPUvV14zBVU`, HTTP 200, 2945 bytes, no attachment. Next periodic attempt no earlier than 13:38:33 UTC.

## 2026-11-03 13:05 UTC — string evidence separated from assignment

- Diagnostic slice complete; installed output and defaults unchanged. Offline traces capture current likelihood, cached prior, updated posterior and onset at the same decision. The streaming auditor retains missing rows and splits annotation age into 0–100 ms, 100–350 ms and settled sound. Labels never enter policy.
- Modal `string-evidence-20261103T1258Z`, app `ap-NqWlIq6poZhVuSSxuzutvJ`, completed at 13:05:27 UTC. Report: `build/modal/string-evidence-20261103T1258Z.json`. Ordinary and isolated-08 outputs match untraced controls and are identical at blocks 32/512/1024; trace bytes also match across blocks. Current Modal job is completed, not running.
- Checks: 46 native offline tests, 10 Python analysis tests and 32 source-contract tests PASS. One focused review found no consequential defect. No new production build, deadline/allocation run, Steinberg validation or install is claimed for this diagnostic.
- Ordinary: 14,107 available ranks out of 33,039 annotated note/tick pairs. Current likelihood correct 8,901; posterior correct 8,978. History fixes 386 ranks and spoils 309, net +77. No posterior penalty is consumed: production requires stable isolated reassignment. Both ranks are correct but valid joint allocation differs in 2,725 cases; downstream rendering recovers 402, leaving 2,323 without the expected string. These decimated counts are not full replay gains.
- Saved-trace cost breakdown for those 2,323: coasting reservation 622, extra-member reservation 1, joint conflict despite lower expected local cost 567; wrong local cost dominated by profile 391, fret 236, cents 202, open-string 67 or retention 237. Descriptive component differences are not isolated causal effects. Extraction and result: `build/modal/string_evidence_cost_diagnosis.py`, `build/modal/string-evidence-20261103T1258Z-cost-diagnosis.json`.
- Isolated-08 control: 1,891/1,902 current ranks correct; 1,895 posterior. All 1,647 settled annotated pairs render the expected string, including 144 intermediate allocation disagreements recovered downstream. Keep this downstream correction intact.
- Next: compare one observation-cost formulation in saved-trace shadow for provisional unreserved ordinary-chord assignments, counting both corrected/spoiled assignments and downstream rescues. No annotation-dependent rule, ownership relaxation or extra smoother. Only useful shadow evidence permits one causal Modal replay. That replay must beat ordinary matched 145385/528632 with wrong notes <=164263, wrong strings <=92653 and extra gap outputs <=62856 on the same source; then all protected and live gates apply. Research/results: `docs/PARTIAL-MOTION-RESEARCH.md`.
- Log compression is complete: 835 inactive files, 3,668,400,185 bytes reclaimed. Current/recent history preserved; verified manifest and restore instructions at `~/.codex/session-archives/m3-20261103/`. No compression job remains active.
- Notification at 13:04:42 UTC was unconfirmed (helper exit 1); do not retry it. The next periodic attempt is due no earlier than 13:14:42. Use current status/final report, inline UTF-8 <=4000 bytes and the saved-credential helper.

## 2026-11-03 12:21 UTC — harmonic measurement availability explained

- Offline diagnostics only. New per-harmonic counters report weak amplitude, phase-step, invalid-frequency, nonfinite and clock-gap causes; fixed-window phase-fit residuals report smoothness, not source purity. No validity rule, source-count decision or MIDI behavior changed.
- Modal `partial-motion-reference-quality-20261103T1222Z`, app `ap-VFZn2Qz136qdPMeap4Fg0b`, completed at 12:20:55 UTC. Report: `build/modal/partial-motion-reference-quality-20261103T1222Z.json`. All prior window, short-hold and single-source statistics remain identical across six saved datasets. No new replay or build.
- Physical isolated note 40 has conditioned valid windows H1–H6 = 13/14, 13/14, 5/14, 0/14, 0/14, 0/14. All six bands are enabled. No nonfinite samples or clock gaps; H4–H6 each fail the existing relative amplitude floor in all 14 windows. H2 improves from 6/14 raw to 13/14 conditioned. The floor is relative to the past peak, not a measured noise level. Do not lower it to manufacture references.
- Physical triple conditioned coverage H1–H6 = 152/164, 163/164, 150/164, 107/164, 82/164, 69/164. Available mixture tracks do not establish a source-dominant reference. The earlier isolated 40.592 cents/second counterexample still rejects standalone motion magnitude; no classifier is promoted.
- Verification: 17 focused Python tests PASS, Python compilation and `git diff --check` PASS, one focused review complete. Earlier capture parity and native/source checks remain as recorded below; no new production, deadline, validator or install result is claimed.
- Next: use explicit availability masks when assessing whether measured motion adds information beyond the existing posterior. A source-dominant reference is still unmeasured and the current physical unison capture has one take. Keep corpus identities separate and report this limitation; synthetic separation cannot stand in for physical acceptance. Preserve 3 seconds / 0.20 / 0.50 and every protected output gate.
- Log compression remains complete: 835 inactive files, 3,668,400,185 bytes reclaimed, verified archives and restore manifest at `~/.codex/session-archives/m3-20261103/`. Active and recent history remain intact. No compression job remains active.

## 2026-11-03 12:12 UTC — partial-motion controls complete; standalone cue rejected

- Offline measurement only; production defaults, installed output and the three-second evidence window are unchanged. Added fixed past-window 160 ms phase slopes after the two causal 15 ms conditioning stages. Annotations choose scoring spans and never reset state. Missing/weak/jumping observations produce unavailable scores.
- Modal saved-capture run `partial-motion-phase-window-20261103T1208Z` completed. Known-single frequency-error RMS falls from 0.205–0.683 cents after conditioning to 0.000644–0.011770 cents with phase-window slopes. This is measurement error on controlled signals, not MIDI accuracy.
- Final control run `partial-motion-isolated-control-20261103T1213Z`, app `ap-LCPNrtGfY6iqQyZpzGzYjw`, completed at 12:11:32 UTC. It reused SHA-verified observations and annotations; no new build or audio replay. Physical isolated note 40 (2.3 seconds) gives 40.592 cents/second H1/H2 motion, inside the scored physical triple range 36.207–136.573. Physical pairs span 42.916–200.541. Standalone motion magnitude is REJECTED as extra-string evidence. One of eight triple windows abstains; isolated bands have 13/13/5/0/0/0 valid slope estimates.
- Verification: 13 Python causal measurement tests PASS; Python compilation and whitespace checks PASS; one focused source/diff review completed. Earlier capture verified all six datasets preserve their control output, with physical-long/isolated-08 fingerprints, counts and trace bytes identical at blocks 32/512/1024; 46 native offline tests and source contract passed for that capture. No new full production build, deadline check, Steinberg validation or install is claimed.
- Research and reproducible route: `docs/PARTIAL-MOTION-RESEARCH.md`. Next: measure reference quality and causes of unavailable harmonic tracks on physical isolated recordings. Select references from signal evidence only. Conditional posterior-plus-motion evaluation requires whole independent physical take holdouts and no added-string regression; current capture has only one physical unison take. No magnitude-threshold tuning or additional ownership/retention tweak is justified by these results.
- Log cleanup is complete: 835 inactive files archived with decompression/SHA-256 verification, reclaiming 3,668,400,185 bytes (3.67 GB); active/recent histories preserved. Manifest and restore instructions: `~/.codex/session-archives/m3-20261103/`. No compression job remains active.

## 2026-11-03 11:19 UTC — supported-owner screen rejected; research route recorded

- Narrowed the offline ownership guard to preserve a disjoint owner only while its signal clears the existing coherence threshold and its phase estimate is valid. Weak, invalid-phase, overlapping and quiet cases retain ordinary handoff/release behavior. Production defaults and the installed bundle are unchanged.
- Verification: full native suite 530/530 PASS; five source-contract checks PASS; causal weak-signal/invalid-phase test fails against the broad guard and passes against the narrowed guard. Production preprocessing excludes the diagnostic guard and state. One focused review completed. Logs: `build/test-results/supported-owner-native-suite.log`, `supported-owner-source-contract.log`, `supported-owner-green-test.log`; exclusion report: `supported-owner-production-preprocess.json`. No production build, validator or install for this rejected trial.
- Modal `supported-owner-handoff-20261103T105408Z`, app `ap-Cm0YTF7v3JilPJ0i9iCqOK`, completed both paired replays. Report: `build/modal/supported-owner-handoff-screen.json`.

| Ordinary recording, block 512 | Matched / 528632 | Wrong note | Wrong string | Extra outputs in unlabeled gaps | Total false outputs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Control | 145397 (27.504%) | 163749 | 92641 | 62856 | 319246 |
| Supported-owner handoff | 146147 (27.646%) | 166731 | 93001 | 63368 | 323100 |

- Verdict: REJECTED. Matching gains 750 frames (+0.516%, +0.142 percentage points), but wrong notes rise by 2982, wrong strings by 360 and extra gap outputs by 512. These are offline counts; the installed baseline is unchanged. No protected replay expansion.
- Research: [measured motion across harmonics](docs/PARTIAL-MOTION-RESEARCH.md) records six primary sources, the relevant physical limits, completed negative experiments, and a bounded Modal comparison. The next question is whether observed cross-partial frequency/envelope motion adds held-out information beyond the existing string posterior. Reuse saved measurements only when recording, calibration and sample identities agree. A fitted component cannot serve as independent evidence. If fields or independent physical takes are missing, report that and keep the feature disconnected.
- Next acceptance: first demonstrate conditional gain on held-out physical recordings without added-member errors on modulated/decaying single-string controls. Any later output trial must improve ordinary matches above 145397 with wrong notes <=163749, wrong strings <=92641 and extra gap outputs <=62856, then pass every protected and production gate. Preserve 3 seconds / 0.20 coherence / 0.50 retention and -9/60/75/poly5/fret24.
- Host housekeeping completed: 835 inactive history/backup files compressed from 5,362,465,648 to 1,694,065,463 bytes, reclaiming 3,668,400,185 bytes (3.67 GB). Every archive passed decompression and SHA-256 verification before its unchanged original was removed. Manifest and restore instructions are outside the repo at `~/.codex/session-archives/m3-20261103/`. Current conversation, recent histories, session database and index were preserved. The separate io24 archive batch reclaimed another 1,831,401,649 bytes; combined savings are 5.50 GB. No compression job remains active.

## 2026-11-03T10:15:13.818535+00:00 — simultaneous attack selection checked; recording screen rejected

- Added offline-only arbitration for simultaneous ready attacks. It chooses compatible complete string groups from current direct-fundamental evidence, fundamental energy and harmonic score, while preserving held/coasting MIDI ownership, attack eligibility, playable frets, event capacity and Max Polyphony. Production defaults and the installed bundle are unchanged.
- Validation: contributor native/replay build PASS; full native suite 529/529 PASS, including both new arbitration tests and existing buffer/label independence, release, panic and allocation checks. Source contract, production-target preprocessing exclusion and whitespace checks PASS. One focused review found no actionable issues. Report: `build/test-results/joint-attack-verification.json`. No new production build, validator or install.
- Modal `joint-simultaneous-attacks-20261103T101209Z`, app `ap-rNtgOFgqotLD2BbtUWWEdn`, completed. Report: `build/modal/joint-simultaneous-attacks-screen.json`.

| Ordinary recording, block 512 | Matched / 528632 | Wrong note | Wrong string | Extra outputs in unlabeled gaps | Total false outputs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Control | 145397 (27.504%) | 163749 | 92641 | 62856 | 319246 |
| Simultaneous attacks | 145676 (27.557%) | 166660 | 93205 | 63273 | 323138 |

- Verdict: REJECTED. Matching gains 279 frames (+0.192%, +0.053 percentage points), but wrong notes rise by 2911, wrong strings by 564 and extra gap outputs by 417. The control fingerprint remains `36150c8ba7813405`. These are offline comparison counts, not a change to the installed baseline. No protected expansion.
- Next: inspect the saved MIDI and candidate timelines for the first lost correct assignment before changing policy again. Require ordinary matches >145397, wrong notes <=163749, wrong strings <=92641 and extra outputs in unlabeled gaps <=62856 before protected expansion. Preserve 3 seconds / 0.20 coherence / 0.50 retention and the measured -9/60/75/poly5/fret24 settings.

## 2026-11-03T09:56:13.772713+00:00 — ownership controls separated; attack-order failure isolated

- Scope: offline diagnostic controls only. The solver and MIDI ownership guard can now run independently. Production defaults and the installed bundle are unchanged.
- Validation: native/replay build PASS; full native suite 527/527 PASS; six CLI success/rejection checks PASS; native source contract, production preprocessing exclusion and whitespace checks PASS. One focused review found no actionable issues. Reports: `build/test-results/joint-ownership-ablation-native-suite.log`, `joint-ownership-ablation-cli.json` and `joint-ownership-ablation-review.json`. No new production build, validator or install.
- Modal ablation `joint-ownership-ablation-20261103T093837Z`, app `ap-XHpdxynmANE0ksnERk09MU`, completed. Report: `build/modal/joint-ownership-ablation-screen.json`.

| Ordinary recording, block 512 | Matched / 528632 | Wrong note | Wrong string | Extra outputs in unlabeled gaps | Total false outputs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Control | 145397 (27.504%) | 163749 | 92641 | 62856 | 319246 |
| Solver only | 145141 (27.456%) | 163749 | 92897 | 62856 | 319502 |
| MIDI guard only | 145629 (27.548%) | 166899 | 93074 | 63378 | 323351 |

- Verdict: both trials REJECTED. Solver-only loses 256 matched frames and adds 256 wrong-string outputs. Guard-only gains 232 matches but adds 3150 wrong-note outputs, 433 wrong-string outputs and 522 extra outputs during unlabeled gaps. The control is an offline comparison, not the installed baseline.
- Causal finding: saved-event analysis completed in app `ap-8yogpvTwJC85C8WI2bdaiQ`; report `build/modal/ownership-guard-first-divergence.json`. At sample 1149183, simultaneous ready candidates 36 and 37 claim lane 0. Ascending pitch order admits 36 first and blocks 37. Candidate 37 has a direct fundamental peak; 36 does not. The missing active 37 later changes harmonic rejection. Labels identify 37 as correct but do not enter the detector policy. This analysis reused saved captures; no new replay.
- Next: Test bounded simultaneous attack arbitration using current spectral evidence and complete string masks before emitting note-ons. Keep existing owners, attack eligibility, silence/release and capacity checks. Require ordinary matches >145397, wrong notes <=163749, wrong strings <=92641 and extra outputs in unlabeled gaps <=62856 before protected expansion.
- Preserve 3 seconds / 0.20 coherence / 0.50 retention and trim -9 dB, Sensitivity 60, Response 75, Max Polyphony 5, Max Fret 24. No broad retuning or annotation-dependent rule. Continue checked GitHub checkpoints and ten-minute inline notifications under 4000 UTF-8 bytes.

## 2026-11-03T08:34:45.317568+00:00 — provisional ownership screen rejected

- Scope: offline, opt-in joint string assignment. Production code and installed output unchanged. GitHub cadence remains checked milestones, with replay outcomes recorded.
- Change: inactive selected candidates no longer reserve experimental solver lanes. Actual emitted MIDI ownership guards new attacks. Atomic handoffs check all other owners before queuing the predecessor note-off; capacity failures leave both event buffer and ownership intact.
- Checks: native/replay build PASS; full native suite 526/526 PASS; six focused ownership, handoff, recovery, silence/panic, partition and label-independence tests PASS; native source contract PASS; production preprocessing exclusion PASS. One focused review found the partial handoff risk; its fix and regression test are included. No new production build, validator or install.
- Modal: `joint-provisional-ownership-20261103T083013Z`, app `ap-bdhTl1v7MuaLw25ekgiQMe`, completed. Report: `build/modal/joint-provisional-ownership-screen.json`. Binary SHA: `b821048920198af92ee12fd98f7229272389e5568a2dea58b86e9848ed933d96`.

| Ordinary recording, block 512 | Matched / 528632 | Wrong note | Wrong string | Extra outputs in unlabeled gaps | Total false outputs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Control | 145397 (27.504%) | 163749 | 92641 | 62856 | 319246 |
| Provisional ownership | 145378 (27.501%) | 166918 | 93325 | 63378 | 323621 |
| Provisional ownership + recovery v2 | 146900 (27.789%) | 166918 | 92930 | 63517 | 323365 |

- Verdict: both trials REJECTED. The combined trial adds 1503 matched frames (+1.034%, +0.284 percentage points), but also adds 3169 wrong-note outputs, 289 wrong-string outputs and 661 extra outputs during unlabeled gaps. Control fingerprint `36150c8ba7813405` is unchanged. Protected corpus and buffer expansion not started.
- Next: inspect the captured assignment and MIDI-event divergences to identify the extra-output mechanism before another output change. Acceptance remains matched >145397, wrong note <=163749, wrong string <=92641, extra outputs in unlabeled gaps <=62856. Preserve 3 seconds / 0.20 coherence / 0.50 retention and the measured -9/60/75/poly5/fret24 baseline.
- Notification: ten-minute cadence, encrypted publisher, inline UTF-8 <=4000 bytes. Most recent confirmed receipt: `40xsBCwnUsLA`, HTTP 200, 2830 bytes, no attachment. Use fresh status/report evidence for each update.

## 2026-11-03T07:47:53.824461+00:00 — offline joint-assignment checkpoint

- GitHub cadence: commit and push completed, checked checkpoints on `work/tuner-stability-20261027`. Keep replay experiments and rejected candidates identified. Heartbeat polls do not create commits. This entry supersedes older instructions below that say the GitHub request has already been fulfilled.
- Latest completed Modal screen: `joint-spectral-recovery-20261103T072228Z`, app `ap-t2y2zYS9IA8nOumnmERTgA`, report `build/modal/joint-spectral-recovery-screen.json`. All three variants were rejected. The best recovery variant changes ordinary matched frames from 145,397/528,632 (27.504%) to 143,509/528,632 (27.147%): -1,888 frames (-1.30%). Wrong-note outputs rise by 19, wrong-string outputs by 3,015, and extra outputs during unlabeled gaps by 139. Installed output is unchanged.
- Added an offline, opt-in bounded joint-assignment solver over complete proposal/fallback combinations. It preserves selected pitches, rejects string conflicts and reserved lanes, and uses posterior margin with incumbent ownership for ties. Existing eligibility and release checks remain in force. Actual MIDI transition logging and residual-recovery continuity diagnostics are included in this checkpoint.
- Current checks passed: contributor `m3_native_tests` and `m3_replay` builds; joint-ownership causal test; positive recovery MIDI-event lifecycle/partition/label-independence/release test; 74 Python analysis/build-contract tests; native source contract; production preprocessing exclusion; focused source review. The lifecycle result supersedes the earlier pending-test note below. Historical full-suite and real-time results do not establish acceptance of this new solver.
- The new combination solver has no corpus result yet. Prepared runner: `build/modal/joint_spectral_combinations_screen.py`; expected report: `build/modal/joint-spectral-combinations-screen.json`. No new replay, production build, validator or install was started for this checkpoint. Source changes remain offline and disabled by default.
- Next: Run the prepared bounded joint-assignment combination screen on Modal once. Require ordinary matched frames >145397, wrong-note outputs <=163749, wrong-string outputs <=92641 and extra outputs during unlabeled gaps <=62856. Only a pass permits the protected recordings and 32/512/1024 comparison. Preserve 3 seconds / 0.20 coherence / 0.50 retention and trim -9 dB, Sensitivity 60, Response 75, Max Polyphony 5, Max Fret 24.
- Notifications retain the ten-minute cadence, encrypted publisher and 4,000-byte limit. The latest 3,200-byte send at 2026-11-03T07:44:29.784034+00:00 is unconfirmed; do not resend it. The last confirmed receipt remains in `build/modal/latest-notification-receipt.json`.

## 2026-11-03T04:45:14.384612+00:00 — recovery ownership/release timeline completed

- GitHub remains `c3d69ae`; installed bundle/default output unchanged. Preserve all intentional prior edits. No new build, corpus replay, validator, install, commit or push in this diagnostic step.
- Existing paired ordinary capture comparison remains REJECTED: matched145397->146110 (+713, zero losses), WN163749 unchanged, WS92641->92636 (-5), extra outputs in unlabeled gaps62856->62960 (+104), FP319246->319345 (+99). These are snapshot assignments, including settling before MIDI-on.
- Read-only cloud extraction completed `ap-cH6K8JxryTBcktPZuE31Q0`; report `build/modal/residual-recovery-v1-timeline.json`; scratch reader `build/modal/residual_recovery_timeline.py`. Initial import/serialization startup failures were repaired; failed reader stopped. Existing captures only, no duplicate replay.
- Note64 activates67754, then receives no ordinary selector renewal and releases68021 after267 steps. Note63 activates80570, remaps lane6->7 at80575 before fine phase becomes valid80811; returns to6 at80813; remaps6->4 at81499, one step BEFORE quiet81500; releases81766 after267 steps. Lanes here are zero-based. This does not establish a sticky-release defect; preserve ordinary Response75 release. Snapshot lifecycle is not an independent actual MIDI ledger check.
- Positive recovered MIDI lifecycle test remains unimplemented: existing synthetic test does not assert recovery activation. Test agent found no honest positive fixture without a captured DP-evicted frame; do not claim that test passed or manufacture active state. Agent instructed to return its precise recommendation and stop.
- NEXT: Keep recovery v1 rejected/offline. Next evaluate bounded continuity of the recovered physical string and renewal from current residual evidence; do not shorten normal release. First establish a deterministic positive MIDI-event lifecycle fixture. Ordinary acceptance remains matched>145397, WN<=163749, WS<=92641, extra-gap<=62856; only then expand to protected corpora and 32/512/1024 parity. Keep3s/.20/.50 and -9/60/75/poly5/fret24. Do not tune against annotation boundaries.
- Heartbeat04:10:17 was already delivered exactly once at04:19:24, idWBchFs0u8imf,3369bytes,HTTP200,inline. Do not resend this trigger. Use fresh current reports, encrypted-credential helper, <=4000UTF8 bytes and saved receipt for later authorized heartbeats. Old notifier scripts below are stale/oversized.

## 2026-11-03T00:44:38.391808+00:00 — bounded recovery first cloud trial

- GitHub request fulfilled at `c3d69ae`; upstream0/0. Do not repeat commit/push. Installed plugin unchanged; newer work remains intentional local experiments.
- Added offline residual-recovery screen: frozen gain.20/energy.0001/margin32/hold3 rule, one highest-gain proposal and guarded16-decision lease. Native assignment hook runs after projection and before ordinary evidence/attack; no phase/evidence donation or forced MIDI.
- Build and4 focused recovery tests passed; existing residual-admission trace parity passed. Label independence and32/512/1024 consistency, true-silence release, lane/capacity/expiry/score/group guards covered. Source contract, whitespace and production preprocessing exclusion pass. First test attempt parsed the TSV header as a sample; parser repaired and rerun passed.
- One review correctly requests positive actual note-on/off proof, still pending. Its initial production-state finding overlooked enclosing compile guards; preprocessing excludes all API/state/implementation. Correction requested; no second review.
- Modal ordinary trial RUNNING `ap-QxLfH2RqPBnFvDyLNIvVEm`, local session64668, `build/modal/residual-recovery-v1.json/log`; combined profile-pair/harmonic-admission/provisional-retention flags plus recovery. Baseline matched145397, FP319246, wrong-note163749, wrong-string92641, extra-gap62856, held10853, fingerprint36150c8ba7813405. Expand only for actual safe gain. No duplicate sweeps.
- Last ntfy confirmed00:42:39UTC; next due00:52:39UTC. Existing10min publisher `build/modal/notify-combined-pair-provisional.py` only. Latest focused tests do not replace historical full515/117 or establish current real-time readiness.

## 2026-11-03T00:15:32.803530+00:00 — protected phase screen complete; actual recovery next

- GitHub already updated at `c3d69ae`; no repeat commit/push. Installed plugin unchanged. Newer diagnostics remain intentional local work.
- Protected capture `ap-cBVDBzLrSMvPVEcyeiK1iI` and analysis `ap-2sKT3EHPKa5Yf03wKZunkr` completed. Reports `build/modal/discarded-phase-protected-shadow.json`, `...-analysis.json`, `...-parity.json`. All10 sets bit-identical on14 fields/fingerprints and physical groups to matching combined controls, same binary f2ddb9a732b3. No active Modal/test/build job.
- Frozen gain0.20/energy0.0001/margin32/hold3 screen makes zero proposals on all10 additional sets. Ordinary remains15 correctly assigned sampled observations, zero wrong notes/strings/gaps. This is diagnostic selectivity, not recovered MIDI or broad improvement. Native frozen58 ranking21->48, not the approximate57.
- Next: root owns a bounded offline opt-in actual recovery experiment. Reader residual_recovery_integration maps detector assignment/activation lifetime only. Preserve native silence/release, free-lane and total-cap limits, existing owners, no label input or forced snapshot output. Start ordinary replay and expand only if actual output improves safely. Do not retune the screen against protected labels.
- Latest confirmed ntfy00:09:11UTC; next due00:19:11UTC. Existing helper `build/modal/notify-combined-pair-provisional.py`,10min cadence only. Full historical515/117 suite predates phase extension; current focused phase/lane/trace, source contract, production exclusion and one review pass.

## 2026-11-02T15:52:46.891584+00:00 — native shadow phase evidence improves discarded-note string ranking

GitHub request is fulfilled: `c3d69ae` pushed on `work/tuner-stability-20261027`, upstream 0/0. Newer diagnostic work remains local. Installed plugin/defaults unchanged.

- Native capture `ap-0CSvQrTyFMTcOy0M7aREMq` and analysis `ap-gwGzVp724WThKmmLRvR91d` completed. Reports `build/modal/discarded-phase-native-shadow.json` and `...-analysis.json`; runner `build/modal/native_phase_shadow_analysis.py`. Binary SHA `f2ddb9a732b34345b55c945cb8e69093ffcfb8530815eb5e4331d76946eb2853`. No active cloud/local test job at this checkpoint.
- Offline-only discarded-candidate phase state shares native estimator arithmetic, preserves warm-up and silence/reset behavior, and never transfers evidence to production candidate state. Assignment trace schema now71 columns, with `phase_shadow` at70.
- Frozen58 correlated observations: 21 ->48 correct (+27), zero broken,31 valid phase. Approximate57/58 prior result overpredicted due to ignored selection/reset lifecycle. All14 output fields, physical group counts and fingerprint `36150c8ba7813405` unchanged. Residual non-cost fields identical. Native groups: note35 1/1,45 20/20,63 6/16,64 12/12,68 9/9.
- Fresh native margin32/hold3 screen:15 expected correctly assigned observations, zero wrong pitches/strings/gap outputs, versus zero previously. Not recovered MIDI frames or independent cases. Broad hold3/margin0 still has8 wrong strings among56 expected observations, so broad recovery is unsafe.
- PASS: causal phase warm-up/reset/silence/no-allocation/no-transfer test, two lane cost tests, residual and assignment replay tests (32/512/1024 parity and label independence), source contract, production preprocessing exclusion, whitespace and focused source review. Contributor replay build complete. Full historical515/117 checks predate these diagnostics; no install/realtime claim.
- Next: use the same fixed screen across protected recordings before any output trial; keep3s/.20/.50 and measured -9/60/75/poly5/fret24. Main installed gates still41,452/68,441 overall (target42,128),25,219/39,378 exact-three (target25,604),2,709 wrong strings (max2,709). Existing10min ntfy only.

## 2026-11-02 14:44 UTC — cost-term diagnosis complete

GitHub checkpoint `c3d69ae624db19ee12ef660d7252c4f19c027368` is pushed on `work/tuner-stability-20261027`; newer diagnostic work remains local. Installed plugin and defaults are unchanged.

Modal cost-term analysis `ap-KlODlrStXdbjasT3m4Sn4N` completed; no active Modal jobs or local sweeps. Report: `build/modal/residual-native-cost-terms-analysis.json`. Its source capture preserves all 14 output fields and the residual trace hash exactly; see `residual-native-cost-terms-parity.json`.

Of 58 persistent sampled observations, native costs rank 21 correct strings and 37 wrong strings. Removing fret cost gives 23 correct; removing profile cost gives 19; removing cents has no effect. Every observation has complete calibration but an invalid phase estimate. The 37 errors are correlated observations from four episodes at MIDI 63, 64 and 68, not independent cases or recovered MIDI frames. Simple reweighting is rejected. Current joint-residual harmonic coefficients cannot be treated as per-source timbre: shared harmonic columns merge ownership.

Current logging extension passed two causal replay tests (including 32/512/1024 and label independence), six profile-parser checks, native source contract and whitespace checks. Historical full 515-native/117-Python results predate this logging extension. No additional full build, install or commit was performed.

Next: inspect the phase-evidence lifecycle for inactive discarded candidates. If selection structurally prevents usable pitch estimates, measure that evidence in a bounded offline-only diagnostic before proposing any output recovery. Keep accepted 3-second / 0.20 / 0.50 behavior and measured -9/60/75/poly5/fret24 setup.

## 2026-11-02T13:40:12.770021+00:00 — native string-ranking recovery rejected; three pitch errors isolated

- GitHub request fulfilled at `c3d69ae` on `work/tuner-stability-20261027`; verified upstream 0/0. No repeat commit/push; newer intentional experiments remain local and the installed plugin is unchanged.
- Offline native costs cover inactive DP-evicted candidates every 16 decisions. Capture `ap-LAO7HAaxNFxLYEWnoJQBqH` completed: 1,733 rows, no truncation, all 14 protected output fields and physical groups identical to combined baseline. Binary SHA `d34884d6f19869ce633080c67d27909483ac9edb40c7a11f59047efee0540da8`; fingerprint `36150c8ba7813405`.
- Analysis `ap-mKEtWxOuDFFaytAbBPC9e1` completed. REJECT simple recovery: 37/58 persistent observations choose the wrong string; margin 32 leaves zero persistent candidates. Reports `build/modal/residual-native-lane-costs-analysis.json`, `...-parity.json`, and `residual-native-lane-error-strata.json`. These are sampled diagnostics, not recovered MIDI frames. No active Modal job/local sweep.
- All 37 errors: MIDI 68, physical string 4/fret 20 -> string 3/fret 16 (9); MIDI 64, string 2/fret 8 -> string 1/fret 4 (12); MIDI 63, string 2/fret 7 -> string 1/fret 3 (16). Calibration best is wrong on all 37. Saved 473 KB trace SHA `6b5d382323a1921127d0b5d0620a597cb360182cf69000a0431291f13ce6ee61`. Do not rerun the capture to repeat this breakdown.
- PASS already complete: 515 native tests, 117 Python/source checks, source contract, production preprocessing exclusion, whitespace and one focused review (two reporting defects fixed). All 32/512/1024 diagnostic traces preserve output. Do not repeat unchanged checks.
- Next: diagnose whether overlapping chord harmonics bias profile evidence before any output trial. `profile_harmonic_energy` at native/src/polyphonic_pitch_detector.cpp:8296 only adjusts partial frequency; its rejected prior experiment does not demix sources. JointPitchResidual currently returns residual/independence, not fitted coefficients. A read-only follow-up is assigned to interval_next_mechanism; lead owns all writes.
- Keep 3 s / 0.20 / 0.50 and measured baseline -9 / 60 / 75 / poly5 / fret24. Installed primary gates unchanged: 41,452/68,441 long (target 42,128), 25,219/39,378 exact-three (target 25,604), wrong-string 2,709 (max 2,709). Existing ten-minute ntfy helper only; notification receipt is authoritative for next due time.

## 2026-11-02T11:14:51.775499+00:00 — decay normalization rejected; simple fix does not generalize

- Modal `ap-VkzWM2BXye5ZIM2idHNTtH` completed. Runner: `build/modal/decay_normalized_beat_audit.py`; report: `build/modal/decay-normalized-beat-audit.json`. Uses the same pinned original-recording NPZ (`62cb53e7ce002a48cf5d364d11314923248c6f1de2f47124912f43559e84316e`), 161 windows, no new replay or production build.
- Fixed log-affine energy envelope normalization before the unchanged linear detrend/Hann correlation. Labels are used only after scoring. Exact exponential causal negatives: 108/108 zero scores. Gain invariance max error `2.22e-16`. Synthetic single-source extra-string support 24/24 -> 0/24; synthetic fundamental triple support 1/8 -> 6/8, all 24 expected pair masks remain supported.
- Physical full-hold pair support 94/94 -> 92/94; extra-string support 53/94 -> 54/94. False triple support 6/94 -> 0/94, but genuine triples remain 0/45. The 85 regularly sampled pair windows preserve 85/85 support and extra-string support improves 46 -> 45; this limited subset does not rescue the full gate.
- Crucial falsification: one source with a sum of two smooth exponential decay components still supports extra strings in 12/12 controls. Amplitude modulation confound also persists. Reject this as a production fix; no source/output/default/install changes.
- Next: Inspect the native calibrated beat-frequency evidence and the saved physical-window spectra to separate smooth-envelope leakage from overlap between the three real beat components. Use source-domain controls to test a phase-aware or component-separated measurement only after identifying the specific failing assumption. Do not lower the 3-second evidence window, 0.20 beat threshold, or 0.50 retention floor. Any output trial must reach 42,128 long matches and 25,604 exact-three frames with at most 2,709 wrong-string frames and no protected-corpus regression.

## 2026-11-02T10:54:17.332523+00:00 — overtone beat augmentation rejected; decay confounder reproduced

- GitHub request fulfilled at c3d69ae on work/tuner-stability-20261027; HEAD/upstream 0/0 rechecked. No repeat commit/push. Newer intentional work remains local. Installed plugin unchanged; combined offline corrections retain all 11 protected-set passes and all 66 buffer cases.
- Modal app ap-FRIDWIxo5SrROC8cRckC2i completed. Report build/modal/harmonic-beat-evidence-audit.json; runner build/modal/harmonic_beat_evidence_audit.py. Reused 161 saved original physical-long harmonic windows; no new audio replay or build. Prepared/capture/calibration hashes pinned in report; every saved time vector and H1 reconstruction checked. Initial metadata-reader failure processed no windows and was repaired before this successful run.
- Whole-hold physical pairs: fundamental expected 94/94, extra-string support 53/94; any harmonic expected 94/94, extra-string support 94/94; two harmonics expected 48/94, extra-string support 13/94. Whole-hold triples: fundamental 0/45, any harmonic 1/45, two harmonics 0/45. Regular-sampling triple subset is 0/31 for all three rules. These all-edge shadow-mask counts are not the production connected-graph rule or new matched MIDI frames.
- Synthetic triple controls: fundamental 1/8 versus overtone rules 8/8; this synthetic gain does not transfer to physical audio. Decaying single-source controls falsely support an extra string in 24/24 cases with fundamental/any-harmonic rules; AM singles 6/18 and 11/18 respectively. Two-harmonic rule removes these single-source false groups but loses 46/94 physical pair supports and adds no physical triples. Reject all simple overtone augmentation rules for integration. Known-beat/zero/gain checks pass; gain error 3.33e-16. Keep 3s/.20/.50 unchanged.
- NEXT: Test whether explicitly removing smooth sustain-envelope curvature can prevent the reproduced decaying-single-string false beat evidence, while preserving known two/three-tone controls. Use a fixed offline nuisance-envelope model on the saved original-recording windows, score before labels, and reject any rule that loses correct pair evidence or increases extra-string support. No output change or new replay matrix unless that screen succeeds. A later output trial must reach 42,128 long matches and 25,604 exact-three frames, with at most 2,709 wrong-string frames and no protected-corpus regression. Keep 3 seconds, 0.20 beat coherence and 0.50 retention unchanged.
- ntfy last confirmed 10:32:46 UTC before this checkpoint; next full summary is due now. Existing ten-minute cadence/publisher only, no new timer. Main accepted gaps remain 676 overall and 385 exact-three frames, with zero wrong-string headroom.

## 2026-11-02T10:32:46.706742+00:00 — loop-frequency confounder measured; use original physical audio

- GitHub request fulfilled at c3d69ae; no repeat commit/push. Combined offline corrections still pass all11 protected sets/all66 buffer cases; main long matches/exact-three unchanged. Installed plugin unchanged.
- Modal app ap-FFRM0qqDj9hZoBrTH9US0G completed; report build/modal/upper-loop-frequency-audit.json; scratch runner build/modal/upper_loop_frequency_audit.py. All7 old float64 looped holds reconstruct exactly; no audio written. Original source and extended hashes preserved in report.
- Known separate single-tone controls recover original frequencies within6e-9Hz; loop-tail strongest frequencies shift -0.065119,+0.308315,+0.138923Hz (-0.430771,+2.029608,+0.914403cents). Closest calibrated spacing0.117449Hz becomes apparent peak spacing0.051943Hz with reversed ordering. These are causal controls, not actual per-string physical-mixture estimates. Constructed upper loops cannot validate fine unison/beat precision or the3-second gate.
- Source inspection: native beat measurement excludes differences below0.25Hz, so expected upper-pair0.117449Hz returns0 structurally. Do not describe that as absent physical beating. Keep3s/.20/.50 unchanged.
- NEXT: inspect already saved original physical-long harmonic envelopes for independently useful overtone beat evidence. Reuse dense-fine-capture prepared NPZ, no new replay or looped audio. Prior joint/drift/coupled/amplitude fits are closed; do not repeat them. Require pair/single negative controls before considering output changes. Main acceptance remains long>=42128/exact3>=25604/wrong-string<=2709.
- ntfy last confirmed10:00:23UTC;10:16:42UTC attempt timed out exit28, delivery unconfirmed. Existing full-summary ten-minute cadence only; next attempt now, no new timer.

## 2026-11-02T10:11:03.194462+00:00 — upper-unison diagnostic complete; selection is not the bottleneck

- GitHub request remains fulfilled at c3d69ae. Combined corrections still pass all11 protected sets/all66 buffer cases and remain offline. Do not repeat unchanged suites or commit/push.
- Replay app ap-fpQKVqDB62MrBrkd1IU6xL, failure analysis ap-B5x7JJFfP6Sm1ACbXI3pOd and fine-window analysis ap-0Op9wiilT3EYx03w4tcXRG all completed. No active Modal job from this slice. Reports build/modal/extended-high-f32-{current-diagnosis,group-failure,fine-windows}.json.
- Matched3893/37800; all exact matches are expected pair96. Triple224:0/10800 exact, pitch selected10665/10800, partial10594/wrong-only71/no pitch135. Fine evidence invalid on9794/10786 captured triple candidates. No DP eviction mechanism. Four late wholly labeled3s windows all have expected-mask224 beat score0, and other masks predict held-out audio better. These are loop-constructed observations, not physical acceptance or an improvement claim.
- NEXT: resolve the loop/source-frequency confounder before any upper-group policy; do not loosen3s/.20/.50. Closest calibrated upper components differ0.117449Hz, so raw fundamental spacing is challenging in3s. Harmonic joint/drift/coupled alternatives have prior closed experiments; do not duplicate them. Original physical recordings remain authoritative.
- Latest full ntfy confirmed10:00:23UTC; next due10:10:23UTC using existing publisher/helper. Primary accepted gaps676 long/385 exact-three; zero wrong-string headroom. Installed plugin unchanged.

## 2026-11-02T09:54:15.619300+00:00 — upper diagnostic input repaired without replacing the source

- Failed original app ap-J31JNHk2v8IJHWmJIuroKS processed no audio: IEEEfloat64 is unsupported by frozen replay. Scratch preparation first had a remote path-depth import error; app ap-yas2hVEAYHXRilCm9IemzK was stopped and fixed, no pending duplicate.
- Verified cloud conversion app ap-YBYDsiD6i1H0za96yIDRes completed. Original SHA239d02dd14d86fc7a342ef65b19776d94027668ae8aa6ac6b06fa7ed264e08a6 unchanged; separate derived/extended-high-f32-v1.wav SHA5b06da36e847a0685028b25552d683b4c3f6e953522788349073d40d9cf56bc6. Same96k/2,611,200samples/labels; max rounding error1.731e-9, RMS2.380e-11. Provenance build/modal/extended-high-f32-provenance.json. No resampling or pitch transformation.
- Current replay RUNNING ap-fpQKVqDB62MrBrkd1IU6xL, session18503, build/modal/extended-high-f32-current-diagnosis.json/log. Scratch runner build/modal/extended_high_float32_diagnostic.py maps only extended-high audio to the derivative. Frozen7f9014a7 baseline and original512 settings, outcome/label/fine-window diagnostics. Analyze with existing group_failure_analysis and inspect_windows after completion. Treat loops as diagnostic artifacts, not independent physical truth.
- Combined candidate all11/all66 protection/parity success unchanged, still offline. GitHubc3d69ae already published; no repeat commit/push. Last confirmed ntfy09:42:44UTC, next09:52:44; existing10mincadence only. Helper prose corrected to completed parity.

## 2026-11-02T09:34:42.067146+00:00 — combined protections and buffer parity complete; upper-unison diagnostic running

- Combined candidate all11 protection sets and all66 control/trial cases pass32/512/1024 invariance, including14 protected fields/fingerprints and physical-group diagnostics. Report build/modal/combined-pair-provisional-v1-buffer-parity.json. App ap-9sYCIRKcoxYonVNl7NzLGz completed; session55979 closed. No duplicate runs.
- No main long gain: matched41452/exact-three25219 and wrong-string2709 unchanged. Candidate remains offline/default false; no production build/install. Constructed held-switch increases +16 and synthetic-four +6 remain disclosed.
- Next bounded diagnostic RUNNING: ap-J31JNHk2v8IJHWmJIuroKS, session94372, report/log build/modal/extended-high-current-diagnosis. Current frozen7f9014a7 baseline, extended-high only at512; outcome/persisted TSV/label details and late note60 fine-window dumps. Captures intentionally cover already-staged loop-constructed holds, not new physical evidence. No classifier/output change. Use existing Modal group_failure_analysis on completed outcome capture, then distinguish warmup, fitting/beat, selector and ownership failure. Do not weaken3s/.20/.50 gates from loop artifacts.
- GitHub c3d69ae remains synchronized; newer intentional work preserved. Last ntfy confirmed2026-11-02T09:30:43.249043+00:00; next due09:40:43. Reuse notify-combined-pair-provisional.py, correcting its initial buffer-pending prose before next send. Existing10mincadence only.

## 2026-11-02T09:30:43.206603+00:00 — combined corrections pass all 11 recording sets; buffer parity running

- GitHub request already fulfilled at c3d69ae on work/tuner-stability-20261027. Preserve newer intentional dirty experiments; no repeat push.
- Combined profile-pair output filter + harmonic-admission/provisional-retention V2 flags pass all 11 recording protections at 512. Same frozen binary 7f9014a7aa3f2baf8fa921fc0d0e537379266196c8ce0a22fe8823b2fc07e114; reused saved matching controls with provenance.
- Gains: ordinary matched +12/false outputs -526; constructed +3340/-2163; isolated02 +280/-1326; synthetic four +1551/-1069. Physical-long matched/exact-three unchanged, false outputs -347. Physical-four matches unchanged, extra gap outputs -376. Short high matches still zero but false outputs -7487; other four sets bit-identical. Held transitions +16 constructed and +6 synthetic-four; disclose these tradeoffs. No production/default/install change.
- Modal buffer candidate run ap-9sYCIRKcoxYonVNl7NzLGz, session55979, report/log build/modal/combined-pair-provisional-v1-buffers-trial. 22 cases at 32/1024; saved 22 controls reused from V2. Use build/modal/compare-combined-pair-provisional-buffers.py after completion; require all 66 control/trial cases invariant including 14 fields and group diagnostics. No duplicate sweep.
- Next useful mechanism target: current-binary extended-high outcome trace after buffer work. Original short high holds 0.75–2.30s never reach accepted 3s gate; old extended report used different binary. Extended holds are loop-constructed (35–85% sustain,20ms crossfade), not new physical recordings; check beat artifacts before drawing detector conclusions. No extended run launched yet.
- Existing component native/Python/source/production-exclusion tests and one review already passed; no repeat without source changes. Primary long gaps remain 676 overall and 385 exact-three frames, with zero wrong-string headroom. Ten-minute ntfy cadence uses latest receipt; next send is due now.

## 2026-11-02T08:35:13.030425+00:00 — V2 passes all recording protections and buffer parity; GitHub current

- GitHub request fulfilled at c3d69ae on work/tuner-stability-20261027; HEAD/upstream0/0 verified. Preserve newer intentional dirty experiments; no repeat commit/push.
- V2 controls reproduce accepted output for all11 datasets. Candidate improves isolated02 matches+280, wrong notes-1076, wrong strings-250, false outputs-1326 and held switches-14. Ordinary matches+8/false outputs-26; constructed matches+1/false outputs-635; short high false outputs-7487/wrong strings-143/extra-gap-2778, but its matched count remains0. Seven other sets bit-identical, including physical-long and both four-string sets.
- All66 cases pass32/512/1024 parity within control and trial:14 protected fields including fingerprints plus physical-group diagnostics. Report build/modal/provisional-open-retention-v2-buffer-parity.json; final trial app ap-MVA0yJOUlTQfdG3hPty2Yp, frozen SHA7f9014a7aa3f2baf8fa921fc0d0e537379266196c8ce0a22fe8823b2fc07e114. Modal completed/idle.
-513 native/85 Python/source,11 focused causal, production exclusion, whitespace and one review already passed; do not repeat unchanged checks. Candidate remains offline/default false. Primary long gains are0; gaps676 overall/385 exact-three remain. No production build/install for this candidate.
- Reader long_unison_next_mechanism corrected the proposed next mechanism:150 raw-fit3/fine1/pending-exact frames are held before proposal by fine consensus, not dropped at commit. Their beat score is below0.20; no bypass justified. NEXT: inspect existing accepted-fine/group diagnostics for an actual ownership bottleneck before adding any counterfactual. Do not reopen rejected faster-confirmation or coherence relaxation.
- Last confirmed full ntfy2026-11-02T08:24:12.924298+00:00; next due08:34:12UTC. Reuse build/modal/notify-provisional-v2.py and existing cadence; no duplicate timer.

## 2026-11-02T07:52:22.773375+00:00 — V2 four-set screen passes; remaining seven controls running

- Modal screen report build/modal/provisional-open-retention-v2-analysis.json: high isolated matched29240->29520 (+280), false outputs5731->4405 (-1326), wrong notes2491->1415 (-1076), wrong strings1400->1150 (-250), extra-gap1840 unchanged, held switches38->24. Short middle/highmid bit-identical. Short high matches remain0, false outputs57726->50239 (-7487), wrong notes8685->4119, wrong strings15403->15260, extra-gap33638->30860. No protected regression. Controls4/4 match accepted14 fields.
- Remaining7 control run: app ap-IrAyYrmXKnkq1q0dgMNDHH, local session74111, report/log provisional-open-retention-v2-protected-control. Same frozen7f9014a7... binary; no rebuild. Datasets iso05/08,long,ordinary,constructed,physical-four,synthetic-four at512. After controls match baseline, run same sets with both guard flags; compare via compare-profile-pair-screen.py provisional-open-retention-v2-protected. Only a full11-set pass permits32/1024 expansion.
- No production/install change.513 native/85 Python and one review already passed. GitHub fulfilled c3d69ae. Latest ntfy attempt07:48UTC timed out exit28; delivery unconfirmed, no immediate retry. Next ten-minute attempt07:58UTC; preserve full summary. Last confirmed receipt preceded this attempt.

## 2026-11-02T07:34:37.205776+00:00 — same-decision provisional correction V2 ready for Modal

- GitHub request already fulfilled at c3d69ae; no repeat commit/push. Installed plugin unchanged.
- V2 requires actual harmonic-exception suppression for this lower candidate in this selector decision. Provenance resets each selector decision, quiet path and reset, and is absent from production preprocessing. Both experimental flags remain default false.
- PASS: 11 focused causal tests, all513 native tests,85 Python/source tests, source contract, production exclusion, diff whitespace. One focused review: no material findings. Test harness initially aborted before main at its512-registration cap; expanded to1024 with an overflow diagnostic, then the full suite passed.
- Frozen binary7f9014a7aa3f2baf8fa921fc0d0e537379266196c8ce0a22fe8823b2fc07e114. Spec build/modal/provisional-open-retention-v2-spec.json. Four-set512 screen: isolated-02, physical-middle, physical-highmid, physical-high; baseline-9/60/75/poly5/fret24, selector-1, DPmask56; control no flags, trial admission+provisional guards. Reject protected regressions; only material benefit permits remaining7sets and buffer parity.
- No V2 replay result yet. Last V1 remains rejected. Existing ten-minute full ntfy cadence continues; receipt is authoritative. No duplicate sweeps or timers.

## 2026-11-02T06:24:31.398714+00:00 — provisional open retention rejected by protected upper unisons

- All11 controls reproduce accepted14 fields. Constructed+271 matches/-271 wrong strings, but short middle/highmid/high wrong strings+75/+322/+26; false outputs rise equally. Constructed held transitions+18, gap transitions+2. Long/isolated/ordinary/synthetic-four bit-identical; physical-four totals same but fingerprint differs. Reports `provisional-open-retention-v1-analysis.json` and `provisional-open-retention-v1-protected-analysis.json`.
- REJECTED. No32/1024 expansion, production change or install. Native511/Python85/source/production-exclusion/review already complete. Current diagnostic guard stays default false.
- NEXT: inspect whether a decision-specific harmonic-admission correction can preserve the lower candidate assignment; one selected pitch is not evidence of one physical string. No new output rule or replay launched yet. Prior calibrated-admission isolated high-string regression remains the causal target.
- Modal complete/idle. Full ntfy summary sent; existing ten-minute cadence, no duplicate timer. GitHub request already fulfilled at c3d69ae; broader readiness remains incomplete.

## 2026-11-02T06:19:06.412104+00:00 — provisional open retention screen passes; protected expansion running

- Six-set control/trial completed. All controls match accepted baseline across14 fields. Trial constructed matches259074→259345 (+271), wrong strings103754→103483 (-271); wrong notes/gap outputs unchanged. Other five sets bit-identical, including long unisons and three isolated strings. Report `build/modal/provisional-open-retention-v1-analysis.json`. This is a screen pass, not production acceptance.
- Five remaining protected control replays running on Modal, session83380, report/log `provisional-open-retention-v1-protected-control`; app ap-PFyLx6fPH6ECjHBD2EzcCB. Trial follows only after control completes. Then test missing32/1024 blocks for all11; reuse six completed512 pairs. Binary SHA c18e6d729867f3e52046f1f3872495f010384213f405937184a699fe6889f92f is frozen.
- No production/install change.511 native,85 Python/source checks, production exclusion and one review already passed. GitHub request already fulfilled at c3d69ae. Existing ten-minute ntfy cadence continues; last confirmed06:10:41UTC.

## 2026-11-02T06:01:11.967714+00:00 — provisional open-lane guard passes native checks; Modal control running

- GitHub remains published at `c3d69ae`; no repeat commit/push. New intentional dirty work remains local; installed plugin unchanged. Broader goal active; original twelve-hour window elapsed.
- Offline/default-false `--diagnostic-provisional-open-retention-guard` suppresses only conflicting retained open bonus for isolated active uncommitted candidates with valid phase, complete calibration and no group/pending/beat ownership. Ordinary retention and release remain intact.
- PASS: 4 focused causal tests, 511 full native tests, 85 Python/source tests, production preprocessing exclusion, CLI help, diff whitespace; one review with no actionable findings. Seeded release fixtures do not prove waveform engagement; corpus decides.
- Frozen spec `build/modal/provisional-open-retention-v1-spec.json`, binary `c18e6d729867f3e52046f1f3872495f010384213f405937184a699fe6889f92f`. Control RUNNING Modal `ap-CEVBdQweGa8sPNbFpmHDz7`, local session72662, `provisional-open-retention-v1-control.log/json`. Trial now RUNNING `ap-pGHV6TlfxLBtwvCmk8SzuI`, local session12850, `provisional-open-retention-v1-trial.log/json`; control6/6 baseline parity passed. Six sets iso02/05/08, long, ordinary, constructed at512; explicit selector=-1 and baseline-9/60/75/poly5/fret24. No other output flags. Do not rebuild or duplicate.
- NEXT: finish control then same-binary trial with `--provisional-open-retention-guard`; compare using `build/modal/compare-profile-pair-screen.py provisional-open-retention-v1`. Only gain without protected regression permits expansion. Guard-alone comes before any combined admission experiment.
- Last ntfy05:54:23UTC, next06:04:23UTC; receipt authoritative. Keep full summary and existing ten-minute monitor, no duplicate timer.

## 2026-11-02T05:28:17.654424+00:00 — high-string regression isolated to provisional open-lane retention

- GitHub request already fulfilled at `c3d69ae`; installed VST unchanged, newer dirty work intentional. No new commit/push needed.
- Completed cloud trace analysis `ap-h8ZeyRH15NpWErTkbqECG9` and bounded transition read `ap-wfyhtpG46gApgewjmdnOj5`; no audio replay repeated. Reports `build/modal/calibrated-harmonic-regression-diagnosis.json` and `calibrated-harmonic-assignment-transition.json`.
- All39,300 outcome frames align and reproduce trial totals. Gains240, losses630, net-390 matches. All630 losses are one C4 passage (samples1195647–1235903), expected mask64/physical string2 moving to128/string1 while selection and active state remain unchanged. Assignment trace cap not reached; lost original trial replay fingerprint remains unverified.
- Sampled transition shows trial starts correctly at sample1177599, moves to open lane by1181695, and retains its -64 open bonus despite calibration favoring string2. At1196031 string2 cost-32.9836 vs open-84.7985 including-64. Control initially also chose the wrong open lane, then changed under two-candidate competition; it is not proof that the false harmonic is useful signal. Trial finally recovers at1235967 as profile evidence outweighs the bonus. All are uncommitted/provisional; phase becomes valid during this passage.
- NEXT: Test an offline-only provisional open-lane retention guard: valid phase and complete conflicting calibration may remove the retained open bonus for an uncommitted isolated single-string candidate. Preserve ordinary retention/release, require paired corpus non-regression before widening.
- Existing accepted scoreboard unchanged; calibrated-harmonic admission experiment remains rejected. Prior507 native/74 Python checks still valid for unchanged code. Existing ten-minute ntfy receipt owns notification cadence; no duplicate timer.

## 2026-11-02T03:29:41.336739+00:00 — calibrated-harmonic admission rejected; isolate assignment regression next

- GitHub checkpoint remains published at `c3d69ae`; preserve newer dirty work. No active Modal/local compute after completed control `ap-ClRdX8xOrrWPLO1ty87Yfc` and trial `ap-o0iFczp4jWuGXsEMTkYvcr`.
- Six-set result `build/modal/calibrated-harmonic-admission-v1-analysis.json` is REJECTED. High string2 matched29,240→28,850 (-390/-1.334%); false outputs5,731→5,075 (-656/-11.447%); wrong notes2,491→1,415 (-1,076/-43.196%); wrong strings1,400→1,820 (+420/+30%). Ordinary gains8 matches, constructed gains1; low/middle/long metrics and fingerprints are identical. No trial promotion/install or expanded matrix.
- Full verification complete:507 native,74 Python/source checks, five causal cases, production exclusion, diff whitespace, one review with no actionable findings. Guard remains offline-only/default false.
- NEXT: narrow paired isolated02 outcome/assignment capture on the same binary `fda8d17f2901719abccbe566de8443ba017fdc650fe54ccb77724174b88147ad`, to distinguish selection losses from ownership mistakes. Hypothesis that removing a false upper changes the lower string assignment is not yet verified. Reuse existing remote outcome analyzer; no local matrix or threshold retuning.
- Accepted scoreboard remains unchanged. Ten-minute ntfy uses the existing receipt/publisher; broader readiness goal remains incomplete.

## 2026-11-02T03:18:14.698656+00:00 — calibrated-harmonic admission guard verified; Modal control running

- GitHub request already fulfilled at `c3d69ae`; preserve newer dirty work. Installed plugin unchanged. Broader stability goal remains active; original twelve-hour window has elapsed.
- Implemented `calibrated_harmonic_admission_guard` as an offline-only, default-false first-admission experiment. It removes the calibration exemption only for inactive, subthreshold, exactly-two-playable-lane upper notes +19 semitones above an eligible stronger direct lower fundamental; preserves active and stronger upper notes. Source/API/CLI/Modal wiring complete.
- PASS: five causal tests including matched ordinary silence/panic timing and ledger cleanup in single/per-voice routing; 507/507 full native tests; 74/74 Python/source checks; new symbols excluded by production preprocessing; Python compilation and diff whitespace checks. Focused review pending on `coasting_harmonic_review`.
- Frozen spec `build/modal/calibrated-harmonic-admission-v1-spec.json`; binary `fda8d17f2901719abccbe566de8443ba017fdc650fe54ccb77724174b88147ad`. Control running on Modal ap-ClRdX8xOrrWPLO1ty87Yfc; local session50279, logs/report `calibrated-harmonic-admission-v1-control`. Six datasets isolated02/05/08, long, ordinary, constructed at512 and baseline-9/60/75/poly5/fret24. Trial now running on ap-o0iFczp4jWuGXsEMTkYvcr, local session47163, matching trial log/report. Review complete: no actionable findings. Do not duplicate either job or rebuild the binary.
- Saved screen `calibrated-harmonic-saved-analysis.json` found740 starting false-candidate observations,363 established false observations and2 actual starts, zero expected upper notes meeting the screen. Ordinary has13,914 labeled +19 pair observations as controls; constructed has none. These associations are not causal recovered frames. Native guard uses an eligible lower before final selection, so replay may affect more frames than the screen.
- NEXT: finish control/review, launch same-binary trial with `--calibrated-harmonic-admission-guard`; compare with `build/modal/compare-profile-pair-screen.py calibrated-harmonic-admission-v1`. Comparator now distinguishes unchanged/no improvement. On actual benefit with no regressions expand to11 datasets/32,512,1024; otherwise leave disabled. Existing accepted primary targets and scoreboard unchanged.
- Ten-minute ntfy cadence uses `build/modal/latest-notification-receipt.json`; reuse publisher and full template. No duplicate notification timer or local replay matrix.

## 2026-11-02T01:03:46.389967+00:00 — coasting-harmonic trial unchanged; activation diagnosis complete

- GitHub request is fulfilled at `c3d69ae` on `work/tuner-stability-20261027`; do not repeat commit/push for that request. Newer intentional work remains local. The original twelve-hour window has elapsed; the broader readiness goal remains incomplete.
- Six-set control/trial completed on Modal, reports `build/modal/coasting-harmonic-handoff-v1-{control,trial,analysis}.json`. All14 score fields, physical-group counts and replay fingerprints are identical for isolated02/05/08, physical-long, ordinary and constructed. Verdict UNCHANGED, no improvement, not accepted/promoted. Do not expand this no-op to eleven sets or buffer matrices.
- Focused isolated02 outcome capture completed on app `ap-TE8JFSW1jJE0ggGIQZ8V48`; report `build/modal/coasting-harmonic-activation.json`, local stream `build/modal/isolated-02-coasting-harmonic.outcome.tsv` (13.8MB,39,300 frames, not truncated). Analysis `build/modal/coasting-harmonic-activation-analysis.json` identifies745 selected-lower/coasting-upper +19 observations:449 for60/79 and296 for61/80. All745 upper candidates have a direct peak;516 pairs have both phases valid and229 both invalid. None has lower-valid/upper-invalid phase evidence. Upper scores are only1.64–3.56% of lower scores, yet upper fundamental share is95.2–99.98%; this illustrates why that share is not independent-source evidence.
- These fields explain the observed guard rejection; tracking fields are post-decision and do not expose all pending/beat/continuity masks. No new instrumentation or relaxed output guard is justified by this result. Keep the offline experiment disabled and the installed plugin unchanged. Existing502 native/69 Python-source checks, production exclusion and one review already passed; no repeat checks absent source changes.
- NEXT: seek an independent onset/source discriminator for the two observed harmonic admissions using saved evidence and real +19 chord controls before another output rule. Do not repeat prior rejected energy-share, broad ownership, or phase-validity rules. Modal is idle; no local heavy work is running. Ten-minute ntfy cadence uses `build/modal/latest-notification-receipt.json`; last confirmed00:57:44UTC, next due01:07:44UTC. Full accepted scoreboard remains in current-status and the notification template.

## 2026-11-02T00:47:53.222078+00:00 — coasting-harmonic safety checks pass; six-set Modal control running

- GitHub request complete at `c3d69ae` on `work/tuner-stability-20261027`; no repeat commit/push. Preserve newer local intentional work. Installed plugin unchanged.
- New `coasting-harmonic-handoff-v1` is offline-only and default false. It releases one unselected +19-semitone single-string owner only with direct/resolved lower support, no direct/resolved upper support, exact two-active/one-selected context, no multi-string/fine/beat/pending ownership, playable lane and an atomic note-off. It does not remap or create the lower note.
- PASS: 5 focused tests including actual silence/panic ledger cleanup in both routing modes; 502/502 full native tests; 69 Python/source checks; production preprocessing excludes helper, setter AND flag; one review completed without actionable findings. Review's tentative API/layout note was disproved by enclosing header macro guards and direct preprocessing; no extra change/review needed. Logs under `build/test-results/coasting-harmonic-*`.
- Frozen screen `build/modal/coasting-harmonic-handoff-v1-spec.json`. Modal control RUNNING app `ap-Ut1fbUOAICqpYpsCGkBf7j`, local session67588, output/log `coasting-harmonic-handoff-v1-control.{json,log}`. Six sets: isolated02/05/08, long, ordinary, constructed;512 samples, baseline-9/60/75/poly5/fret24. Trial is NOT launched yet. Require accepted-control parity, actual gain, zero protected regressions before widening.
- Live Modal profile is `research`, workspace `snorkelai`, environment `main`. `main` is NOT a configured profile; that attempted launch failed before creating a job. Reuse `MODAL_PROFILE=research` for this authorized M3 workload. Remote replay is capped at two workers; no local replay matrix.
- NEXT: finish control, launch same-binary trial with `--coasting-harmonic-handoff`, compare using `build/modal/compare-profile-pair-screen.py coasting-harmonic-handoff-v1`. On pass with gain require eleven sets and32/512/1024 parity; on regression/no gain keep disabled. Existing accepted scoreboard and primary long targets unchanged. Latest notification receipt controls ten-minute cadence; no duplicate timer.

## 2026-11-02T00:25:12.149087+00:00 — high-string coasting-harmonic lane conflict identified; GitHub request complete

- GitHub remains synchronized at `c3d69ae` on `work/tuner-stability-20261027`. Do not repeat commit/push for the same request; preserve all newer intentional dirty diagnostics/experiments. Installed output unchanged.
- Saved `isolated-02-phase-group.tsv` identifies all27 expected-lane reservation observations: lower60 blocked by coasting79 (8 rows), lower61 by coasting80 (19 rows), all on zero-based string6/mask64. No selected-group extra reservation; one selected candidate. Lower phase valid in12 rows, fine/beat valid in0. These are sampled diagnostic observations, not recovered MIDI frames. Report `build/modal/isolated-coasting-harmonic-diagnosis.json`.
- Bounded reader review complete: no prior targeted +19 coasting-handoff trial found; existing adjacent handoff requires distance1. The reference labels establish false upper notes in these isolated examples, but the trace lacks contemporaneous owner direct-fundamental/score evidence. A +19 interval can also be a real chord. No general upper-harmonic release rule is justified or implemented.
- NEXT is a narrow causal fixture reproducing this reservation, with independently direct upper-note and 2–4-member group negative cases. Preserve atomic ownership, release and panic. Do not repeat broad ownership/admission trials already rejected. No output repair accepted, cloud job, native build or installation started in this diagnosis.
- Corrected energy-share screen remains the latest completed Modal result and rejected. Accepted scoreboard unchanged. Latest full ntfy receipt:2026-11-02T00:23:32.535187+00:00 HTTP200; existing ten-minute cadence, no duplicate timer. Original12h window elapsed; broader readiness goal remains incomplete.

## 2026-11-02T00:17:02.107088+00:00 — independent-transfer proposal withdrawn; isolated assignment diagnosis active

- GitHub update remains complete at `c3d69ae`; no additional commit or push for the same request. Native production output and installed bundle remain unchanged.
- The proposed saved-trace complex-transfer discriminator is withdrawn: the trace has mixed common-center correlations, not independently observed per-source components. Using fitted components would assume the separation being tested. No raw-audio or output experiment follows from this proposal.
- Current read-only diagnosis: reader `admission_pair_diagnosis` examines saved isolated string5/2 and chord failures; root examines assignment and group/render code. Separate pitch, lane, lifecycle and false-multiplicity mechanisms. Reuse prior rejected results; no duplicate sweep.
- Corrected energy-share screen is final and rejected for both fixed relief caps; all37 analyzer tests pass. No active Modal or local compute. Existing ntfy receipt controls ten-minute cadence. Broader live-readiness goal remains active and incomplete.

## 2026-11-02T00:08:20.516277+00:00 — corrected energy-share screen final; output remains unchanged

- Modal `ap-YzO1T513MOUWFQnh7XlKgl` completed; session54786 exit0. No active cloud job. Corrected reports `build/modal/small-fret-relief-screen-v2.json` and `small-fret-relief-screen-v2-verdict.json` supersede the original fundamental-support interpretation. Keep originals for provenance.
- The erroneous zero-qualifying-candidate claim is withdrawn. With native0.20 energy-share support, ordinary caps0.025/0.05 yield90/98 expected-only missing-lane observations versus1,162/3,553 risky observations; physical-long yields0 useful and9/20 wrong pitches. Both fixed caps still fail the declared screen. These are observations, not MIDI recovery. No threshold/register tuning or output trial follows.
- Exact original unguarded outcomes, report totals, snapshot counts and capture hashes are preserved. All37 Python analyzer tests, syntax, whitespace and one focused correction review pass. Native production code and installed bundle unchanged; no new audio replay/build/validator/install.
- NEXT: clarify whether proposed held-out complex transfer is an independent observable. Existing captures contain mixed correlations, not separated sources; demodulation rotation or fitted-component frequencies must not masquerade as source evidence. Reader `admission_pair_diagnosis` is resolving that specific concern. No new experiment yet.
- GitHub request already fulfilled at `c3d69ae`. Broader stability goal remains active, no accepted tracking gain from this diagnostic repair. Existing ten-minute ntfy receipt controls cadence.

## 2026-11-02T00:06:46.416902+00:00 — diagnostic energy-share correction; saved-trace confirmation next

- GitHub update already fulfilled at `c3d69ae`. Preserve newer intentional dirty work; no additional push for the same request.
- CORRECTION to the preceding small-fret screen: `fund_ratio` is fundamental energy divided by weighted harmonic energy, bounded 0..1. Using >=1 as normal support excluded signals with meaningful overtones. Withdraw the previous zero-qualifying-candidate conclusion. Unguarded option counts remain valid, including physical-long zero useful vs13/33 wrong-pitch observations.
- Fixed all analyzer bins/probes to use energy-share units, reject impossible shares, version the analysis schemas and preserve remote interpretation versions. The 0.20 support stratum repeats the existing native direct-peak floor; it is not an independent classifier or a newly optimized threshold. All37 analyzer tests pass, including realistic overtones and gain-invariant fractions; syntax and whitespace pass. No native/output change.
- Next: Modal reinterprets the same two saved traces with unchanged0.025/0.05 caps and register boundaries. Spec `build/modal/small-fret-relief-screen-v2-spec.json`, output `small-fret-relief-screen-v2.json`. No audio replay, build or install. Keep existing installed output and acceptance gates.
- Read-only agent `admission_pair_diagnosis` separately seeks one genuinely untested signal discriminator; no duplicate job. Last ntfy receipt controls ten-minute cadence.

## 2026-11-01T23:58:30.104575+00:00 — fixed small-fret-relief screen completed; no output trial

- GitHub request is fulfilled at `c3d69ae` on `work/tuner-stability-20261027`; preserve newer intentional dirty work. No additional commit/push for the same request.
- Modal `ap-PBlfquD0FPM5g0WJ5ndtzO` completed, session49870 exit0. Reports `build/modal/small-fret-relief-screen.json` and `small-fret-relief-screen-verdict.json`. No active local or Modal job.
- REJECTED for output testing: fixed caps0.025/0.05 produce ZERO qualifying direct/local/fundamental-supported observations on both saved accepted traces. Without that evidence guard, ordinary options are181 useful vs1,223 risky and266 useful vs3,672 risky; physical-long options are0 useful vs13/33 wrong pitches. These are candidate observations, NOT recovered/lost MIDI frames. Do not widen evidence or tune caps/registers after this result.
- No new audio replay/native build/output change. Saved trace hashes, snapshot counts and report totals verified on Modal. Analyzer33/33 Python tests, syntax, whitespace and one focused review pass. Native/production verification is historical, not rerun for this Python-only slice.
- Accepted long41,452/68,441 and exact-three25,219/39,378 stay below42,128/25,604; wrong-string2,709 at ceiling. Existing installed output and eleven protected dataset fingerprints remain unchanged by this analysis. No newly accepted tracking gain.
- NEXT: independent signal evidence must separate real missing notes/third-string components from false candidates before another output trial. Prior broad penalty/ownership/faster-confirmation proposals are already rejected. No new trial selected from this screen.
- Last ntfy23:51:46UTC, next due00:01:46UTC Nov2; existing ten-minute monitor/receipt owns cadence. Broader goal active; original twelve-hour window has elapsed. No new timer.

## 2026-11-01T23:33:42.457252+00:00 — ownership capture complete; broad preemption ruled out

- GitHub request already completed at `c3d69ae`; current diagnostics remain local. Installed plugin and output unchanged. No active Modal job.
- Completed `build/modal/fine-group-ownership.json`, app `ap-ohvTSkNaZwactdFpxothxD`. All14 accepted metrics/fingerprints unchanged at32/512/1024; all88,232 diagnostic rows byte-identical and not truncated. Downloaded only512 trace; verified SHA. See `fine-group-ownership-parity.json`.
- `fine-group-ownership-analysis.json`: only63 correct triple-group rows blocked by other owners;3,954 physical pair7+6 rows reject an incorrect committed triple. Most ownership conflicts are protective. Do NOT broadly override them. Pair8+6 has945 evaluated/accepted incorrect committed triples. No diagnostic count is a hypothetical rendered-output gain.
- Distinguish raw `fit_mask` from committed `fine_mask`/`fine_group_mask` and post-inference `assigned_mask`. For example pair7+6 retains committed7 during2,100 rows with raw fit6; pair8+6 commits7 while raw fit5 for75 rows. Triple has675 singleton-fine rows followed by a partial pair. The completed mechanism review found no distinct output policy justified by this trace; prior confirmation evidence already rejects faster commitment based on duration or residual strength.
- Verification:497 native tests,37 Python/source checks, production exclusion, focused replay buffer parity, one focused review all pass. Do not repeat checks absent changes.
- Reader `/root/fine_mask_mechanism` completed. Slice verdict: `build/modal/fine-group-ownership-verdict.json`; no active local or Modal job and no new output experiment. Next evidence must independently distinguish true three-string unisons from false third-string proposals in physical pairs; broad ownership overrides and faster confirmation are ruled out. Last notification receipt controls the existing ten-minute cadence. Broader readiness remains incomplete; original12h window ended with execution gaps documented. Published GitHub revision remains `c3d69ae`; preserve this newer local work.

## 2026-11-01T23:26:57.938821+00:00 — ownership diagnostics pass; accepted-control cloud capture running

- GitHub already updated at `c3d69ae` on `work/tuner-stability-20261027`. Current follow-up remains local; preserve dirty worktree. Installed plugin and production behavior unchanged.
- Offline diagnostics now name `FineGroupDisposition` explicitly and snapshot every overlapping selected/coasting owner before inference mutates assignment. Captures assigned/MIDI/owned masks, score and fundamental ratios, age, fine evidence and lane multiplicity. Distinct from old numeric `FineFrequencyDisposition`.
- PASS: native 497/497 (`build/test-results/ownership-native-suite.log`), four causal ownership tests, unchanged output and identical complete traces at32/512/1024 in the focused replay test, 37 Python/source checks, production preprocessor exclusion, whitespace. One focused review complete, no actionable findings. Quiet coasting ownership until ordinary release is correct and tested.
- Modal capture RUNNING ap-ohvTSkNaZwactdFpxothxD; local session45477. Report/log `build/modal/fine-group-ownership.{json,log}`. Physical-long control only, no experimental output flags; blocks32/512/1024, baseline-9/60/75/poly5/fret24, note40 full candidate trace. No duplicate sweep.
- NEXT: require 14 accepted output fields/fingerprint and trace parity; then inspect actual named ownership conflicts and owner records against physical labels. No weak-harmonic preemption claim until this evidence establishes it. Do not repeat the rejected selector or signal-floor trials.
- Last ntfy receipt controls the existing ten-minute cadence. Broader goal remains incomplete; requested12h window already ended, with prior execution gaps documented.

## 2026-11-01T23:11:35.707234+00:00 — GitHub update complete; ownership diagnosis corrected

- GitHub is updated at `c3d69ae` on `work/tuner-stability-20261027`. Newer rejected selector experiment, reporting repair, and this checkpoint remain local; preserve the dirty worktree. Installed plugin unchanged.
- Important correction from the bounded read-only diagnosis: the 6,900 value-3 rows in `fine-proposal-evidence.tsv` are `FineFrequencyDisposition::residual_rejected`, NOT `FineGroupDisposition::conflicts_other_owned`. These are separate enums. Do not use that count as evidence of accepted-baseline ownership preemption.
- Accepted control remains 41,452/68,441 physical-long matches, 2,709 wrong strings, fingerprint `519bc0f9f4710566`, invariant at 32/512/1024. Existing downloaded trace lacks exact blocker provenance; no weak-harmonic displacement mechanism has yet been established on accepted output.
- Diagnosis report: `build/modal/ownership-diagnostic-correction-20261101.json`. NEXT: minimal offline-only logging of actual fine-group disposition and pre-inference overlapping owners (note, selected/coasting origin, assigned/MIDI masks, age/evidence, multiplicity), with causal logging tests for weak selected, coasting MIDI, and legitimate interval owners. Require unchanged outputs before using the diagnostic capture to choose a policy. No new cloud job was started by this review.
- Latest selector experiment remains rejected; no new accepted metrics. Requested twelve-hour window is over and broader readiness remains incomplete. Existing ten-minute ntfy monitor remains the notification owner; latest receipt controls cadence.

## 2026-11-01T23:05:33.802272+00:00 — state-local open prior rejected; reporting recovered

- Paired six-set Modal screen final: control `ap-vzV3IZqE3SdoSkb4tV4qbn`, trial `ap-iw6WL6O6zCAQbNgQ6SEP3U`. No active replay. Report `build/modal/state-local-open-prior-v1-analysis.json`; all six controls match accepted output across 14 fields. Three isolated sets are bit-identical under the trial.
- REJECTED: ordinary matches +2,291 but extra gap outputs +240; constructed matches +9,507 but false outputs +7,684 and wrong pitches +14,956; physical-long matches -1,886, exact triples -26 and wrong strings +2,426. Constructed exact-four falls 3,447 to 519. No wider replay or install. Trial flag stays false by default.
- Trial work was saved before `_parse_aggregate` hit CSV's default 128 KiB field limit. Recovered only aggregate prefixes from all six saved volume TSVs; no replay repeated. Parser now has a bounded 8 MiB limit and restores the prior global value. Actual oversized-row reproduction/recovery and empty-input handling checked; syntax/whitespace pass. Trial elapsed time remains not measured.
- Native 493/493, 7 causal tests, 43 Python/source checks and one implementation review passed before the reporting-only repair. Production preprocessing confirms helper/flag/workspace absent from production.
- GitHub update already complete at `c3d69ae` on `work/tuner-stability-20261027`. This newer failed experiment and CSV repair are uncommitted. Installed plugin unchanged. Preserve dirty worktree.
- NEXT: Inspect saved accepted-control string-ownership conflicts for a distinct cause of lost multi-string assignments. Do not repeat rejected fret-penalty trials or widen this failed screen. Broader goal remains incomplete; requested twelve-hour window ended with documented gaps. Latest notification receipt is authoritative; keep existing ten-minute monitor.

## 2026-11-01 22:55 UTC — state-local open prior on Modal

- GitHub already updated at `c3d69ae` on `work/tuner-stability-20261027`; current selector experiment remains uncommitted, offline-only, default disabled.
- Seven causal selector tests PASS; native source contract and 32 source Python tests PASS, plus 11 build/profile-analysis Python tests PASS. Guarded native/replay build PASS.
- Full native suite PASS:493 tests,0 failures. Log `build/test-results/state-local-open-prior-native.log`.
- Paired Modal six-set screen RUNNING: control session `51880`, trial session `61752`. Logs/reports `build/modal/state-local-open-prior-v1-{control,trial}.{log,json}`; app IDs in `build/modal/current-status.json`. No duplicate sweep. All at512, trim-9/sens60/response75/poly5/fret24; only trial enables `--state-local-open-prior`.
- Single implementation review requested from existing assignment_cost_review reader; root sole writer. Algorithm review already done; no repeat review.
- New helper evaluates complete selections with selected open-pitch counts, retaining atomic/priority ownership and unconditional high-note penalties. Current MIDI/install unchanged.
- NEXT: compare with `python3 build/modal/compare-profile-pair-screen.py state-local-open-prior-v1`. Any protected regression rejects before widening. Preserve source and verdict for diagnosis.
- Last ntfy22:54:21UTC; next due23:04:21UTC. Full summary stays in build/modal/latest-notification-sent.txt.

## 2026-11-01T22:35:44.590566+00:00 — GitHub updated; active-note cache trial rejected for promotion

- Requested GitHub update completed: `c3d69ae` on `work/tuner-stability-20261027`, pushed to `Ajuntanaga/polyphonic-audio-to-midi`. Includes guarded replay diagnostics and protected comparisons; output experiments remain disabled by default. Commit verification: 486 native tests previously passed on the committed source, 68 Python/source tests plus source contracts and whitespace passed. No installed bundle change.
- Active-note state cache trial built in Release but failed the strict ordinary callback gate. ABBA control wall p99 250034/374353 ns, trial 186338/173626 ns; target below166666 ns. Trial CPU maxima329965/246994 ns meet333333 ns, but this does not offset p99 failure. Different CPU placement and control variability prevent a causal speedup claim. Report `build/test-results/active-cache-verdict.json`. Original source restored; no corpus sweep, repeated timing or install.
- IMPORTANT: `build/vst3/release/m3_vst3_realtime_tests` currently contains the rejected cache trial, so it is not a current-source validation binary. Explicit copies are `build/test-results/m3_active_cache_control` and `m3_active_cache_trial`. Rebuild this target before any new current-source timing claim. Other production bundles/installed plugin were not changed by this trial.
- Modal idle; latest recency result rejected. No active local/Modal jobs. Broader project goal incomplete; the requested twelve-hour window ended earlier with documented gaps. Accepted long41452/68441 and exact-three25219/39378 remain below42128/25604; wrong-string2709 at its ceiling. V1 remains offline with protected benefits and its documented transition tradeoff.
- Latest ntfy22:33:54UTC, next22:43:54UTC. Reuse the existing ten-minute monitor and credential-backed publisher. Next choose a distinct evidence-backed mechanism; do not repeat rejected trials. Short upper recordings are at most2.30s and are onset/false-output protections, not three-second close-unison acceptance data.

## 2026-11-01T22:13:41.183797+00:00 — requested window and follow-up checkpointed

- Requested 08:37–20:37 UTC twelve-hour window ended; recorded execution gaps remain explicit. Broader project goal is active and incomplete. No active local/Modal jobs, no install/commit/push. Root sole writer; preserve dirty worktree.
- Latest native486/486 and eleven recency captures preserve accepted output. V1 remains offline with all11 protections/66 buffer cases passed, constructed+3339 and synthetic-four+1551 matches; physical-long/exact-three unchanged and constructed transitions+16. Recency rule rejected:236 correct versus195 false sampled holdout removals. Scratch input-hoist rejected on timing. No further repetition of rejected trials without a new mechanism.
- Corrected causal interpretation: ordinary minimum evidence40ms (multivoice50ms) differs from the accepted3s close-unison gate. Saved floor-reentry analysis already shows6654/6785 quiet2 triple misses also belowfloor,131 signalpresent. Prior floor-relief trials increased false outputs; do not repeat or call this a new recovery gain.
- Next: Compare the saved assignment-conflict reports before selecting a distinct new replay-only trial; do not repeat rejected signal-floor, recency, or continuity-echo rules. Preserve V1 offline. Require physical-long matches >=42128, exact triples >=25604, wrong strings <=2709, no protected corpus regression, and repeatable normal callback timing before installation.
- Full closeout: `build/modal/autonomous-window-20261101-followup.md`; status and JSON summary updated. Ntfy remains every10min; latest receipt is authoritative. No defensible overall-completion percentage; live readiness remains unverified.

## 2026-11-01T22:07:58.081981+00:00 — shared-input optimization rejected; existing code retained

- Scratch-only resonator input hoist failed its performance gate. Fixed-CPU ABBA: control wall p99 137169/133188 ns; trial 130953/174186 ns. Second trial CPU max 371795 ns also exceeds 333333 ns budget. Report `build/test-results/mixed-sample-timing-pinned.json`. No production source change, no corpus sweep, no further timing retries without a new mechanism.
- Modal idle; latest completed recency capture/analysis remains rejected. All accepted metrics and installed bundle unchanged. No install/commit/push.
- Read-only reader `next_long_failure` partitions 8253 physical-long three-string no-rendered-pitch observations using existing reports. Separate accepted initial3s collection from later selector/lifecycle misses; feasible string masks alone cannot prove multiple sources.
- Latest ntfy22:05UTC; next~22:15. Scheduled12h window ended20:37 with recorded gaps; broader goal active. Keep laptop light.

## 2026-11-01T21:55:08.025506+00:00 — profile-pair recency rejected; full suite passed

- Completed Modal capture/analysis apps `ap-fIADRKq3jSLzSRexhhxXuc` and `ap-QTlpV6rFWGarScxMtz7l7C`. All eleven recording outputs preserve accepted fingerprints and all14 output fields; no truncated captures. `profile-pair-recency-output-parity.json`. No active cloud replay.
- Locked current-window gain-ratio<=.05/blended-gain>=.01 rule selected only on ordinary/isolated05 training data: 60 false sampled outputs removed, zero correct. Nine holdouts reject it:236 correct removed versus195 false,159 unscoped. `profile-pair-recency-verdict.json`. These are sampled observations, not full-frame MIDI gains. No output trial and no holdout retuning. Weak recent support alone is unsafe for genuine pairs.
- Full native486/486 passed. Three focused causal/observational tests, Python6/6, source32/32, native source contract, diff and one review passed. Production unchanged; no install/commit/push. Earlier normal runtime failures remain unresolved.
- Next: choose a distinct evidence-backed mechanism from existing failure diagnostics; preserve V1 offline. Broader goal active; scheduled12h window already ended with interruptions recorded. Latest successful ntfy receipt controls ten-minute schedule.

## 2026-11-01T21:49:59.135057+00:00 — recency diagnostics capturing on Modal

- Offline-only current/350ms/1.5s fixed-pair spectral diagnostics added; no output change. Causal stale-vs-real pair, scale/zero-energy/reset, observational and buffer/label-independence tests pass. Python6/6, source32/32, native source contract and diff pass; one focused review complete.
- Eleven-corpus capture RUNNING ap-fIADRKq3jSLzSRexhhxXuc, local session84445, `build/modal/profile-pair-recency.{json,log}`. Frozen plan `profile-pair-recency-plan.json`: train ordinary/isolated05 only; choose zero-correct-loss rule, lock it before nine holdouts. No duplicate replay. Then existing cloud `profile_pair_analysis` entrypoint. Static sampled removals are not MIDI gains.
- Preserve rejected V2 and offline V1 results. Accepted installed metrics unchanged; no install/commit/push. Latest ntfy receipt controls ten-minute schedule. Broader project goal active; scheduled12h window already ended.

## 2026-11-01T21:31:48.503993+00:00 — V2 rejected; work window and follow-up checkpointed

- No active local or Modal jobs. Latest completed apps: `ap-K738ZVflc3FsbR8j3bBBdU` and `ap-eF7CSWRcaN9U2oAVqwhSlC`. Root sole writer; preserve dirty worktree. Scheduled 08:37–20:37 UTC window is over. Broader project goal remains incomplete; do not mark it complete. Execution gaps are recorded in the window report.
- V2 continuity-echo filter REJECTED: physical-long loses 7,401 correct pair frames (41,452→34,051); constructed exact pairs 447→1. Middle-string gain 3,508 and constructed gain 17,681 do not offset these losses. All six controls preserve the 14 accepted fields. Report `build/modal/profile-pair-output-v2-analysis.json`. No wider V2 sweep or production integration.
- Preserve V1 offline: eleven corpus protections pass; 66 control/trial cases invariant across 32/512/1024; native 485/485. Constructed +3,339 matches/-1,528 false outputs; synthetic-four +1,551/-1,069; long matches/exact triples unchanged. Constructed held-note transitions +16. Long improvement gates remain unmet. V2 separately built and passed two causal tests before rejection; no post-V2 full-suite claim.
- Latest normal paired timing run passes (wall p99 131,026 ns; CPU max 185,716 ns), but prior normal failures remain unresolved. No timing-repair claim. Prior production builds/validators predate V1/V2 follow-up. No install/commit/push this slice; installed bundle unchanged.
- Next: independently distinguish false profile pairs from genuine two-string unisons using saved evidence before another output change. Existing mixture/phase/continuity-echo rules were rejected. Start at `build/modal/profile-pair-evidence-analysis.json`, `profile-pair-phase-analysis.json` and V2 outcomes; do not rerun completed sweeps. Primary targets still long ≥42,128, exact triples ≥25,604, wrong strings ≤2,709; current 41,452/25,219/2,709.
- Full results: `build/modal/autonomous-window-20261101-summary.{json,md}`; live state: `build/modal/current-status.json`. Latest ntfy receipt is authoritative; retain the authorized ten-minute monitor. No duplicate publisher loop. Overall readiness remains unverified; no defensible overall completion percentage.

## 2026-11-01T21:20:32.476710+00:00 — output-filter V1 invariant; continuity-echo diagnosis

- Both buffer sweeps completed. All66 replay rows (2 arms x11 datasets x3 blocks) invariant across14 fields/fingerprints and physical-group diagnostics. Report `build/modal/profile-pair-output-v1-invariance.json`. No active Modal job; do not duplicate. Native485/485 passed. V1 remains offline; long improvement gates unmet.
- All229 traced middle-string profile pairs carry continuity masks identical to assigned masks, no spectral projection. V1 treats any nonzero continuity as independent support, explaining unchanged isolated05 results. Next narrow V2 differentiates an unchanged echo, retaining V1 mode and other evidence guards. Root sole writer. No install/commit/push.
- Last ntfy21:17:21 UTC, next21:27:21. Scheduled12h ended20:37; active goal continues.

## 2026-11-01T21:17 UTC — all eleven corpus screens passed; buffers running

- Offline output-only profile-pair filter: six-set and remaining-five controls match accepted output across14 fields. Trial gains: ordinary +4 matches/-500 false outputs; constructed +3339/-1528; synthetic-four +1551/-1069. Long matches/exact3 unchanged with347 fewer false outputs; physical-four matches unchanged with376 fewer extra gap outputs. Isolated low/middle/high and all three short upper-unison sets bit-identical. Constructed held-note transitions+16 (+0.313%). Reports `profile-pair-output-v1{,-protected}-analysis.json`. Native485/485 PASS. Not production-accepted: long improvement gate unmet.
- Buffer sweeps RUNNING: control `ap-eywZgXYcT5O1wSXvxadv0d` session24661; trial `ap-xbxqLeRcV7N1pSsAe7CQRy` session96847. Reports `build/modal/profile-pair-output-v1-buffers-{control,trial}.json`, all11 datasets at32/1024; combine with512 reports. Do not duplicate. Compare14 fields/fingerprints and physical-group diagnostics perarm/perdataset.
- Installed unchanged. No install/commit/push. Notification receipt authoritative; next21:18:12 UTC. Scheduled12h ended20:37; active goal continues.

## 2026-11-01T21:14 UTC — output-only screen passed; protected expansion

- Six-set same-binary controls preserve accepted output across14 fields. Trial: ordinary +4 matches/-500 false outputs; constructed +3339/-1528; long matches/exact3 unchanged, false outputs-347. All three isolated sets bit-identical. Constructed held-note transitions+16 (0.313%); wider gates pending. Report `build/modal/profile-pair-output-v1-analysis.json`. Offline only, not accepted for production.
- Remaining-five paired Modal screen RUNNING: `ap-EdAocM0qx7xVgfH783rHMl` control/session39327 and `ap-fX2SlkK54odTBMIP06Ef8a` trial/session98197. Reports `profile-pair-output-v1-protected-{control,trial}.json`; short unisons and physical/synthetic4 at512. No duplicate. Same comparison helper supports all11 accepted datasets. If safe, run32/1024 invariance; otherwise reject.
- Guarded full native suite RUNNING session18771, `build/test-results/profile-pair-output-v1-native.log`. Installed unchanged. Next ntfy21:18:12 UTC. No install/commit/push.

## 2026-11-01T21:11 UTC — paired output-only filter screen

- Guarded native/replay build and both causal lifecycle/handoff tests PASS. Source contract, Python syntax and whitespace pass. One focused review completed; snapshot projection is limited to actually filtered candidates. No production integration.
- Paired six-set Modal screen RUNNING: control `ap-6cp1zgnEl0JGsORMRmB83L` (session69090), trial `ap-xVEWMEa7d2Yr0z7QNk24Vx` (session19070). Reports `build/modal/profile-pair-output-v1-{control,trial}.json`; ordinary/constructed/physical-long/isolated08/05/02 at512, selector=-1. Do not duplicate. Compare with `python3 build/modal/compare-profile-pair-screen.py profile-pair-output-v1` once complete.
- Accepted installed metrics unchanged. No install/commit/push. Last ntfy21:08:12 UTC; next21:18:12, receipt authoritative. Scheduled12h window ended20:37; active goal continues.

## 2026-11-01T21:08 UTC — profile-pair output filter build

- Offline-only output filter implemented in detector/replay/Modal plumbing. Causal lifecycle and atomic-handoff fixtures added. Source contract, Python syntax and whitespace checks pass. Review correction: only actually filtered candidates use the emitted ledger for snapshots; preserve state on capacity failure and coasting.
- Guarded rebuild RUNNING session40128, `build/test-results/profile-pair-output-v1-build.log`. Then `M3_TEST_FILTER=profile_pair_output_filter` causal tests and paired six-set cloud screen (`ordinary,constructed,physical-long,isolated-08,isolated-05,isolated-02`,512,selector=-1). No cloud job active yet. Do not duplicate.
- No production integration/install/commit/push. Accepted metrics unchanged; ntfy receipt authoritative, ten-minute interval. Active goal continues after scheduled12h window ended.

## 2026-11-01T20:58 UTC — output-only profile-pair trial

- Latest paired normal callback timing run PASSED2/2: wallp99131026ns, CPUmax185716ns, zero in-callback migrations. Log `build/test-results/paired-callback-timing-normal-run1.log`. Earlier normal failures unresolved; no timing repair claim or install. Diagnostic instrumentation only.
- Root implements offline-only final-output profile-pair projection, preserving internal ownership; causal tests then paired six-corpus Modal screen. No active job; no duplicate. All accepted output metrics unchanged.
- Scheduled12-hour window ended20:37; active goal continues. Check notification receipt for actual last send; ten-minute interval. No install/commit/push.

## 2026-11-01 20:32 UTC — window closeout: diagnostics repaired, tracking unchanged

- The scheduled window ends at 20:37 UTC. Root owns the dirty worktree; no local or Modal jobs remain active. Last completed Modal app: `ap-OwSi6fp03qmqNcXKQr79Z5`. Preserve all prior work. No install, commit or push this window.
- Ten replay-only tracking candidates were rejected; zero tracking changes were accepted. Per-corpus match and false-output deltas are in `build/modal/autonomous-window-20261101-summary.{json,md}`. Do not repeat these candidates. An execution interruption around 16:00–19:54 UTC is recorded; uninterrupted work or notification delivery is not claimed.
- The offline stack crash was repaired with constructor-owned diagnostic storage. All 483 native tests pass. Final Modal replay: 33/33 checks (11 datasets at 32, 512 and 1024 samples) are bit-identical to accepted output across all 14 fields and fingerprints. See `build/modal/diagnostic-storage-parity-verification.json`. The 32 source-contract checks, Python checks and focused review passed. Both production configurations build; contributor and Release validators each passed 47 tests with zero failures. Saved Release result: `build/test-results/diagnostic-storage-release-validator-result.json`.
- **The runtime gate remains FAILED.** Final normal Release p99 is 181,938 ns against a 166,666 ns limit; CPU maximum is 306,355 ns against 333,333 ns. An earlier normal Release run also failed. Current fixed-CPU runs passed at 133,817 and 128,998 ns p99; an old-build run had a CPU outlier. See `build/test-results/diagnostic-timing-abba.json` and `build/test-results/diagnostic-storage-release-realtime-final.log`. Allocation and thread checks pass. Fixed-CPU passes do not clear the normal failure. Do not install this build.
- Next, capture paired wall/CPU durations and CPU migration for slow callbacks in the normal unpinned fixture. Independent sorting currently loses pairing, so aggregate results cannot distinguish scheduling delay from detector work. Preserve strict deadlines. The read-only Ryzen 7 7730U topology snapshot in `build/test-results/diagnostic-timing-topology.json` does not establish frequencies during prior tests. Once timing is resolved, consider filtering unsupported profile pairs only at final output while preserving internal ownership and release. The broader pair guard improved middle-string and ordinary results but damaged constructed chords and physical pairs. Keep output experiments offline until corpus, runtime and lifecycle gates pass.
- Accepted long matches: 41,452/68,441 (60.57%), target 42,128. Exact three-string assignment: 25,219/39,378 (64.04%), target 25,604. Wrong strings: 2,709, at the maximum of 2,709. These are test results, not overall completion. The latest successful ntfy time is authoritative in `build/modal/latest-notification-receipt.json`; the final window update is due at 20:36:37 UTC.

## 2026-11-01 20:12 UTC — assignment trial rejected; offline storage repair

- `assignment-partial-v1-analysis.json`: six controls match accepted output across14 fields. Trial rejected: long matches unchanged41452 but false outputs+314/wrong strings+14; ordinary matches-84/false outputs+111; constructed matches-28/false outputs+66; isolated02 matches-6/false outputs+6; isolated05/08 identical. Both apps completed. Flag stays disabled.
- Full native suite SIGSEGV diagnosed by GDB at the four-detector continuity test: each detector2139968 bytes, exceeding the8MiB stack. Assignment trace storage moved to constructor-owned offline memory; reset/process reuse it and allocation-failure disables capture. Extended causal trace test checks reset and no configure/process allocations. Guarded rebuild RUNNING session62739, `build/test-results/diagnostic-storage-build.log`.
- Next full native suite, runtime/source/diff checks and Modal default-output/buffer invariance. Accepted installed output unchanged; no install/commit/push. Continue through20:37 UTC. Last ntfy20:06:29, next20:16:29; receipt authoritative.

## 2026-11-01 20:02 UTC — shared memory correction rejected; assignment-only trial

- Shared-memory partial correction rejected: long matches -12,664, wrong strings +8,578; constructed false outputs +84,948. Low/high identical; middle +20 matches. All six controls match accepted output across14 fields. Report `build/modal/profile-memory-partial-v1-analysis.json`.
- Replay-only assignment-fast-profile correction implemented separately; shared EMA, fine/group evidence remain unchanged. Causal measured-template test added; guarded native/replay build running session91974. Source32/Python/diff pass. Next causal test, then paired six-set Modal screen. No active cloud sweep now.
- Reader verified saved templates use partial-peak energies; other direct-support/projection consumers remain outside this isolated experiment.
- Continue through20:37 UTC. Last notification receipt authoritative (19:55:12); next20:05:12. No install/commit/push.

## 2026-11-01 19:55 UTC — harmonic-memory representation trial

- Mixture-fit and phase-proximity filters rejected in saved cloud analysis: each useful phase policy removes correct secondary voices. No output change.
- Replay-only partial correction now aligns runtime harmonic memory with calibration measurement. Two focused tests and32 source checks pass, build and diff pass. Production excluded.
- Paired six-set Modal control/trial RUNNING: ap-efeMXetP6ov4VX0aRvtBoc / ap-0zuPuUjDIA6EBSzEuxB4Vu; local sessions19280/21312; reports `build/modal/profile-memory-partial-v1-{control,trial}.json`. Next compare14 actual fields, then only widen if no regressions. No duplicate sweeps.
- Continue through20:37 UTC. Last ntfy receipt authoritative. No install/commit/push.

## 2026-11-01 15:09 UTC — broad profile-pair guard rejected

- Paired six-set control/trial complete; all14 control fields match accepted output. `build/modal/profile-pair-corroboration-v1-analysis.json`: isolated05 +3558 matches/-4208 false outputs; ordinary +4040/-14286; constructed +30914 but +23592 false outputs; physical-long -7960 pair matches, triples unchanged25219. Rejected; offline flag stays disabled.
- Reader identifies internal ownership/release/adjacent-handoff coupling as a supported cause of constructed wrong-note growth. Root next captures profile single/mixture residuals and component weights on genuine and false pairs, then considers a narrower final-output projection preserving internal ownership. No new cloud job yet.
- Continue through20:37 UTC; next ntfy10min after latest successful receipt. No install/commit/push. Laptop-light Modal replay only.

## 2026-11-01 14:44 UTC — unsupported profile-pair experiment

- Phase/group capture COMPLETE: `assignment-phase-group-observation-verification.json`; six runs preserve all14 actual fields and TSV hashes across32/512/1024. Both512 traces downloaded and SHA verified.
- Reader found all222 middle-string false-extra sampled rows from profile pairs lacking fine/beat support. Early phase readiness admits adverse correct rows; defer that idea. Root implementing replay-only pair corroboration guard; no production changes.
- Last ntfy success14:37 UTC; next14:47. Continue through20:37 UTC. No install/commit/push. Build/causal tests and paired protected Modal screen next.

## 2026-11-01 14:21 UTC — phase and group-origin capture

- Extended assignment trace with raw/filtered/previous phase, calibrated cents, group proposal origin, pre/post group masks, and primary-only projection. Offline-only. Build, causal output/label/buffer fixture, source contract and diff pass; root review complete.
- RUNNING Modal `ap-Z7T4e9F7bFXOwIrXDLRypx`, local session36410, `build/modal/assignment-phase-group-observation.{json,log}`. Six isolated02/05 runs at32/512/1024. Compare14 actual fields and trace hashes; then download512 traces and analyze phase readiness and false group origins. Do not duplicate.
- Previous capture completed; isolated05 has222 sampled post-DP false groups and30 wrong primaries; isolated02 has60 wrong primary with correct lane free and27 reserved. Not recovered frames.
- Continue through20:37 UTC. Last successful ntfy14:03;14:18 DNS failed, retrying. Receipt is authoritative. No install/commit/push.

## 2026-11-01 13:39 UTC — string assignment capture

- Offline string-assignment cost trace implemented; winner-cost, output and label-independence test passes at32/512/1024. Source contract, Python syntax, diff and one root review pass. Production trace state excluded.
- Modal capture RUNNING `ap-pmJt2Z9o1Fcmp255OCFhFw`, session76523, `build/modal/assignment-cost-observation.{json,log}`: isolated02/05 at32/512/1024. Next compare14 accepted output fields and trace hashes, then analyze primary cost/reservations and later projection. No duplicate replay.
- Residual persistence exploratory: third consecutive strong observation gives106 expected-pitch observations,0 wrong pitch,1 gap;72/106 still wrong calibrated string. No independent chord validation, no output gain.
- Continue through20:37 UTC; ntfy last13:33:35, next13:43:35. No install/commit/push.

## 2026-11-01 13:23 UTC — residual admission results

- Capture and cloud analysis completed: `build/modal/residual-admission-screen{,-analysis}.json`; all14 output fields identical accepted control on4/4 sets, saved invariance report. Gain>=0.2 gives180 expected-pitch vs11 false-pitch sampled observations in ordinary chords, with misleading calibrated string in100 expected-free cases. This is not recovered MIDI coverage; no safe scalar threshold/string assignment yet.
- Ordinary trace downloaded and SHA verified: `build/modal/residual-admission-ordinary.tsv` (364619B). Reader weak_candidate_evidence analyzes temporal persistence; reader primary_state_rescue_effects diagnoses isolated5/2. Root owns implementation. Cloud idle, no duplicate replay.
- Numerical1/replay1/analyzer5/source/Python/diff checks pass; root review complete. No production change, install, commit or push. Continue through20:37 UTC. Latest ntfy timestamp is in latest-notification-receipt.json.

## 2026-11-01 13:13 UTC — residual admission cloud capture

- Fine-proposal evidence verdict: false pair triples outlast the true missed triple and have stronger residual improvement. Do not shorten consensus or relax spectral threshold. Evidence saved in `build/modal/fine-proposal-evidence-verdict.json`.
- Offline added-pitch residual trace is implemented. Its synthetic replay fixture now uses two strong open tones (40/44) and weaker fretted tone 51; the original adjacent 40/41 fixture never reached the DP and was replaced.
- Numerical test, buffer/label independence test, five streaming-analysis tests, source contract, Python syntax and diff check pass. One root review complete. No production/MIDI changes.
- Modal `residual-admission-screen` captures ordinary, constructed, physical-long and isolated-08 at512. App/session and report are in current-status/log; local exec session66590. Run cloud `residual_admission_analysis` after it completes; compare all14 actual fields/fingerprints with accepted control.
- Last ntfy13:11:21 UTC, next due13:21:21. Continue through20:37 UTC.

# M3 Polyphonic Audio to MIDI — Resume

Updated: 2026-11-01

## Autonomous continuation — 2026-11-01

- 13:06 UTC: fine-proposal capture COMPLETED; 88,232 rows and all14 output fields identical at32/512/1024. Verified downloaded TSV and `build/modal/fine-proposal-evidence-invariance.json`. Reader primary_state_rescue_effects compares actual analysis ticks for false pair vs true triple proposals. Root implements residual-admission offline trace; native build running session3816; Python analyzer5 tests PASS. New helper measures base pitch model versus base+missed candidate with truth attached after fitting; no MIDI change. Next focused native tests, then four-set Modal trace. Last ntfy13:03:28, next13:13:28. No install/commit/push.

- 12:49 UTC: initial unison timing shortcut REJECTED: false pair proposals last3 actual fine analyses, missed true triple lasts2; current threshold4. No timing change. Trace-only residual/ratio/beat/unique-member getters added; candidate trace partition/output test, source contract, diff check PASS. Physical-long capture RUNNING app `ap-KjvJYcOmMEgWtN2AnxqZYc`, session61841, `build/modal/fine-proposal-evidence.{json,log}` at32/512/1024. Reader confirms residual candidate-addition is distinct from prior deletion/veto trials; root implements shadow-only discriminator next. Last ntfy12:44:43,next12:54. No install/commit/push.

- 12:40 UTC: saved-trace half-penalty outcome comparison COMPLETED, app `ap-afPqRCGh9ZgXaQg7wsZJDd`, `build/modal/fretted-penalty-half-outcomes.json`. Ordinary gained12387/lost4218 matched labels; added12856 correct voices but11894 wrong-string,11098 wrong-note,4276 extra gap outputs. No safe simple directness rule. Root continues offline work; primary_state_rescue_effects joins physical candidate trace with exact labels for initial complete-group false-pair exposure; weak_candidate_evidence reads existing residual lane for a distinct counterfactual-admission hypothesis. No new jobs active. Last ntfy12:34:22,next12:44.

- 12:35 UTC: half-fret-penalty screen COMPLETED and REJECTED. Ordinary +8169 matches/+10399 false outputs; constructed +9455/+20102; long -1325/+7088, triples -17. Isolated08 bit-identical. Analysis `build/modal/fretted-penalty-half-analysis.json`. Same-binary ordinary/long controls decisive. Next cloud outcome comparison from saved traces; subset `fretted-penalty-half-paired.json`. Reader checks narrow initial complete-playable fine consensus; first multi already uses0.20sec, not2.25. No install/commit/push.

- 12:27 UTC: selector-local capture completed and all14 output fields/fingerprints equal accepted ordinary/long baseline; `build/modal/selector-local-invariance.json`. Cloud analysis `selector-local-analysis.json`: of28,694 strong ordinary misses,27,724(96.62%) have no positive fret-adjusted option;917 occupied,45 free-but-capacity-full,8 unpooled. Half-strength fixed/per-fret penalty screen now RUNNING on ordinary/constructed/long/isolated08; report/log `build/modal/fretted-penalty-half.{json,log}`. Existing offline penalty controls only; no DSP change. Root handles screen; reader primary_state_rescue_effects examines new fine_disposition trace `selector-local-physical-candidate.tsv`. Capture/analysis apps completed. Last ntfy12:26 UTC, next12:36. No install/commit/push.

- 12:21 UTC: offline selector-local observations and fine disposition added. New causal negative-fret-score test plus candidate/outcome partition-invariance tests pass; Python25/25, source contract and diff pass. Root focused review found no behavioral edits. Modal capture RUNNING app `ap-F4qocB0f7DmwZ1O6myVEja`, session56652, `build/modal/selector-local-observation.{json,log}` on ordinary/physical-long at512; both traces, note40 first60sec. Next compare14 output fields, analyze strong evictions by pool/adjusted score/free ownership and triple fit7 narrowing by fine disposition. Three-second gate unchanged. Last ntfy12:15 UTC; next12:25. No install/commit/push.

- 12:04 UTC: fine reset capture and posterior trace COMPLETED. Physical-long output/trace identical32/512/1024; 4467/4784 selected triple collecting frames are uninterrupted3sec warmup. No gate change. Posterior v1 causal mechanism: tick34855 harmonic note52 takes lane1, blocking later valid note40 fine pairmask3 at35805. Trial remains rejected; no gain elsewhere. Ordinary joint eviction analysis COMPLETED: 27807/28694 strong expected-pitch misses occur with selector capacity unused. Report `build/modal/ordinary-eviction-joint-analysis.json`. Next offline pool/score/ownership diagnostics, then causal narrow trial if evidence supports. Reader primary_state_rescue_effects handles remaining post-warmup triple gaps; root handles ordinary. Last ntfy12:04 UTC. No install/commit/push.

- 11:48 UTC: joint-posterior v1 COMPLETED and REJECTED: long41452->38059, all3393 lost matches are pairs, triples25219 unchanged; ordinary/constructed/isolated08 bit-identical. Analysis `build/modal/polyphonic-posterior-v1-analysis.json`. No install. Follow-up read-only diagnosis says commit flag indirectly freezes primary correction, not a direct unison gate; causal corpus mechanism still unproven. New offline fine-reset provenance implemented (unselected gap, selected gap, invalid fundamental, floor loss, inactive energy loss; decimation separately marked). Two focused native tests, source contract and diff pass. Capture RUNNING app `ap-93JmriucndS9afIfF3ychG`, session98304, `build/modal/fine-history-reset-control.{json,log}` at32/512/1024, note40 first60sec. Next verify14-field invariance, then locate resets; do not repeat collecting-fine-history-carry trials (already rejected). Last ntfy11:44:06 UTC. Root sole writer; weak_candidate_evidence reads ordinary failure data for next distinct-pitch target.

- 11:29 UTC: floor-reentry group analysis COMPLETED;6,654/6,785 quiet triple misses remain below input gate,131 occur with signal present. Strong ordinary wrong-string assignment is next. Offline joint-posterior exception implemented: all2–4 selected pitches require complete >=.95 distinct posteriors, mature direct evidence, no multi-source/committed/coasting conflict. New causal test red2->green; six posterior tests pass. One read-only review pending. Four-set disabled control RUNNING app `ap-WktwCnoBQZFunBmYIbcCRo`, session66502, `build/modal/polyphonic-posterior-v1-control.{json,log}`. Trial not launched yet. Source contract repaired conditional-brace parsing without behavior change, passes; do not rebuild replay until matched trial has used this binary. Second reader isolates fine-history reset diagnostics. Last ntfy11:21:24 UTC.

- 11:18 UTC: floor-reentry observation COMPLETED and all14 output fields/fingerprints match both accepted and prior diagnostic controls on4/4 sets; `build/modal/floor-reentry-output-parity.json`. Cloud group analysis RUNNING, app `ap-WWfIK7JT7j7g3xU1sa6jeN`, session70443, `build/modal/floor-reentry-group-analysis.{json,log}`. Quiet-specific signal/score/directness axes added; Python21/21 pass. Next distinguish below-floor audio from returned pitch inside the40ms wait. Two read-only agents cover strong ordinary wrong-string assignments and non-quiet long partial triples. Last ntfy11:10:51 UTC.

- 11:10 UTC: offline floor-reentry observation RUNNING, app `ap-ZsibaCJb7IWZHdTnYCLKvl` / session85755; report/log `build/modal/floor-reentry-observation.{json,log}`. Four sets ordinary/constructed/long/isolated08,512 samples, rescue disabled. New quiet2 read-only scoring causal test failed3 assertions before repair, now passes; related diagnostics test passes; native/replay build and diff pass. Selection remains disabled and temporary scores cleared before downstream evidence updates. Native/Python group matched and denominator totals agree on4/4; automatic parity guard added, Python20/20 tests pass. Next: all14-field output invariance, then cloud group analysis. Last ntfy11:02 UTC.

- 11:02 UTC: physical-group attribution COMPLETED, app `ap-NzQjJtE7FrUDlRDnXmUrEv`; report `build/modal/group-failures-control.json`. Constructed exact groups5,715/433,208; partial305,633. Lane-only typed-row coverage332,733/1,614,601; historical exact-row259,074 unchanged. Ordinary/long/isolated08 group results equal historical counts. Python19/19 tests, syntax/diff and one review pass; no tracking gain claimed. Next: offline read-only spectral evidence in quiet2 after input-floor reset. No active cloud job.

- 10:48 UTC: label failure attribution RUNNING on existing control traces, app `ap-r4siJ5GKVdbKHrHBnq5Buj` / session80882. Report `build/modal/label-failures-control.json`, same-stem log. No new audio replay. Added exact rendered-mask attribution, five tests (14 total pass), syntax/diff check, one root review. Separate missing pitch, wrong string, partial group, extra member, rebinning and selection state. Two read-only agents separately diagnose physical-long cause tables and strong assignment source. Next notification due10:52:52 UTC.

- 10:43 UTC: population analysis COMPLETED, report `build/modal/candidate-population-control.json`. No tested weak-admission rule separates expected notes safely across sets. Missed weak labeled frames ordinary57,058, constructed1,069, long0, isolated08 zero. Move to strong expected-note assignment and missing unison evidence; no duplicate capture needed. Notification timestamp in receipt.

- 10:38 UTC: pre-selection population analysis RUNNING on existing cloud traces, app `ap-zlITIAHikhdlNJJgJoO4YY` / session61652. Output `build/modal/candidate-population-control.json`; log same stem. No new capture/replay. Added streaming analysis and five causal Python tests (nine total pass), syntax/diff check and one root review pass. Rules exclude output/phase/onset/selection/fine state; labels only score hypotheses. Last ntfy actual timestamp10:35:30 UTC; next due10:45:30.
- 10:37 UTC: V5 COMPLETED and REJECTED. All four controls preserve all14 metrics. Ordinary +8,840 matches/+20,120 false outputs; constructed -11,601 matches/+29,543 false outputs; long unchanged from V4 matches36,284/wrong strings7,723, triples25,107. Analysis `build/modal/rescue-onset-v5-analysis.json`. Focused onset repair works but is insufficient. Next use existing pre-selection weak-direct candidate population from cloud traces; no new capture. Last ntfy sent10:37 UTC.
- 10:30 UTC: V5 onset guard implemented offline; nine focused rescue tests pass (four sample rates), native/replay builds and diff check pass. Paired Modal screen RUNNING: control `ap-9pT7HV2MecfQFpxGulYl52` / session42338; trial `ap-Ac79aCs4nB9SBp3r3YQX7I` / session43280. Reports `build/modal/rescue-onset-v5{,-control}.json`; compare with `python3 build/modal/compare-rescue-screen.py rescue-onset-v5` after completion. Do not duplicate. Outcome-feature review found no globally safe admission threshold; phase/voice-string agreement is post-selection and confounded. Last ntfy sent10:25 UTC.
- 10:25 UTC: paired outcome analysis COMPLETED (`ap-8yr1jxHg305ceJqv5WZieS`), `build/modal/outcome-attribution-analysis.json`. All four capture controls/trials reproduce V4 metrics. Direct rescued notes recover7,276 ordinary matches but add8,418 wrong-string and2,397 wrong-note outputs; constructed/long/isolated direct rescues recover zero correct outputs. Downstream primary-state changes dominate additional regressions. Read-only primary-state review finished: weak selection can raise the global onset wait40->50ms and clear mature primary selection. New causal test reproduces eight failed assertions at four sample rates; log `build/test-results/rescue-onset-v5-red.log`. Next: offline admission guard at50ms, then paired Modal screen. No active cloud job or duplicate capture needed.
- User requested another 12 hours from approximately 08:37 UTC, through 20:37 UTC.
  Continue bounded improvement work, with recording tests on Modal and detailed
  ntfy summaries every 10 minutes. Keep this checkpoint current across compaction.
- Use the authenticated publisher `$HOME/.local/bin/researchos-ntfy-publish`
  with topic `Reaper_PolyphonicVST`; never read or expose the saved credential.
- Completed v2 comparisons (rejected): control `ap-iigYDvpmNmaxaWlIJD41a3` / session35342;
  trial `ap-ZA7vi0a9PoPD6V0RFXtmrS` / session20644. Reports/logs
  `build/modal/rescue-ownership-v2{,-control}.{json,log}`. Do not duplicate.
- V1 pair diagnosis: expected06 observed06 loses5,131 frames, observed07
  gains4,918. Expected05 observed07 gains2,477. Fine evidence expands toward
  mask07. Most pair loss is an extra third string; primary-lane retention alone
  is not an established fix. Read-only diagnosis is complete.
- Fine-window capture comparisons completed: control `ap-7E5wUZvSq8H4KpooBFZb2w`,
  trial `ap-2ocsC2ZQlBQeI8OnduJ44j`. Reports/captures:
  `build/modal/rescue-v2-fine-trace{,-control}.{json,fine-windows.jsonl}`;
  analysis `build/modal/rescue-v2-fine-trace-analysis.json`. Every control
  solve time exists in the trial (72 control, 125 trial); shared audio samples
  are identical. Scheduling starvation is disproved. Rescue adds observations,
  displaces older samples from the bounded history, and advances false group
  expansion in two physical pair sections.
- V3 completed and REJECTED: control `ap-YEg6Q3Hp9KgC4WmTKVHgn7`, trial
  `ap-PTfLZaWk6nY0LBZlSW7LFI`; analysis `build/modal/rescue-history-v3-analysis.json`.
  Direct rescue-only selections now cannot seed fine history (causal test red
  then green; seven focused tests and group carry test pass). Nevertheless,
  all output counts equal the rejected v2 result on four screened sets. The
  same-binary disabled control preserves all14 fields on4/4. Do not repeat.
- Bounded offline candidate timeline implemented and verified: output fingerprint
  and trace identical at32/512/1024; invalid ranges rejected. Focused test passes,
  Python syntax and diff checks pass. No production trace state.
- Completed Modal trace pair: control `ap-vWFHRN0FXIOhSp6okJodAS`, trial
  `ap-4AXdL7KiXqJ1bdpeH2aWRc`. Captures downloaded; analysis:
  `build/modal/rescue-history-v3-trace-timeline-analysis.json`. At tick8324,
  weak note59 changes the isolated octave-classifier context for note40,
  permitting its relaxed threshold. Fine history then diverges at tick8325.
  A separate earlier quiet-state divergence remains outside this repair.
- V4 excludes diagnostic rescue candidates from primary spectral context;
  their active ownership still counts normally. A causal test reproduced eight
  assertions before repair; all eight focused rescue tests now pass. Logs:
  `build/test-results/rescue-context-v4-{red,focused}.log`. Native test and replay
  targets build, and diff check passes. All changes remain offline-only.
- V4 completed and REJECTED: control `ap-fWrLYoEfeuCxyW0mlB6u4m`, trial
  `ap-y5jbRKYY0Y43v7ZyO3Y8n8`. Reports and analysis:
  `build/modal/rescue-context-v4{,-control,-analysis}.json`. All four control
  datasets preserve all14 fields. Long matches41452->36284, wrong strings
  2709->7723; triples25219->25107. Ordinary +8825 matches also adds20106
  false outputs; constructed loses11680 matches. No install or wider gates.
- Next: identify a measured discriminator between real weak notes and false
  overtones before another rescue policy. Existing population diagnostics show
  almost no below-threshold labeled targets in constructed/long/isolated08,
  despite abundant extra candidates. Do not repeat the broad rescue screen.
- Last phone summary sent10:15 UTC; subsequent summaries every10 minutes.

## Free-string rescue ownership screen — 2026-11-01

- The collision-v2 label diagnosis is complete: only three of 499 labels change.
  Two sustained ordinary notes lose 136 exact frames in total, offset by three
  recovered frames in another label. Resetting a coincident pitch is insufficient
  evidence to invalidate its calibration. Keep that experiment disabled.
- Repaired the separate, offline-only weak-candidate rescue: account for
  unselected active/coasting string owners and their physical voice capacity;
  carry the admitted free-string mask into final assignment. Established
  multi-string candidates remain on the existing fine/retention path. The
  calibrated production rescue is unchanged.
- A causal test reproduced two ownership failures before the repair. Four
  focused rescue tests passed; native test and replay targets built. Log:
  `build/test-results/rescue-ownership-focused.log`. One focused review completed.
  The selector's lane allocation is not itself proof of final lane ownership;
  recording evidence must establish whether this narrow repair is useful.
- Same-binary Modal comparisons completed over ordinary/constructed chords,
  physical-long, and isolated strings8/5/2 at512 samples. Control app
  `ap-ebiRqIzVA6HaD0DLggtpep`, trial app
  `ap-8b4DimJXRgsHC5yHOB3hSW`. Reports/logs:
  `build/modal/rescue-ownership{,-control}.{json,log}`. Do not duplicate them.
  Trial ratios0.20/0.80; measured baseline trim-9, sensitivity60, response75,
  polyphony5, fret24. V1 rejected: ordinary matches145,385->156,926 but false
  outputs319,772->343,481; constructed matches259,074->247,394; long
  matches41,452->35,909 and wrong strings2,709->10,273. Exact triples
  25,219->25,107; exact pairs16,233->10,802. Only isolated string2 remains
  bit-identical. Disabled control preserves all14 fields on all six datasets.
  Analysis: `build/modal/rescue-ownership-analysis.json`. No install/commit/push.
- Review found two additional conflicts: rescue ignored the decisive selector
  string mask, and overlapping DP/coasting lane masks undercounted occupied
  voices while claiming an alternative lane was free. Two new causal tests
  reproduced six failed assertions. V2 respects the effective selector mask,
  counts logical voices separately, and conservatively refuses rescue when
  the DP lane witness overlaps a coasting owner. All six focused rescue tests
  now pass: `build/test-results/rescue-ownership-v2-focused.log`.
- V2 comparisons completed and remain REJECTED. Analysis:
  `build/modal/rescue-ownership-v2-analysis.json`. Ordinary matches145,385->154,210,
  false outputs319,772->339,878. Constructed259,074->247,394; long41,452->35,909,
  wrong strings2,709->10,275. Exact pairs16,233->10,802; triples25,219->25,107.
  The disabled control preserves all14 fields on6/6 sets. No wider acceptance
  tests, install, commit or push for this rejected policy.
- Fine-history trace and v3 follow-up are recorded in the continuation section
  above. Only a passing screen proceeds to full corpus/buffer/runtime gates.

## Calibrated-pitch collision experiment — 2026-11-01

- Both v1 Modal jobs completed; rejected. Reports:
  `build/modal/calibrated-collision{,-control}.json`; comparison:
  `build/modal/calibrated-collision-analysis.json`.
- Ordinary matches 145,385 ->145,252, false outputs319,772 ->320,509;
  constructed matches259,074 ->259,748, false outputs294,652 ->296,654.
  Long unison and all three isolated sets are bit-identical. Same-binary
  disabled control preserves all14 output fields on6/6 sets. No installed change.
- One focused review found that base-note reset leaves a second MIDI projection
  active, ignores other projected owners, and can terminate another candidate
  in single-channel routing. Stronger lifecycle tests reproduced33 assertions;
  log: `build/test-results/calibrated-collision-v2-red.log`.
- V2 implemented: compare actual MIDI notes; atomically reset both projections
  and consensus after queue-capacity preflight; protect established groups;
  restrict to per-voice routing and non-quiet audio. Added silence regression.
  Replay-only/default-disabled. Native/replay build passed; rebin13/13,
  release19/19, panic9/9, native-source contract and whitespace checks pass.
- V2 Modal comparisons completed over ordinary/constructed chords,
  physical-long, and isolated strings8/5/2 at512 samples. Control app
  `ap-8A5b2lZRj4EWpPUhwoEeVC` (local session54045), trial app
  `ap-N1HNTYfxMl4SyO5lWhMEAV` (local session12868). Both completed.
  Reports: `build/modal/calibrated-collision-v2{,-control}.json`; logs share
  those stems. Analysis: `build/modal/calibrated-collision-v2-analysis.json`.
  Rejected: ordinary matches145,385->145,252, false outputs319,772->320,509,
  wrong notes164,263->165,007, transitions11,903->12,009. Constructed scores
  unchanged but fingerprint differs; long and isolated outputs bit-identical.
  Same-binary control preserves all14 fields on all six datasets.
- Label-span diagnosis completed in
  `build/modal/calibrated-collision-v2-label-analysis.json`. A coincident output
  pitch alone does not establish invalid calibration. Keep v2 offline; no
  further acceptance checks for this rejected policy. Installed bundle unchanged.

## Candidate-admission recovery screen — 2026-11-01

- Completed Modal app `ap-gP9djZPb9nxTKG0DWrL6Gz`; rejected the six-recording
  experiment. Analysis: `build/modal/candidate-admission-rescue-analysis.json`.
- Ordinary matches improved 145,385 to159,578, but false outputs increased
  319,772 to364,432. Physical-long matches fell41,452 to35,913; wrong-string
  outputs rose2,709 to9,408. Constructed matches fell259,074 to247,536.
- The installed bundle and its accepted metrics remain unchanged. The weak
  candidate policy is replay-only, default disabled. No commit/push.
- Implemented replay-only correction: require pitch-band dominance, prevent a
  diagnostic-only candidate from suppressing a baseline candidate as a harmonic,
  and preserve priority of the existing calibrated rescue slot. Three focused
  tests reproduced conflicts before the correction and pass afterward (3/3).
- Both guarded-comparison Modal apps completed and stopped with zero tasks:
  control `ap-3XR9Sg2XbhOwyvmtyQEndl`, candidate `ap-Gj8U1Dxtaf4MdwslSjgNiZ`.
  Analysis: `build/modal/candidate-admission-guards-analysis.json`. No rerun needed.
- Guarded experiment rejected: ordinary matches145,385->157,468, but false
  outputs319,772->345,909; constructed matches259,074->247,399; long matches
  41,452->35,909 and wrong strings2,709->10,275. Exact triples25,219->25,107;
  correct pairs16,233->10,802 account for5,431 of5,543 lost long matches.
- Same-binary disabled control preserves all14 metrics/fingerprints on all six
  sets. One focused review found no material code defect; tests establish
  selection guards, not downstream ownership. No full-suite run for this repair.
- Next: diagnose lost pair/string assignments and added false pitches before
  another policy. Keep the experimental rescue disabled and production unchanged.
- Same measured baseline: trim -9 dB, Sensitivity60, Response75, polyphony5,
  fret24. Any protected match/error regression rejects the experiment.

## Assignment-cost optimization checkpoint — 2026-11-01

The assignment-cost optimization is accepted and installed. The guarded
false-note rule remains opt-in in replay/test builds and is excluded from
production. Global defaults remain unchanged.

- Candidate/string lane costs are computed once per decision before the
  assignment-state loop. Arithmetic order and ownership constraints are
  preserved. One focused review found no material defect.
- Full native suite: 455/455. Runtime checks: 2/2, including 100,000 callbacks
  without allocations or thread creation. p99 147,435 ns <166,666 ns; maximum
  CPU 221,810 ns <333,333 ns. Maximum wall time 403,755 ns; live glitch-free
  behavior is not established. Logs: `build/test-results/assignment-cost-hoist-*`.
- Both Modal jobs completed: enabled 33 rows (eleven sets at 32/512/1024),
  disabled eleven rows at 512. All enabled deterministic fields and 22 buffer
  comparisons are identical. All disabled actual output fields are identical;
  its older control predates the physical-model repair, so observer counters
  are not claimed identical. Analysis: `build/modal/assignment-cost-hoist-analysis.json`.
- Production build, Steinberg validator and whitespace checks passed. Bundle
  installed with SHA `c3a877dfeacba6293013ef4c4372a6dbe0210baabc2c9ee0728dfd33be62518f`.
  Backup: `~/.vst3/.m3-backup-before-assignment-cost-20261101T045637Z`.
  Live host reload is unverified. Receipt: `build/test-results/assignment-cost-hoist-install.json`.
- Experimental false-note suppression (entry 0.001, restore 0.005) preserves all
  eleven correct-match and wrong-string totals, removing 5,575 wrong-note frames
  and 271 extra outputs in unlabeled gaps, with six extra transitions. Seven
  recordings are bit-identical. It remains excluded from the installed plugin.
- Long-unison matching remains 41,452/68,441 (target 42,128); exact three-string
  assignment remains 25,219/39,378 (target 25,604). Wrong strings 2,709 have zero
  safety headroom. Overall live-use readiness remains incomplete.
- Next: use existing missed-note diagnostics to target an actual recovery
  mechanism across intervals/chords and practical unisons. Do not repeat the
  completed optimization checks or resurrect rejected classifier/beat fits.

## Callback residual checkpoint — 2026-10-28

- `M3_ENABLE_RESIDUAL_SHADOW_TESTS` enables the bounded residual observer only
  in native tests, replay and the real-time test target. Compile-command checks
  confirm that production, probe and historical CLAP bundles exclude it. The
  observer runs on M3 snapshots at the existing 64-sample decision cadence,
  after the initial 0.8-second history gate. Existing pitch-group identities
  supply raw candidate notes without changing telemetry or MIDI.
- The first full native run exposed an 8 MiB stack overflow in the existing
  four-detector test. The fixed 52,920-byte solver workspace is now allocated
  once when each detector is constructed, before configuration or processing.
  Configuration, reset and audio calls reuse it. The original fixture and stack
  limit are unchanged; the full native suite now passes 450/450.
- A review found that the real-time test's maximum pitch counter included
  warmup. Metrics now reset before measurement. The test repeatedly clears only
  the solver cache and times the rebuilding inside actual audio callbacks.
  At 96 kHz/32 samples, final p99 is 112,305 ns against 166,666 ns; maximum
  thread CPU time is 168,136 ns against 333,333 ns. Measured-only counters show
  6,000 evaluations, 3,417 ready and 2,583 rebuilding, with eight pitches and at
  most four rebuild work items. The 100,000-callback allocation/thread check
  also passes. These measurements include the prototype, not an output policy.
- Modal reports `residual-callback-protected.json` and
  `residual-callback-buffers.json` preserve every prior reported metric,
  fingerprint and counterfactual policy count across eleven sets and the
  ordinary/physical-long 32/512/1024 checks. Core and offline evaluation,
  readiness, waiting and residual counters match exactly. The diagnostic rule
  retains 3,110 hypothetical false-output removals with no correct loss.
- Source-contract, Python syntax and whitespace checks pass. One focused review
  completed; its counter issue is fixed. No installed-bundle or MIDI change.
- Next: evaluate logical candidates before the active MIDI lifecycle and apply
  a guarded render-suppression rule there. Suppressed candidates must remain
  available to the model; filtering the rendered snapshot would remove their
  own evidence. Require note-off/retrigger/release and transition-capacity tests,
  protected replay improvement, and callback checks before production use.

## Bounded residual checkpoint — 2026-10-28

- `JointPitchResidual::evaluate_bounded` now performs at most four rebuilding
  work items per call. It returns no usable result until the current model is
  ready; changed topology, invalid input, silence and reset discard incomplete
  work. Completed results use the current audio correlations. Synchronous replay
  still uses the same math without the scheduling limit.
- The workspace is 52,920 bytes. The isolated eight-note rebuild takes 88 calls
  at this budget, with measured p99 10,895 ns per call. These are kernel-only
  timings. Full callback timing is still required before production use.
- Replay adds `--diagnostic-bounded-joint-pitch-residual`; the Modal wrapper
  exposes `--bounded-joint-pitch-residual`. Both remain offline diagnostics.
  Reports include waiting frames and maximum rebuild work. No MIDI, UI,
  parameter, default or installed-bundle changes.
- Modal `bounded-joint-protected.json` (app `ap-Oyc6Badcek8peHjH6XPQm3`)
  preserves all actual metrics and fingerprints across eleven sets. The safe
  policy retains 3,110/3,137 hypothetical false-output removals (99.14%):
  ordinary 5, constructed 1,504, middle isolated 948 and upper unison 653.
  No correct matches are removed and no error category increases. Waiting for
  rebuilding forgoes 27 removals; these remain counterfactual results, not
  recovered or suppressed MIDI events.
- `bounded-joint-buffers.json` (app `ap-R2z6J2bGhEuE11bQfhnf5A`) matches
  the ordinary and physical-long results at 32/512/1024 samples, including all
  diagnostic counters. Full native suite 449/449, source contract, Python
  syntax and whitespace checks pass. One focused state-machine review found
  no material defect.
- Next: invoke this bounded work in a production-shaped shadow path, verify
  callback deadlines and allocations during rebuilding, then integrate a MIDI
  policy only if the protected recording and note-release gates still pass.

## Compact residual checkpoint — 2026-10-28

- The shared native residual kernel now uses one packed Cholesky factorization
  and small inverse-block factors for individual pitch deletions. Shared
  harmonics, ridge regularization and overlap protection are preserved. The
  original offline solver remains the numerical reference. Replay diagnostics
  use the compact kernel; the production detector does not invoke or store it.
- Object memory falls from 671,072 to 43,680 bytes (93.5%). In an isolated
  eight-note kernel benchmark, cached p99 falls from 31,359 to 9,150 ns;
  rebuilding still takes 209,036 ns. Those are kernel measurements, not full
  VST3 callback measurements. A synchronous rebuild is not ready for production.
- Full native suite 447/447, source contract, whitespace checks and one
  numerical review pass. Tests compare full and deletion energies across
  1–8 pitches, shared harmonics, scaling, ordering, cache changes and four
  sample rates, with no allocations or deallocations.
- Modal reports `build/modal/compact-joint-protected.json` and
  `build/modal/compact-joint-buffers.json` preserve all reported metrics,
  fingerprints and diagnostic policy counts across eleven protected sets.
  Ordinary and physical-long results also match at 32/512/1024 samples.
  The conservative offline rule still removes 3,137 hypothetical false outputs
  with no lost matches; this is not a change to actual MIDI output.
- Next: bound rebuilding across callbacks, with no valid result until the
  current model is ready and cancellation when its inputs change. Require
  equivalent completed math, allocation and callback-budget checks before
  integrating any MIDI policy. Installed production and tracking gates remain
  unchanged.

## Active tuner-stability checkpoint — 2026-10-27

- Continue in the repository root on `work/tuner-stability-20261027`.
  This is a development checkpoint, not a validated release. Preserve any
  subsequent native/offline changes. Use `build/modal/current-status.json` and the
  newest completed Modal reports for current metrics. Sections below are
  historical checkpoints.
- Dense native-history capture is complete. Replay now accepts
  `--fine-window-start`, `--fine-window-end` and `--fine-window-min-spacing`.
  The half-open range selects the newest observation time without trimming the
  history; spacing zero captures every distinct eligible observation. Defaults
  remain 0.5 seconds and 512 windows. Note filtering, duplicate suppression and
  truncation reporting remain intact. No production code or MIDI changes.
- `build/modal/dense-fine-capture.json` (app `ap-LDZwq1xqkTAPa1mHSIYCBR`)
  captures 161 E2 histories before 38 seconds. All captures are byte-identical
  at 32/512/1024 samples, with no truncation; all tracking metrics and existing
  diagnostics match the accepted replay. Full native suite 445/445, five build
  checks, native source validation, eight CLI cases, Python syntax and whitespace
  checks pass. One diff review completed.
- Dense controls and coupled confidence completed on Modal:
  `dense-harmonic-control.json` (app `ap-QIa7JajL2us4PHfl5I2cEn`) and
  `dense-coupled-confidence.json` (app `ap-EOEqUcJapDGgHi7uoV4pEl`). Native
  fundamental reconstruction relative RMS error is 7.85e-11. There are 116 pair
  and 45 triple decisions, including 14 incomplete prior triple assignments.
  The alternative profile condition supports 11 consecutive triple decisions
  from 35.87 to 36.37 seconds: 11/45 (24.4%), including 3/14 incomplete cases
  (21.4%). No false third qualifies in 116 pair decisions. Competing wrong pair
  masks still qualify in 62/116 (53.4%); strict two-harmonic support finds no
  triples. These overlapping observations are not recovered MIDI frames or
  independent examples. Production remains unchanged.
- A bounded amplitude update is rejected for integration. The new
  `tools/harmonic_amplitude_audit.py` fits a positive 0.5–2 gain per string using
  only the later half of training audio, preserving pitch, phase, decay and
  harmonic ratios. Every model receives the same update. Modal report
  `dense-amplitude-refresh.json` (app `ap-nStC6Mxl6PygnYGLoXFLkJ`) increases
  diagnostic triple support from 11/45 to 12/45 and incomplete support from
  3/14 to 4/14, but loses a supported pair at 24.77 seconds. Pair support rises
  from 94/116 to 95/116 through two gains and one loss; false thirds remain
  0/116 and wrong-pair alternatives fall from 62 to 57. When larger models must
  beat the best smaller model across both original and updated states, triple
  support returns to 11/45 and 3/14; pair support falls to 93/116. The apparent
  recovery gain therefore does not survive that comparison. Do not combine
  previously qualified states with an unconditional OR. The shared comparison
  is recorded in `dense-amplitude-model-pool-analysis.json`.
- One review found that reopened prepared arrays were not bound to frozen
  reports. New prepared files now carry a SHA-256 checked by fitting workers
  and input validation. Legacy amplitude audits recompute and match every saved
  current-energy audit field before using a reopened window. Five amplitude
  tests and three provenance tests pass, including mutated audio and saved-score
  rejection, future-audio isolation, scale, bounds, pair and silence controls.
  All 161 existing windows reproduce their saved audits through the repaired
  path in `dense-amplitude-refresh-verified.json` (app
  `ap-HEGt95JVR08uyxWAwSONQg`); qualification results are unchanged.
  No production/native changes accompany this Python-only experiment.
- Next: move to the already measured joint-pitch residual/overlap rule for
  intervals and chords, while retaining the dense unison evidence. Its offline
  removal of 3,137 false outputs across eleven protected sets still needs a
  bounded production implementation and real-time proof. Do not revive rejected
  classifiers or relax the unison sampling, decay, silence or release guards.
- Completed joint-fit and confidence experiments:
  `build/modal/coupled-harmonic-screen.json` (app `ap-XDcuPU0Ct9iHV9irwT0G8n`)
  and `build/modal/coupled-harmonic-confidence.json`
  (app `ap-n3Skfuv78l8aQYhXOurfT3`). The fit jointly estimates pitch, decay,
  complex phase and harmonic balance from older samples, with ascending-only
  measured profiles. The 3-dB profile scale and 6-dB bound are explicit modeling
  assumptions, not learned confidence intervals. The first fit predicts later
  audio better in 26/36 triple windows but supports neither missing triple.
- Scoring those fixed fits against current-band energy, while retaining the
  original training-derived noise floor, supports one of the two missing
  sampled triples (35.87 seconds) through the alternative allowing one supported
  harmonic per member plus the joint profile. Two of 36 triple windows meet
  this diagnostic condition; no false third qualifies in 13 pair windows.
  Strict two-harmonic-per-member support still finds no triples, and competing
  wrong pair masks still qualify in 6/13 pair windows. This is not an admission
  policy or a recovered-frame count; production remains unchanged.
- Six signal/causality/scale/silence tests pass. One review found incomplete
  input-identity validation; capture, calibration, rate, source set, window
  indices, model families and profile-extractor identity are now checked.
  Three input-validation tests and validation of the completed run's actual
  inputs pass. Rerunning the optimizer produced differences up to 0.0483 cents
  without changing original support flags. Therefore normalization comparisons
  use the same frozen parameters within the new report, not assumed bit identity
  across separate cloud runs. Details are in the corresponding `-analysis.json`.
- Completed harmonic-balance audit: `build/modal/harmonic-balance-screen.json`,
  app `ap-BDSPM6pilNNkJ9jh5Ry10o`. Four causal/filter/holdout tests pass and one
  review found no material defect. Three ascending E2 attacks train separate
  string profiles; eleven descending/checkpoint attacks remain held out. Both
  two- and three-harmonic profiles distinguish the expected string in 10/11
  held-out attacks. This is a small, single-pitch diagnostic, not overall
  precision. In the 13 recorded pair windows, with source count fixed at two
  for analysis, harmonic balance ranks the expected mask first in 11; it fails
  at 17.22 and 18.22 seconds. It must not control source count or MIDI alone.
  Captured optimizer parameters and all production output remain unchanged.
- The new comparison keeps the 15-Hz DC-filter response in both domains and
  removes only the 40-ms correlation response from fitted complex powers.
  Earlier static `profile_similarity` also removed DC response and therefore
  was not an exact calibration-domain comparison. That old diagnostic is not
  an acceptance rule; the new audit does not alter it or production behavior.
- Two E2 checkpoint spans need signal-quality review, recorded separately in
  `build/modal/harmonic-balance-outliers.json`, app
  `ap-QpWd54YGFDpOvQ9E9IzX1l`. String 8's final E2 checkpoint has very little
  E2 energy and a strongest spectral peak near 207.46 Hz (G-sharp 3). String 6's
  final open checkpoint is dominated by 163.79 Hz (E3), with little E2
  fundamental. These observations do not establish a replacement label or
  string identity. Preserve the original annotations and all acceptance gates.
  Next, evaluate harmonic balance as bounded evidence inside the joint fit,
  with explicit pitch evidence; post-fit profile ranking alone is insufficient.
- Latest completed offline control: `build/modal/joint-harmonic-known-bands.json`,
  app `ap-Q8sJLZxnYcfefYrPXCOJXZ`. One review found that unknown partial detuning
  was being treated as absent harmonic energy and that large observation gaps
  were not blocking source qualification. Both are repaired: all masks use the
  same calibrated harmonic bands, and both median-spacing and maximum-gap
  checks must pass. Nine causal tests pass. Of 36 sampled triple windows, 18
  meet sampling requirements and one supports the expected mask; neither of
  the two incomplete triples is recovered. No false third qualifies in the
  13 pair windows (11 meet sampling requirements). This control provides no
  production recovery gain. Diagnostic windows overlap; they are not MIDI
  frame counts.
- The pitch-drift/string-decay comparison completed on Modal as
  `ap-YoFBIFsv5rHdi0pbPAa5U0`, output `build/modal/harmonic-drift-screen.json`.
  It reuses the same 49 recorded windows and compares steady pitch, gradual
  pitch change, amplitude evolution and their combination. Frequencies and
  amplitude evolution are fitted on older samples only; newer samples score
  prediction. Every larger string mask competes with smaller masks across
  all four model families. Four causal tests pass; recorded source hashes
  match the checked files. Allowing string decay reduces median prediction
  loss from 0.32680 to 0.01567 in pair windows and 1.32738 to 0.87033 in triple
  windows, but supports neither incomplete triple. No false third qualifies
  in the 13 pair windows; competing two-string masks nevertheless qualify in
  six. Better signal prediction does not establish correct string identity.
  Reject this version for production. The next uncertainty is whether measured
  harmonic balance can distinguish those competing assignments. This remains
  offline; no production behavior, defaults or acceptance gates change.
- Earlier offline experiment: `build/modal/joint-harmonic-screen-v2.json`, app
  `ap-mGUJguLggrLUcm3o3xvlxh`, completed. Its counts below predate the review
  corrections and must not be used as the corrected control.
  The fit uses current pitches within the note cell, calibrated partial offsets,
  and three complex harmonic histories. Older samples fit frequencies; newer
  samples separately measure frozen-amplitude prediction and amplitude-refit
  residual. The physical screen supports the expected mask in 15/36 triple
  windows and 6/13 pair windows, but neither of the two sampled incomplete
  triples. It proposes a false third string in one pair window (17.72 seconds),
  wholly inside the pair label and already correctly assigned by the detector.
  These are overlapping diagnostic windows, not recovered MIDI frame counts.
  Reject this version for production. The two incomplete triples' refit losses
  are 0.01509 and 0.00175 while frozen-amplitude prediction losses are 1.54844
  and 0.61139; phase/amplitude evolution remains a concrete next uncertainty.
  Check unknown partial-detuning handling before using harmonic support as
  independent source evidence. The new fitter and its Modal entry point are
  offline-only; all production behavior, defaults and acceptance gates remain
  unchanged. Current working files are `tools/joint_harmonic_fit.py`, its unit
  tests and additions in `tools/modal_m3_replay.py`. No additional recording
  matrix or production build is running.
- Accepted lowest-string MIDI output correction retains selector history and
  requires two consecutive observations. True silence clears pending
  acquisition while preserving an emitted pitch for its matching note-off.
- `build/modal/dp-output-silence-fix-protected.json` preserves all ten other
  datasets and improves ordinary-chord matched frames from 145,382 to 145,385,
  with three fewer wrong-note and false-positive frames. Physical-long stays
  at 41,452/68,441; exact triple at 25,219/39,378; wrong strings at 2,709.
- Prior native 431/431 and focused release 5/5 checks passed. The previous
  claim that all three realtime checks passed was incorrect: the instrumented
  native suite compiled out the deadline assertion and reported a dummy pass.
  At that checkpoint the dedicated Release test failed at 96 kHz/32 samples: wall p99
  1,948,855 ns versus a 166,666 ns target; maximum thread CPU time 5,119,790 ns
  versus a 333,333 ns deadline. Its separate zero-allocation/thread test passes.
  The timing test is now registered only in configurations that execute its
  assertions. See `build/test-results/github-update-realtime.log`.
  The rebuilt native suite passes all 436 registered tests after that repair.
  Source contract, production build and Steinberg validator pass; these do
  not establish callback deadline compliance. The later efficiency update below
  passes the actual timing gate. Ordinary/physical-long fingerprints agree
  at 32, 512, and 1024 samples.
- Installed module SHA-256:
  `43d668187db33c286000e6e539809af675a86c674303a74589b646fdad6d889e`.
  Prior bundle is recoverable at
  `$HOME/.vst3/.m3-backup-before-profile-reuse-20261027T185556Z`.
  REAPER was running and was left untouched: its reload/live behavior remains
  unverified. The efficiency update was installed only after the checks below.
- Both completed correlation-window experiments were rejected. The full-window
  grid has 66 results in `build/modal/correlation-window-grid.json`; the
  selector-only grid has 55 in `build/modal/selector-window-grid.json`.
  All 40 ms controls match the accepted baseline. Selector-only 50 ms gained
  4,961 ordinary-chord matches and removed 32,540 false outputs, but lost
  2,783 physical-long matches and 348 isolated-high matches. None was installed.
- Rejected shadow experiment: `build/modal/correlation-shadow-grid.json`, Modal
  app `ap-mU8JEUSva0F9iJocMxo2Dm`, completed. Thirty-three replays cover all eleven protected
  datasets at 40/80/120 ms. The secondary window only scores 36 hypothetical
  removal rules; actual selection, tuner and MIDI output must stay identical.
  Rules protect attacks, coasting/release, corrected pitches and shared
  unison groups, and use causal note age rather than label age.
  Two scale/guard tests and all 18 offline replay tests passed. The focused
  test also proves unchanged output at 32/512/1024 samples. Source contract,
  Python syntax and whitespace checks pass. Inspect the report before launching
  another run. `build/modal/correlation-shadow-analysis.json` records the
  rejection: none of the 72 changed-window policies preserves all datasets.
  The closest rule removes 665 false output frames but loses 314 correct
  constructed-interval frames. Its ordinary-chord reduction is 82 wrong-note
  frames with no correct-frame loss. All 33 actual fingerprints are unchanged.
- Rejected narrow follow-up: `build/modal/correlation-pending-guard.json`, app
  `ap-2iiPQG8Npo8PKffaMLyVet`, completed. It runs ordinary and constructed at 80 ms, adding
  a conservative exemption when existing fine-frequency, pending-member or
  committed evidence indicates multiple strings. The original 36 policies
  remain first in the output; the additional 36 enable this exemption.
  Guard/scale tests (2) and the block-partition test (1) pass. This still only
  scores hypothetical removals. No guarded rule preserved both datasets. The
  least damaging still loses the same 314 constructed matches; unresolved
  fine-group protection did not fix the failure. Raw output fingerprints and
  the first 36 unguarded policies exactly match the previous experiment.
  Details: `build/modal/correlation-pending-guard-analysis.json`.
- Keep the longer-window rejection rules offline and disconnected. Do not
  repeat their threshold grids or install an experimental window.
- Completed experiment: `build/modal/joint-pitch-shadow.json`, Modal app
  `ap-Tt09dpdjyXFWIH9DXDj75w`; eleven protected recordings, baseline settings.
  New offline `joint_pitch_residual.*` fits real sine/cosine coefficients from
  the existing complex harmonic correlations using their exact exponential
  window Gram matrix. A one-pitch deletion measures independent support;
  duplicate frequencies share ownership. Seven veto thresholds are evaluated
  without changing actual output. Shared fundamentals, unison evidence,
  attacks, coasting, corrected identities and release remain protected.
  Three causal/scale/partition tests and all 18 existing replay tests pass;
  source contract and diff checks pass. One read-only review found no concrete
  defect. All eleven actual output fingerprints and disabled-rule controls
  match the accepted baseline. No numerical fit failed. The weakest changing
  rule removes only two false frames without losing correct frames. A stronger
  rule removes 3,170 false frames but loses 96 correct ordinary-chord frames;
  it is rejected. Keep this model offline. Results are summarized in
  `build/modal/joint-pitch-shadow-analysis.json`.
- Completed narrow follow-up: `build/modal/joint-pitch-overlap.json`, Modal app
  `ap-8IGggE1YyBcmqIxYn8ropq`; ordinary and constructed recordings first.
  Protect fundamentals that nearly overlap another pitch's harmonic using
  the measured correlation window's normalized overlap. This tests whether
  ambiguous shared energy explains the ordinary-chord regression. Thirty-five
  shadow rules include the original seven as controls. Three focused tests
  pass, including near-overlap ambiguity and block-partition invariance.
  The nine remaining sets completed in
  `build/modal/joint-pitch-overlap-protected.json`, app
  `ap-YkWr8wgzf53Zd3Ky1crAvL`. Energy floor 0.001 with overlap protection at
  0.99 removes 3,137 hypothetical false-output frames with no correct-match
  loss or increase in any scored error category across all eleven sets:
  ordinary 10, constructed 1,526, isolated string 5 948, upper unison 653.
  This is a modest 0.28% reduction in total extra outputs. Long-unison matched
  counts do not improve, so this does not meet the main stability milestone.
  Actual output fingerprints and the original seven control rules are
  unchanged. All fits are numerically valid. Aggregate results:
  `build/modal/joint-pitch-overlap-analysis.json`.
  Ordinary/physical-long results, including all 35 hypothetical rules, are
  identical at 32/512/1024 samples; see
  `build/modal/joint-pitch-overlap-invariance-analysis.json`. All Modal jobs
  are complete. This joint-fit experiment remains offline and disconnected.
- Historical timing investigation, resolved by the accepted efficiency
  checkpoint below: statistical CPU
  samples in `build/test-results/github-callback-profile.json` identify
  spectral corridor observation and repeated single/group classification as
  substantial costs. Group classification runs once per decision after
  readiness. Simply skipping it while ownership is infeasible changes its
  persistent cache and can affect later restoration; do not assume that is
  behavior-preserving. A bounded implementation needs the protected replay
  matrix and actual production deadline test before acceptance. After that,
  evaluate joint evidence for better selection, not just removing extras.
- Performance follow-up: stage timing in
  `build/test-results/callback-stage-profile.tsv` identifies assignment and
  group classification as the largest decision spikes. The unchanged test
  also fails at normal priority (p99 1,705,395 ns), so low build priority alone
  does not explain the problem.
- Rejected matrix-elimination cache: all 19 focused classifier tests passed,
  and all eleven recording fingerprints/metrics remained identical in
  `build/modal/spectral-solve-cache-protected-analysis.json`. A later timing
  run reached 355,355 ns p99 but still failed the 166,666 ns limit; host timing
  varied, so the full change cannot be attributed to the cache. The full native
  suite then crashed. Debugger evidence in
  `build/test-results/spectral-solve-cache-crash-diagnosis.log` identifies the
  four-detector continuity test: adding roughly 175 KiB per detector exceeded
  its 8 MiB stack. The optimization and its test were reverted; the failing
  existing test was preserved. Prototype patch:
  `build/test-results/spectral-solve-cache-only.patch`. Do not reintroduce this
  fixed per-detector cache without resolving its memory cost.
- Current candidate: reuse one candidate's six-value fast harmonic profile
  throughout a single string-assignment decision. Previously each physical
  string comparison recomputed it, and the posterior pass computed it again.
  The settled helper now accepts the already-computed fast similarity. There
  is no persistent audio cache and no arithmetic reordering. Only detector
  source/header behavior changes. All eleven protected recording sets retain
  identical fingerprints and all fourteen score metrics; see
  `build/modal/assignment-profile-reuse-protected-analysis.json`. Ordinary
  and physical-long results also agree at 32/512/1024 samples in
  `build/modal/assignment-profile-reuse-invariance-analysis.json`.
  The full native suite passes 436/436, including the four-detector test that
  exposed the rejected cache's memory cost. Two order-reversed, normal-priority
  timing comparisons measured candidate p99 at 119,709/118,313 ns versus
  control 129,278/122,992 ns (7.4%/3.8% reductions). Both controls and candidates
  pass under current host conditions; this does not attribute the earlier
  host-dependent timing failures to this optimization. Candidate CPU maxima
  are 161,081/175,716 ns, below 333,333 ns; allocation/thread checks pass.
  Successful timing tests now print their measured values as well as failures.
  The source-contract check mistook overload forwarding for recursion; the
  helper was given a distinct name and the check passes. The final replay's
  runtime image is byte-identical after that naming-only repair (excluding
  non-runtime symbols/debug sections and the build-id note). The final native
  suite again passes 436/436; both dedicated realtime tests pass with p99
  112,445 ns and maximum CPU 180,186 ns. Production build, Steinberg validator,
  source contract and whitespace checks pass. The bundle was installed with
  the previous version preserved at the backup path above. This is an accepted
  efficiency improvement, not completion of the tracking milestones. See
  `build/test-results/assignment-profile-reuse-*`.
- Current causal replay: `build/modal/current-unison-causal-detail.json`,
  run `current-unison-causal-detail-1793127522-a73cb366bea0`, preserves
  fingerprint `519bc0f9f4710566` and all fourteen score metrics. Triple-group
  frames: 25,219 exact, 8,253 absent, 5,906 incomplete. Selected incomplete
  frames include 4,784 collecting, 902 with valid fine evidence and 210 waiting
  for scheduled analysis. Only 54 incomplete frames already have the exact
  fine group. `reason=none` means valid evidence, not necessarily a full group.
  A collecting-state pending bridge is unreachable: pending masks are created
  only after the full three-second fit and reset with the history state.
- Joined causal replay completed:
  `build/modal/unison-causal-joins.json`, Modal app
  `ap-Gsjo6MuzeuwPSajsMLk6uv`; decoded results in
  `build/modal/unison-causal-joins-analysis.json`. All fourteen score metrics,
  fingerprint `519bc0f9f4710566`, and every previous physical-group diagnostic
  are unchanged. Eighteen offline replay tests, source contract and diff check
  pass. Production detector/VST3 files are unchanged.
  All 150 pending-exact/fine-subset/incomplete triples have one fine member
  and no production cache: existing recovery has nothing to restore. Of the
  1,112 valid/analysis-wait incomplete triples, 30 have no expected model;
  1,082 have expected-model rank 1, but none clears minimum pairwise beat
  coherence 0.20. Of these, 1,014 have a connected beat graph. The joins score
  existing frame-end state only; they do not feed labels into decisions.
- Completed/rejected weighted-detrending screen:
  `build/modal/hann-beat-shadow-screen.json`, Modal app
  `ap-u5Bmvk79JKJO9vZDFgO0VA`; nine jobs for physical-long, isolated-08 and
  isolated-05 at 32/512/1024 samples. Analysis:
  `build/modal/hann-beat-shadow-screen-analysis.json`. Actual fingerprints and
  all fourteen score metrics are unchanged; every diagnostic agrees across
  buffer sizes. No output projection or production integration was made.
  Weighted detrending newly supports 2,325 expected triple frames, but 2,321
  are already correctly tracked and only four incomplete frames benefit.
  It newly supports 612 false triples during physical pairs (240 currently
  correct pair outputs, 372 already containing extra strings), plus 1,397
  wrong-pair model evaluations. These model counts can overlap; do not describe
  their sum of 2,009 as unique false-triple frames. Reject global replacement.
  The isolated recordings produced zero feasible multi-source fits, so their
  negative-control result is not measured, not a safety pass. Real physical
  pair passages supplied the informative negative control.
  All 33,809 eligible physical-long model windows prepared successfully;
  50,878 selected labeled groups were encountered. The report states both
  denominators and all 135,236 evaluated masks.
  Two math tests, the unchanged four-detector test, and eighteen replay tests
  pass. A fixed detector-table implementation exceeded the test stack and was
  replaced by replay-owned heap memory. One large-report test fixture also
  needed heap storage; every assertion remains unchanged. One code review
  completed; its missing denominator was fixed. The full native suite passes
  438 tests, and source-contract/whitespace checks pass. No VST3 installation
  is included.
- Completed/rejected local frequency-refinement screen:
  `build/modal/frequency-refinement-shadow.json`, Modal app
  `ap-ljBdon8l1Yqm0C9vCDyyLg`; nine jobs cover physical-long, physical-four
  and synthetic-four at 32/512/1024 samples. Analysis:
  `build/modal/frequency-refinement-shadow-analysis.json`. All fourteen actual
  score metrics and fingerprints match the accepted baseline; every diagnostic
  counter agrees across partitions. Four causal math tests and the full 442
  native tests pass. Source contract and whitespace checks pass. One focused
  code review is complete. No production behavior or installation changed.
  The label-free observer compares fixed calibrated frequencies, one common
  correction and one per-component Gauss-Newton step. Training uses the oldest
  two-thirds of the admitted history; testing uses the newest third. Separate
  metrics report training-amplitude prediction and held-out amplitude-refit
  residual. The full-window production beat statistic remains separate at
  0.20. Corrections are limited to a quarter cycle over the training span,
  five cents, and (for individual motion) a quarter of nearest-source spacing.
  Bound hits disqualify the result. All arms use the same unregularized QR
  amplitude solver with conditioning rejection: the fixed control is not
  production ridge LS. Per-component motion includes a shared shift; only
  benefit beyond the common arm could support individually different drift.
  None of the 1,062 evaluated incomplete-triple frames gains qualified useful
  support. All 1,062 per-component fits and 1,046 common fits hit their bounds;
  corrected full-window beat support remains zero. Mean amplitude-refit test
  residuals are 0.041854 fixed, 0.036478 common and 0.034598 per-component, but
  mean prediction error is worse for per-component than common (4.5643 versus
  2.3021). These means use the same 1,062 valid frames in every arm. A smaller
  refit residual alone therefore does not establish recoverable strings.
  Physical-four produced 6,064 eligible model windows, but its source mask
  255 denotes ambiguous string labels, not eight known sources. Synthetic-four
  produced no eligible fine models. Exact four-string refinement quality is
  not measured; the four-source numerical test passes.
- Completed complex-history inspection: `build/modal/fine-window-capture.json`
  exports 49 low-E2 windows, sampled at least 0.5 seconds apart without using
  labels or fit outcomes to choose them. The raw JSONL captures are byte-identical
  at 32/512/1024 samples. All fourteen actual score metrics and all previous
  physical-group diagnostics remain identical. The final export-status repair
  is verified by `build/modal/fine-window-review-final-analysis.json`: 49 windows,
  cap 512, no truncation, unchanged fingerprint `519bc0f9f4710566`.
  The capture reports the assignment entering fine analysis, not the final
  frame output. Of the sampled contexts, 13 are physical pairs and 36 are
  triples; two triple contexts enter with only one assigned string. These are
  diagnostic windows, not recovered-frame counts or independent trials.
  `build/modal/fine-window-harmonics-final.json` reconstructs the first three
  harmonic correlations using the detector's exact DC blocker, carrier phase,
  40 ms smoothing and original observation times. Its fundamental matches the
  native capture to 1.323e-10 relative RMS error. Eight known-frequency/sampling
  checks pass in `build/modal/fine-window-spectrum-checks-final.json`.
  A review found and repaired silent export truncation and missing sampling
  warnings. All 49 windows pass the median-spacing guard, but only 35/29/29
  pass the conservative maximum-gap guard for harmonics 1/2/3. Those guards
  do not prove absence of out-of-band aliasing or irregular-window sidelobes.
  Both sampled incomplete-triple windows are uniformly sampled. Harmonic
  inspection shows different frequency shifts where fundamental peaks overlap;
  peaks alone do not establish source count or string identity. All prior
  spectrum values are unchanged after adding the warnings. All 443 final native
  tests, eight frequency/sampling checks, native source/build contracts, Python
  syntax and whitespace pass. One read-only code review is complete.
  This remains offline-only; no production behavior or installation changed.
- Next mechanism: fit the measured harmonics together using each feasible
  string/fret's calibrated partial detuning and harmonic profile. Allow current
  pitch evidence within the physical note range rather than treating recorded
  absolute cents as fixed truth. Fit only the older samples, measure prediction
  and amplitude-refit residual separately on the newest samples, and require
  independent cross-band support beyond the smaller mask. Keep physical pair
  passages as false-third controls and already-correct triples as preservation
  controls. Irregular sampling must retain its actual times; a denser Fourier
  grid does not improve physical resolution. No classifier or MIDI integration
  is justified yet. Preserve three seconds, the 0.20 beat gate, 0.50 retention
  floor, physical limits and zero wrong-string headroom. The targets remain
  +676 long matches and +385 exact triples, with all protected corpora preserved.
- Research context: [Klapuri 2006, section 2.5](https://archives.ismir.net/ismir2006/paper/000125.pdf)
  motivates evaluating pitch sets jointly. This experiment uses M3's existing
  complex correlations and a real-valued weighted least-squares model.
- Keep the 3-second unison gate and measured
  trim -9/Sensitivity 60/Response 75/Max Polyphony 5/Max Fret 24 baseline.
  The 98.40% milestone ratio is not product completion or tracking precision.
  Matched-label coverage and extra false notes are different measures. The
  ntfy automation is active every ten minutes and explains these separately,
  including an overall readiness assessment without inventing a completion
  percentage from unrelated test gates.

## Historical product checkpoint (superseded by the current status above)

- Active worktree: repository root, branch `main`. It integrates the current
  stereo/96 kHz staging and generic host tuner parameters with the native
  eight-voice detector, tuner telemetry, and custom VSTGUI editor. The staged
  live preset selects full polyphony by default and opens the editor
  automatically.
- The native suite passes 191/191, including the REAPER custom-to-generic-to-
  custom editor reattach regression and a real detector-driven open-to-fret-24-
  to-open calibration sweep. Its simultaneous-string regressions use
  independent cents offsets, oscillator phases, amplitudes, and harmonic
  profiles, and verify every M3 tuner assignment remains within its physical
  string's configured open-to-maximum-fret range. A calibrated same-note pair
  now remains locked to its two physical tuner lanes throughout slow beating
  at 44.1, 48, 88.2, and 96 kHz, while a single calibrated string remains one
  lane. The VST3 detector matrix now covers those four rates at 17 host buffer
  sizes from 16 through 4096 samples, including non-power-of-two sizes, and
  proves dry-audio equality plus partition-invariant absolute MIDI onset/release
  positions. A Claude read-only audit found the remaining response attack gate
  was measured in raw 64-sample ticks; it is now normalized to elapsed time and
  a regression constrains cross-rate onset spread to 2 ms. This is in-process
  host-contract evidence, not a physical-driver dropout claim. Python discovery
  passes 343/344; its sole
  failure is the workspace-hygiene assertion finding 29 pre-existing ignored
  `.vst3` build bundles beneath `.worktrees/`, which were preserved. The
  plugin-facing checks, `tools/validate_native_source.py`, and Steinberg's
  production VST3 validator pass. The canonical release module is
  `build/vst3/release/VST3/M3_Polyphonic_Audio_to_MIDI.vst3/Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI.so`,
  SHA-256 `5ec895e5800fe87c4ed2d1a362ff62a88ae33d2d895bb3c3c8ddcf68ff734379`.
- M3 mode now assigns detector voices to stable physical string lanes and
  supports per-string calibration directly from the tuner: double-click one
  meter, tune and hold its open string, slide steadily to fret 24 and back,
  then hold open briefly to finish. Each 25-fret map stores cents bias and a
  six-harmonic fingerprint, persists in VST3 project state, and influences
  both tuner correction and physical-string assignment. M3 also pins the
  NYXL0980 lane gauges thick-to-thin as `.080, .060, .044, .032, .024, .016,
  .012, .009`; the fixed gauge/tuning prior breaks coarse fingering ties, and
  the measured harmonic maps perform the final same-note identity split. The
  split now reaches generated MIDI as well as tuner telemetry: in `Per Voice`
  mode each physical lane has a distinct stable note identity and deterministic
  base-channel-plus-lane routing, so two strings sounding the same MIDI pitch
  can start and release independently. `Single` mode retains one pitch event.
  The
  installed bundle now matches the validated release at SHA-256
  `5ec895e5800fe87c4ed2d1a362ff62a88ae33d2d895bb3c3c8ddcf68ff734379`.
  The immediately preceding installed bundle is retained at
  `~/.vst3/M3_Polyphonic_Audio_to_MIDI.vst3.backup-before-rate-buffer-fix-20260924`;
  the earlier pre-unison and pre-calibration backups remain available as well.
- The disposable system-audio profile is
  `build/m3-native-live-midi-system/reaper.ini`. It is bound only to the
  built-in `Generic_1` ALC257 codec through `plughw:Generic_1,0`, with REAPER
  configured for 96 kHz and 512 samples. Direct device checks confirmed
  96 kHz/512 stereo capture; built-in playback is physically 48 kHz/256 and is
  converted by ALSA `plughw` while the plug-in graph remains 96 kHz/512.
  The external audio interface (`R24`) was not opened.
- A real disposable REAPER 7.79 launch discovered the production VST3, created
  the armed `M3 Native 8-String Guitar to MIDI` track, opened the custom editor,
  and held only `/dev/snd/pcmC2D0{c,p}`. This verifies discovery, editor
  integration, and the selected normal-audio route. It does not by itself
  prove musical tracking from a physically played guitar; that still needs a
  player-generated input pass.
- The separate V4 evidence worktree is sealed through Q46 at commit
  `ba895a28c6676116dbca81d16a4d57f104e011dd`. Q46 unifies eight captured ELF
  nodes, ten ordered dependency declarations, and ten exact SONAME matches;
  no unmatched declarations remain. That lane is evidence for future isolated
  fixture/host closure, not a substitute for the working product checks above.

## Current native M3 polyphonic VST3 + tuner checkpoint

- Worktree: `.worktrees/m3-live-editor`, branch `feat/m3-live-editor`. Commit
  `4fa2c09` contains the native polyphonic detector, truthful tuner telemetry,
  and redesigned precision editor. A focused two-file follow-up remains
  uncommitted in `native/vst3/vst3_component.cpp` and
  `native/tests/test_vst3_processing.cpp`.
- The native VST3 now performs bounded polyphonic selection for up to eight
  voices instead of disabling detection when Max Polyphony is greater than
  one. It includes per-new-voice causal evidence, deterministic release/onset
  ordering, subharmonic rejection, and M3 string/fret feasibility with
  backfilling of feasible candidates.
- The audio thread publishes a fixed-capacity, lock-free tuner snapshot to the
  editor. The editor renders a read-only eight-card Voice Stack with note,
  signed cents when valid, confidence, per-row state, configured maximum, and
  explicit no-signal/unavailable states. It never sends parameter edits or
  presents a global in-tune verdict. The editor is now 1024x808 (maximum
  2048x1616), and VSTGUI's developer-only Open UI Editor button is disabled.
- Fresh native verification is green: Debug 151/151, Release 151/151 (including
  the 96 kHz max-eight deadline gate), ThreadSanitizer 150/150, and
  AddressSanitizer plus UndefinedBehaviorSanitizer 150/150. Leak scanning alone
  was disabled because LeakSanitizer cannot operate under this sandbox's ptrace
  boundary; GCC vptr checks are disabled only for the Steinberg COM-style ABI
  representation casts, with all other ASan/UBSan checks retained.
- The broader offline build/source contract is green: 343 Python tests,
  `tools/validate_source.py`, `tools/validate_native_source.py`, and
  `git diff --check`.
- The production bundle and project validation target are green at
  `build/vst3/release/VST3/M3_Polyphonic_Audio_to_MIDI.vst3`. Current binary
  SHA-256: `5988a72d5b7783e4e178874af93261dbff1e6dbd6810e05510777dfd4ba4d094`.
- A real headless VSTGUI render was inspected at 1024x808. The editor was then
  visually redesigned as a flat precision-instrument surface: stronger brand
  and status hierarchy, compact labeled mode switches, detailed dial scales,
  restrained section rails, and eight simultaneous vertical pitch lanes with
  meaningful cent rails and segmented confidence. Settling voices do not claim
  a cent estimate. The SDK's developer editor button was also removed. The
  final render was rechecked and temporary screenshot instrumentation removed.
- The official Steinberg validator now passes the production bundle. Evidence
  is retained in
  `build/test-results/vst3-validator/production/result.json` with timestamp
  `2026-09-11T13:45:40.049+00:00` and validator return code 0.
- A guarded disposable REAPER run exposed and fixed a real host-integration
  defect: REAPER may alternate VST3 `kRealtime` and `kPrefetch` process calls
  without another `setupProcessing`, as the VST3 contract permits. The old
  exact-mode comparison rejected those blocks before dry audio and detection.
  The focused repair now accepts realtime/prefetch interchangeably while still
  refusing every offline transition without a matching setup.
- The repaired release completed an exact live E2+B2 lifecycle in disposable
  REAPER: four MIDI events (note-on 40, note-on 47, note-off 40, note-off 47),
  one on/off pair per note, and no capture overflow. Evidence is retained at
  `build/reaper-test/test-results/m3-polyphonic-host-smoke.tsv`. The normal
  REAPER profile remained byte-identical at SHA-256
  `0c9a808df5361758c7f6656ed052332cfe16004b4a9f2d476d9c319829ae0a41`.
- Actual hosted editor evidence is retained at
  `build/evidence/native-m3-host-smoke-20260911.png`. A dynamic dyad screenshot
  is optional presentation evidence only; exact host telemetry and MIDI
  lifecycle are already proven. The next substantive product gate is physical
  guitar/96 kHz audio-interface validation, which must not be inferred from the
  synthetic dyad result.

## V4 scan-isolation design reviewed — Task 0A sealed non-admissible

- Commit `8f0d1db` (`docs: define V4 scan isolation gate`) records the
  independently reviewed V4 one-row scan-isolation design, static runtime
  inventory, and TDD implementation plan. It preserves every sealed v1/v2/v3
  artifact and creates no new execution authority.
- The design places a fresh private VST3 root inside a Bubblewrap namespace,
  keeps control receipts and uncertainty markers solely in an outer
  retained-dirfd controller, and requires scope confirmation, zero REAPER PID
  census, bounded attester PRE/POST evidence, descriptor-pinned regular inputs,
  and anchored nonregular inputs before any future scanner can run.
- Commit `fac3b5e` (`feat: add V4 non-admissible protocol skeleton`) completes
  Task 0A as a deliberately non-admissible source component. It validates only
  an in-memory frame envelope/base configuration and exposes a mocked-testable
  process barrier. A pre-import AST gate proves it has no receipt writer, ACK
  reader, descriptor control, measured collector, runner, admission entrypoint,
  process-launch path, or import-time side effect. Four focused tests pass.
- Commit `940f64d` (`docs: harden V4 runtime manifest gate`) records the
  independently reviewed Task 0B block: a closure-construction method and
  explicit offline Task 0B1 authority precede source authoring; fixture
  and host manifests are separate; and any future descriptor-pinned manifest
  must refuse over-copy, FD, `RLIMIT_NOFILE`, or memory/tmpfs budgets.
- The original Task 0B0 method is
  `docs/superpowers/specs/2026-09-01-v4-task0b-closure-construction-method.md`.
  Its original review and Task 0B1 source-component/runtime-root amendment are
  independently CLEAN. The user has granted the bounded Task 0B1 author-only
  scope. The amendment records that Task 0B1 may author, but not invoke, four
  sources: the static closure
  constructor plus the receipt-schema, measured-collector, and child-adapter
  runtime modules, along with their catalog schemas and synthetic static-data
  fixtures. They are analysis roots only; no Task 0B1 file is a session or
  manifest runtime root. A separate explicit offline Task 0B2 authorization is required to
  test or invoke the constructor against sealed data; it remains data-only and
  excludes target import/execution/loading, namespace or fixture creation,
  Bubblewrap/systemd/REAPER command formation, GUI/X11/audio/network access,
  and all host actions.
- The static source closure is recorded only as an unresolved Task 0B input:
  it includes Python `ctypes`, `hashlib`, `json`, `struct`, and their extension
  / ELF candidates. It is neither fixture-complete nor compatibility-complete.
  Task 0B1 author-only source/catalog work is sealed: the four bounded source
  modules, two schema files, two synthetic fixtures, and their exact hash
  seals passed the seven-check AST/JSON-byte gate. Two independent static
  reviews are CLEAN. No Task 0B1 module was imported, compiled, or invoked,
  and no host process was launched. Any later Task 0B2 invocation must return
  `BLOCKED_UNRESOLVED(runtime_session_entrypoint_unresolved)` until a separately
  reviewed session runtime root exists. Task 0B1 never authorizes testing or
  invoking the constructor; that later step needs its own Task 0B2 authority.
- Under the recorded user `Proceed` authorization, and only after the
  demonstrated sealed-synthetic-data RED, Task 0B2 applied the one private
  normalization correction in `tools/reaper_v4_closure_constructor.py` needed
  for its own constructed synthetic record to validate. It resealed the
  Task 0B1 static constructor source hash, reran the static contract and
  Task 0B2 tests, and received independent review. All other Task 0B1 source
  expansion or correction, target import/execution/loading, fixture or
  namespace action, and host action remained forbidden.
- Task 0B2 is now sealed as an offline constructor-only result. Its first
  synthetic-vector invocation produced the expected RED: private nested
  immutable snapshots reached `ClosureRecord` as non-caller built-in
  containers. The sole source correction normalizes that private record before
  its existing deep freeze; it is sealed at constructor SHA-256
  `2f8b1f02f5a730c70e38b6ebe06a99ec8abbd3c70a05851f66d6be6c5e2a97f7`.
  `ionice -c 3 nice -n 10 python3 -B -m unittest
  tests.test_reaper_v4_task0b2_constructor -v` passed one test, and the
  seven-check Task 0B1 static contract also passed. Independent review is
  CLEAN. The sole output is
  `BLOCKED_UNRESOLVED(runtime_session_entrypoint_unresolved)`, canonical
  digest `0fdb65aa2467554f85fb21e2e570850921cb1615bfe56ebb4b1a0b5d5fb185bf`.
  It uses only sealed synthetic placeholder identities; it does not bind a
  real Task 0A/Task 0B1 graph, produce a fixture manifest, or authorize a host
  action.
- Task 0B3 is now independently reviewed as a design-only session-owner
  checkpoint at
  `docs/superpowers/specs/2026-09-01-v4-task0b3-session-owner-design.md`.
  It assigns exactly one later runtime root for the PRE/ACK/child/POST state
  machine, binds the complete session policy and selected direct input hashes
  through immutable Task 0A receipt identity, keeps durable control artifacts
  with the outer controller, and requires provenance-backed/certificate-bound
  PRE assertions, bounded raw transport, and PRE-only failure for uncertainty.
  It also names separate source, receipt, measurement, runner, state-machine,
  graph-construction, closure, fixture, and host gates. This is not source,
  component, fixture, namespace, Bubblewrap/systemd/REAPER, or host authority.
- Task 0B3a is sealed as a non-admissible session-root source checkpoint.
  Commits `81df235` and `91c86c5` establish the reviewed fail-closed contract;
  `a1808cb` reduces the preliminary pseudo-runtime to an immediate-fail
  skeleton; and `d257b5d` hardens its pre-import AST/hash guard. The sealed
  source SHA-256 is
  `f3867a75817670916f2a450f7d7024f5c1bf1932d97fb65d34c4ca251a9f5c60`.
  `ionice -c 3 nice -n 10 python3 -B -m unittest
  tests.test_reaper_v4_task0b3a_static_contract -v` passed one static-only
  test, and the final independent source re-review is CLEAN. That historical
  guard is retired now that the successor B4b static contract pins the
  executable implementation. Neither public
  function can progress past its immediate error; no target or dependency was
  imported, compiled, or invoked, and no fixture, namespace, Bubblewrap,
  systemd, REAPER, X11, audio, or host action occurred. It preserves the
  future single-root identity but remains
  `BLOCKED_UNRESOLVED(runtime_session_entrypoint_unresolved)` for its original
  historical scope. The subsequent B4b implementation replaces that skeleton
  under its own verified static contract.
- Task 0B3b is sealed as a pure in-memory receipt gate. Its 12 adversarial
  tests exercise the real receipt/protocol validators against the synthetic
  PRE/ACK/POST vector: valid immutable snapshots; exact ACK; independently
  valid identity and shared-attestation mismatches; required containment facts;
  row, clock, PID, and return-code boundaries; malformed text; cycles; and
  container subclasses. The sealed seven-check Task 0B1 source contract also
  remains green, and independent review is CLEAN. No production source changed
  and no session, raw stream, namespace, Bubblewrap, systemd, REAPER, X11,
  audio, or host action occurred. This is not evidence of ACK EOF, raw frame
  order, or session behavior. The next safe gate is separately authorized Task
  0B3c measurement validation; full session behavior remains Task 0B4.
- Task 0B3c is sealed as a temporary-directory/descriptor-only measurement
  gate. Its synthetic-only RED exposed collector validation holes; the narrow
  production corrective amendment changed only `tools/reaper_v4_measurements.py` to take
  an exact-plan local snapshot before validation, reject non-canonical strings,
  duplicates, and unhashable values before `os.open`, normalize root
  `OverflowError` and close failures to `MeasurementError`, and require
  `MEASUREMENT_KEYS == ("mode", "size")`. The sealed collector source SHA-256
  is `27fa32e618a1a1461f3ec50820e7ad8717aa0747f1a6c7e475badefa0b4f7a22`.
  The combined static contract and B3c suite passed 20 tests, and independent
  review is CLEAN. This proves neither ACK EOF, raw-frame order, nor session
  behavior; it created no session or namespace and performed no Bubblewrap,
  systemd, REAPER, X11, audio, network, or host action. The next safe gate is
  separately authorized Task 0B3d for the child adapter only; full session
  behavior remains Task 0B4.
- Task 0B3d is sealed as a direct-child adapter gate. Its mock REDs exposed
  post-bind cleanup, cleanup-slot accounting, and interruption-order defects;
  the narrow reviewed correction keeps the single launch inside its
  bound-process recovery boundary, reserves at most two cleanup slots before
  `kill()`, keeps a bounded wait after each entered-slot kill error, and
  preserves the first non-`Exception` interruption, and escalates a cleanup
  non-`Exception` over an ordinary original adapter error. The sealed runner
  SHA-256 is `a9cecba05537a349355fc204d2a8343a51caf6fabb7ab5d184ef341270f5a946`.
  Seven static checks plus twelve B3d tests passed (19 total), including three
  isolated temporary-directory sentinel invocations. Each child was direct and
  non-forking with `-I -S -B -c`; no session, raw stream,
  namespace, Bubblewrap, systemd, REAPER, X11, audio, network, host scan, or
  descendant-containment claim occurred. Pre-bind and unconfirmed cleanup
  paths remain outer-session/scope uncertainty. Task 0B4 session
  implementation requires separate scoped authority.
- Task 0B4a is sealed as a documentation plus intentional-RED checkpoint.
  Pre-implementation review corrected an unsafe combined gate before any
  session code changed: frozen Task 0B1 receipt snapshots cannot be passed
  directly to the sealed Task 0A encoder, and a real namespace controlled
  fixture needs a parent scope/harness the session root does not own. The
  design now splits the work into Task 0B4a, Task 0B4b-pure (bounded
  in-memory compatibility helpers), Task 0B4b-state-contract, separate later
  admission/evidence/bootstrap-transport/state gates, Task 0B4c-design, and
  Task 0B4c-execution (a later separately authorized outer-harness controlled
  fixture). The raw-byte
  skeleton pin is
  `f3867a75817670916f2a450f7d7024f5c1bf1932d97fb65d34c4ca251a9f5c60`;
  its source-only test reports one normal pass and two intentionally retained
  expected failures after their RED was recorded. Two independent reviews are
  CLEAN.
- Task 0B4b-pure is sealed as the narrow compatibility-helper increment.
  It retired the B4a expected-failure guard, added an exact pre-import AST
  contract and five in-memory behavior tests, and changed only
  `tools/reaper_v4_session.py` as production source. Its source SHA-256 is
  `9aa503dc77f37ace46202a35797925e784e9e302b866d3c81d880897e7a86c99`
  (the historical B4b-pure source identity before the later admission gate).
  The immutable Task 0B1 static gate, B4b-pure pre-import contract, and
  helper suite passed 13 checks; two independent reviews are CLEAN. The
  session still has immediate-failure public entrypoints and no raw transport,
  configuration-path/descriptor I/O, barrier, measurement, child, fixture,
  namespace, Bubblewrap, systemd, REAPER, X11, audio, network, or host action.
  It proves no session admission, ACK order, receipt emission, or host
  compatibility. Any state-machine source or execution now needs a fresh named
  authority and reviewed contract; Task 0B4c remains a separate outer-harness
  gate.
- Task 0B4b-admission-pure is sealed as the bounded in-memory SessionConfig
  relation gate. It replaces the B4b-pure source contract while preserving its
  helper regressions, removes the inert child-runner/measurement imports, and
  adds a validator-owned snapshot boundary plus closed Task 0B3 §3 relation
  checks. The sealed source SHA-256 is
  `5bb71ab032b13b59170dd8034528b7b0e990751fd0d0b5b59da6e711a9ce1c11`.
  Eighteen checks passed: the immutable Task 0B1 static gate, the new
  pre-import admission source contract, five B4b-pure regressions, and five
  synthetic admission tests. Three independent reviews are CLEAN after
  test-first repairs for forged-object normalization, lexical environment/X11
  bindings, screen syntax, scan-root mount closure, static capability edges,
  and bounded snapshot walkers. This gate did not open a path, establish a
  barrier, read/write a frame, launch a child, create a fixture/namespace, or
  run REAPER, audio, X11, network, or host work. Public session entrypoints
  remain immediate-failure stubs. Task 0B4b-bootstrap-transport is next.
- Task 0B4b-evidence is sealed as the bounded supplied-observation and
  descriptor-retention gate. It replaced the admission static contract while
  preserving B4b-pure/admission regressions, and added cwd/environment,
  measurement, scan/private-home, X11, FD/mount, certificate, retained-recheck,
  and one-shot-release helpers. Its registry binds every successful baseline to
  its original descriptor tuple, refusing forged or mutated values before they
  can close a descriptor. The sealed source SHA-256 is
  `6049ec3096cf9a2fc50678884180fe4e0ef6072032418931f0d48afa14f83a1f`.
  Thirty checks passed across the immutable Task 0B1 static, evidence static,
  B4b-pure, admission, and temporary-resource evidence suites; three
  independent reviews are CLEAN and `git diff --check` passes. Only temporary
  controlled resources/supplied descriptors were used. No fixed `/run` path,
  raw stream, barrier, child, namespace, launcher, REAPER, audio, network, or
  host scan ran; public entrypoints remain fail closed. The next gate is
  Task 0B4b-bootstrap-transport.
- Task 0B4b-bootstrap-transport is locally implemented and verified, but is
  not yet independently reviewed or sealed. Its implementation checkpoint is
  commit `2ce8abc`; it adds only private fixed-literal
  sidecar/config reading and fd-0/fd-1/fd-2 helpers; the current source
  SHA-256 is
  `5aaeef6dcf84ac988fa537e63cf7016fde03c46fcbc755d71886133186687e38`.
  Its static RED recorded the absent imports/helpers, its five behavior REDs
  recorded the fail-closed stubs, and the preserved suite now passes 46
  checks. The added `POLLHUP` regression accepts it only as second-read EOF
  readiness; the read itself must still prove EOF. The raw fd-0/fd-1 waiter
  now sets `O_NONBLOCK` before every bounded poll and refuses a flags failure
  before any raw operation. The tests use syscall/poll doubles and canonical
  synthetic config bytes only. No real `/run`, child,
  state machine, namespace, REAPER, audio,
  or host action has occurred under this checkpoint.
- Task 0B4b-state is now locally implemented and verified as a mock-only
  composition checkpoint in `2ce8abc`, but remains unsealed pending independent review.
  It replaces the predecessor static contract, imports only the sealed child
  adapter, and gives the public root its literal-path loader plus one local
  PRE -> ACK+EOF -> child -> POST transition. At that checkpoint, the runtime
  observation and payload-assembly edges were exact fail-closed stubs, so no
  runtime invocation could self-assert receipt facts. Its checkpoint source
  SHA-256 is
  `5aaeef6dcf84ac988fa537e63cf7016fde03c46fcbc755d71886133186687e38`.
  The preserved suite had 46 checks: mock-only success, failure, outcome,
  post-finalization, interruption, and one-shot terminal-release vectors prove local ordering only. No
  real `/run` read, barrier, measurement, child, fixture, namespace, REAPER,
  audio, X11, network, or host action occurred.
- Task 0B4b-payload-assembly is locally verified, pending independent source
  review. It replaces only the PRE/POST payload stubs with
  `_shared_receipt_attestation`, which re-admits the supplied configuration,
  verifies a registry-owned controlled evidence baseline against its retained
  environment, measurement, scan, private-home, X11, FD/mount, and certificate
  records, and returns fresh ordinary receipt values. PRE and POST now validate
  with the sealed Task 0B1 receipt grammar; POST adds only
  `scan_root_unchanged` and the existing finalizer retains
  `validate_post -> validate_exchange -> encode` ordering. The current source
  SHA-256 is
  `41f8d1fbaebb69c4aad2de50c16ff2fd48ad68b1d55e4fadf1e428889893d937`.
  The test-first PRE vector captured the original stub refusal, then the full
  V4 source-only/controlled-descriptor suite passed 51 checks, including five
  payload vectors. No namespace, real `/run` access, barrier, child process,
  REAPER, audio, X11 client traffic, network, fixture, or host scan ran.
- Task 0B4b-runtime-observation is locally verified, pending source review.
  It replaces the three runtime-evidence stubs with a bounded five-descriptor
  acquisition path, a 64-FD census, a bounded mountinfo projection, retained
  evidence recheck, and one-shot release delegation. The current session
  source SHA-256 is
  6a2bbdfee29c26253ffb4a8f05c62feeab207ea21942aa40368a9ac9e8fcdc1c.
  The complete controlled V4 suite passed 57 checks, including six
  temporary-resource/syscall-double vectors for descriptor handoff, census
  closure, mount projection, partial-open cleanup, invalid-admission
  non-observation, and mountinfo EOF closure. No real /run read, namespace,
  Bubblewrap, child process, REAPER, audio, X11 client traffic, network, or
  host scan ran. A reviewed closure/fixture-manifest and a later controlled
  fixture remain required before any actual session execution.
- Task 0B5 source closure and parent-harness implementation is locally
  verified and committed as `feat: pin V4 observed runtime catalog`.
  `tools/reaper_v4_session_entry.py` establishes the one source root;
  `tools/reaper_v4_fixture_manifest.py` produces a deterministic seven-source,
  eight-edge graph and rejects bootstrap-config self-reference; and
  `tools/reaper_v4_fixture_harness.py` performs the parent-side
  PRE -> ACK+EOF -> POST exchange against an isolated non-REAPER Python
  sentinel. The full V4 discovery suite passed 113 checks. The persisted
  `tests/fixtures/reaper_v4_closure/observed-runtime-catalog.json` pins 77
  observed interpreter/extension/ELF regular inputs (9,499,630 bytes) under
  canonical catalog SHA-256
  `fc2e615cdcfc57468d8227074ba260f6c35dc56e9d2f722a53986270d00e90a0`.
  The public fixture replaces its seven contributor-local workspace prefixes
  with `/REDACTED` while retaining their relative tool paths and file hashes.
  Rechecking that catalog plus the seven source files builds only an 84-entry,
  9,647,488-byte `DECLARED_RUNTIME_MANIFEST` in memory; it remains explicitly
  `UNRESOLVED` for builtin/frozen modules, conditional imports, interpreter
  startup, native effects, and virtual resources. The local Bubblewrap probe
  failed before executing a child because this Codex execution environment
  refuses new namespaces even though the host user-namespace sysctls are
  enabled; `strace` is also denied ptrace. No
  fallback, actual fixture, session invocation, REAPER, audio, X11-client,
  network, or host scan was attempted. Resume with the individually pinned
  runtime catalog and complete fixture-runtime-manifest, then use a host that
  permits the reviewed Bubblewrap scope for actual fixture execution.
- Task 0B4b-state-contract is sealed as a documentation-only prerequisite
  checkpoint
  under the user's fresh `Proceed`. It resolves the name boundary that keeps
  Task 0B4c for the later outer-harness fixture, and records why B4b-pure's
  non-admitting parser, descriptor-only collector, and direct POST encoder
  cannot be used as a state-machine admission path. It reserves four future
  ordered the four source gates: `0B4b-admission-pure` for complete in-memory
  SessionConfig relation validation, `0B4b-evidence` for bounded private
  provenance/baseline helper implementation, `0B4b-bootstrap-transport` for
  fixed-loader/raw-helper implementation against doubles, and `0B4b-state` for
  mock-only local composition. Admission and evidence are sealed; bootstrap
  transport and the mock-only state source are now locally verified but pending
  independent review. This documentation checkpoint itself changed no source or
  test and performs no target import/execution, configuration/path/descriptor
  I/O, raw transport, barrier, measurement, child, fixture, namespace,
  Bubblewrap, systemd, REAPER, X11, audio, network, or host action. A
  source-free `0B4c-design` must define the bounded fixture before Task 0B5,
  successor closure review, and bounded fixture-runtime-manifest review;
  `0B4c-execution` stays later and must name one independently reviewed
  non-REAPER scope mechanism rather than silently choosing a launcher. Three
  independent documentation reviews are CLEAN and `git diff --check` passes;
  no source/test/runtime authority was consumed by this checkpoint.
- A source-free **draft** of the Task 0B4c controlled-fixture definition now
  lives at
  `docs/superpowers/specs/2026-09-05-v4-task0b4c-controlled-fixture-design.md`.
  It fixes the intended non-REAPER data plane, stream topology, parent
  ownership, and resource bounds without advancing B4c-design: bootstrap/state
  review, runtime evidence/payload source review, Task 0B5 closure, and
  fixture-manifest review remain required before any fixture execution.
- The future manifests are deliberately distinct. A `fixture-runtime-manifest`
  can permit only a bounded non-REAPER fixture; a
  `reaper-host-runtime-manifest` must reference it and resolve every REAPER,
  libSwell, GUI, X11, Python, and dynamic-load input before compatibility or a
  host request is possible. Both require copy-byte, FD, `RLIMIT_NOFILE`, and
  memory/tmpfs preflight refusal budgets.
- Therefore no V4 REAPER/Bubblewrap/systemd command may be formed or executed.
  Tasks 0B3a, 0B3b, 0B3c, and 0B3d add only sealed non-admissible, receipt,
  synthetic descriptor, and direct-child-adapter evidence respectively. Task
  0B4a adds the sealed source-contract checkpoint, and Task 0B4b-pure adds
  only bounded in-memory compatibility helpers with fail-closed public
  entrypoints. Task 0B4b-admission-pure adds only locally snapshotted,
  self-consistent configuration admission and still exposes no runnable session
  path. Task 0B4b-evidence adds only temporary/supplied-observation and
  descriptor-retention helper behavior, not executable session admission.
  Task 0B4b-state-contract adds documentation-only prerequisite ordering, not
  an executable state machine. Task 0B1 remains preservation-only. Its static
  test may be rerun without importing target modules; bootstrap-transport,
  state-machine, fixture, namespace, or external action follows in its own
  scoped implementation gate.
- Any later V4 host execution needs the compatibility-complete
  `reaper-host-runtime-manifest`,
  implementation and independent review of the isolation controls, fresh roots
  and preflight, and new explicit user authority. It cannot consume prior v2 or
  v3 authority or unblock Task 16.

## Current post-v3 offline correction and containment boundary

- Read-only forensic work established the direct cause of the sealed v3
  timeout: its staged capability ReaScript allowed only the old
  `/build/reaper-test/test-results` suffix, while v3 used
  `/build/reaper-test-observer-diagnostic/test-results`. Its assertion ran
  before any phase/telemetry write or disposable-instance close, which explains
  the empty evidence and fixed-cap `124` without diagnosing the project,
  observer, production adapter, or MIDI path.
- The smallest TDD correction now accepts only the two fixed disposable
  profile suffixes and still rejects a live-profile-shaped path and a near
  miss. The Lua regression proves both allowed profiles reach setup. It changes
  only future staging source; the sealed v3 copy, evidence, marker, and no-retry
  boundary remain untouched.
- A separate read-only review found that REAPER appended `~/.vst3` to the
  sealed profile's `vstpath` and cached an external `ATONE.vst3` bundle. This
  is a scan-containment breach, not a demonstrated timeout cause. Preserve the
  profile as evidence; do not mask or rewrite it. A future host design must add
  pre-launch containment plus post-exit profile/cache validation before any new
  host authority is sought.
- The current safe work is offline fixture-driven scan-containment validation
  and documentation only. Do not retry v1/v2/v3, launch a tail, start Task 16,
  alter the product adapter, or open REAPER without a fresh, separately
  authorized host gate.

## Task 15 v3 one-shot observer diagnostic sealed infrastructure-invalid — Task 16 blocked

- The user's `continue` freshly authorized exactly the presented twenty-row v2
  Gate C5 matrix once: 44.1, 48, 88.2, and 96 kHz at blocks 32, 64, 128, 256,
  and 512, serially in disposable background REAPER instances on workspace 5,
  with permanent stop on the first non-pass and no retry.
- All non-launching gates passed before the host run: guarded native debug and
  sanitizer tests, the exact release probe build, official probe validation,
  the focused host/recovery suite, all 170 repository tests, the native source
  validator, and an exact twenty-row dry plan. Immediately before launch,
  about 25.7 GiB was available, temperature was 48 C, and memory-full and
  I/O-full PSI were zero; workspace 1 remained active and no REAPER process or
  window existed.
- The first runner invocation launched no REAPER process. It conservatively
  recovered stale v1 staging into
  `build/test-results/native-vst3-probe-v2/batches/44100-32.invalid-20260831T091010Z-recovered`.
  Its marker has the legacy v1 input hashes and no v2 namespace; each of its
  five staged result files is byte-identical to the corresponding sealed v1
  file. It has no `metadata.json` or `pressure.json` because staging had not
  reached sealing. It is not a v2 attempt and remains preserved.
- TDD commit `a551021` (`fix: namespace VST3 recovery evidence`) adds the v2
  namespace to new attempt markers and ignores only a well-formed recovered
  marker proven to be foreign legacy evidence. Missing, malformed, non-object,
  symlinked, current-v2, or ordinary invalid evidence still blocks forever.
  This offline runner fix consumed none of the twenty launch authority and
  changed no production detector, adapter, probe, timeout, or pressure guard.
- The actual v2 execution launched only 44.1 kHz/block 32. REAPER exited
  normally with guard return code zero; `phase.log` ends in `suite-fail`; and
  the runner classified the row `fail` because the sole assertion label is
  `observer-magic`. The immutable row is
  `build/test-results/native-vst3-probe-v2/batches/44100-32.invalid-20260831T092345Z`,
  with seven-file manifest digest
  `6d47f22e360e202a3c4cd905302ed0e8c8bfe587909e29dc58cd593872776e62`.
- The observer failed closed before parameter, state, audio, MIDI, lifecycle,
  or reporter assertions. The empty event/state bodies and `-1` diagnostics
  are therefore deliberate non-evidence. This result proves no production
  detector or native-adapter defect and authorizes no such edit.
- The row began/ended at 26269.34/26201.62 MiB available, load 0.48/0.84,
  48/50 C, and zero memory-full/I/O-full PSI. Cleanup left zero REAPER
  processes/windows and left workspace 1 active. There was no crash, timeout, or
  meaningful system-pressure spike.
- Per the gate, nineteen rows were not launched and no retry occurred. The v1
  sealed manifest remains unchanged at
  `98c48c74eeea2ef8bc962689d210bfc6154cf9069fa7c4dee34ed072a4fa0958`.
  Check-only adjudication now rejects the sealed v2 invalid row and the missing
  tail, as required.
- A subsequent read-only observer diagnosis made no REAPER launch, retry, or
  source/configuration edit. The staged cache proves that REAPER discovered and
  inserted the exact capability-source JSFX. The ReaScript and all three JSFX
  observers use the same `m3_poly_midi_tests_v1` segment; their indices are
  valid; and no other repository effect writes cells 2205-2209. No static
  naming, address-range, insertion-call, or hexadecimal-literal defect is
  supported by the sources or REAPER's documented APIs.
- The v2 row records only `observer-magic`, not the raw magic, generation,
  ready, heartbeat, acknowledgement, attachment state, source-FX parameter
  state, or JSFX compile state. It therefore proves only that the first live
  observer poll's magic/generation/ready/heartbeat tuple was not all zero while
  magic differed from `0x4D335633`; the raw magic itself could have been zero
  or another value. The row cannot distinguish the earlier cell-address
  pattern from a boot-order, attachment, track-scheduling, compilation, or
  other pre-product host boundary.
- The v1 row proves that the same source later processed real 44.1 kHz,
  32-sample blocks while other observer values followed the exact cell-address
  pattern. The established synthetic harness instead places a short MIDI item
  on its track and waits for a coherent ready/heartbeat tuple until its
  deadline. Those differences make a startup race, attachment transition, or
  empty-track scheduling boundary plausible, but none is proven by the
  immutable v2 evidence.
- The user approved the diagnostic-only non-launching amendment. Commit
  `176923e` (`test: preserve VST3 observer diagnostics`) now records all nine
  raw observer fields after clear, after FX creation, at the first observer
  poll, and at the terminal verdict. It also records both same-name gmem attach
  returns and the source FX's exact name, enabled/offline state, parameter
  count, and rate/block sliders after setup and at the terminal verdict.
- The amendment changes no production source or adapter, dependency, source
  scheduling, timeout, boot verdict, guard, runner, or evidence namespace. Its
  focused Lua tests cover zero, exact address-value, wrong-magic, and
  valid-ready snapshots plus the complete failed-boot diagnostic record.
  Fresh low-priority verification passes 172 repository tests and both source
  validators. The v1/v2 evidence digests remain byte-identical, no REAPER
  process was launched or left running, and the final passive snapshot was
  26079.05 MiB available, load 1.35, 44 C, and zero full memory/I/O pressure.
- The user clarified that 96 kHz with host blocks 256-512 is the normal use
  case. Any later capability, latency, and correctness report must call out
  96 kHz/256 and 96 kHz/512 as the primary real-world rows while retaining the
  mandatory full 20-row matrix and the independent 96 kHz false-note gate.
- Task 16 and Tasks 17-24 remain blocked. The user has now authorized exactly
  one fresh diagnostic execution. Commit `0a216d4` (`feat: isolate one-shot
  VST3 observer diagnostic`) introduces a fixed `--observer-diagnostic-once`
  path for only 44.1 kHz/block 32 under the new
  `native-vst3-probe-v3-observer-diagnostic` namespace. It cannot invoke the
  v2 matrix, check mode, or tail and restores all v2 paths after use.
- The v3 staging root, project root, and evidence root must each be absent and
  nonsymlinked before any write. Any pre-existing, malformed, pending, or
  interrupted v3 artifact is a permanent refusal; it is never recovered,
  overwritten, adopted, or retried. This preserves the old v2 staging residual
  and both immutable v1/v2 rows exactly.
- The guarded launcher allows the v3 profile only with the exact build-local
  VST3, paired v3 completion sentinel, GUI workspace 5, 45-second limit, and
  fixed project/script arguments. It rejects CLAP/plain REAPER use, aliases,
  cross-paired paths, altered workspace/timeout, and any other arguments.
- Offline verification after the boundary amendment passes all 178 repository
  tests plus both source validators; `git diff --check` is clean. No REAPER
  launch has occurred from v3 and all three v3 roots are absent at this
  checkpoint. The next action is the single guarded row, after a fresh host and
  workspace preflight; stop immediately on any guard refusal or non-pass.
- The authorized v3 row then ran once at 44.1 kHz/block 32. The guard returned
  `124` at its fixed 45-second cap before any `phase.log`, `capability.tsv`,
  `events.tsv`, `state.tsv`, or `probe-vst3.tsv` existed. The runner sealed
  `build/test-results/native-vst3-probe-v3-observer-diagnostic/batches/44100-32.invalid-20260831T113425Z`
  as `infrastructure-invalid`; its two-file metadata/pressure manifest digest
  is `4c6fe0dde5c96cacd8d3f5cd7f1f6fe77a7b66fbde40de78067b6c0166ed921a`.
- The isolated staging marker remains in place by design and makes v3
  permanently non-runnable. REAPER's disposable VST cache did discover the
  exact probe bundle, but its profile records a `faultyproject` and no script
  telemetry. This is an incomplete host-startup boundary, not evidence of an
  observer, production detector, adapter, or MIDI defect.
- Pressure stayed safe: available memory was 25773.08/25772.81 MiB before/after,
  load was 0.71/1.59, temperature 46/47 C, and both full-pressure PSI values
  were zero. Post-run checks found zero REAPER processes/windows and workspace
  1 active. The immutable v1/v2 digests remain exactly
  `98c48c74eeea2ef8bc962689d210bfc6154cf9069fa7c4dee34ed072a4fa0958`
  and `6d47f22e360e202a3c4cd905302ed0e8c8bfe587909e29dc58cd593872776e62`.
- The one-row authorization is consumed. Do not delete, alter, recover, retry,
  or relaunch v3; do not launch the v2 matrix or tail. Task 16 remains blocked.
  Any later corrective work begins with read-only/offline diagnosis and needs a
  new, separately authorized execution design before another host launch.

- On 2026-08-29, immediately after the sealed Task 2 checkpoint stopped at
  Gate D2, the user explicitly said `Authorize all`. This authorizes every
  remaining named work in the approved 24-task native VST3 plan, including its
  bounded network, build, disposable-host, benchmark, clean-DI, and final
  installation phases. The plan's later Task 15 Gate C5 is an explicit
  exception: its text requires a fresh authorization for exactly twenty
  guarded disposable REAPER launches and says prior general authorization does
  not open that gate.
- This authority does not weaken any pressure guard, stop-on-first-failure
  rule, immutable-evidence boundary, or acceptance threshold. It does not add
  unrelated package changes, REAPER MCP installation, live-project mutation,
  CLAP retries, or work outside the approved plan. Gate D8 still requires
  suitable input material before it can execute, and I9 remains conditional on
  every prerequisite release gate being green.
- Fresh post-authorization baseline verification passed 44 native tests and
  125 Python tests at the unchanged Task 2 checkpoint. No REAPER process was
  present; the tests ran serially at low priority after an unrelated
  audio-interface test process completed and the ACPI temperature fell.
- Task 3 is sealed at commit `9851237` (`build: vendor pinned VST3 SDK
  3.8.1`). The official root tag and all four root gitlinks/submodule HEADs
  match the approved revisions exactly. The retained 24 MiB source-only tree
  contains 1,003 manifest-covered files under only `base`, `cmake`,
  `pluginterfaces`, and `public.sdk`, with no `.git`, root `doc`, `tutorials`,
  or `vstgui4` content.
- `third_party/vst3sdk/SHA256SUMS` has SHA-256
  `4d5b8c240b842a85b39b97ccc8b69e3bb7ed6b000709e62c07a3e41c855063f0`;
  all 1,003 entries pass offline verification. The SDK contract suite passes
  11/11 and the native source validator passes. `.gitattributes` preserves the
  byte-exact upstream whitespace and intentional short Setext heading while
  keeping project-authored files under the normal Git whitespace check.
- Retrieval ran once into ignored `build/vendor/vst3sdk-src` under low CPU and
  idle I/O priority. No automatic retry or alternate SDK was used. The final
  Task 3 snapshot had about 32 GiB available memory, zero swap/full pressure,
  45 C temperature, no REAPER process, no VST3 `.cpp`, and no bundle or
  persistent plug-in copy.
- Task 4 is sealed at commit `282ba18` (`build: add guarded VST3 CMake
  foundation`). The authoritative source graph is now explicit CMake 3.25+
  with C++17, strict warnings, disabled exceptions/RTTI, hidden symbols,
  RELRO/NOW/no-undefined, reproducible prefix/build-ID flags, VSTGUI and SDK
  examples disabled, and no download or source-glob construct. The official
  validator and module-info utility are excluded from the default build.
- `native/Makefile` is now only a serial wrapper. Every non-clean build/test
  command passes through `tools/run_guarded_native_build.py`, which refuses at
  the approved memory/load/temperature/PSI thresholds; rejects package,
  network, recursive, parallel, and repository-escape commands; and applies a
  one-CPU quota, 1536/2048 MiB memory high/max, 256 MiB swap max, 128-task
  limit, nice 15, idle I/O priority, wall timeout, and atomic before/after JSON.
- Fresh committed-state verification passes the same 44 native tests in both
  debug and ASan/UBSan builds, the focused VST3/guard suite 20/20, all 133
  Python tests, the native source validator, and Git whitespace checks. The
  excluded `m3_clap_history` CMake target also links as a build-local x86-64
  ELF with the expected `clap_entry`; no `.vst3` bundle exists. The final guard
  snapshot recorded 32398 MiB available, load 0.87, 38 C, and zero memory-full
  and I/O-full PSI.
- Task 5 is sealed at commit `c85d9ab` (`refactor: extract format-neutral
  parameter contract`). One host-free constexpr table now owns all sixteen
  IDs, ranges, defaults, increments, update classes, persistence/list/read-only
  metadata, and exact VST3 step counts. It also owns finite canonicalization,
  plain/normalized conversion, config application, and bounded text conversion.
- CLAP flag/type mapping is isolated in `clap_parameter_bridge`; the shared
  header/source contain no CLAP include and the compiled neutral object has no
  CLAP or Steinberg symbol. The exact state image remains compatible. Debug and
  ASan/UBSan runs each pass 48 tests, all 133 Python tests pass, and the final
  guard snapshot recorded 31996 MiB available, load 1.65, 57 C, and zero
  memory-full and I/O-full PSI.
- Task 6 is sealed at commit `42859f7` (`refactor: separate state image from
  host streams`). The exact 184-byte image, explicit little-endian encoding,
  IEEE CRC-32, validation, and atomic decode now live in the host-free
  `m3/state_image` module. The default image SHA-256 is
  `f29e4ef09aaf4a5bfd4719efbe96d4370a31da4be404510329e2c27fee21a475`.
- CLAP partial stream progress and failure handling now live only in
  `clap_state_stream`; neutral roots contain no `clap_istream`,
  `clap_ostream`, or `IBStream` reference. Every truncation plus trailing,
  schema, CRC, ordered-ID, duplicate/missing/unknown-ID, non-finite,
  canonicalization, and atomic-publication case is covered. Debug and
  ASan/UBSan runs each pass 51 tests, all 133 Python tests and the source
  validator pass, and the final guard snapshot recorded 32091 MiB available,
  load 1.79, 63 C, and zero memory-full and I/O-full PSI.
- Task 7 is sealed at commit `5c77caf` (`refactor: extract generated-note
  delivery ledger`). The host-free ledger owns activation-sized transition
  storage, exact `ceil(max_frames/64)*16+8` capacity, off-before-on ordering,
  fixed active/pending pitch bitsets, exhaustive individual note-off cleanup,
  sink rejection inhibition, and explicit quiet-call recovery.
- The historical `MidiPipeline` now delegates generated-note state and output
  failure decisions to that ledger while retaining CLAP raw-event merge and
  CC123/CC120 cleanup locally. Its existing passthrough, every-push-failure,
  Panic/reset, dry-audio, and no-heap tests remain green. Debug and ASan/UBSan
  runs each pass 59 tests; all 133 Python tests, the source validator, and the
  excluded historical CLAP target pass. Neutral source and the compiled ledger
  object contain no CLAP or Steinberg dependency. The final snapshots recorded
  about 31692 MiB available, load 2.02, 68 C, and zero full memory/I/O PSI.
- Task 8 is sealed at commit `d757877` (`feat: add minimal VST3 lifecycle and
  bus adapter`). The build-local probe now exposes exactly one
  non-distributable combined `SingleComponentEffect` class under the locked
  probe identity, with one default-active stereo input/output, no event input,
  one default-active sixteen-channel event output, no editor, and zero declared
  latency or tail.
- The component accepts only paired stereo layouts, finite positive host rates,
  blocks through 16384 samples, and float32/float64 processing. Its in-place and
  out-of-place dry pass/mute paths are bit-exact for finite input; NaN/Inf and
  null/shared/unsupported layouts fail closed while zeroing safely addressable
  output. Repeated processing, invalid-layout handling, and processing-state
  transitions perform no allocation after activation.
- The debug probe is an x86-64 Linux VST3 bundle under ignored `build/` with
  SHA-256 `ecff02d3b0a2ecea556d22a1a5ec15ba5ba00ea61769d6fc1d8e85d48ba747b5`.
  Dynamic symbols include `GetPluginFactory`, `ModuleEntry`, and `ModuleExit`;
  compiled identity storage contains the probe FUID and neither production nor
  benchmark FUID. Its source graph contains only the three neutral core files,
  the two VST3 adapter files, and Steinberg's official combined-component and
  Linux-entry sources—no CLAP source or header.
- Debug and ASan/UBSan runs each pass 66 tests; all 134 Python tests, the
  native source validator, Git whitespace checks, and the excluded historical
  CLAP target pass. The final guarded sanitizer snapshot recorded about 32.2
  GiB available, load 1.07, 41 C, and zero memory-full and I/O-full PSI. No
  REAPER process was launched, and no persistent plug-in copy, live project,
  or hardware input was touched.
- Task 9 is sealed at commit `02ba96f` (`feat: add VST3 parameters and exact
  state`). The combined component now registers the sixteen generic VST3
  parameters directly from the neutral contract, including exact IDs, titles,
  defaults, step counts, list/read-only flags, conversions, and bounded text.
  Status cannot be written; Panic is momentary, nonpersistent, and retries its
  Ready output when the host rejects publication.
- Host parameter input is atomic and bounded to sixteen queues with at most 64
  points each. Known controls use the last valid boundary value, unknown queues
  are ignored, and malformed counts, offsets, values, and noncanonical edits
  fail without partial mutation. The process bridge performs no allocation or
  locking; its only new allocations create SDK parameter objects during
  initialization.
- VST3 component/controller state is byte-identical to the neutral 184-byte
  image. Partial `IBStream` progress is handled exactly; null, failed, zero,
  negative, over-reported, truncated, trailing, and invalid images are rejected
  before publication. Component-state synchronization preserves the live,
  nonpersistent Status value and does not invoke a component-handler callback.
- The final committed-state gates pass 78/78 native tests in debug and under
  ASan/UBSan, 134 Python tests plus 50 subtests, the native source validator,
  exact source-graph/build contracts, Git whitespace checks, the guarded VST3
  probe build, and the excluded historical CLAP target. The final probe
  SHA-256 is
  `19958d801a87eb8f078a6f911ec6f630ab4b33b6162007029bfbceca39bcfb76`;
  it is an ELF64 little-endian x86-64 shared object with immediate binding and
  exports `GetPluginFactory`, `ModuleEntry`, and `ModuleExit`.
- The final guard snapshot recorded 32772 MiB available, load 0.81, 66 C, and
  zero memory-full and I/O-full PSI. Task 9 launched no REAPER process and made
  no persistent plug-in copy, live-project mutation, or hardware/input action.
  Its initial missing-bridge RED and the later nonpersistent-Status regression
  RED both failed for the intended reasons before their respective fixes.
- Task 10 is sealed at commit `69f3ab3` (`feat: add fail-closed VST3 note
  delivery`). The narrow sink emits only zero-initialized VST3 NoteOn/NoteOff
  records on bus zero, converts channels 1..16 to 0..15, preserves valid block
  offsets, maps velocity exactly, and uses matching deterministic note IDs
  `-1000-pitch`. Invalid pitch/channel/velocity/kind/offset/context and host
  `addEvent()` rejection all fail closed.
- The combined component now owns the neutral generated-note ledger. Event
  input remains absent and `ProcessData::inputEvents` is never read. Equal-time
  offs precede ons, multiple ticks retain sequence, and output contains no CC,
  DataEvent, note expression, pitch bend, MPE, or passthrough event.
- Every injected note-on and cleanup rejection position latches MIDI Output
  Blocked, inhibits later ons, retains accepted or maybe-active pitches, and
  retries individual offs at offset zero in ascending pitch order with at most
  one bounded 128-pitch pass per call. Dry audio remains bit exact. Explicit
  Panic plus two complete quiet calls is required before ons resume.
- Event delivery performs no heap work or locking after activation. Normal,
  null-output, and rejecting sink paths each passed 100,000 bounded calls with
  allocation/deallocation counters unchanged. Debug and ASan/UBSan each pass
  83/83 native tests; all 134 Python tests plus 50 subtests, the source
  validator, exact source graph, whitespace checks, probe build, and historical
  CLAP target pass.
- The final Task 10 probe SHA-256 is
  `d4a5fc40ede51e07f2ce0a104bb475b71f512979616b839da48b99341551fe33`;
  it retains ELF64 little-endian x86-64 DYN identity, immediate binding, and
  `GetPluginFactory`, `ModuleEntry`, and `ModuleExit`. The final guard snapshot
  recorded 32436 MiB available, load 4.21, 58 C, and zero memory-full and
  I/O-full PSI. No REAPER process, persistent bundle, live project, or
  hardware/input action was used. The primary RED was the intended missing
  `vst3_event_sink.hpp` boundary.
- Task 11 is sealed at commit `db32720` (`feat: complete bounded VST3
  processing lifecycle`). Host setup now accepts finite positive rates from
  the host without a fixed sample-rate matrix, including 44.1, 48, 88.2, 96,
  32, 50, and 192 kHz, while rejecting zero, negative, non-finite, and
  numerically unsafe rates. Prepared timing stores exact sample and 64-sample
  decision periods outside `process()`.
- Main-thread structural edits publish generation-tagged prepared
  configurations through the bounded exchange. The audio callback adopts only
  a matching generation at the parameter boundary; missing preparation enters
  Reconfiguring, releases reachable notes, keeps the old configuration and dry
  path, and never prepares in `process()`. Matching late preparation commits
  once and resets phase and detector transients.
- Stop/start, deactivate/reactivate, and host-rate changes preserve the fixed
  pending-note ledger while freeing transition storage. The first resumed
  process retries old-channel note-offs at offset zero before detector work.
  Input/output layout, sample format, block size, pointers, aliasing,
  non-finite audio, parameter-only calls, silence flags, missing/rejecting host
  output queues, and all processing modes fail closed or pass dry audio under
  their explicit contracts.
- The 64-sample decision phase is invariant across variable partitions,
  process modes, and float32/float64 paths, including multiple ticks in long
  blocks. Repeated 100,000-call process and 100,000-call stop/start runs changed
  neither allocation nor deallocation counters after activation.
- Fresh final gates pass 92/92 native tests in debug, ASan/UBSan, and TSan;
  all 134 Python tests plus 50 subtests; the native source validator; exact
  source graph; Git whitespace checks; the guarded VST3 probe; and the
  historical CLAP target. The final probe SHA-256 is
  `d8382bab6732faf77ee72f50165a3477735ecad98f19e204de513704dc43b0d8`;
  it is a stripped ELF64 little-endian x86-64 shared object with RELRO,
  immediate binding, and only the expected VST3 entry points among the checked
  adapter symbols.
- Task 11's initial RED failed on the absent setup/phase test seams. Its final
  packaging gate then exposed one missing prepared-config source in the
  authoritative CMake graph; that defect was repaired and every affected gate
  reran green. The final stability check showed about 32 GiB available and
  zero full memory/I/O pressure. No REAPER process, persistent bundle, live
  project, or hardware/input action was used.
- Task 12 is sealed at commit `7c02188` (`test: seal offline VST3 adapter and
  validator`). A fixed-seed `0x4D335633` adversarial run now executes 100,000
  bounded operations across malformed parameter/state/process/layout/event and
  lifecycle inputs. Its initial RED exposed delivery of a ninth generated
  voice; the neutral ledger now blocks that event before host delivery and
  retains the first eight for deterministic cleanup.
- The real-time gate performs 100,000 process plus stop/start cycles with
  allocation/deallocation counters and `/proc/self/task` unchanged. The
  production-source validator now rejects threads, locks, conditions, futures,
  filesystem/stream/stdio access, network access, sleep/wait, exceptions,
  RTTI, recursive neutral-core functions, growable containers, CLAP symbols,
  test identities, report environments, and test schedules.
- Production and probe are real two-file build-local VST3 bundles with exact
  official module-info. The production `.so` SHA-256 is
  `e6f6ebfbe522a1eb3a785db97902296931d8f57c0083904f9b656b770302e37d`,
  module-info is
  `7a6247b9d1ccd815c0bf6ff0821a906168e2bb48d755f0e22cd60450734e8738`,
  and the full bundle digest is
  `fed1e4062ba5f29511df2c4b9f430ed3fe0d70172d897ec91dacdc5d2a9e1eaa`.
- Gate O4 is green. The build-local official Steinberg validator ran exactly
  once against the canonical production bundle and reported 47 passed, 0
  failed with classification `pass`, return code zero, and no automatic
  retry. Its atomic evidence is
  `build/test-results/vst3-validator/production/{result.json,stdout.txt,stderr.txt}`.
- Two independent serial builds using `SOURCE_DATE_EPOCH=1788129797` under
  `build/repro-{a,b}/release` are byte-identical to each other and to the
  canonical release bundle. Compiler, flags, SDK/module/binary hashes, complete
  manifests, official-validator hashes, and the one-run record are preserved
  in `docs/VST3-TESTING.md`.
- Final Task 12 gates pass 95/95 native tests in debug, ASan/UBSan, and TSan;
  all 142 Python tests; the native source validator; exact production/probe
  targets; the retained historical CLAP link target; and Git whitespace
  validation. One earlier build preflight safely refused at memory-full PSI
  1.49 before compilation; no limit was loosened, and later pressure returned
  to zero. The final snapshot had about 30 GiB available, zero swap/full
  memory/I/O pressure, and no REAPER process. No persistent bundle, live
  profile/project, or hardware/input action was used.
- Task 13 is sealed at commit `f3c3fe2` (`test: guard build-local VST3 host
  matrices`). Disposable staging now permits the exact host-derived rates
  44.1, 48, 88.2, and 96 kHz and block sizes 32, 64, 128, 256, and 512. Only
  the disposable `reaper.ini` receives the exact build-local VST3 scan root;
  stale VST3 and CLAP caches are removed without touching the live profile.
- The generalized launcher accepts mutually exclusive CLAP or VST3 injection,
  validates the exact probe bundle, binary, module-info identity, and
  symlink-free containment, and strips inherited plug-in injection variables
  without changing `HOME`. Existing workspace-5 isolation, background and
  nonactivating window handling, 50%-of-one-CPU quota, 384/512 MiB memory
  high/max, 64 MiB swap, 64-task limit, and bounded CPU/wall time remain.
- `tools/run_native_vst3_probe.py` defines the exact ordered twenty-row matrix.
  Every future row gets a fresh disposable profile, unique project, and one
  guarded process. Input hashes cover the probe binary, bundle, module-info,
  capability source/script, guard, stager, and runner. Complete rows require
  the suite sentinel, rate/block identity, before/after pressure, return
  status, and every expected TSV. Changed or interrupted evidence is renamed
  invalid and cannot be retried; the first failure, timeout, post-stage
  preflight abort, or pressure abort stops the tail.
- Task 13 verification passes 77/77 focused tests, 163/163 repository Python
  tests, Python compilation, the native source validator, and Git whitespace
  checks. The real non-launching dry plan printed all twenty rows in order and
  left zero REAPER processes. One earlier dry-plan preflight correctly refused
  while system memory-full PSI was elevated; no staging or launch occurred,
  the limit was not loosened, and the final dry plan passed after active PSI
  returned to zero. No persistent bundle, live profile/project, hardware/input,
  or REAPER action was used.
- Task 14 is sealed at commit `848bf80` (`test: add audio-triggered VST3
  capability probe`). The test-only factory selects a separate probe processor
  while the production factory and source graph remain free of the probe
  identity, trigger protocol, diagnostics, and capability schedule.
- The probe decodes only a bounded stereo-audio test code at the fixed
  64-sample cadence. It emits deterministic ordinary VST3 note-on/off events,
  validates the complete process contract and every input sample before
  decoding, latches malformed/overflow conditions, and publishes fixed atomic
  diagnostics only once per processing start with a four-attempt bound.
- The disposable JSFX source and ReaScript verify exact VST3 discovery,
  parameters, write protection, state, dry pass/mute, float32/float64 audio
  triggering, lifecycle cleanup, deletion silence, and global diagnostics.
  A disabled reporter is reserved before playback so module-static evidence
  survives deletion of the tested instance; failure never publishes the suite
  sentinel or self-closes the disposable host.
- Fresh Task 14 gates pass 101/101 native tests in debug, ASan/UBSan, and TSan;
  all 164 repository Python tests; all 30 source contracts; the native source
  validator; exact probe and production builds; and Git whitespace checks.
  The official Steinberg validator classifies the probe `pass` with return
  code zero and no automatic retry. Its bundle digest is
  `e21f55b673e529feb35620bb80dcc1426671fb066e7a761739f9ed86bcaa4018`.
- Task 15's non-launching preauthorization gates are green: native debug and
  sanitizer suites, release probe build, official probe validation, 48 focused
  guard/runner tests, and a real dry plan containing exactly twenty ordered
  rows from 44.1 kHz/32 through 96 kHz/512 all pass. The final process scan
  found zero REAPER processes. This was the final state before Gate C5
  authorization; no row had yet been launched.
- In direct response to the exact Gate C5 scope, the user said `Proceed` on
  2026-08-30. This freshly authorized exactly twenty guarded disposable REAPER
  launches once, retaining workspace 5, serial execution, hard resource
  ceilings, stop-on-first-failure, immutable evidence, and no retry.
- The immediate launch preflight passed with 26782.62 MiB available, load
  1.34, temperature 55 C, memory-full and I/O-full PSI 0.00, workspace 5
  present, workspace 1 active, and no REAPER process or window.
- Gate C5 launched only its first row, 44.1 kHz/block 32. The guarded process
  reached its 45-second timeout and returned 124. The runner classified the
  row `infrastructure-invalid`, atomically preserved it at
  `build/test-results/native-vst3-probe/batches/44100-32.invalid-20260831T004349Z`,
  stopped the remaining nineteen rows, and made no retry.
- `phase.log` ends in `suite-fail`, not `suite-finish`; `capability.tsv`
  reports status `fail` with 77 assertion labels; and every probe lifecycle,
  format, buffer, rate/block, and trigger diagnostic remains `-1`. Those
  partial TSV values are invalid non-completion evidence, not product
  capability measurements or a proven adapter diagnosis.
- The seven-file lexical evidence-manifest digest is
  `98c48c74eeea2ef8bc962689d210bfc6154cf9069fa7c4dee34ed072a4fa0958`.
  Exact file hashes and the runtime input hashes are recorded in
  `docs/VST3-TESTING.md` and the immutable row metadata.
- Cleanup is green: the after snapshot recorded 26863.25 MiB available, load
  3.16, temperature 59 C, and zero full memory/I/O pressure. Zero REAPER
  processes/windows remain, workspace 1 is still active, and workspace 5
  remains present. The check-only adjudicator fails closed on the sealed
  invalid first row and nineteen unlaunched rows, as required.
- **Decision:** Gate C5 did not pass. Task 16 and all remaining detector-port
  and release work are blocked. The infrastructure-invalid result authorizes
  no retry and no adapter, runner, profile, timeout, or assertion-script edit.
- The subsequently authorized, non-launching harness recovery is sealed at
  `7ca54a5`, and its evidence-namespace recovery correction is sealed at
  `a551021`. The first v2 runner invocation recovered and preserved the stale
  v1 staging duplicate without launching REAPER or consuming launch authority.
- Fresh v2 Gate C5 authorization then launched exactly one row. The 44.1
  kHz/block 32 process exited cleanly with guard return code zero and a terminal
  `suite-fail`; the only assertion label is `observer-magic`. The v2 row is
  immutable at
  `build/test-results/native-vst3-probe-v2/batches/44100-32.invalid-20260831T092345Z`
  with manifest digest
  `6d47f22e360e202a3c4cd905302ed0e8c8bfe587909e29dc58cd593872776e62`.
- The v2 result is a valid capability `fail`, not another infrastructure
  timeout. It stops before any product assertion, so it neither establishes a
  production-adapter defect nor authorizes a corrective edit. Nineteen rows
  remain unlaunched; retry and Task 16 remain blocked.

- The user approved exact-plan inline execution with `Proceed --continuous` on
  2026-08-29. Task 1 is sealed at commit `436b396` (`test: seal VST3
  migration identities and baseline`). The user separately opened Gate T1 by
  naming exact package `cmake=4.2.3-2ubuntu2` with
  `--no-install-recommends` for Task 2 only. Task 2 is sealed at `21f544b`
  (`docs: record authorized VST3 CMake prerequisite`). Task 3 was subsequently
  authorized and sealed at `9851237` as recorded above.
- Task 1 added the SDK-independent production/probe/benchmark identities and
  stable metadata in `native/vst3/vst3_ids.hpp`, ten focused build-contract
  tests, the reusable source-boundary validator seam, and
  `docs/VST3-TESTING.md`. Their Task-1-seal SHA-256 values were respectively
  `40959108a44ab18eb827838fd20a95033d789671cb85858493e108608f0d38d2`,
  `b873e2e35bd170395a73be6f24d9733a558a746a20921dc6db7824f3b3e131d1`,
  `22b34d74f919abf36a2bee3e56b38aa09775326cda2c289ea33176e12b1a6fef`,
  and `296a46bde863dbf12169397bfa6f74eb339f54247ad53ccee5e781e8453a4813`.
- Task 2 adds one real prerequisite contract to
  `tests/test_vst3_build_contract.py` and records the exact package evidence in
  `docs/VST3-TESTING.md`. Their current SHA-256 values are respectively
  `35a817fbffaf739f9d74fed44b8749cf12ab53a30e395feff189060168791aa2`
  and `665becd911275f6e066e0b299b791086d7e37f39356470790db0e32a0df359f1`.
- The exact committed state passes 44 native tests and 125 Python tests; the
  focused VST3 suite passes 11/11. The source validator, C++17 identity
  compile, Python compilation, whitespace check, frozen-JSFX comparison, and
  sealed specification-hash check pass.
- Final Task 2 regression preflight was stable: 32325 MiB available memory,
  load 1.25, memory-full and I/O-full PSI 0.00, and maximum readable
  temperature 54 C.
  Tests ran serially at low CPU and idle I/O priority.
- `/var/log/apt/history.log` records the approved command exactly from 04:35:35
  through 04:35:42 PDT. CMake reports `4.2.3`; dpkg reports `install ok
  installed 4.2.3-2ubuntu2`. Only required automatic dependencies
  `cmake-data`, `libjsoncpp26`, and `librhash1` accompanied it. Swap use and
  full pressure remained zero.
- The exact approved Steinberg SDK is vendored and Task 8 has produced only the
  ignored build-local probe bundle. No persistent M3 plug-in copy or REAPER
  process exists, and no live profile/project, hardware input, or REAPER action
  has occurred under the VST3 plan.
- Gates D2 and the Task 4 build foundation passed at `9851237` and `282ba18`;
  Task 5 neutral parameters passed at `c85d9ab`, and Task 6 neutral state
  images passed at `42859f7`. Task 7's neutral generated-note ledger passed at
  `5c77caf`, opening Gate N3, and Task 8's minimal VST3 lifecycle passed at
  `d757877`. Task 9's generic parameter and exact-state bridge passed at
  `02ba96f`, Task 10's fail-closed VST3 note delivery passed at `69f3ab3`, and
  Task 11's bounded host-rate processing lifecycle passed at `db32720`, and
  Task 12's offline adapter and official-validator seal passed at `7c02188`,
  Task 13's disposable VST3 staging/guard matrix passed at `f3c3fe2`, and Task
  14's offline audio-trigger capability probe passed at `848bf80`. Task 15
  then sealed its first and only launched row infrastructure-invalid. Task 16
  is blocked; do not retry or edit from this result without new direction.

## Approved VST3 design and sealed implementation plan

- On 2026-08-29 the user approved replacing the failed CLAP production path
  with one Linux x86-64 VST3 effect built over the preserved format-neutral
  C++17 detector core. The authoritative new specification is
  `docs/superpowers/specs/2026-08-29-native-vst3-adapter-correction-design.md`.
  Its initial design commit is `35f8a88`; the host-authoritative rate revision
  is `ba1302b` (`docs: make VST3 rate host-authoritative`). The current
  written specification was approved by the user via `Continue on` on
  2026-08-29. Its current SHA-256 is
  `bf27a627432bb360b7e123300e01edb80228b1de0d71331d5d5e968f6d43e4d5`.
- The replacement test-driven implementation plan is
  `docs/superpowers/plans/2026-08-29-native-vst3-polyphonic-audio-to-midi.md`.
  It was written and self-reviewed at commit `9390763`
  (`docs: plan native VST3 implementation`); its SHA-256 is
  `b7dbe1a7eb3a93ba4e06575dc88c45f800191adc5e6e6ef530a7bdc51e768de3`.
  The plan has 24 ordered tasks, 152 executable checkboxes, ten named gates,
  exact files/interfaces/commands/commits, and no unresolved placeholder.
- The selected adapter is Steinberg's official non-distributable
  `SingleComponentEffect`: one host object owns processing, generic parameters,
  state, and prepared-configuration publication. There is no custom GUI,
  worker, helper process, model runtime, lookahead, or declared latency.
- The signal contract is guitar audio to generated VST3 NoteOn/NoteOff events
  to a downstream VSTi. There is one stereo audio input/output, no event input,
  one sixteen-channel event output, up to eight ordinary discrete notes, and no
  raw-MIDI passthrough, CC output, MPE, or event merging.
- M3 tuning remains `G#1 C2 E2 G#2 C3 E3 G#3 C4`; General Tonal mode, the
  fixed 64-sample decision cadence, fifteen writable controls, read-only
  Status, fourteen-value state, dry pass/mute, and every existing detector and
  stability threshold remain unchanged.
- The user clarified that sample rate belongs to the host. The plug-in has no
  sample-rate control, whitelist, preferred-rate override, or hidden resampler;
  it derives bounded coefficients from the finite positive rate supplied by
  VST3 setup. The mandatory verification points are 44.1, 48, 88.2, and 96
  kHz, while other finite host rates remain governed by the same preparation
  and safety contract rather than being silently converted.
- The user explicitly added block size 512. The exact host matrix is twenty
  serial rows: 44.1, 48, 88.2, and 96 kHz, each at blocks 32, 64, 128, 256,
  and 512. It stops after the first failed, invalid, timed-out, or
  pressure-aborted row. Separately, the REAPER child memory ceiling remains
  512 MiB.
- 96 kHz remains a hard release gate with native-rate processing and the same
  64-host-sample cadence. The existing 96 kHz 32+56 false MIDI-44 regression
  is not waived by an adapter probe and must pass before release.
- The stable descriptive identity is
  `com.ajuntanaga.m3-polyphonic-audio-to-midi`. The locked production, probe,
  and benchmark FUIDs are respectively
  `4A1BA42F-6D70-4609-8B52-450C3842F11F`,
  `6F62F8B1-B8A1-4872-A0D9-2C3C274421D8`, and
  `28713895-1CCA-47EC-919F-6CC1BCB88A8F`; they must not be regenerated.
- The pre-Task-1 planning preflight passed 44 native tests and 114 Python tests
  under low-priority serial execution. CMake was absent at that checkpoint and
  the read-only candidate was exactly `4.2.3-2ubuntu2`. Task 1 subsequently
  wrote only the SDK-independent identity/source-boundary files recorded
  above; detector source remains untouched and no dependency, SDK, or host
  action occurred.
- Task 2 subsequently installed only that exact CMake package under separately
  explicit authority and stopped at Gate D2. The later `Authorize all` opened
  D2, and exact SDK retrieval was sealed at `9851237`.

## Task 10 CLAP capability gate failed — hard stop

- The user explicitly authorized the four-row Task 10 gate on 2026-08-29.
  Fresh non-launching preflight passed with about 30 GiB available, load 2.42,
  temperature 46 C, memory-full PSI 0.00, and I/O-full PSI 0.18. The dry run
  emitted exactly the planned serial workspace-5 rows for 48 kHz block sizes
  32, 64, 128, and 256.
- The real runner launched block 32 only. Its guard returned zero and REAPER
  completed `suite-finish`, but the runner rejected the capability result and
  atomically preserved it at
  `build/test-results/native-clap-probe/batches/32.invalid-20260829T074326Z`.
  Per Gate C2, blocks 64, 128, and 256 were not launched and no retry was made.
- `capability.tsv` records `status=fail`, `failure_count=19`, `dry_error=inf`,
  positive `synth_peak=0.43603515625000033`, zero source fault, and zero capture
  overflow. The failure labels are `parameter-count`, all fourteen persistent
  `parameter-not-writable-*` checks, `status-state-persisted`,
  `scripted-phase-timeout`, `lifecycle-reset`, and `trigger-two-count`.
- The row did prove discovery and bounded execution: create/init/activate/start,
  stop/deactivate/destroy, float32 processing, separate host buffers, and both
  alias/separate activation self-tests passed. The first CC119 trigger reached
  the plug-in. REAPER did not invoke `reset`; the scripted phase did not reach
  its eight-event completion condition, so the held-note/second-trigger phase
  never ran. The empty event transcript and infinite dry-error sentinel are
  therefore non-completion evidence, not independent measurements.
- All fourteen state rows remained at their defaults after attempted ReaScript
  writes. The first sixteen names/ranges/defaults produced no failure labels,
  but REAPER reported a non-exact total parameter count. This single capture
  does not distinguish a CLAP-adapter contract error from a REAPER/ReaScript
  exposure mismatch, so no corrective claim or code change is made.
- Pressure stayed safe: before/after available memory was 29982.57/29808.68
  MiB, load 2.12/2.67, temperature 50/49 C, memory-full PSI 0.00/0.00, and
  I/O-full PSI 0.05/0.03. No REAPER application process remained afterward;
  PID 118 is Linux's `[oom_reaper]` kernel thread, not the DAW.
- The lexical seven-file evidence-manifest digest is
  `12abeeb42c9cf3bf9293540ed952951bfcbeeeaf1e22139af380ac527c837d51`.
  Individual hashes are recorded in `docs/NATIVE-TESTING.md`.
- **Decision:** Gate C2 failed. Task 11 and all later detector-port work are
  blocked. Do not retry this CLAP row, launch the remaining rows, download a
  VST3 SDK, install anything, or modify the adapter under this authorization.
  Per the approved plan, the only next design action is a separately approved
  VST3 adapter correction.

## Native Tasks 1-9 sealed checkpoint — retained pre-gate state

- Branch `main` is sealed through `cc938f7` (`test: add disposable CLAP
  capability probe`). Native plan Tasks 1-9 are complete in commits
  `c682664`, `52ba588`, `b208f83`, `9e0ba74`, `facd070`, `bbae558`,
  `546ae84`, `ff7e330`, and `cc938f7`.
- The only retrieved dependency is the official CLAP `1.2.10` header tree at
  commit `195b42a004144fab0b3cf95e9c067187d15365b7`, copied with its license and
  exact provenance/checksum manifest. No VST3 SDK or fallback was retrieved.
- The bounded C++17 core foundation, minimal CLAP lifecycle/ports, exact
  parameter and versioned-state surfaces, ordered MIDI/fail-closed cleanup,
  prepared detector-configuration publication, build-local host guard, and
  disposable capability probe are implemented. The probe-only processor and
  report markers are excluded from the production build.
- Latest offline verification is green: 44 normal native tests, the same 44
  tests under AddressSanitizer/UndefinedBehaviorSanitizer, 114 Python tests,
  both source validators, Python bytecode compilation, and Git whitespace
  checks. The staged capability ReaScript matches its repository source
  byte-for-byte.
- Build-local artifact SHA-256 values are
  `4a9b8ff7e0febf7120c91319db5ec49837d35a0908f0b35919a09376329d3840`
  for `M3_Polyphonic_Audio_to_MIDI.clap` and
  `2dedbd2532c84c5d6522b0dd28f7143ba3bfd800cddbb672d7cd355c3e2a9066`
  for `M3_Polyphonic_Audio_to_MIDI_Probe.clap`. Both are x86-64 ELF shared
  objects; only the probe artifact contains `M3_CLAP_PROBE_REPORT`.
- This was the authoritative pre-launch state. Task 10 was subsequently
  authorized and failed at block 32 as recorded above; its remaining rows are
  no longer launchable under the current plan.
- Clean-DI/hardware input, live projects, REAPER MCP, detector-port Tasks
  11+, production-host validation, performance measurement, persistent
  installation, MPE, and a custom GUI remain separately gated.

## Authoritative state

- Branch: `main`. The current VST3 implementation feature checkpoint is
  `7c02188`;
  the older CLAP implementation checkpoint is `cc938f7` and its failed-host
  gate remains recorded below as retained history. The retained
  Task 13 terminal JSFX checkpoint is `0be04d3` (`feat: complete
  polyphonic JSFX experiment and record native gate`); its predecessor is
  `8a1332d` (`test: generate deterministic synthetic matrix`).
- The approved native CLAP design was introduced at `3ac7dcb` (`docs: approve
  native CLAP architecture`). Its authoritative written specification is
  `docs/superpowers/specs/2026-08-28-native-clap-polyphonic-audio-to-midi-design.md`.
  The architecture and written specification were both approved on 2026-08-28.
  The authorized native implementation plan is now
  `docs/superpowers/plans/2026-08-28-native-clap-polyphonic-audio-to-midi.md`.
  Its SHA-256 is
  `4cb0a1daf31e34dfc853cffba0c0e4e57c5ec7eb8a00e47cfe6cd16cbc9c25b2`.
  It defines 24 TDD tasks, 149 executable checkboxes, and explicit dependency,
  capability-host, production-host, performance, clean-DI, and installation
  gates. At that planning-only checkpoint, no CLAP header, native source,
  build artifact, or REAPER launch had yet been created; the newer Tasks 1-9
  checkpoint above supersedes that implementation state.
- Current runtime fingerprint:
  `7f2724003de54d623b434abf263e6dae3e571d4064194440094ed4367aa29ac4`.
- The deterministic synthetic manifest is byte-identical to its generator and
  has SHA-256
  `683a72b34aaf01354fad11c0479ce03bd28a6b24bc7e5f3ae61dafca7bc67725`.
- Final 48 kHz/128-sample evidence is
  `build/test-results/task13-v232-final-jsfx-48k128-slice`. Within that 48-case
  capture, all 45 M3 cases and 124 expected M3 notes pass with precision,
  recall, and F1 `1.0`, zero false positives, false negatives, duplicates, or
  hanging notes. `events.tsv` SHA-256 is
  `a695ebdc5ac641bf3f51b16cfd0f48dca08f3723f717e296bde003bb437c2f2a`.
- Single-open latency passes at `21.333 ms` median and `40.133 ms` P95. The
  required three/four-note chord gate fails at `78.667 ms` median and
  `99.600 ms` P95 against limits of `40/65 ms`.
- Two independent 10,000-block 48 kHz/128-sample dense-M3 deadline runs failed
  decisively. Run A was `0.588229` median, `1.181451` P95, `19.909088` P99,
  and `20.577708` maximum deadline fraction; Run B was `0.594384`, `1.178591`,
  `19.914089`, and `20.711463`. Every block in both runs exceeded the `0.50`
  hard limit. Raw hashes are
  `30da3aa4a3cf0d19bd63fa7f4d8ea6d54b3f4cf9adf30c01058f48e4f0527122`
  and
  `d608a7039be77f0e0939cfcaab50e00ebbe38dec45f4135d8ecdc15d5fb1e9ab`.
- Current 48 kHz core cases 12101–12118 and case 4102 pass; case 4102 also
  passes at 44.1 kHz. At 96 kHz, its new 32+56 regression detects one false
  MIDI 44, so 96 kHz is independently not release-ready.
- Fresh current-tree checks: all 142 Python tests and 95 native tests in debug,
  ASan/UBSan, and TSan pass. The native source validator, exact production and
  probe source graphs/bundles, one-run official validator, reproducibility
  comparison, Git whitespace checks, and historical CLAP target are green.
  Probe-only diagnostics remain excluded from the production artifact.
- The task-local `RESUME.md` remains authoritative. The canonical ResearchOS
  project dashboard and native implementation-plan note are synchronized as a
  human-facing, non-Git index.
- Every earlier JSFX-evidence REAPER instance ran serially, backgrounded on
  workspace 5, under the 50%-of-one-core and 512 MiB limits. Tasks 1-12 added
  no REAPER launch, and no REAPER application process remains.
- Decision: native CLAP plan Tasks 1-9 remain retained, but its Task 10 gate
  failed and must not be retried. The replacement VST3 plan is sealed through
  Task 12 at `7c02188`; continue with VST3 Task 13, not any old CLAP task. The
  JSFX detector remains stopped and uninstalled.
- The user's `Authorize all` covers the remaining actions in the approved VST3
  plan only when their ordered prerequisites are reached. Clean-DI input,
  persistent installation, live-project mutation, and REAPER launch have not
  occurred in Tasks 1-12; REAPER MCP remains outside scope.

## Approved native-design amendment

- Delivery form: one Linux x86-64 CLAP track effect with stable ID
  `com.ajuntanaga.m3-polyphonic-audio-to-midi`.
- Runtime: format-neutral C++17 detector core plus a narrow CLAP adapter; no
  plug-in-owned worker, helper process, model runtime, lookahead, or declared
  latency.
- Scheduling: sample-wise conditioning/resonators and a fixed 64-sample
  salience/selection/lifecycle cadence independent of host block size.
- MIDI: raw MIDI 1.0 input passthrough and generated discrete output on one
  configurable channel; MPE remains deferred.
- Interface: the existing fifteen writable controls through REAPER's generic
  parameter view plus one read-only Status value. A custom GUI is deferred.
- Safety: all active-path storage is bounded and prepared outside `process()`;
  output exhaustion blocks new note-ons, retains pending releases, and keeps
  dry audio available. Native validation inherits the guarded disposable
  workspace-5 REAPER boundary.
- Adapter fallback: a failed minimal CLAP capability probe stops before the
  detector port. VST3 requires its own approved correction; it is not built in
  parallel.

## Verified Task 4 evidence

- Expected RED: assertion 4101 selected MIDI 24 instead of 32. Evidence
  `build/evidence/task-04-resonator-tuning-red-4101.png`, SHA-256
  `a0f797d6ed016930e81debbd3bc14d505467fea27e7e851aad3de41b7757611d`.
- Diagnostic RED: MIDI 32 was a real local peak but an unguarded lower analysis
  edge scored higher. Evidence
  `build/evidence/task-04-resonator-diagnostics-48k.png`, SHA-256
  `91eb621d563a2005b5310146a26745ee5db8b7fe81340ec74ae417d69b6e2e68`.
- Final correctness matrix: cases 4101–4106 all passed at 44.1, 48, and 96 kHz
  in 18 separate disposable workspace-5 launches. Every suite state was `2` and
  every failed assertion ID was `0`.
- Case 4101 ran 19 assertions at each rate; cases 4102–4106 ran three assertions
  each. The SHA-256 of the lexically ordered `sha256sum` output for all 18 result
  files is
  `8c154e597dae4d2ef9dddbd2cecb9e87ed6968258651e8517f8d2f880a81306b`.
- Final 44.1 kHz case-4101 PASS panel:
  `build/evidence/task-04-44100-case-4101.png`, SHA-256
  `f9d9181172ba9414e88236aed596bad987a36d3222f16844b06f43ed755948f2`.
- During the final matrix, preflights remained far inside the fixed stops:
  about 29 GiB available memory, load below 3.7, and readable temperature no
  higher than 73 C. No REAPER process remained afterward.

## Verified Task 5 evidence

- Expected interface RED: `m3_select_voices` was undefined in real REAPER.
  Evidence `build/evidence/task-05-selector-interface-red.png`, SHA-256
  `aa3a2cbc770ec7ede0f57fc85e05d72522cf0182b3f87281c18045984f7c4c87`.
- Expected behavioral RED: a bounded zero-result scaffold compiled and failed
  assertion 5102. Evidence
  `build/evidence/task-05-selector-behavior-red-5102.png`, SHA-256
  `8bb0fbe08b62204aeea00f884c7b73458f5b3deb9ac8d1c776698d0aa8eef205`.
- Final selector matrix: cases 5101–5106 passed at 44.1, 48, and 96 kHz in
  18 separate disposable workspace-5 launches. Every run had three assertions,
  suite state `2`, and failed assertion ID `0`.
- The SHA-256 of the lexically ordered `sha256sum` output for all 18 Task 5
  result files is
  `ed8e57aa646282cc8abe76d5672c7905d6c59a373edc9c2232d0b0dcf9026ff8`.
- Final eight-open-string selector panel:
  `build/evidence/task-05-48000-case-5104-pass.png`, SHA-256
  `357a4d05f59d2179659ac9e96934ec6c51bd07fc71d3d5d4b30ed6fb2b36b9c9`.
- These are selector-layer tests over salience and per-harmonic energy cells;
  they are not an end-to-end chord-audio accuracy claim. That remains gated by
  later synthetic and separately authorized clean-DI metrics.

## Verified Task 6 evidence

- Expected interface RED: `m3_bank_process_reference()` was undefined in real
  REAPER. Evidence `build/evidence/task-06-reference-interface-red.png`,
  SHA-256
  `94b831eb431c2fe23b50bb6c4c8dbdbda53197389a641eef0dd8539ff4d92b24`.
- Behavioral RED: assertion 6105 measured 440 full-rate cell updates per input
  sample against a maximum of 45. The observer's numeric result is authoritative;
  the attempted gray GUI capture is not evidence.
- Final Task 6 matrix: cases 6101–6106 passed at 44.1, 48, and 96 kHz in 18
  separate guarded launches. The SHA-256 of the lexically ordered `sha256sum`
  output is
  `b5155c896c3c52b95957c38ce86852b8cd289b5bd38baad9b50f15cbb98a38f5`.
- Worst open-string salience deltas were `0.019250096364574` at 44.1 kHz,
  `0.020745752092474` at 48 kHz, and `0.013100931661116` at 96 kHz, all below
  the `0.03` bound.
- At 48 kHz over MIDI 32..84, 251 cells averaged 44.75 updates per input
  sample, about 89.8% below the 440-update full-rate baseline.
- The final adaptive multi-rate implementation also passed all 18 Task 4 and
  all 18 Task 5 regression cases at 44.1, 48, and 96 kHz. Their refreshed
  result digests are
  `c3793e0626760661340b6b1da5be0433ebb1f232b7369ff74448af07d1e6ab4d`
  and
  `5b199fb184c853421338f011266788c903a8ea6a9ce990e5ed21162daa2519ca`.

## Verified Task 7 evidence

- Expected RED: a zero-result profile scaffold reached assertion 7101 in real
  REAPER with three assertions and observed open-note error 368. Preserved
  result `build/evidence/task-07-profile-red-7101.txt`, SHA-256
  `8aa336e939f82225d9e52e211ca88fd89cd36a1b27f469c1eb0252759cd25b60`.
- Final profile matrix: cases 7101–7106 passed at 44.1, 48, and 96 kHz in 18
  separate guarded workspace-5 launches. Every result had three assertions,
  suite state `2`, and failed assertion ID `0`.
- The SHA-256 of the lexically ordered `sha256sum` output for all 18 Task 7
  results is
  `6096b227cca280fd720c8420be467aedf7b80a7aafd7e243898ebbf3239429d7`.
- Cases 4104, 5104, 6102, and 6105 were rerun at all three rates as a
  proportional cross-layer regression; all 12 passed.
- During these launches, available memory stayed near 28 GiB, load stayed
  below 3.3, and readable temperature stayed at or below 73 C. Workspace 4 was
  restored after each workspace-5 run and no REAPER process remained.

## Verified Task 8 evidence

- Expected RED: the complete 8101–8111 harness plus a zero-result lifecycle
  scaffold reached assertion 8102 in real REAPER at 48 kHz/block 64. It had
  three assertions and aggregate error 64. Preserved result
  `build/evidence/task-08-lifecycle-red-8102.txt`, SHA-256
  `421def10592db36a72b2697beea40573336ab6c663068ab6c77ca5f26e0e24a8`.
- Final lifecycle matrix: cases 8101–8111 passed at block sizes 32, 64, 128,
  and 256 in 44 separate guarded launches. Every result had three assertions,
  suite state `2`, failed assertion ID `0`, matching block identity, and zero
  active notes after cleanup.
- The SHA-256 of the lexically ordered `sha256sum` output for the 44 results is
  `c4698e0d4571f9a53c37d7d0d1524226e78f1787025e55b84b4e52e818deb6ea`.
- Cases 4104, 5104, 6102, 6105, 7102, and 7105 passed again at 48 kHz as a
  six-case proportional regression.
- A first-green harness expectation used raw floating-point `floor` and saw
  191 instead of the intended nearest-sample 192 for 4 ms at 48 kHz. Only the
  expectation changed; lifecycle coefficients and production behavior did not.
- Available memory stayed near 28 GiB, load stayed below 3.8, and readable
  temperature stayed at or below 73 C. The runner restored the user-selected
  workspace (4 early, 1 later) and left no REAPER process running.

## Verified Task 9 evidence

- Expected RED: the complete 9101–9109 host harness plus a zero-result emitter
  scaffold reached assertion 9101 in real REAPER at 48 kHz. It had three
  assertions and aggregate error 322. Preserved result
  `build/evidence/task-09-midi-host-red-9101.txt`, SHA-256
  `bb4045cf18175e0ce8684c10b75a220e0faf21bb9f62a3f44d5341d0c17664e7`.
- Final host matrix: cases 9101–9109 passed at 44.1, 48, and 96 kHz in 27
  hidden guarded workspace-5 launches. Every result had three assertions,
  suite state `2`, and failed assertion ID `0`.
- The SHA-256 of the lexically ordered `sha256sum` output for all 27 results is
  `1a20321b3c6bb43ae671dc306f4ecc326f0ef286fa25faa333cd1c45d52a40e9`.
- Cases 4104, 5104, 6102, 6105, 7102, 7105, and 8102/block 128 passed again at
  48 kHz as a seven-case detector-through-lifecycle regression.
- A separate disposable load smoke instantiated the production JSFX enabled
  and online with two inputs, two outputs, and all fifteen named controls in
  order. Result `build/evidence/task-09-production-smoke.txt`, SHA-256
  `321e87851cbda022d3744f5cc8d1df8530a1a113ca863e0ee4b693780d087173`.
  The script dirtied the disposable project while swapping FX, so the guard
  enforced its 60-second termination bound rather than producing a clean host
  close; Task 11 still owns host-sequence and VSTi-routing proof.
- Matrix preflights stayed above 30 GiB available memory, below load 1.2, and
  at or below 59 C. Workspace 1 stayed active and no REAPER process remained.

## Verified Task 10 evidence

- Expected RED: the complete 10101–10106 harness plus a permissive telemetry
  scaffold reached assertion 10101 in real REAPER at 48 kHz. It had three
  assertions and aggregate error 87. The raw observer result SHA-256 was
  `2d36f7973607e5cc6310aba3d878877b18204fff23f53be456371b50b768e5cd`;
  compact preserved evidence
  `build/evidence/task-10-telemetry-red-10101.txt` has SHA-256
  `c025e01d67f2723e670df7e30748defc9615a7f28a0895c8c9137b44e2e42297`.
- Final telemetry matrix: cases 10101–10106 passed at 44.1, 48, and 96 kHz in
  18 hidden guarded workspace-5 launches. Every result had three assertions,
  suite state `2`, and failed assertion ID `0`.
- The SHA-256 of the lexically ordered `sha256sum` output for all 18 results is
  `56768676bb073d9bba8e84e38322ff01e3692959a41f4ba1e9c2634e26969b47`.
- Cases 4104, 5104, 6102, 6105, 7102, 7105, 8102/block 128, 9101, 9104, and
  9109 passed again at 48 kHz. A transient X11 `BadDrawable` caused one safe
  preflight refusal before the bounded 9109 retry passed.
- The production-load smoke passed enabled and online with two inputs, two
  outputs, and all fifteen named controls, then saved and closed only its
  disposable project. Result `build/evidence/task-10-production-smoke.txt`,
  SHA-256
  `321e87851cbda022d3744f5cc8d1df8530a1a113ca863e0ee4b693780d087173`.
- Matrix preflights stayed above 30 GiB available memory, below load 0.9, and
  at or below 58 C. Workspace 1 stayed active and no REAPER process remained.

## Verified Task 11 evidence

- The staged dummy-audio host chain was Signal Source -> production detector ->
  MIDI Capture -> ReaSynth -> Synth Output Probe. It used only the disposable
  `build/reaper-test/reaper.ini` profile in hidden, nonactivating workspace-5
  launches.
- The accepted run completed all 13 cases: mono, dyad, the full eight M3 open
  strings, and ten repeated eight-note Panic trials. Each row passed with exact
  expected note-on/off coverage, no capture overflow, no duplicate or
  unexpected notes, and nonzero ReaSynth output. Normal dry-path identity had
  maximum error `3.3306690738754696e-16`.
- All ten Panic trials released eight notes within `1.750–5.333 ms`, below the
  500 ms gate. Trial 10 executed the actual Safe Bypass ReaScript inline. The
  runner observed the detector disabled after the script's 50 ms cleanup wait,
  then deleted only that detector after all ten trials passed; ReaSynth and the
  output probe remained present.
- Synthetic onset evidence at 48 kHz was: mono E2 `49.333 ms`; dyad E2
  `49.333 ms` and B2 `68.000 ms`; eight opens C4 `41.333 ms`, C3 `54.667 ms`,
  G#2 `60.000 ms`, G#3 `89.333 ms`, E3 `134.667 ms`, E2 `150.667 ms`, and
  G#1/C2 `177.333 ms`. These are causal evidence times, not hardware
  round-trip latency, and the detector declares neither lookahead nor PDC.
- Preserved accepted artifacts are
  `build/evidence/task-11-results/{events.tsv,summary.tsv,safety.tsv,phase.log}`.
  Their individual SHA-256 values are respectively
  `cf3a128ab1442055039bb39eeef434a50630cd30c7ee8b32a5242d20194d987a`,
  `96fbad6c2e175ecfc7060b96c9a69aa0e34c9c9e4edc7f692f7d870ba45db2d2`,
  `1eedf2e3deb52f54687dbe9ebd50f762f543be84bdb1c164c2de467d83e0e92d`,
  and `e616554dbe23678dcc3b3426a506e195b1875c5ed7e57c2d81b3900278decd30`.
- The source/host debugging run exposed one stability boundary: TasksMax 32
  caused a kernel-recorded cgroup fork rejection. A source test was added and
  only TasksMax was raised to 64. The 50%-of-one-CPU quota, 384/512 MiB memory
  bounds, 64 MiB swap cap, low CPU/I/O weights, nice 10, idle I/O class, and
  hard wall timeout were retained. The accepted run caused no later cgroup
  rejection; post-run memory and I/O pressure were zero, about 30 GiB remained
  available, and no REAPER process remained.
- This is synthetic dummy-audio/VSTi-routing evidence. It is not a live-guitar,
  clean-DI, audio-interface, audible-output, or performance-readiness claim.
- A fresh post-documentation rerun against the staged current tree passed core
  cases 4102 and 9108 at 48 kHz, then passed the complete 13-case/10-trial host
  chain again. That rerun contained 182 MIDI events, exactly one inline Safe
  Bypass execution, Panic release times `0.479–2.667 ms`, nonzero ReaSynth
  output for every case, no remaining REAPER process, no recent cgroup/OOM
  record, about 30 GiB available memory, and zero memory/I/O pressure.

## Current implementation and tuning

- The production bank uses fixed eight-word cells, causal 8 ms/35 ms complex
  correlations, 4096-sample oscillator renormalization, and no allocation.
- Four causal streams run at `sr`, `sr/2`, `sr/4`, and `sr/8`, with two
  second-order low-pass sections before each divide-by-two stage. Rate routing
  is fixed until reinitialization and uses a `0.16` threshold plus edge
  promotion. At 44.1 kHz, pitch cells use `sr/4` or faster.
- Harmonic allocation is bounded and adaptive: six partials through MIDI 52,
  four through MIDI 75, three at MIDI 76 and above, and three for analysis-only
  guard notes. This preserves the missing-fundamental E2 regression.
- The M3 profile loads exact open notes `32,36,40,44,48,52,56,60`. Its
  distinct-string matcher first builds a 16-note bounded shortlist, then uses
  three fixed 256-word dynamic-programming rows and at most `8 * 256 * 16`
  transitions per feasibility pass. Scratch guards remain outside the 768-word
  working region.
- Production filters selected M3 sets before lifecycle updates. Infeasible sets
  lose the lowest-confidence candidate and retry at most eight times; the final
  stable mode control exposes M3 Eight-String and General Tonal behavior.
- The lifecycle module stores eight fixed words for each of 128 pitches and an
  82-word ordered event queue. It implements OFF/ATTACK/ON/RELEASE hysteresis,
  eight-active-note enforcement, same-pitch collapse, release-all cleanup,
  note-off-priority overflow, and fixed/dynamic velocity. The emitter encodes
  channel 1–16 events, clamps block offsets, and sends each event once.
- The production effect has the frozen fifteen-slider surface. `@slider` only
  clamps and stages settings. `@block` performs reachable panic-before-reset
  for rate, stop, hard reconfiguration, and explicit Panic. A fixed signal
  floor blocks stale silence selection, and a Panic latch prevents same-block
  detector refill until a quiet block is observed. `@sample` performs streaming
  analysis, one-time MIDI output, and the optional two-assignment dry mute.
  Incoming MIDI is untouched.
- Telemetry alternates two fixed 40-word snapshots, marks in-progress writes
  odd, and publishes only completed even generations. The 64-word UI region
  holds one snapshot plus a fixed twelve-note-name table. `@gfx` reads only the
  published snapshot and cannot write detector/lifecycle memory.
- Input trim ramps over 64 samples. Project serialization contains only
  `saved_schema_version=1`; active notes and detector state are discarded on
  load. Fault codes 1–5 disable detection, preserve available dry audio, and
  use reachable note-off cleanup. Two sample-edge `time_precise()` calls feed
  the three-block half-deadline overload indicator.
- Requested pitch bounds are stored separately from analysis-only guard
  semitones. Production remains requested MIDI 32..84.
- Final Task 4 score coefficients are harmonic mean `0.85`, minimum-three
  `0.05`, missing-fundamental support `0.10`, and neighbor penalty `0.03`.
  Decays, harmonic weights, and base threshold `0.20` remain unchanged.
- The selector uses at most eight fixed iterations, four words per output cell,
  `0.18` harmonic residual attenuation, `0.35` independent-fundamental
  protection, a 16-note bounded shortlist, deterministic onset ordering, and
  234 words inside the 256-word fixed selection region.
- `tools/prepare_core_harness_project.py` generates only build-local, literal
  rate/case RPPs. Its nine behavioral tests cover correct slider state and
  refusal of source/output paths outside `build/`.
- `tools/observe_core_harness_case.lua` accepts only the exact disposable Task
  4–10 case path shape, including mandatory collision-free block identity for
  Task 8, removes only that case's old result, publishes atomically, and exits
  REAPER. It does not analyze audio or emit performance MIDI.
- `docs/PERFORMANCE.md` records all measured coefficient, guard, and matrix
  evidence.

## Guarded REAPER boundary

Every GUI launch must use `python3 tools/run_guarded_reaper.py --gui --workspace
5` with only `build/reaper-test/reaper.ini`. The guarded launcher enforces GNOME
workspace 5 (wmctrl desktop index 4), fixed memory/CPU/swap/task limits, one-core
affinity, low CPU/I/O priority, preflight memory/load/thermal checks, clean
interrupt handling, and a bounded retry only for the observed transient X11
`BadWindow` teardown race. GUI tests use `-noactivate`, detached standard
streams, hidden test windows, and 20 ms startup placement. A pre-launch snapshot
excludes already-open REAPER windows. The guard records the user's active
workspace and restores only a focus steal to workspace 5, including a short
post-exit settling window; it never overrides a third workspace the user
selected. Repeated destroyed-window snapshots defer to the next bounded poll;
other workspace failures still refuse immediately. TasksMax is 64; CPU remains
limited to 50% of one logical core and memory remains capped at 512 MiB. A live
10 ms observation kept workspace 1 active for the full launch and left no
REAPER process behind.

## Offline scan-containment hardening — future guard only

- The future VST3 guarded path now fails closed on exact scope/receipt,
  symlink, lock, recovery, process-census, marker, and cache-validation
  boundaries. The systemd transient scope is considered exited only after an
  exact inactive state, or after collection with a positively exited launcher.
- Independent read-only review is clean. The low-priority `221`-test repository
  suite, both source validators, Python compilation, and whitespace validation
  pass. Verification used mocks or dry-run paths only: it launched no REAPER
  process and did not alter sealed v1/v2/v3 evidence.
- This is future-guard hardening, not a fresh host design, a proof of
  pre-launch scan isolation, or authorization to launch REAPER. Before any new
  host work, preserve the seals, design and independently review the isolation
  boundary, use a new namespace, and obtain new explicit host authority.

## Exact resume action

1. Verify harness-recovery commits `7ca54a5` and `a551021`, observer-
   diagnostic commit `176923e`, and isolated v3 gate `0a216d4`, then verify the
   immutable v1 and v2 seven-file
   manifest digests
   `98c48c74eeea2ef8bc962689d210bfc6154cf9069fa7c4dee34ed072a4fa0958`
   and
   `6d47f22e360e202a3c4cd905302ed0e8c8bfe587909e29dc58cd593872776e62`.
2. Preserve both v2 directories exactly: the proven legacy staging duplicate
   ending `091010Z-recovered` and the current-v2 failed row ending
   `092345Z`. Do not adopt, delete, rename, overwrite, or retry either one.
3. Confirm zero REAPER processes/windows, the user's active workspace unchanged,
   and acceptable passive pressure before any further work.
4. Do not rerun the sealed matrix or launch its nineteen-row tail. The sole
   `--observer-diagnostic-once` authorization is consumed by the sealed v3
   timeout at `44100-32.invalid-20260831T113425Z`; its staging marker and batch
   are preservation-only. Any next host execution requires a new design and
   separate explicit authority.
5. Keep every adapter/probe change, REAPER launch, clean-DI/live input,
   performance run, persistent installation, live project, custom GUI, and
   REAPER MCP behind its named gate.

The prior 07:55 PDT pause boundary was honored. The user explicitly resumed the
task afterward.

## Remaining plan actions and prerequisite gates

- VST3 Task 15 v1 remains sealed `infrastructure-invalid`. Its repaired v2 gate
  is now sealed `fail` after one cleanly exited row stopped at
  `observer-magic`; nineteen rows remain unlaunched. Because the observer gate
  failed before any product assertion, Tasks 16-24 are blocked and no retry,
  production-adapter diagnosis, or corrective implementation is authorized by
  the v2 result. Read-only observer diagnosis cannot recover the raw magic or
  distinguish boot, attachment, scheduling, or compilation. The diagnostic-
  only offline amendment is complete at `176923e`; one separately authorized
  fresh guarded diagnostic row is the next possible evidence step.
- Persistent VST3 installation at I9 remains conditional on every required
  release gate being green.
- Clean-DI/live guitar execution at D8 remains conditional on suitable input
  material being available.
- Live-project modification, REAPER MCP installation, CLAP retry/remaining
  Task 10 rows, and custom native GUI work remain outside this authorization.
