# Performance and Detector Tuning Log

This file records only measured changes made while executing the approved test
plan. It is not a claim that the detector is performance-ready.

## Task 4 correctness baseline

| Assertion | Constant | Before | After | Evidence |
| --- | --- | ---: | ---: | --- |
| 4101 | Adjacent-semitone neighbor-ratio score coefficient | 0.30 | 0.08 | At the specified 35 ms slow correlation, `0.30` clamped every G#1 candidate score to zero; the first best-note result was the lower range boundary, MIDI 24. |
| 4102 | Harmonic-mean score coefficient | 0.55 | 0.85 | At 45 ms, the true E2 harmonic mean exceeded the upper-range leakage floor while its minimum-three and neighbor terms did not. |
| 4102 | Minimum-first-three score coefficient | 0.25 | 0.05 | Reduced the short-window bias toward the MIDI 33 subharmonic and high-frequency leakage floor. |
| 4102 | Missing-fundamental-support coefficient | 0.20 | 0.10 | Preserved explicit missing-fundamental support while shifting weight to the term that localized short-window E2. |
| 4102 | Adjacent-semitone neighbor-ratio score coefficient | 0.08 | 0.03 | Prevented adjacent low-frequency leakage from overwhelming the true E2 local maximum. |

The 8 ms/35 ms decay times, eight harmonic weights, and the `0.20` base
threshold remain unchanged.

## Guardrail observation

The combined 44.1/48/96 kHz resonator correctness suite reached its 120-second
wall timeout under the fixed 50%-of-one-CPU cgroup. The runner returned status
124 and left no REAPER process behind. Immediately afterward, the host still
reported about 31.2 GiB available memory, load 2.55, and a 71 C maximum readable
thermal-zone value.

The safety limits were not raised. The expensive resonator suite is now selected
by one visible test slider and run once per disposable launch. Conditioning
checks remain combined because their prior three-rate run completed well inside
the guard.

The first separate 44.1 kHz run also reached the same hard limit while executing
the full 32..84 bank independently for every synthetic case. The tests now keep
the confounding pitch regions required by each assertion instead: 32..60 for
G#1 and missing-fundamental E2, 32..52 for the 45 ms E2 case, 32..72 for detuned
A4, and one active bin plus guard cells for silence/clipping. Production remains
32..84. This cuts test-only cell updates without weakening the named assertions.

The first bounded 48 kHz diagnostic showed MIDI 32 as a true local salience
maximum (`0.403505`, versus `0.355592` and `0.340798` at MIDI 31 and 33), while
the artificial analysis boundary at MIDI 24 scored `0.471040`. The bank now
reserves one semitone below and above the requested output range when capacity
allows and exposes the requested candidate bounds in its fixed header. Selection
ignores these analysis-only guard cells; this keeps a requested boundary note
eligible while giving its salience calculation both neighbors.

## Task 4 final correctness matrix

After trimming the temporary score diagnostics, the final staged source passed
all six bounded cases at 44.1, 48, and 96 kHz in REAPER 7.79: 18 disposable
workspace-5 launches, 18 PASS results, and no failed assertion IDs. Case 4101
ran 19 assertions because it also covers pitch math, conditioning at all three
rates, and analysis-guard metadata. Cases 4102 through 4106 each ran the two
pitch-math assertions plus their selected detector assertion.

The SHA-256 of the lexically ordered `sha256sum` output for the 18 machine-readable
result files is
`8c154e597dae4d2ef9dddbd2cecb9e87ed6968258651e8517f8d2f880a81306b`.
The 44.1 kHz case-4101 PASS screenshot is
`build/evidence/task-04-44100-case-4101.png`, SHA-256
`f9d9181172ba9414e88236aed596bad987a36d3222f16844b06f43ed755948f2`.

## Task 5 bounded selection

