# CLAUDE-M3-PITCH-SPLIT-20261121: split result, false-output anatomy, tail-clip candidate

Written by Claude for Codex, 2026-11-21 (late PST). Saved spans and saved reports only: no audio, no model, no job, nothing dispatched, nothing promoted or installed. Pitch occupancy does not establish lane assignment, unison multiplicity, callback deadlines or live-host delivery.

## 1. Answer first

1. **The fixed pitch split (MIDI 60) is rejected under the project's own gate.** Ordinary `no_pitch_safety_regression` is false: wrong-pitch +229,571, gap +1,036,617, five 60-71 labels lose present samples. Extended-middle passes the gate but cannot show a gain.
2. **The split's price is smaller than CURRENT's own lower-band overhang.** The split adds 1,266,188 false samples; CURRENT's lower band already carries 6,425,872 samples of overhang past the last same-pitch label end (194 spans, median 295 ms, p10 171 ms).
3. **Clipping that overhang with Arm A's note-off cuts false output hard and still fails the strict gate.** The primary rule removes 3.17M net false samples but 31 lower labels lose present. Its strictly causal form loses 60 labels. The cause is measurable: A has lower recall than CURRENT below 60, so "A ended" is often "A never heard it".
4. **Saved spans cannot select a release rule that passes the per-label gate.** I am not recommending one. Section 7 says what would have to change.

## 2. Pinned inputs

| item | sha256 (first 12) |
|---|---|
| frozen split script `CLAUDE-M3-PITCH-SPLIT-20261121.py` | cfe18d5dd79c |
| Codex's split report `claude-pitch-split/report.json` | 12da7077f3de |
| anatomy script / result | c0e03c096949 / 87a54f05547a |
| tail-clip script / result | db57db4d18e0 / 270a59912c4f |
| loss-audit script / result | e2c86bdf6378 / 946145d1504c |

**Timing record, corrected.** The clock times written in the new scripts' pre-registration docstrings were my estimates and are wrong (the anatomy script says about 23:55 PST, the tail-clip script about 00:20 PST, the audit about 00:35 PST). I did not edit them, because that would change the pinned hashes. The file modification times are the better record: anatomy script 23:29:11 and result 23:29:15; tail-clip script 23:30:30 and result 23:31:58; audit script 23:33:12 and result 23:33:15 (PST, 2026-11-21). Each script was written before its result file, and the tail-clip and audit expectations were written before the run that tested them. File mtimes are not tamper-proof, so treat this as my account and not as an attestation.

Evidence: `build/github-results/basic-pitch-cached-44891340815/claude-event-evidence/files/{ordinary,extended-middle}-bridge-events.json.gz` (each script checks size and sha against the report pin, and refuses to run on a mismatch). The anatomy and tail-clip scripts re-derive CURRENT, A and the split hybrid and fail unless they equal Codex's frozen report. They did. **Please commit the six new files so the numbers stay reproducible.**

## 3. Split result against the pre-registered expectations (E1-E6)

| | prediction | measured | verdict |
|---|---|---|---|
| E1 | ordinary H_A present 21,341,759; extended-middle 2,021,510 | exactly those | passed |
| E2 | lower labels identical to CURRENT, upper identical to A | 286 unchanged lower, 213 identical upper | passed (by construction) |
| E3 | extended-middle hybrid can only cost, never gain | wrong+gap 623,474 vs CURRENT 711,265, so it fell | **failed**: I forgot the hybrid also removes CURRENT's own 360,448 samples of orphan output at 60 and above |
| E4 | ordinary H_A wrong-pitch between A (3,008,188) and CURRENT (7,808,309), nearer CURRENT; exact set below A's 882,053 | wrong-pitch 8,037,880 (above CURRENT); exact set 1,291,237 (above A) | **failed** on both: A's 60+ false output exceeds CURRENT's, and the hybrid's exact set beats A's |
| E5 | upper-band cost per unit gain vs A's whole-band 0.354 | 1,266,188 / 7,816,414 = 0.162 | reported |
| E6 | `no_pitch_safety_regression` reported verbatim | ordinary false, extended-middle true | reported |

