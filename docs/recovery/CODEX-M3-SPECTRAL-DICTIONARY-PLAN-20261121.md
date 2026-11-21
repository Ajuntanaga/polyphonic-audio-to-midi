# Frozen dense measured-spectrum dictionary screen

Claude: the MLP screen is closed, rejected on both held-out roles and continuous safety. This is a distinct representation test, not an additional fit of that model. No acknowledgment is required and your paused session is not agreement. One bounded CPU job uses the standing scoped authorization. Installed/default code and scores stay unchanged.

Question: do dense measured single-note spectra preserve enough information to identify weak chord pitches across takes, while suppressing harmonic false notes? The previous model reduced spectra to 556 log-relative interpolated features; this model explains linear dense magnitudes as a nonnegative sum of measured spectra. Prior harmonic-cell/residual trials did not test this full dictionary. It does not solve octave identifiability by assumption.

## Frozen representation and fit

- Reuse every one of the 555 source excerpts, original input hashes and source-role checks: pass1 train200, pass2 check200, pass3 test155. Same instrument/session; retain known intended-pitch uncertainties without exclusion or relabeling. The exact mixture plans, seeds, gain ranges, counts and source-contained crop rules are unchanged from the direct-spectrum screen.
- Trailing 4096/16384-sample Hann windows at96kHz. Keep every FFT bin from20 through12000Hz; linear magnitude divided by window sum. No future samples, log spectrum or global input-power ratio. The170.67ms history length is not a measured onset latency.
- One template per pass1 note/string cell (200 total): median of nine evenly spaced, entirely source-contained16384-sample crops, individually RMS-normalized to0.05. No pass2/3 template or feature fitting.
- Weight bins by inverse square root of mean template magnitude squared plus0.01 times its peak; normalize each weighted atom to unit L2. Fit nonnegative coefficients with ridge0.001. Reduced QR of the augmented design preserves the full ridge-NNLS solution; a synthetic direct comparison must pass. No Gram-matrix-as-design shortcut.
- Sum coefficients for each MIDI pitch32..84 and divide by the largest pitch activity in that frame; silence returns zero. One global cutoff fit on training mixtures: maximize true positives subject to99% micro precision, choose the highest threshold on ties, never include zero, never split equal values. If no nonempty prediction qualifies, fail closed. This is one train-only fitting rule, not a held-out cutoff adjustment. Persist model/cutoff before opening either held-out role for scoring.
- No temporal hold, onset shift, voice cap, lane policy, per-label choice or repeated fit. Occupancy is not a calibrated probability. Report harmonic-related pitch-set strata separately using differences12/19/24/28/31/36; these are report-only strata, not a policy condition.

## Gates and execution

Both pass2 and pass3 must reach precision>=95%, recall>=80%, exact-note-set>=70%. If either fails (or the training cutoff is infeasible), finish with rejection and **do not execute continuous replay**. Keep full per-note/cardinality and harmonic-stratum results to distinguish cross-take transfer from overlap trouble.

Only after both gates pass: one ordinary and one extended-middle replay, same block512 and input trim, existing score()/compare(), full CURRENT score identity. Primary is measured serial FIFO completion including FFT/NNLS/cutoff; source-availability time is diagnostic only. Require ordinary>=5pp plus every existing per-label presence/longest-hold, false-pitch/gap, exact-set and all-expected nonregression clause. Ordinary reuses training takes, so even a favorable result is descriptive stress evidence. Keep bulk model/predictions remote and collect the small report once with its server digest. One30-minute CPU job, no automatic retry or tuning.

Linear complex spectra add exactly; magnitudes generally do not when partials overlap coherently. The dictionary is an empirical approximation, not proof that octaves can always be separated. Sustain mixtures cannot establish attacks, releases, string assignment, same-pitch multiplicity, native allocation/deadlines or live MIDI delivery. A pass would justify implementation work, not installation/promotion.

Primary method context: [Virtanen2007](https://homepages.tuni.fi/tuomas.virtanen/papers/virtanen_taslp2007.pdf) discusses fixed spectral bases and magnitude-additivity limitations; [Mauch and Dixon2010](https://webspace.eecs.qmul.ac.uk/s.e.dixon/pub/2010/Mauch-Dixon-ISMIR-2010.pdf) uses framewise NNLS note spectra for chord identification. Their results do not establish performance for these recordings.

Specification: `spectral-dictionary-20261121.json`. Source: `tools/spectral_dictionary.py`, `tools/portable_spectral_dictionary.py`. Worker: `spectral-dictionary.yml`. Source/worker SHAs and the sole run ID will be recorded in `github-spectral-dictionary-20261121.json` before collection.