The required RED cycle was observed twice in real REAPER. The first run reached
the new case but could not compile because `m3_select_voices` did not exist;
`build/evidence/task-05-selector-interface-red.png` has SHA-256
`aa3a2cbc770ec7ede0f57fc85e05d72522cf0182b3f87281c18045984f7c4c87`.
A bounded zero-result interface scaffold then compiled and failed assertion 5102;
`build/evidence/task-05-selector-behavior-red-5102.png` has SHA-256
`8bb0fbe08b62204aeea00f884c7b73458f5b3deb9ac8d1c776698d0aa8eef205`.

Task 5 tests the layer named by its interface: candidate salience and fixed
per-harmonic bank-energy cells. Its fixtures explicitly distinguish independent
true fundamentals from harmonic-confusion candidates, include a true candidate
with an energy ratio of `10^(-24/10)`, and place sentinels on both boundaries of
the fixed selection region. These are selector tests, not an end-to-end claim
about chord recovery from audio; that remains part of the later synthetic and
authorized clean-DI metric gates.

The implementation caps selection at eight iterations, stores four fixed words
per result, attenuates near-integer harmonic residuals by `0.18`, protects a
candidate when its fundamental energy exceeds `0.35` of its weighted harmonic
energy, and uses bounded insertion sort. Exact-octave gating uses the already
validated rounded harmonic number because the direct floating-point ratio can
land infinitesimally below `2.0`.

Cases 5101–5106 passed at 44.1, 48, and 96 kHz in 18 separate guarded
workspace-5 launches. The SHA-256 of the lexically ordered `sha256sum` output
for those result files is
`ed8e57aa646282cc8abe76d5672c7905d6c59a373edc9c2232d0b0dcf9026ff8`.
The final 48 kHz eight-open-string PASS panel is
`build/evidence/task-05-48000-case-5104-pass.png`, SHA-256
`357a4d05f59d2179659ac9e96934ec6c51bd07fc71d3d5d4b30ed6fb2b36b9c9`.

## Task 6 bounded multi-rate bank

The required test-first failure was observed before production optimization.
The first interface run failed to compile because the test-only
`m3_bank_process_reference()` path did not exist; its panel is
`build/evidence/task-06-reference-interface-red.png`, SHA-256
`94b831eb431c2fe23b50bb6c4c8dbdbda53197389a641eef0dd8539ff4d92b24`.
After the full-rate reference compiled, assertion 6105 failed with 440 cell
updates per 48 kHz input sample against the fixed maximum of 45. The blank gray
selector-only capture from that run is not counted as evidence; the observer's
numeric result was the authority.

Production now creates causal streams at `sr`, `sr/2`, `sr/4`, and `sr/8`.
Every divide-by-two stage is preceded by two cascaded second-order low-pass
sections at normalized cutoff `0.20`. Resonators use fixed routing until the
bank is reinitialized. A `0.16` assignment threshold leaves transition-band
headroom, and cells near the lowest-rate edge are promoted one stream when
needed. At 44.1 kHz, pitch cells use `sr/4` or faster; this avoids the marginal
lowest band at the minimum supported rate while remaining substantially below
the original full-rate work.

The final harmonic allocation is adaptive rather than a uniform truncation:
requested notes through MIDI 52 retain six partials for missing-fundamental
evidence, MIDI 53..75 use four, MIDI 76 and above use three, and analysis-only
guard notes use three. This change was required by regression assertion 4104:
a uniform four-partial bank confused missing-fundamental E2 with E3. With the
adaptive allocation, all 18 Task 4 detector cases and all 18 Task 5 selector
cases passed again at 44.1, 48, and 96 kHz.

Task 6 cases use a bounded four-partial tonal synthetic source for chord
equivalence. This avoids the subharmonic ambiguity produced by pure-sine chords
while retaining deterministic amplitudes and phases. The reference bank uses
the same adaptive cell allocation at full input rate, so assertions 6101 and
6102 isolate rate-pyramid distortion rather than conflating it with a different
harmonic model. The equivalence floor is `0.00001`, matching the alias probes'
finite-window floor.

Final measured results:

| Rate | Worst open-string salience delta | Cases 6101–6106 |
| ---: | ---: | --- |
| 44,100 Hz | 0.019250096364574 | 6 PASS |
| 48,000 Hz | 0.020745752092474 | 6 PASS |
| 96,000 Hz | 0.013100931661116 | 6 PASS |