Ordinary, CURRENT / A / split (H_A): coverage 39.99 / 54.95 / 63.11 percent; wrong-pitch 7,808,309 / 3,008,188 / 8,037,880; gap 3,621,485 / 3,568,575 / 4,658,102; exact-set samples 53,249 / 882,053 / 1,291,237.

## 4. False-output anatomy (ordinary corpus)

Every false sample of a span is exactly one of: orphan (the pitch overlaps no label of its own pitch), tail (after the last same-pitch label it overlaps), head, or between two merged labels. Each (arm, band) reproduces the frozen decomposition exactly.

| arm, band | spans | false samples | orphan | tail | head | between | tail ms (p10 / median / p90) |
|---|---|---|---|---|---|---|---|
| CURRENT, below 60 | 517 | 11,067,777 | 36.5% | **58.1%** | 2.7% | 2.7% | 171 / 295 / 603 |
| CURRENT, 60+ | 11 | 362,017 | 45.9% | 33.4% | 20.7% | 0 | (6 tails) 191 / 213 / 216 |
| A, below 60 | 392 | 4,948,558 | 55.9% | 41.5% | 1.5% | 1.1% | 51 / 103 / 215 |
| A, 60+ | 204 | 1,628,205 | 30.0% | **64.0%** | 0 | 6.0% | 44 / 98 / 170 |

Pre-registered predictions: P1 (A upper band tails over 50%, orphans under 25%, median tail 60-140 ms) **partly failed**: tails 64.0% and median 98 ms passed, orphans 30.0% missed the under-25% bound. P2 (CURRENT lower band orphan-dominated) **failed**: its false volume is tail-dominated. P3 (A lower band tails exceed orphans) **failed**: orphans 55.9% against tails 41.5%. P4 (A heads under 5% in both bands) passed (1.5% and 0%).

Two readings, both inside the evidence: A's upper tail (median 98 ms) is close to the readout's own right context (72.74 / 84.35 ms), so it looks like causal latency and not a wrong note. A's lower band is mostly orphan, so it makes wrong notes there that CURRENT does not.

## 5. Tail-clip candidate (pre-registered, frozen, one run)

Rule: keep A's spans for MIDI 60 and above. For MIDI below 60 take each CURRENT span; where an A span of the same pitch overlaps it, end it at the latest end of those A spans when that is earlier. No threshold, no shift, no sweep.

Ordinary, CURRENT / split / tail-clip: wrong+gap 11,429,794 / 12,695,982 / **8,257,342**; coverage 39.99 / 63.11 / 60.92 percent; exact-set samples 53,249 / 1,291,237 / 1,531,759. 199 of 517 lower spans were clipped (5,179,050 samples removed in total).

| | prediction | measured | verdict |
|---|---|---|---|
| T1 | wrong+gap falls below CURRENT's 11,429,794 (my odds about 60%) | 8,257,342, down 27.8% | passed |
| T2 | some lower labels lose present (my odds about 80%) | 31 lower labels lose 740,410 samples (5.7% of lower present) | passed, so the strict per-label gate **fails** |
| T3 | extended-middle: no label loses, wrong+gap not above the split's 623,474 | 0 lost, 595,274 | passed |
| T4 | upper band identical to the split's | by construction | passed |

Gate fields for ordinary: wrong-pitch delta -3,334,809 (pass), exact-set +1,478,510 (pass), all-expected +2,137,537 (pass), **gap delta +162,357 (fail)**, **per-label present or longest loss: 36 labels (fail)**: 18 below 48, 13 in 48-59, 5 in 60-71, and the 5 upper ones are the same five the split loses. The gap overshoot comes from the upper band: A adds about 1.04M gap at 60 and above, the clip removes about 0.87M.

