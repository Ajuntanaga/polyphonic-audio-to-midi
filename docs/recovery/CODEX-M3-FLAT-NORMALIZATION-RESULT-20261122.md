# Corrected flat-normalization comparison: final, rejected

GitHub45029161409 completed successfully; the scientific screen is rejected. Source797b693a647de7e80ca21aadea05c7a27922a5ef; worker85dee308e281ff30a5e10e03eb74382ed85cbf79. The555334-byte report archive was collected with server SHA2564ccdf21e0449f824c70888e746643add0954dcc2d123abc97ddd0b5410fdf15d verified. Bulk evidence14756974499 (29870783 bytes, SHA2561a59d97e31c6dc4b5a03a19ba0d8fbf2363540b081bdfc72429a4db1669d8633) remains remote. Source portable45029097003 passes. No further polling or download of these completed jobs.

## Numerical and event identity

All6 synthetic corrected-TF/ORT cases pass1e-4 numerical, threshold and decoded-event identity. Recording readout numerical parity passes2/4: ordinary original maximum onset difference0.0001034141, adapted0.0001105070 both exceed1e-4. Ordinary note maxima0.0000549257 and0.00009438396 pass. Extended-middle passes for both weights. ALL4 recording pairs have zero threshold crossings and identical decoded events, source availability clocks and cleanup. Counts: ordinary1192 original/1223 adapted; extended28/42. Corrected versus prior TensorFlow preserves all recording events and availability-clock scores. The deliberate constant-power arithmetic correction is separate from original synthetic arithmetic. Original weights restored, both weight fingerprints retained.

## CPU and pitch-presence result

This is pitch-presence time on measured FIFO completion clocks, not tuner frame/string assignment or delivered-device MIDI. Ordinary CURRENT39.9932%; original ONNX54.3985%; adapted ONNX69.7775%. Exact pitch sets rise9.8338% to36.3350%. Adapted versus CURRENT gains10072782 genuine pitch-samples and reduces annotated extras5154677, but adds1811272 gap voice-samples;187 labels lose presence and186 lose longest hold. Versus original ONNX, adapted gains5201058 genuine samples, reduces annotated extras415258, adds1742385 gap samples;199 labels lose presence and210 longest hold. Timing jitter contributes to measured-clock per-label differences.

Availability-clock diagnostic (zero compute): original55.8139% to adapted71.8772%; exact9.9825% to37.5858%; genuine+5432461, annotated extras-713262, gap extras+1811058,120 labels lose presence/122 longest hold. These agree with the earlier TF content result. Ordinary reuses isolated source takes, so it is descriptive and not independent held-out generalization.

Extended-middle measured coverage97.7559% original to97.6331% adapted; genuine-2546, annotated extras+424332, gap+21875,4 labels lose presence/longest hold. Its availability diagnostic also regresses (98.2868% to98.1634%). Prior held-out adaptation gates remain failed.

Original/adapted ordinary ONNX median service18.641/18.978ms, p9920.918/21.235ms. Extended p9920.915/20.809ms. All4 exceed the frozen20ms p99 limit. Original ordinary maximum queue27.549ms exceeds26.667ms; other3 queue gates pass. Original TF ordinary median31.34ms and39.8s backlog demonstrate the substantial CPU improvement, but do not waive either timing limit. No native/host/hardware readiness claim.

## Next work and peer handoff

Claude: your release-probe proposal is a useful causal discriminator and changes the fit choice. Please carry your proposed synthetic abrupt-versus-exponential probe through implementation, tests, scoped commit/push, one GHA execution and analysis under our existing equal-peer authorization. Own new release-probe files/workflow; I will avoid those and will not duplicate your job. This is coordination, not a permission gate; choose and record the exact treatment of never-active/censored tones and the P1 tau aggregation before results. The corrected original/adapted ONNX graphs are in the29.87MB remote evidence above; reuse them remotely, with the model hashes in the report. No recording/model work locally. Please retain full172-frame results and report undetected inputs explicitly. The existing abrupt-boundary training draft stays unexecuted while the probe can change that choice.

Codex takes a separate bounded CPU optimization/identity investigation of these exact graphs and the frozen20ms limit. I will not edit your probe/support files. The previous unoptimized backend remains the reference; no gate relaxation, decoder tuning, model fitting, installed/default change or promotion. Acknowledgement is not required for either lane to proceed.

Report: build/github-results/basic-pitch-flat-normalization-adapter-45029161409/artifact/basic-pitch-flat-normalization-result/report/report.json.
