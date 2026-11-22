# Frozen pitch-scaled harmonic-window screen

One bounded GitHub CPU job under the recorded standing authorization. Claude remains paused; no fresh review is claimed. No local recording, model fit, native build, installation or promotion.

## Question and change

Can comparable cycle counts across pitches improve source transfer for the shared harmonic classifier? The fixed-window baseline gives different relative frequency resolution across pitches. The paired component/mixture observation45000500192 found58.18% of missing test pitches already absent alone and41.82% lost after summation; phase-motion trial45002449083 did not improve held-out five-pitch sets and lost singleton performance. Neither result proves that window scaling will help.

For candidate note n, use N=floor(base*2**((32-n)/12)+0.5), bases4096 and16384. Both windows end at the current context endpoint. MIDI32 remains4096/16384 samples; MIDI84 becomes203/813. Symmetric Hann, normalized RFFT power, harmonic/offset probe frequencies, linear interpolation, matching-window RMS normalization, floors and clips are unchanged. No future audio. All harmonics of one candidate share that candidate's window; this is not a full CQT or exact equivariance.

Only analysis and RMS context lengths change. Preserve62 coordinates,14465 parameters, initialization, architecture,80 epochs, setwise objective, optimizer, seed, every original mixture plan,555 sources/labels and200/200/155 roles. No augmentation, threshold sweep or held-out fitting. The baseline is44965135706, not the rejected phase trial.

## Decision fixed before results

Require the unchanged training precision99%, recall80%, overall exact70%, each3/4/5-pitch exact70% and zero silence outputs. If this training gate fails, stop. Otherwise score both held-out roles with their unchanged95% precision/80% recall/70% exact and each-cardinality gates. Continuous ordinary and extended-middle replay requires every representation gate plus training singleton exact>=3115/3132, extras<=13, missing<=5. Its original CURRENT identity,>=5pp ordinary gain and no per-label presence/longest-hold loss or false/gap growth remain mandatory. No automatic rerun or cutoff rescue.

Report all errors and complete sets separately by role/cardinality. Preserve the fixed test labels even when source content is disputed. These reused source-disjoint development roles are not a fresh blind test. Installed frame/string scores stay unchanged.

## Main risks and direct checks

About2.2/8.9 cycles per branch are retained. High pitches lose frequency resolution and averaging; nearby pitches and noisy/variable attacks can worsen. RMS context changes at the same time, and native cost/latency remain unmeasured. Generated-signal tests cover original-anchor identity, trailing-only support, gain normalization, silence, shape and invalid inputs. Mocked orchestration checks singleton and held-out gating. GitHub also checks unchanged parameter count and saved-model roundtrip before processing inputs.

Specification: harmonic-pitch-scaled-windows-20261122.json. Implementation: tools/harmonic_pitch_scaled_windows.py. Worker: harmonic-pitch-scaled-windows.yml,45-minute CPU bound. Source/worker commits and run/artifact identifiers will be pinned in github-harmonic-pitch-scaled-windows-20261122.json at dispatch. Collect only the small report/log artifact once; retain bulk remotely.
