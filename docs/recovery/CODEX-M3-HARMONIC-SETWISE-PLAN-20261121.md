# Frozen setwise training objective

Status: frozen before implementation and fitting. One bounded CPU GitHub experiment under the standing M3 job authorization; Claude remains paused. No fresh Claude review is claimed.

## Problem and experiment

Run44962588969 improved five-pitch complete sets to1759/2529 but failed the1771 target. It also reduced complete single-pitch sets3108->3097/3132 and increased their false pitches18->32. Paired diagnosis shows all22 lost previously exact single-pitch mixtures retained the intended pitch and added extras;24/26 new false pitches were outside the fixed harmonic-interval set. Do not rerun that objective or retune its cutoff.

Replace only its added worst-polarity term with a setwise log-sum-exp term. For each mixture with logits z, true set P and false set N:

    BCE_mean + batch_mean(log(1 + sum(P, exp(-z))) + log(1 + sum(N, exp(z))))

The additional coefficient is1. The two polarity terms are summed, not averaged; empty sets contribute0. Use a zero sentinel and masked logsumexp for numerical stability. Every finite true/false logit receives a correctly signed additional gradient, with larger errors weighted more. This may address multiple extras and weak chord notes; it guarantees neither single-example preservation nor better transfer.

The added term follows [ZLPR equation1](https://arxiv.org/html/2208.02955v1#S1.E1). Our experiment retains mean BCE and the existing train-only cutoff rule, rather than the paper's fixed zero-logit readout. Gradient scale changes along with the pooling rule, so a result cannot isolate those effects.

## Frozen scope and decision

Specification: `harmonic-setwise-learning-20261121.json`. Same14,465-parameter network, harmonic features,16384 training mixtures,200 training sources, seed,80 epochs, optimizer, schedule and training-plan hash. All555 labels retained. No replay of rejected configurations, threshold sweep, source exclusion or held-out fitting. Preserve the existing training, two held-out and continuous acceptance gates exactly. Fit once on GitHub CPU; score held-out roles only after training passes; continuous only after both held-out roles pass.

Report the single-pitch reference3108/3132 exact,18false,8missing next to the new figures. Any regression leaves the preservation objective unmet even if aggregate research gates pass. Report five-pitch exact vs1771/2529 separately; never average the two. Failed gates stop the screen. No automatic rerun, install, promotion or native/host claim.

## Verification and provenance

Synthetic checks: exact formula, extra gradients on non-worst true and false logits, multiple-false penalty, silence/all-true sets, finite extremes/ties, pitch permutation and batch reduction, invalid targets, objective fit/save/restore, unchanged specification and fail-closed orchestration. Torch checks run on GitHub; no local install or recorded processing. One focused code review before one dispatch; pin source/worker SHA and collect the small report once with server digest verified. Keep the model and bulk predictions remote unless a named later diagnosis requires them.
