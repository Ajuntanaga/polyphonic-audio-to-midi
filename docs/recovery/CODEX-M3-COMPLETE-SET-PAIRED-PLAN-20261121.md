# Paired training-error comparison

Compare the saved predictions of baseline44960075844 and loss-only
trial44962588969 on their identical training mixtures. Both rejected screens
stay frozen. No fitting, cutoff change, audio/model loading, held-out scoring
or new GitHub processing.

Collect artifact14730172985 once and verify its recorded server digest.
Extract only the report-pinned training predictions and mixture plan; leave
the model unextracted. Expected retained storage is about9.1MB. Reuse the
already collected baseline predictions and diagnosis.

Before interpreting, require report/member hashes, identical decompressed
plans and targets, original count reproduction and the same200 pass-1 source
keys. Use the existing ranking and error-class definitions. Keep both frozen
cutoffs; scores from different objectives are not calibrated probabilities.

Report exact-set and pitch gains/losses separately for each distinct-pitch
count, including silence. Retain every changed example, its missing/extra
notes, source components, and ordering against the strongest false pitch.
Stratify target transitions by scheduled relative gain, false-output
transitions by the fixed harmonic intervals, and enumerate single-pitch
regressions. Compare current five-pitch ranking failures with the prior
diagnosis. Strict separation remains an oracle bound, never a claimed gain.

The decision is which remaining error mechanism a distinct design must
address, including the single-pitch tradeoff. Do not select a new threshold,
exclude sources, change any gate or open held-out data from these results.
Installed output and labels remain unchanged; Claude is paused.
