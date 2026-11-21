# Saved harmonic-context training errors

Written before opening the training prediction arrays from run 44960075844.
The completed screen remains rejected. This is one saved-array diagnosis, not
a fit, cutoff selection, held-out evaluation or new remote job. Claude is
paused; no fresh review by Claude is claimed.

Collect evidence artifact 14729601382 once, verify its server SHA-256, and
extract only `train-predictions.npz` and `train-mixture-plan.json.gz` after
matching their report hashes. Leave the model unextracted. Expected storage
is about 9.1 MB for the archive and two members. Preserve all source labels.

Use the existing `spectral_ablation_ranking.diagnose` definitions. Require
identity of the frozen cutoff, all aggregate/per-polyphony/per-pitch counts,
source-use counts, and the 200 pass-1 source keys before interpreting results.
Report all examples, including silence and duplicate-pitch mixtures.

For each distinct-pitch count, classify frozen sets as exact, missing only,
extra only, or both. For each missed expected pitch, report whether its saved
score exceeds, ties or falls below the strongest non-target pitch. Strict
`min(true score) > max(false score)` is only a per-mixture oracle separation
bound: no actual threshold or cardinality oracle will be applied. Do not
credit that bound as a recovered chord or relax the 99% precision/70% complete
set gates.

Stratify target miss rates by scheduled relative component gain, pitch and
harmonic relation to other true pitches; report five-pitch results separately
so chord-size composition cannot explain that comparison. A pitch is above
or below another true pitch when the signed interval is one of
`{12,19,24,28,31,36}` semitones. The four exclusive classes are above only,
below only, both, or unrelated. Use these same classes for false outputs and
show their denominators among all available non-target pitch positions.
Scheduled gain is not measured mixture power; relationships are associations,
not proof of a physical masking or harmonic mechanism.

Keep the frozen rejection and installed scoreboard unchanged. The outcome
should identify whether the remaining five-pitch failure is chiefly weak
target ranking, output cutoff placement, false-pitch ordering, or a mixture;
it can guide a distinct future design, but does not authorize retuning this
screen or opening the held-out roles.