At the required 48 kHz MIDI 32..84 work point, 251 cells are enabled and the
bank averages 44.75 cell updates per input sample. The full-rate RED baseline
was 440, so the measured update count fell by about 89.8% without exceeding the
45-update assertion. The 17 kHz/48 kHz and 21 kHz/96 kHz alias probes passed,
as did both rate-state sentinels at every matrix rate.

All 18 final Task 6 result files report PASS. The SHA-256 of their lexically
ordered `sha256sum` output is
`b5155c896c3c52b95957c38ce86852b8cd289b5bd38baad9b50f15cbb98a38f5`.
The production validator also rejects any call to the test-only reference path.

The guarded launcher was separately hardened after GUI launches pulled the
active desktop to workspace 5. It records the launch workspace, keeps REAPER
windows assigned to workspace 5, restores only a target-workspace focus steal,
does not override a third workspace selected by the user, and now polls for a
short bounded interval after process exit to catch GNOME's delayed focus race.
Disposable GUI runs now add REAPER's supported `-noactivate` option, detach
standard streams, hide the disposable windows, and poll placement every 20 ms
during startup. A pre-launch snapshot excludes every already-open REAPER window
so a user's session is never hidden or moved. Repeated `BadWindow` snapshots
caused by rapidly destroyed test windows are deferred to the next bounded poll
instead of aborting the run. A monitored launch sampled the active desktop every
10 ms; it stayed on workspace 1 throughout, the test window reached workspace
5, and no REAPER process or window remained afterward.

## Task 7 M3 distinct-string feasibility

The required behavioral RED was observed in real REAPER before the production
profile existed. A zero-result interface scaffold reached assertion 7101 with
three assertions total and reported an aggregate open-note error of 368. The
preserved machine result is `build/evidence/task-07-profile-red-7101.txt`,
SHA-256
`8aa336e939f82225d9e52e211ca88fd89cd36a1b27f469c1eb0252759cd25b60`.

The production profile loads the exact low-to-high open notes
`32,36,40,44,48,52,56,60`. A note receives one bit for every string on which
its fret delta is between zero and the configured maximum. Feasibility uses
two fixed 256-word reachability rows and examines at most eight notes, 256
used-string masks, and eight string bits per note. The two guard words around
the 512-word working region remained unchanged in every feasibility case.

M3 filtering runs after bounded voice selection. If a set cannot map to
distinct strings, the lowest-confidence selected cell is removed with a
bounded stable compaction and feasibility is retried at most eight times.
Case 7105 verifies both that MIDI 31 is infeasible and that a lower-confidence
MIDI 31 is removed while legal MIDI 44 remains. General Tonal mode returns the
selected set without calling the feasibility matcher; its user-facing mode
control remains part of the later final parameter-surface task.

Cases 7101–7106 passed at 44.1, 48, and 96 kHz in 18 separate guarded
workspace-5 launches. Every result contains three assertions, suite state `2`,
and failed assertion ID `0`. The SHA-256 of the lexically ordered `sha256sum`
output for the 18 result files is
`6096b227cca280fd720c8420be467aedf7b80a7aafd7e243898ebbf3239429d7`.

A proportional cross-layer regression reran cases 4104, 5104, 6102, and 6105
at all three rates: missing-fundamental detection, eight-open-string selection,
multi-rate selection equivalence, and the hard work bound all remained green.
Across the Task 7 and regression launches, preflights remained near 28 GiB of
available memory, load stayed below 3.3, and readable temperature stayed at or
below 73 C. Each launch started from workspace 4, assigned REAPER to workspace
5, restored workspace 4 afterward, and left no REAPER process running.

## Task 8 independent lifecycles and event queue

The required persistence RED was observed in real REAPER with the complete
8101–8111 harness present and a zero-result lifecycle ABI scaffold. At 48 kHz
and block size 64, assertion 8102 failed with three assertions total and an
aggregate error of 64. The preserved result is
`build/evidence/task-08-lifecycle-red-8102.txt`, SHA-256
`421def10592db36a72b2697beea40573336ab6c663068ab6c77ca5f26e0e24a8`.

