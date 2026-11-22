# Fixed training-source variation

Frozen before fitting under the standing CPU GitHub authorization. Claude is paused; no new Claude review is claimed.

Run44965135706 passes the original training gates but fails both source-disjoint roles. The training generator already varies crops and scalar gains. This experiment tests component spectral-envelope variation, without inferring that envelope mismatch uniquely caused the failure.

For each component in the unchanged 16,384-example training plan, independently choose identity with probability0.5, otherwise a shelf gain uniform[-6,+6]dB using seed20261124. Use a one-pole low-pass L with pole exp(-2*pi*1000/96000), initialized at the first sample's steady state. Filter y=g*x+(1-g)*L(x), g=10^(gain_dB/20), after cropping and before existing RMS normalization. The shelf has DC gain1 and bounded response between1 andg. It changes harmonic balance around1kHz without pitch shifting or nonlinear distortion. Gain0 bypasses exactly. Store every gain in a separate plan.

The original plan, crops, labels, component/global gains, 200/200/155 source roles, model, setwise loss,80epochs, optimizer and seed stay fixed. Fit normalization and weights only on the augmented matrix. Select the99%-precision cutoff and apply training gates on the ORIGINAL clean training matrix, then freeze the model before either held-out role is scored. Held-out waveforms and mixture plans are never augmented. All existing gates remain; continuous replay only after both held-out passes. No cutoff sweep or next seed after failure.

Report original training/held-out exact pitch sets and false/missing counts against44965135706. Distinguish sampled sets from installed frames. Repeated use of these roles makes them development checks, not a fresh final benchmark. Preserve all555 labels, including unresolved source-content disagreements. Installed VST3/defaults are unchanged. No new recordings uploaded, no local recorded processing, no model installation.

Verify synthetic identity bypass, deterministic independent gain plan, held-out rejection, finite/bounded filter response and changed harmonic ratios with unchanged frequencies, target/role/crop identity, and orchestration using augmented fitting but clean cutoff/gates. Pin original and augmented plan hashes; run required Torch checks on GitHub. One focused review, one CPU dispatch, one digest-verified small report collection; bulk stays remote.
