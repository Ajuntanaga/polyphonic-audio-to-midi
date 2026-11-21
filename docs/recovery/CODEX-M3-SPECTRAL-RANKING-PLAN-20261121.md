# Saved training ranking diagnosis

Frozen before opening the saved prediction/plan members from run 44953542438.
This is report-only diagnosis of its rejected training screen, not a new gate,
fit, cutoff search, held-out evaluation or replay.

- Collect evidence artifact 14726114992 once; verify its recorded server SHA256
  `85e1269bafbf992764a47fbd5bfa89d998dd1cda900f92e3f506a892993d5893`.
  Extract only `train-predictions.npz` and `train-mixture-plan.json.gz`, checking
  their hashes against the already collected report. Do not open the model.
- Require finite 4096 by 53 scores in [0,1], Boolean targets, unchanged saved
  cutoff, exact plan/target correspondence, train-only source keys, exact source
  usage, and reproduction of the frozen TP/FP/FN and complete-set counts.
- For every nonsilent mixture compare the weakest true score with the strongest
  false score: strict positive margin, exact tie, or negative margin. A strictly
  positive margin is an oracle per-mixture threshold possibility, not a usable
  detector or measured improvement. Ties cannot separate the complete set.
- Count true pitches strictly above all false pitches in their mixture. Split
  frozen missed pitches into above, tied with, or below the strongest false score,
  and zero versus positive activity. No fitted replacement threshold is produced.
- Report by distinct pitch count 1–5, and by scheduled component gain relative to
  the strongest component. Use the loudest scheduled component for a duplicated
  pitch; report duplicated-pitch groups separately because coherent summation is
  not measured acoustic power. Keep all unisons in the main denominator.
- Retain per-example margins and per-target rows for the full local evidence.
  Do not use original-label uncertainty to exclude examples. These are synthetic
  training mixtures from one instrument/session, not corpus frame/string scores,
  MIDI, audibility or live readiness.

Decision: a high rate of false-over-true ordering rules out cutoff-only repair
for complete chords on those mixtures. Strict separation with frozen misses
instead points to calibration of the shared score scale, without accepting a
new cutoff. Report both populations; do not force a binary verdict on a mixture
of failure types. Any future implementation still needs its own frozen screen.