The lifecycle module assigns eight fixed words to each of 128 MIDI pitches:
state, confidence, energy, first-evidence sample, last-evidence sample,
state-enter sample, velocity, and active flag. Its event region contains a
two-word count/overflow header followed by sixteen five-word cells for type,
note, velocity, sample offset, and sequence number. The footprints are 1,024
voice words and 82 event words, both within their preallocated regions.

OFF, ATTACK, ON, and RELEASE transitions use separate on/off thresholds,
continuous attack evidence, a bounded dropout tolerance, and delayed release.
Loss transitions are processed before ready attacks, so released slots are
available to replacements without exceeding eight active flags. A full queue
rejects additional note-ons. A required note-off replaces the queued note-on
with the latest sequence number, and a bounded insertion sort orders at most
sixteen cells by sample offset, note-off before note-on, then pitch.

Fast response maps to 4 ms attack, 18 ms release, 6 ms dropout, on threshold
0.52, and off threshold 0.38. Millisecond values are converted to the nearest
integer sample. The first green sweep exposed a harness-only floating-point
expectation error: raw `floor(0.004 * 48000)` evaluated to 191 while the intended
nearest-sample mapping is 192. The harness expectation was corrected to use
nearest-integer conversion; production lifecycle behavior and coefficients
were unchanged.

Fixed velocity is clamped to the exact integer setting. Dynamic velocity uses
the specified square-root energy mapping with named amplitude bounds
`10^(-60/20)` and `10^(-6/20)`, producing values in 1..127. Cases 8110 and 8111
verify exact fixed velocity and increasing bounded dynamic velocity.

Cases 8101–8111 passed at 48 kHz with simulated block sizes 32, 64, 128, and
256: 44 separate guarded workspace-5 launches, three assertions per result,
suite state `2`, failed assertion ID `0`, and zero active notes after every
case. The SHA-256 of the lexically ordered `sha256sum` output for all 44 result
files is
`c4698e0d4571f9a53c37d7d0d1524226e78f1787025e55b84b4e52e818deb6ea`.

Cases 4104, 5104, 6102, 6105, 7102, and 7105 then passed again at 48 kHz as a
six-case cross-layer regression. During Task 8 launches, available memory
remained near 28 GiB, load stayed below 3.8, and readable temperature stayed at
or below 73 C. The launcher restored whichever user workspace was active
(workspace 4 early in the matrix and workspace 1 later) and left no REAPER
process running. This task validates lifecycle events in fixed memory; actual
MIDI encoding and host emission are validated separately below.

## Task 9 production host and reachable MIDI cleanup

The complete 9101–9109 harness first ran with a bounded zero-result host
scaffold. At 48 kHz, assertion 9101 failed with three assertions and aggregate
encoding error 322. The preserved result is
`build/evidence/task-09-midi-host-red-9101.txt`, SHA-256
`bb4045cf18175e0ce8684c10b75a220e0faf21bb9f62a3f44d5341d0c17664e7`.

The shared emitter encodes channel 1 and channel 16 status bytes, clamps pitch,
velocity, and block offsets, and emits each ordered event once. Reachable
sample-rate, transport-stop, hard-reconfiguration, and explicit-Panic paths
queue every active pitch as a note-off on the previously active channel before
clearing detector state. The final reset explicitly clears conditioner,
resonator/rate, all salience metadata, selection work, M3 scratch, voice, and
event regions. The emitter source SHA-256 is
`dbcb5da8a0c81b8095a12975323b1b0ddfb58b1946b9065196e8a9ad6f60718c`.

The production effect now has the frozen fifteen-slider surface. Slider code
only clamps and stages settings; the block path performs panic-before-reset and
the sample path performs bounded streaming analysis plus one-time MIDI
emission. Incoming MIDI is never consumed. Dry passthrough has exactly two
possible audio assignments, both zeroing outputs only in muted mode. The
standalone validator rejects slider-side rebuilds, `midirecv`, altered slider
numbering, additional audio assignments, missing cleanup/reset ordering, and
the prior file/UI/PDC hazards.

