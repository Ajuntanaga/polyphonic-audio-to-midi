# Saved prediction diagnosis: single sources and mixtures

Frozen before collecting/reading prediction arrays from completed source-variation run `44966587324`. Its rejected screen, cutoff, original labels and all acceptance gates remain fixed. This is a descriptive diagnosis of reused development roles, not a new held-out benchmark or a policy test.

Collect artifact `14731592882` once, verify its recorded server digest, and extract only the three original role plans and three prediction arrays. No model extraction/loading, recorded audio access, fitting, threshold selection or remote processing. Expected archive size is 8,013,695 bytes; selected files add about 6.9 MB. Keep the archive and receipt.

Reproduce each role's original overall, per-pitch-count and per-note counts and source uses. Verify the source-manifest pin, all 555 source keys, role isolation, plan order, component metadata, Boolean targets and frozen cutoff. A failed identity stops diagnosis.

Definitions fixed before inspection:

- A singleton has exactly one component. A multi-component unison is not a singleton even when its target has one distinct pitch. Silence remains in all original denominators.
- Produce one row per source: role, key, string, intended pitch, existing consistency status, singleton count/target misses/exact failures/false pitch cells, mixed occurrences, mixed exact-failure exposures, and unique-source intended-pitch misses by distinct pitch count. Mixed exact-failure exposure is non-additive and cannot attribute an extra output to that source.
- A source's singleton status is `unknown` (no singleton), `never_exact`, `sometimes_exact`, or `always_exact_observed`. The last name describes only sampled rows, not reliability on unmeasured crops. Separately retain whether its intended pitch was ever missed.
- In mixtures, count intended pitches once. If two components share a pitch, keep that target in an explicit unison bucket; do not assign it to either source. Stratify uniquely attributable targets by source singleton status, pitch band (<48, 48–59, 60–71, 72–84) and scheduled gain relative to the loudest component. Gains are not measured source audibility.
- Classify each mixed example once as all sources observed exact alone, at least one observed singleton error, or otherwise unknown. Report exact failures, missing and extra pitches for every bucket; no filtering of original scores.
- Count matching source/crop/effective scheduled gain singleton observations for mixed unique-pitch targets. Only matched observations could support a paired contrast; unmatched clean-singleton versus mixed differences are associations, not proof of masking.
- Existing consistency metadata is descriptive only, including the explicitly unexamined sources. No exclusion, relabeling or alternate score.

Interpretation: singleton failures demonstrate a transfer problem without simultaneous-note interference for those sampled examples. Mixed failures from sources that were exact alone identify an additional context/level question but do not isolate its cause. If crop/level-matched controls are absent, name that limitation instead of launching a speculative repeat. Choose the next design from these two observed error populations without tuning on held-out rows. Installed scores and live-readiness claims stay unchanged.

Validation: small synthetic cases for singleton versus unison, missing singleton coverage, duplicate target accounting, role/target mismatch, and crop/level matching; original count reconciliation on the saved arrays. One read-only collaborator review of generator semantics has confirmed the unpaired-crop/level and role/protocol limitations. Claude is paused; no new Claude review is claimed.
