# Pitch-local residual screen rejected

Run `44956322150` completed successfully, but the frozen method failed its training chord gates. It supplies no installed tracking improvement. Held-out scoring and continuous replay did not run.

Source `bd8017ffcab2b41649fb347ee1cbd18aa4172d86`; worker `e16a4294413cba341ff8282d11c3cc340714bdf0`. Source CI `44956304105` passed native tests, replay comparison contracts and synthetic buffer parity. All 47 synthetic checks also passed in the worker. These checks establish implementation behavior, not chord quality or live readiness.

| Training measure | Prior power-ablation run44953542438 | New local-residual run44956322150 | Frozen target |
| --- | ---: | ---: | ---: |
| Expected pitches recovered | 3625/11489 (31.55%) | 137/11489 (1.19%) | >=80% |
| False pitches | 36 | 1 | Precision >=99% |
| Precision | 99.02% | 99.28% | >=99% |
| Complete pitch sets | 951/4096 (23.22%) | 219/4096 (5.35%) | >=70% |
| Complete 3-pitch sets | 24/799 | 0/799 | >=70% |
| Complete 4-pitch sets | 2/889 | 0/889 | >=70% |
| Complete 5-pitch sets | 0/635 | 0/635 | >=70% |

The total includes 205 silent mixtures, all exact. Only 14/3891 voiced mixtures were complete. The train-only cutoff 0.9857675820830275 maximized recovered training pitches while keeping precision at least 99%; it was not adjusted after the result. Recovery falls by 3488 expected pitches and 30.36 percentage points relative to the preceding screen. Fewer false pitches accompany far fewer detections, not a useful safety/coverage tradeoff.

The local addition did produce positive support for 3153 of 173179 globally inactive pitch evaluations. That is a mechanism observation, not an accepted-note count or a labeled gain. At the frozen cutoff, all 137 true detections are notes 80, 82, 83 and 84; the single false detection is note 76. The report does not establish why this selectivity occurs. The result rejects this conditional-residual design, not every possible residual estimator.

All 555 original source rows and intended labels remain included. No source-consistency metadata filtered fitting or scoring. No corpus output, string assignment, unison multiplicity, MIDI lifecycle, native timing or live-host result was produced by this screen. Installed/default output and the installed scoreboard remain unchanged.

The small report artifact `14727054292` was collected once and its server digest verified: `910c3ec043052cea1dec5aef626f320fc642eba20aad34793890e5766331d7f0`. Report: `build/github-results/pitch-local-residual-44956322150/artifact/pitch-local-residual-result/report/report.json`. The 5068730-byte evidence artifact `14728375272` remains remote. Compact counts and provenance are in `pitch-local-residual-summary-20261121.json`.

Next is a distinct chord-evidence design with Claude when available. Keep the training 99/80/70 precision/recall/complete-set gates, each 3/4/5-pitch complete-set gate and zero silence extras before held-out and continuous safety checks. No cutoff retune, rerun, promotion or next job is queued. Claude is paused; this result does not claim fresh joint review. The broader live-readiness goal remains open.
