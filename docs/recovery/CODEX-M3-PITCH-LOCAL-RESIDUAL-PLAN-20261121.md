# One pitch-local residual screen

The saved power-ablation rankings reject cutoff-only repair: oracle complete
3/4/5-pitch ceilings were 33.42/17.32/6.30%, and 2,956 expected pitches had zero
activity. This screen changes the evidence, not the old cutoff. Standing job
authorization is recorded in `m3-standing-job-authorization-20261121.json`.
Claude is paused; this is not a new Claude review or an unfinished split task.

## Frozen estimator

Reuse the pinned 555 original source excerpts, roles, mixture plans, nine-crop
training templates and trailing 16,384-sample averaged-power representation.
For each MIDI pitch 32..84, form a fixed mask of bins within two FFT bins of an
A440 integer harmonic up to 12 kHz. Multiply shared-bin weights by the inverse
square root of the number of pitch masks covering that bin. No annotation or
recording-specific pitch estimate constructs the mask.

On each of the two alternating spectral folds, fit all competing pitch atoms
with globally training-whitened, unregularized NNLS. QR reduction preserves
that objective; no ridge shrinkage residual is allowed into the score. Remove
all atoms for the target pitch together. Reuse the full null solution only
when the full optimum already assigns zero to that group.

Hold these nuisance coefficients fixed. Fit a nonnegative target-only addition
to the masked residual on the fitting fold. Target column norms are measured
on that fold only and carried unchanged to the other fold. Candidate ridge is
0.001 times target atom count, after that normalization. Score the positive
fractional reduction of masked null residual SSE on the held fold; residuals
below 1e-12 of local observed energy get zero. Swap folds and take the minimum.
Test every represented pitch, including globally inactive groups.

This is a conditional addition heuristic, not a local full-refit likelihood
ratio: nuisance atoms are fitted globally and then held fixed for the local
addition. Shared harmonics and template mismatch can still yield false notes.
Mask bins are correlated, and nominal masks can miss detuned partials. These
risks are judged by the fixed gates, not by a claim that residual support is
probability or audibility.

## Fixed execution and acceptance

One CPU GitHub workflow `pitch-local-residual.yml`, at most 45 minutes, existing
private release inputs only. No local audio, model fitting on recordings,
native replay, new data upload, label alteration, installed/default change or
promotion. The public source repository receives only source/spec/docs.

Use 4,096 training mixtures and the existing train-only cutoff procedure:
precision >=99%, recall >=80%, complete sets >=70% overall and separately for
3/4/5 distinct pitches, zero silence extras. Failure stops before held-out
scoring. If training passes, both 1,024-mixture source-disjoint held-out roles
must separately reach precision/recall/complete sets >=95/80/70%, each 3/4/5
complete-set gate, and zero silence extras. Do not change any threshold after
seeing the result. All original source labels, including unresolved intended
pitch disagreements, stay in every applicable denominator.

Only after all representation gates pass, run the existing ordinary and middle
continuous comparison with CURRENT identity, >=5pp ordinary pitch-presence
gain, no per-label presence/longest-hold loss, no wrong-pitch or extra-gap
growth. Report Python FIFO timing separately from native realtime/live-host
acceptance. Training/held-out/pitch-presence metrics never replace installed
labeled-frame/string scores. Small report collected once; bulk stays remote.

## Direct checks before dispatch

Small synthetic checks cover exact-parent false-upper support, weak pitches,
globally inactive local evidence, fold disagreement, duplicate-atom projection,
feature geometry, silence/scaling and the remote-only guard. Existing runner
tests cover fail-closed training/held-out orchestration. A focused read-only
mathematical review identified ridge shrinkage as the actionable defect; the
unregularized all-competitor null fit resolves it. No broader review loop.
