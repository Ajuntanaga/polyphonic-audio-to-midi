# Trailing harmonic peak contrast: frozen comparison

One bounded CPU GitHub fit tests whether explicit local peak measurements improve transfer of complete pitch sets. The comparator is unaugmented setwise run `44965135706`, source `6b4d39aa8b308ce8f808486b345dbe865b1bb4a0`; its report SHA256 is `43b65016f2073661540499843adf12137645e59ed79a62e408c0a8c7449834b9`. The recently rejected transposition run is context, not the comparator or a new acceptance bar.

The original 62 features sample energy at fixed offsets. They do not explicitly report the position and prominence of a local maximum or agreement of those positions across partials. Training-only spectrum variation and coherent transposition did not pass held-out gates. This distinct representation change adds that evidence without lowering an admission threshold or imposing a hard harmonicity rule.

## Frozen implementation

Specification: `harmonic-peak-contrast-20261121.json`. Keep the original 62 coordinates bit-identical and append 22 observations for each existing trailing window (4096 and 16384 samples at 96 kHz), giving 106 coordinates per candidate pitch, MIDI 32–84.

For harmonics 1–5, find the largest local maximum whose interpolated frequency is within +/-40 cents of the nominal partial. Use eightfold zero padding and three-bin parabolic interpolation of log power. Each partial contributes RMS-relative peak dB, offset in cents, prominence over mean linear power at +/-3 native FFT bins, and an explicit valid-local-maximum flag. Negative flank frequencies are reflected. Prominence is clipped to +/-60 dB. If no maximum exists, use nominal-frequency power and its flank contrast, offset zero and valid zero. Per window, append the power-weighted standard deviation of valid offsets and the fraction of valid partial peaks. Fewer than two valid peaks gives zero dispersion; validity remains available to disambiguate it.

These are learned inputs. A sidelobe can be a valid local maximum; the flag is not note validity. Bends, legitimate inharmonicity, overlapping partials and low-frequency resolution can weaken or corrupt the measurements. No hard rejection is introduced. Zero padding adds interpolated samples, not physical resolution or lower latency; maximum context remains 170.67 ms.

The input layer adds 1,408 parameters (14,465 to 15,873). All other architecture, optimizer, 80 epochs, setwise loss, original 16,384 training mixtures, seeds, gains, crop schedule, source roles and training-only cutoff rule remain unchanged. There is no source augmentation. Report the capacity/initialization confound rather than claiming an isolated causal feature effect.

The decompressed original training plan must retain SHA256 `7c5c676126082c3bae9fb68dc03cec20f583951c44b7e7de1c84b1ca7b72d25d`. Preserve all 555 sources, including unresolved source-content disagreements, with train/calibration/test roles 200/200/155. No relabeling or exclusion. Previously inspected held-out roles remain outside fitting, but are not a fresh blind test of the research program.

## Decision and measurement

Training must meet precision >=99%, recall >=80%, complete sets >=70% overall and separately for 3/4/5 distinct pitches, with zero silence extras. The training-only cutoff maximizes expected pitches found at >=99% precision. Both held-out roles then must each meet precision >=95%, recall >=80%, the same complete-set gates and zero silence extras. Neither role changes fitting or cutoff selection.

Baseline five-pitch exact sets: training 1818/2529 (71.89%), calibration 283/639 (44.29%), test 27/327 (8.26%). Targets are 1771, 448 and 229. Training single-pitch baseline is 3115/3132 exact, 13 extras and 5 misses. Report complete sets, true pitches, extras and misses separately at each cardinality; disclose single-note regressions. Do not turn the training pass into promotion.

Only if all three representation gates pass, run the existing ordinary and extended-middle continuous evaluation on measured FIFO completion clocks. Require full CURRENT identity, >=5 percentage-point ordinary gain, and no per-label presence/longest-hold loss or wrong-pitch/extra-gap growth on either recording. The existing gates are unchanged. Failure ends this configuration; no refit, retune or automatic rerun.

The compact report also carries descriptive peak-prominence, offset-dispersion and valid-fraction distributions for expected/found/missed/extra candidate-pitch cells. They do not choose a cutoff or change the verdict. Their cells share mixtures and are not independent samples.

## Execution and protection

Use `Ajuntanaga/m3-offload`, workflow `harmonic-peak-contrast.yml`, one frozen source SHA, CPU only, 45-minute maximum, existing private input releases and concurrency group. Standing authorization is recorded in `m3-standing-job-authorization-20261121.json`. Synthetic measurement, layout, gate and model-persistence tests run first; local torch tests are skipped because pinned torch runs on GitHub. No local recorded processing or installation.

Collect the small report/log artifact once with server digest verification; keep model, predictions and plans remote. Record source/worker SHAs, job, artifacts, output paths and final verdict. Installed plugin/defaults, installed scoreboard and source labels remain unchanged. String assignment, real attacks and releases, unison multiplicity, native allocation/deadline and external host/device gates remain required before live readiness. Claude is paused; this is not a new Claude review.

Technical references: [quadratic spectral peak interpolation](https://www.dsprelated.com/freebooks/sasp/Quadratic_Interpolation_Spectral_Peaks.html) and [spectral interpolation by zero padding](https://www.dsprelated.com/freebooks/sasp/Spectral_Interpolation.html).
