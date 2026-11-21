# Frozen complete-set objective screen

The previous context model recovered 43,101/45,698 training pitches at 99.005% pitch precision but completed only 1,547/2,529 five-pitch mixtures (61.17%; target 1,771). Saved training diagnosis found 863 missing-only failures, 48 extra-only and 71 mixed failures. In 500 mixtures a false pitch outranked the weakest true pitch; another 482 were strictly separable but incomplete at the frozen cutoff. A cutoff-only repair is not this experiment.

## One change

Keep the network, 62 harmonic coordinates, pooled training-only normalization, all source roles, all 16,384 training mixtures, initialization/order seed, Adam settings, 80 epochs, batch size and cutoff selection rule fixed. Change only the loss to mean pitch BCE plus a complete-set term with coefficient 1. For each mixture, compute the largest positive logistic loss over true pitches and the largest negative logistic loss over false pitches; average the available polarities, then average mixtures. A silent mixture contributes its strongest false pitch only. No per-note weights, sweep, architecture change or oracle cardinality at inference.

This directly emphasizes the weakest chord tone while retaining absolute pitch calibration and false-pitch penalties. It can also overfocus hard/ambiguous mixtures, reduce otherwise correct pitches, or fail to transfer across recording passes; none of those outcomes will be repaired by tuning this frozen screen.

## Execution and gates

One CPU-only GitHub Actions job, `harmonic-complete-set-learning.yml`, using the standing authorization in `m3-standing-job-authorization-20261121.json`. Source and worker SHAs recorded before dispatch. No new input upload. Existing four release hashes, source manifest, baseline and source-consistency metadata remain pinned. All 555 original labels retained. The decompressed training-plan hash must equal run44960075844 before fitting; gzip headers are not compared.

Synthetic tests run before recorded processing: loss formula and hard-pitch gradients, silence/all-positive cases, batch and pitch ordering, ties/extremes, persistence, fail-closed stage progression and unchanged source/clock/scoring tests. Local Torch is not installed; Torch execution remains on GitHub.

Training: select the single cutoff by maximum train TP at >=99% precision, stricter tie. Require recall>=80%, exact sets>=70% overall and separately for three, four and five pitches, and zero silence extras. Five-pitch integer target is 1,771/2,529. Failure ends the screen before any held-out scoring.

If training passes, score the 4,096 calibration and 4,096 test mixtures with no fit or cutoff adjustment. Each requires precision>=95%, recall>=80%, exact sets>=70% overall and each three/four/five-pitch stratum, plus zero silence extras. Only if both pass, replay ordinary and extended-middle once on the existing measured FIFO protocol; require >=5 percentage points ordinary pitch coverage gain and no per-label presence/longest-hold loss, wrong-pitch or extra-gap growth on either recording.

Collect the small report once with server-digest verification; keep model/predictions remote. Report paired training counts and every attempted gate, including rejection. No automatic rerun or cutoff retune. Installed tracker, labels and scoreboard unchanged. This is sustained-mixture pitch learning; string assignment, attacks, unisons, native allocation/deadlines and external MIDI delivery remain unverified.

Claude is paused; no fresh Claude review is claimed. This follows the recorded training diagnosis rather than reopening completed work.
