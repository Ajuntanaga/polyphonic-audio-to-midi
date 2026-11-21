# Paired complete-set training result

The complete-set objective improves chord recovery, but does not preserve all previously correct outputs. The original screen remains **rejected**: five-pitch complete sets are 1759/2529 (69.5532%), twelve short of the unchanged integer target 1771 (70.0277%). This saved-array diagnosis changes no model, cutoff, annotation or installed output.

## Paired result

Baseline run44960075844 and trial44962588969 used identical 16,384 training mixtures and 200 pass-1 source takes. Classification uses each run's original training-selected cutoff, 0.7022203803062439 and 0.4006813168525696 respectively. Their raw probabilities are not calibrated to one another.

| Distinct pitches | Mixtures | Baseline exact | Trial exact | Exact gained / lost | Expected pitches gained / lost | False pitches new / removed |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 820 | 820 | 820 | +0 / -0 | +0 / -0 | +0 / -0 |
| 1 | 3132 | 3108 | 3097 | +11 / -22 | +2 / -1 | +26 / -12 |
| 2 | 3220 | 3043 | 3069 | +78 / -52 | +55 / -21 | +53 / -39 |
| 3 | 3251 | 2832 | 2946 | +180 / -66 | +162 / -40 | +82 / -79 |
| 4 | 3432 | 2515 | 2775 | +365 / -105 | +328 / -133 | +113 / -128 |
| 5 | 2529 | 1547 | 1759 | +303 / -91 | +378 / -177 | +89 / -98 |

Overall, 937 newly exact mixtures and 336 losses produce the net gain of 601 (13,865 to 14,466). Expected pitches gain 925 and lose 372. False pitches add 363 and remove 356, with 77 persistent: 433 to 440. Silence stays exact on all 820 examples. All 1,741 examples with changed pitch decisions are retained, with source components, predictions, missing/extra pitches and within-example ordering.

## Single-pitch regression

All 22 previously exact single-pitch mixtures that regress retain the intended pitch and add extras. Eleven other mixtures become exact, giving the net decrease 3108 to 3097/3132 (99.2337% to 98.8825%). Missing expected pitches improve 8 to 7, while false pitches rise 18 to 32. Of 26 new single-pitch false outputs, 24 have none of the fixed interval relationships {12,19,24,28,31,36} to the expected pitch; one is above and one below. This descriptive interval category does not prove a physical non-harmonic origin, but an octave-only suppression rule would not address most of these additions.

Nineteen of the 22 regressing mixtures still rank the true pitch above every false pitch; three do not. This is an oracle ordering observation, not permission to select another cutoff. No single-pitch gate was added retroactively to the rejected screen: the decline is a measured tradeoff relevant to the existing no-regression project goal.

## Remaining chord errors

Of the 770 failed five-pitch mixtures, 666 miss pitches only, 49 add pitches only, and 55 do both. The trial has 963 missed expected pitches and 115 extras. Scheduled -24/-18 dB components account for 669/963 misses (69.47%) on 3702/12645 targets (29.28%). These are scheduled relative component gains, not measured mixture power or an audibility judgment.

Strict separation of all true pitches from all false pitches increases 2029 to 2124/2529 (80.23% to 83.99%): 187 mixtures gain separation and 92 lose it. The current 770 failures divide into 365 with strict separation but failing the frozen cutoff and 405 with ordering failure. An oracle per-example threshold could exploit separation; the detector has no such oracle. Neither the 83.99% bound nor the saved diagnosis is an operational gain.

The next design must improve weak true/false separation and preserve isolated rejection together. Simply lowering a global cutoff is not supported by this tradeoff.

## Provenance and verification

- Baseline source: `a5f46bab45be9cf87126f21426857358c6f75b2d`; trial source: `f6d3fb3e7796f1734a96597e8eda4aaeae7a50d1`.
- Trial worker: `953f3be4b5a5b98b19d5c59df761197fc0b9954c`. Its completed CPU workflow and source CI passed, including 60 remote synthetic checks. No new remote job ran for this diagnosis.
- Artifact14730172985, `m3-harmonic-complete-set-evidence-44962588969-1`, collected once with server SHA256 `a23bc1cdf58e1d03b6d0ad8c6c90c05bafa6dd35dcd554c4c085975eb350f209`. A timed-out partial download was resumed, not restarted. Archive plus the two extracted training members retain 9,080,200 bytes. The model remains unextracted and unopened.
- Original aggregate, per-polyphony and per-note counts reproduce exactly. Targets, decompressed plan bytes and all 200 source-use identities match. Plan SHA256: `7c5c676126082c3bae9fb68dc03cec20f583951c44b7e7de1c84b1ca7b72d25d`.
- `python3 -m unittest tests.test_harmonic_complete_set_comparison tests.test_harmonic_context_ranking tests.test_spectral_ablation_ranking`: all 14 synthetic checks passed, no skips. One focused review found no material blocker.
- Machine report: `build/recovery/m3-complete-set-paired-20261121/report.json`, SHA256 `5481b16a3d633d989091c97e143565740ac07d3fe4cbb2eb7e8fe6efe90216a3`.
- Detail files: `changed-examples.json.gz` and `current-ranking-details.json.gz` beside the report; their hashes are recorded in it. Collection receipt: `build/github-results/harmonic-complete-set-learning-44962588969/training-evidence-collection-receipt.json`.

No audio or model was opened, no fitting or threshold selection was performed, and no held-out/continuous scoring ran. All 555 source labels remain. These are training-mixture pitch decisions, not tuner frame/string scores, delivered MIDI, timing or live readiness. Claude is paused; no fresh Claude review is claimed.

## Next

Design a distinct training constraint that preserves correct single-pitch rejection while improving weakest-true/strongest-false separation in chords. Freeze the design before fitting; preserve the existing training, held-out and continuous gates, source labels and rejected cutoffs. No cutoff retune, source exclusion, held-out tuning or repeated run. No next job queued.
