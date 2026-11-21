# Claude: diagnosis of the four relief-test assertions (portable run 44879958359)

Read-only: I read LastTest.log (sha256 88e37b2c8ed03e4a88bac8169fa888dd77caeb3a0bdea666dafaf5e8a9bce921), the pushed test at ab0b3eb and `select_m3_feasible_candidates`. Nothing was built or run, the predicate and DSP are untouched, nothing dispatched.
The test is my own (`native_detector_upper_fretted_relief_waives_only_the_fixed_term_for_unrelated_parents`), so the error is mine.

## What failed
Exactly four expectations, all on index 0 (`selected`) of `upper_fretted_relief_probe`:
- test line 11157 `off[0] == 0` (relief off, parent 40)
- line 11163 `none[0] == 0` (relief on, no parent)
- line 11184 `blocked[0] == 0`, twice (parents 53 and 34)
Every counter assertion (indexes 1-6: evaluated, no_parent, related_blocked, applied, rendered_disagreements, active_only), the `unrelated` and `rendered` cases all passed. So the predicate and its counters behaved as specified in this first native execution; only my expectation about the emitted note was wrong.

## Cause
The probe holds a single candidate (note 65, score 0.15, fundamental 0.14) and the parent has no score, so the DP has nothing but the target. With the 0.225 fretted cost the DP correctly prefers the empty chord (best.voice_count == 0). Then the lone-pitch safeguard at `polyphonic_pitch_detector.cpp` (the `if (best.voice_count == 0U)` block after the DP) admits the strongest direct-fundamental candidate anyway ("must not turn the only physical pitch into silence"). `has_direct_fundamental_peak` is true for 0.14 >= 0.20 x 0.15 and a peak with zero neighbours. So `selected[65]` is 1 in every case, whatever the penalty.
My comment in the probe ("keeps note 65 out") ignored that safeguard. It only matters in a chord, where a selected lower note makes voice_count > 0, which is exactly the situation relief targets. It also means a lone note is never affected by relief, which is the intended behaviour.

## Two fixes, neither executed
A. Keep the probe, drop the three `[0] == 0` expectations in off/none/blocked and assert that the relief-off/none/blocked results equal each other, and that `unrelated`/`rendered` are 1 only by documented contract (the counters carry the predicate check). The causal effect of the 0.20 term is then exercised by the corpus replay, where the parent is selected. Robust, zero new risk.
B. To keep a DP contrast in the unit test, set `fundamentals[target] = 0.02`. That is below 0.20 x 0.15, so `has_direct_fundamental_peak` is false and the fallback is skipped. `has_m3_candidate_evidence` stays true through `missing_fundamental` (0.02 <= 0.15 x 0.15) with `local_energy_peak`. Unverified risk: a later spectral-eligibility stage may reject a candidate with no direct peak, which would make evaluated 0 in the `unrelated` case. It needs one more GitHub iteration to find out.
I recommend A for the screen, since the gate is the corpus result and not this probe; B only if you want the unit-level contrast.

## What this does not change
No claim about the screen result. The relief predicate is as frozen. This is one test's expectation, not a DSP finding.
