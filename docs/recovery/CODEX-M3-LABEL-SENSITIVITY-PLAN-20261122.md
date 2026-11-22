# Saved-target sensitivity, frozen before calculation

Question: could the eight independently observed non-octave source disagreements explain the rejected held-out result sufficiently to change the next development decision?

Use only the already collected source-variation predictions and original mixture plans from run 44966587324. Verify their recorded hashes and original counts. No audio, model load, fit, cutoff change, remote job, source exclusion, or official label/score change.

Two report-only calculations, with all original examples retained:

1. Optimistic ceiling: grant every mixture containing one of the eight disputed sources a perfect complete set, leaving every other mixture's prediction unchanged. Also show the broader fifteen-source set including the seven unresolved octave cases. This deliberately overgenerous bound needs no replacement label. Report overall and by ORIGINAL distinct-pitch count, with the original 70% complete-set target. It is not achievable performance and does not assert that unaffected sources have verified labels.
2. Explicit hypothetical target substitution: for only the eight non-octave sources, substitute the periodic pitch already recorded in source-consistency-20261121.json. Rebuild each mixture's pitch set from all its components (preserving shared pitches/unisons), without altering predictions, cutoff, source roles, or mixture membership. Report original and hypothetical TP/extra/missing/complete counts, target cardinality changes, and per-example outcomes. The seven octave cases receive no proposed replacement. This is a sensitivity scenario, not a corrected benchmark, performance claim, or evidence of the player's intent.

Train and calibration should be identical because these eight sources belong to test. Reject the analysis if source/role/target identity or saved counts fail. Synthetic checks cover shared-pitch ownership, duplicate target merging, the perfect-row bound, and unchanged unaffected examples.

Decision rule: if even the optimistic eight-source ceiling misses an original complete-set gate, resolving those eight labels alone cannot accept this frozen model. The fifteen-source bound is a broader sensitivity check, not a reason to relabel octave ambiguities. Preserve the rejected result either way; no alternative manifest, refit, or automatic new experiment follows.