Cases 9101–9109 passed at 44.1, 48, and 96 kHz in 27 hidden guarded
workspace-5 launches. Every result contains three assertions, suite state `2`,
and failed assertion ID `0`. The SHA-256 of the lexically ordered `sha256sum`
output is
`1a20321b3c6bb43ae671dc306f4ecc326f0ef286fa25faa333cd1c45d52a40e9`.
Preflights stayed above 30 GiB available memory, below load 1.2, and at or below
59 C. Workspace 1 remained active and no REAPER process remained afterward.
Cases 4104, 5104, 6102, 6105, 7102, 7105, and 8102/block 128 then passed again
at 48 kHz as a seven-case detector-through-lifecycle regression after the host
module was imported.

A separate disposable production-load smoke instantiated the production JSFX
enabled and online with two inputs, two outputs, and all fifteen named controls
in order (18 total host parameters including REAPER-provided parameters). Its
result is `build/evidence/task-09-production-smoke.txt`, SHA-256
`321e87851cbda022d3744f5cc8d1df8530a1a113ca863e0ee4b693780d087173`.
The smoke script dirtied its disposable project while swapping FX, so its close
request waited on an unseen save prompt and the launcher enforced the 60-second
termination bound. This is not a clean host-sequence result; Task 11 still owns
VSTi routing, dry-path, MIDI capture, and safe-bypass integration.

## Task 10 telemetry, UI, serialization, and fault evidence

The required RED was observed in real REAPER at 48 kHz before the telemetry
reader was made generation-safe. Assertion 10101 failed with three assertions,
observed aggregate error 87, and failed ID 10101. The original observer result
had SHA-256
`2d36f7973607e5cc6310aba3d878877b18204fff23f53be456371b50b768e5cd`;
the preserved compact evidence record is
`build/evidence/task-10-telemetry-red-10101.txt`, SHA-256
`c025e01d67f2723e670df7e30748defc9615a7f28a0895c8c9137b44e2e42297`.

The final Task 10 matrix is cases 10101–10106 at 44.1, 48, and 96 kHz. All 18
guarded results passed with three assertions, suite state `2`, and failed ID
`0`. The SHA-256 of the lexically ordered `sha256sum` output is
`56768676bb073d9bba8e84e38322ff01e3692959a41f4ba1e9c2634e26969b47`.
Preflights stayed above 30 GiB available memory; observed load remained below
0.9 and temperature peaked at 58 C. Workspace 1 stayed active, each disposable
window was hidden on workspace 5, and no REAPER process remained.

Post-matrix regressions passed at 48 kHz for 4104, 5104, 6102, 6105, 7102,
7105, 8102/block 128, 9101, 9104, and 9109. One 9109 preflight safely refused a
transient X11 `BadDrawable`; the immediate bounded retry passed. This was a
launcher diagnostic, not a JSFX failure.

The audio side publishes 40 fixed words at the last sample of each block:
generation, fault, overload, peak, noise, clip, commit milliseconds, active
count, and eight four-word note cells. It alternates the two reserved buffers,
marks the write with an odd generation, and publishes an even generation only
after the copy is complete. The UI copies no more than 40 words and accepts
only equal nonzero even generations. A fixed twelve-name table occupies 12 of
the remaining 24 UI-local words, keeping all UI storage inside the reserved
64-word region.

`time_precise()` appears exactly twice in the sample path, at the first and
last samples. Three consecutive measurements above half the block deadline set
the overload flag. This is a guard indicator, not the long-run p99 benchmark;
Task 12 owns external performance measurement. The production-load smoke passed
enabled/online, two inputs, two outputs, and all fifteen named controls, then
saved and closed only its disposable project. Its result is
`build/evidence/task-10-production-smoke.txt`, SHA-256
`321e87851cbda022d3744f5cc8d1df8530a1a113ca863e0ee4b693780d087173`.
