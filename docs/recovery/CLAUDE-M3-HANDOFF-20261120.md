# Independent note52 calibration diagnosis

Read RESUME.md and github-reserved-assignment-costs-20261118.json first. Codex owns source edits and GHA dispatch. Please start read-only; return findings and a proposed minimal experiment, not another replay or code change. Preserve existing dirty files. No local native builds, installs, uploads, cleanup, or repeated downloads.

## Exact question
Why does note52 prefer physical lane0 instead of annotated lane1 at the chord starting sample7099417? Separate calibration confidence weighting, raw profile discrimination, and overlapping-note contamination. Do not assume the last cause without evidence. Identify a generic correction, not a label/time/note-specific rule.

## Authoritative evidence
Source0a5726b3b66b6bfe3e1bf9d5f547fb2ca28081c7; worker44417227738 is final and collected. Do not poll/rerun/download it. Root: build/github-results/reserved-assignment-costs-44417227738/.
- ordinary-harmonic-fixed-competition/report.json: both traced modes preserve complete snapshot and raw MIDI identity.
- evidence/**/retention-assignment-367-harmonic-admission-on-costs.tsv.gz: bounded73.9-74.2s trace,112 columns; unreserved_lane_terms contains real reserved costs. Actual reserved lane_terms are intentionally zero.
- reserved-assignment-counterfactual.json: original DP reproduced for367 frames per mode; frozen arithmetic only, not lifecycle prediction.
- reserved-cost-decomposition.json and calibrated-prior-transition-comparison.json.
- note52-profile-persistence.json: all302 captured selected rows prefer lane0 profile over lane1 by14.48158..14.48484 cost units, including242 active and81 unreserved rows. Window is not the whole held chord.
- note52-calibration-points.json: bank hash matches runtime manifest b7025b4fd3ea55901ea9f189966b4f62b6fe905ad16b9f8d0df88a0a1a76e997. Struct fields confirmed in native/src/calibration_state_image.cpp: confidence, observation_count, quality. Artifact's samples_raw means observation_count.

## Mechanism already established
Old note42 correctly occupies lane0 in preceding chord but persists into new49/52 chord. Releasing lane0 alone still assigns49/lane2 and52/lane0. Even releasing lanes0+1 and reducing fret weight1->0.005 leaves that same joint choice at7103807/7105023.
Only fret and profile costs are nonzero at those ticks. For49, lane0 profile advantage~2.91 loses to8-fret difference. For52, lane0 profile advantage~14.48 exceeds4-fret difference. Posterior and retention are zero in these decisions.
calibration_similarity_from_energy_profile uses cosine * quality * (0.75+0.25*confidence/32767), then assignment profile weight512. Note52 lane0 profile [32767,0,0,0,0,0], confidence31197; lane1 [32753,13,0,0,0,0], confidence27489; both quality1 and2 observations. Inspect this confidence difference against observed cost gap.
corrected_harmonic_energy compensates common tuning offset; it does not subtract other pitches. profile_harmonic_energy adds partial detuning correction.

## Do not repeat rejected approaches
Broad calibrated prior trial44267870125 vs44259013770: +2002 matches,-2133 false outputs but24 passage losses; label36 held26048->12928, label11114835->1395.
Earlier assignment_partial_experiment is rejected; build/modal/assignment-partial-v1-analysis.json reports no unison gain and protected losses/false-output growth.
Coasting-only release trial44413488077 improved aggregate matches/false outputs but49 held-label losses totaling399445 samples. Missing direct evidence alone is not safe release authority.

## Return
A concise causal finding with file/sample evidence; what remains unproved; smallest generic test able to distinguish explanations. Any candidate must retain OFF/reference identity, improve correct holds without passage/false-output regression, and later pass allocation, buffer, p99/max and host gates. Installed plugin remains unchanged; no live-readiness claim.

## Follow-up analytic bound
`build/github-results/reserved-assignment-costs-44417227738/note52-confidence-bound.json`: normalized lane0/lane1 profile distance0.00039691. Any common confidence multiplier <=1 bounds their shape-cost difference by0.20322, far below the4-point fret preference. Their unequal confidence weights alone permit14.48482 points at unit cosine, matching the observed14.48158..14.48484 gap. Lane0 confidence31197/32767 exceeds0.95, disabling settled-shape blending when playable (source6880). This supports testing confidence as reliability rather than an independent string preference; it does not validate a global equal-confidence policy or resolve joint/reservation lifecycle.

## Bank provenance and confidence semantics
The codec confirms quality1=measured and the count field=observation_count. tools/run_unison_spectral_shadow_experiment.py materializes the hash-pinned embedded factory bank; these are not newly measured replay calibration points. Do not interpret count2 as proof of only two raw audio frames or two independent physical plucks without tracing factory generation. native/src/string_calibration.cpp computes confidence from mean observation confidence times 1/(1+8*profile_variance): it is a reliability quantity, not a measured probability that a candidate came from that string. This semantic mismatch is a hypothesis for the cross-string offset; preserve strong-shape evidence when proposing a correction.

## Collaboration mailbox
User has authorized Codex and this open Claude session to work together. Claude session: Polyphonic audio to MIDI, CLI id 815b5e63-6552-4750-b29d-00290e65621a.
Codex writes this handoff; Claude writes `docs/recovery/CLAUDE-M3-REPLY-20261120.md`. Start the reply with acknowledgment and task ownership. Codex owns source changes and GitHub dispatch. Claude owns independent read-only diagnosis and proposed next experiment; do not edit source or launch processing.
Current dispatched trial: 44721049174, source dc83c97b1a8770bc953b4f4448b98ee3046b88ac, worker da9c329a2f86fd3e807562d4c857c1bc98ba4f55. It tests default-off common assignment confidence. Source portable 44720429648 and CI 44720429657 passed. Follow RESUME.md for updated collection state. Do not duplicate the trial.
This is a shared-file mailbox, not an automatic message transport. The desktop CLI cannot submit prompts to an existing session; initial user delivery is still needed.