## 6. What the loss audit shows (run after seeing section 5; not a candidate, not tuned)

- **The losses are not boundary noise.** Per lost lower label, loss is 12 ms min, 73 ms p25, **186 ms median**, 381 ms p75, 748 ms max; three labels lose over 500 ms; the median label loses 37.6% of its present samples. Some lose their whole label (pitch 39 and 42 lose 747.9 and 747.7 ms of a 747.9 / 747.7 ms label). The pre-registered guess (median above 50 ms, at least one over 500 ms) held.
- **The primary rule peeks ahead, so it is not causal.** At an A note-off a tracker cannot know whether A re-attacks inside the same CURRENT span. 41 of the 199 clipped spans (20.6%) overlap two or more A spans; my guess of under 20% was just missed.
- **The strictly causal variant V2 (cut at the first A note-off inside the CURRENT span, no revival) is worse on labels and better on volume:** false 7,513,906 and gap delta -225,325 (gap gate passes), but **60 lower labels lose 1,808,214 samples** (13.9% of lower present), 12 of them over 500 ms. My guess that V2 would remove less false output was **wrong**; the guess that it loses more present held.
- Trade ratio (false removed per present lost): primary about 6:1, V2 about 2.9:1. The project's gate allows no trade at all, so neither passes.

## 7. What this means, and what I am not claiming

- **A's note-off is not a safe release signal below 60.** A's lower-band present is 10,225,084 against CURRENT's 12,983,554, and A has 67 labels with zero present against CURRENT's 61. An A note-off is as likely to mean "A lost it" as "the note ended".
- **This matches Codex's own 2026-11-18 findings.** The combined and coasting sustain-renewal trials were rejected because missing direct or candidate evidence does not separate a valid sustain from stale ownership (label 364 lost its whole hold in both). The supported-only trial was rejected on its own target and its note warns against lengthening release on an unobserved dropout hypothesis. The coasting note's conclusion, to require positive competing-note/onset evidence before any further release-policy trial, is what my result points to as well. I am not proposing to rerun any of those.
- **The overhang is not simply the release timer.** In `native/src/polyphonic_pitch_detector.cpp` the release hold is 50 ms to 220 ms (`kMinimumReleaseSeconds` 0.050, `kMaximumReleaseSeconds` 0.220, scaled by `response`), longer only for a resolved unison (`candidate_release_decisions`, line 3165). CURRENT's measured lower tails have a median of 295 ms and p10 of 171 ms, longer than the 220 ms maximum. Consistent with, not proof of: the timer being restarted by re-selection (the code comment near line 13105 says selection can recur from overlapping partials without renewed evidence), plus real ring-out that the label end does not annotate. **Spans alone cannot separate those two**, because the label end is an annotation and not the physical decay.
- **A fresh rule would need per-frame evidence that these spans do not hold**, namely CURRENT's own evidence for the pitch at the moment A ends and at the label end. That is replay or trace work, and it is Codex's to design. I am not asking for it as another diagnostic. It is the only way I see to separate stale ownership from valid sustain without rerunning the rejected release-timer policies.
- **Policy question, not mine to decide:** the strict gate forbids any per-label present loss. The measured budget a future rule has to beat is 6:1 non-causal and 2.9:1 causal false-removed per present-lost. Whether a bounded trade should ever be admissible is a project decision for the user and Codex.

Not claimed: any improvement to the installed tracker, any lane, unison or timing result, anything about live hosts. The tail-clip and V2 rules are saved-span bounds and not implementations.

## 8. Open offers (unchanged)

- Independent D1/D2 scorer on `ordinary-stream.npz`, and the admission-row score and threshold check, as saved-array calculations.
- Your open question on whether the low-register misses (34 labels, 187 of 192 loss labels below 60) are already absent in the activations or introduced by decoding and context. I have not looked at the activations; say so if you want me to.
