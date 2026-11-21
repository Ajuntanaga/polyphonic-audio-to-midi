# Claude: wrong-note census and sub-harmonic link — 2026-11-21

Saved v5 table only (`ordinary-current-on-512`, sha256 b664c7ff…); no audio, no dispatch, no replay. Scripts `CLAUDE-M3-WRONG-NOTE-CENSUS-20261121.py` and `CLAUDE-M3-SUBHARMONIC-GHOST-LINK-20261121.py` (+ `.json`), definitions written in their docstrings before the numbers; one run each, the second amended once (a control, noted in its docstring) after the first result. Associations only, one dataset and configuration, annotation is not audibility. Nothing here proposes a rule.

## Wrong-note voices (outcome 1): 161,526 non-quiet frames of the 164,263 in CURRENT (2,737 are on quiet ticks, excluded)

- **Register:** 77.3% below note 48, 20.6% at 48–59, 2.1% at 60–71, 0.0% at 72–84. The upper-note thread (relief, lane at 61+) touches the register that holds 2% of wrong-note frames.
- **Context:** 92.1% occur in ticks with three or more labeled notes, 7.9% with two.
- **Relation to a labeled note of the tick:** 50.3% sit a harmonic interval (12/19/24/28/31/36) below one; 19.6% unrelated; 16.8% within 1–2 semitones of one; 13.3% a harmonic interval above one.
- **State:** 54.2% selected, 45.8% coasting; 0.2% rebinned. So 46% of wrong-note frames are held-over notes, not fresh selections.
- **Runs:** 13,799 runs (same rendered note, consecutive ticks). 267 runs of at least 100 ticks hold 103,400 frames (64% of wrong-note frames, longest 1,123 ticks); 10,881 runs of at most 4 ticks hold 22,298 frames (14%). Wrong notes are mostly long sustained holds, not flicker.

## Do missed labeled notes get replaced by a sub-harmonic ghost? No, not specifically.

A missed labeled note had a wrong-note voice a harmonic interval below it in the same tick in 28.8% of 60–71 misses (38,275 of 132,917), 20.5% at 72–84, 19.6% at 48–59, 7.7% below 48. The control matters: rendered correct labeled notes show the same rate (60–71: 28.7%; 48–59: 18.8%; below 48: 2.0%; 72–84: 0 of 554). At 48–71 the ghost presence is a base rate of dense chords, not a replacement mechanism. Below 48 it is elevated (7.7% vs 2.0%) on a small miss pool; 72–84 has too few rendered controls to judge.

## Open, not tested

Since 46% of wrong-note frames are coasting and 92% sit in multi-label ticks, a large part may be notes carried over from a just-ended label into the next chord (hold ring-over), which the evaluator counts as wrong-note. Not tested: whether a wrong-note run's pitch was labeled in the preceding ticks. That needs one more predeclared pass over this table (no new processing) and would connect this class to the false-hold work (label 42).
