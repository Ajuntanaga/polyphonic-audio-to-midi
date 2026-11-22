# Same-network consistency: differentiate both paths

The previous feature-grid fit, run44980872011, is final and rejected. Both loss components jump at epoch23 and the final total is4.668e12; no training cutoff meets99% pitch precision. The no-output fallback is not a safety improvement. Installed output is unchanged.

## Concrete failure mechanism and its limits

The original code evaluates `z=f_theta(x)` and `zs=f_theta(Sx)` using the same network, then minimizes `Huber(zs, stopgrad(z))`. Its update contains the shifted Jacobian but omits the original Jacobian. Since both outputs change with the same parameters, this update is not the full derivative of the reported consistency scalar. The distinction follows from [PyTorch detach semantics](https://docs.pytorch.org/docs/2.15/generated/torch.Tensor.detach.html) and the [Huber definition](https://docs.pytorch.org/docs/2.15/generated/torch.nn.HuberLoss.html); execution will be checked with the pinned Torch2.5.1 CPU runtime.

A pure scalar counterexample uses original=`2*w`, shifted=`w`, delta1, initialw=.5,20 SGD steps at.1, no supervised term. The detached update raises the actual Huber loss from.125 to1.771794405; the full derivative lowers it to.0018476103676793238. Saved arithmetic: `build/recovery/m3-grid-gradient-diagnosis-20261122/scalar-counterexample.json`. The new synthetic test also checks finite differences in both Huber regions using the production loss helper.

This demonstrates a non-descent mechanism; it does not establish the sole cause of the recorded failure. A stopped target can be an intentional learning rule, but the same-network moving target here is not a fixed teacher. Huber bounds output residual derivatives, not network parameter gradients. Biased hidden activations and boundary padding also mean shifted inputs need not produce identical aligned outputs. Full differentiation does not guarantee convergence or source transfer.

## One frozen change

New spec: `harmonic-full-gradient-consistency-20261122.json`; new workflow: `harmonic-full-gradient-consistency.yml`. Remove only the target detach for this named configuration. Preserve the historical function default and old spec for reproducibility. Training remains original supervised setwise loss plus weight1 mean aligned Huber, delta1;53 inputs,52 aligned logits,zero-fill/no-wrap shift,two forwards and one optimizer step. Inference still uses one unshifted forward.

All555 original labels and train/calibration/test roles, original mixture plan, features, normalization,14465 parameters,Adam.001,weight decay.0001,batch128,80epochs,seed20261121 and all gates stay fixed. No clipping, learning-rate change, checkpoint rescue, cutoff retuning or additional fit. GHA synthetic tests must verify both-branch gradients, boundary exclusion, the shared-weight finite difference/counterexample, correct mode forwarding and persistence before recorded processing.

## Decision and execution

One bounded CPU GHA fit under the standing job authorization. Reuse existing authorized inputs; no uploads or local audio/model/native processing. The training gate must pass before both source-disjoint development roles are scored; both must pass before continuous replay. Preserve the baseline single-note exact/false/missing comparison as well as complete chords. Any original gate failure rejects the screen; workflow success alone is not acceptance.

The small report is collected once with server digest verification. Bulk stays remote. Compare training loss components with the failed detached run and pitch counts with original setwise run44965135706. If stability returns, that is evidence about this fixed run, not a general convergence proof. If held-out safety fails, do not promote or call the stable fit a tracking gain.

No installed/default change. Claude remains paused and no fresh Claude review is claimed. Native performance, held-note quality, delivered MIDI and live readiness remain separate gates. No automatic rerun or next experiment is included.
