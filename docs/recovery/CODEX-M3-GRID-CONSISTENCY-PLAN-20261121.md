# One training-only feature-grid consistency screen

Frozen before fitting. Authorization: `m3-standing-job-authorization-20261121.json`.
One CPU GitHub fit; existing input releases only. Claude remains paused. No
installed/default change, native execution, source exclusion or threshold sweep.

The setwise baseline (run 44965135706) passed clean-training gates but failed
both held-out roles. The measured-halo screen (44978661693) lowered test extras
2705 to 2472 but regressed complete sets 1749 to 1725 and single-pitch exact
607 to 569. Adding context and removing boundary padding were confounded.
The original network's 73-row receptive field exceeds its 53-row input, so
padding can expose absolute pitch position despite shared weights. This screen
tests whether constraining dependence on that position improves transfer.

## Fixed change

Use the original setwise network and its 53 pitch rows (MIDI 32–84), 62 features,
14,465 parameters and zero padding. Normalize with the original training-only
scaler. For each existing minibatch, compute original logits `z = f(x)` and
one shifted companion:

```
Sx[:, :, 0] = 0  # training mean after normalization
Sx[:, :, 1:] = x[:, :, :-1]
zs = f(Sx)
loss = original_setwise_loss(z, labels)
     + mean_Huber(zs[:, 1:], stopgrad(z[:, :-1]), delta=1)
```

The consistency coefficient is 1. There is no wrap, no target for the filled
row or dropped original row, no shifted supervised labels and no second
teacher model. The original logits remain supervised; their consistency
teacher branch is detached. Record both loss components, optimizer steps and
the exact configuration in the report and persisted model.

Retain all 555 sources and roles, the original mixture plan/pins, batch order,
initialization, seed, Adam settings, 80 epochs, cutoff selection and gates.
The second forward adds training work, not optimizer steps. Inference stays
one original-grid forward. No physical audio transposition occurs.

## Acceptance and limits

Use the setwise run as the baseline, not the halo run. The original clean-train
cutoff rule (at least 99% precision) and every train/held-out/continuous gate
remain fixed. Training five-pitch target is 1771/2529; calibration 448/639 and
test 229/327. Report single-pitch exact/extra/missing changes beside chord
results; a single-note regression cannot be called preservation. Both held-out
roles run once only after training passes; continuous recordings run only after
both pass. Failure rejects the screen, with no automatic rerun or retuning.

Features carry finite-FFT and source signatures when translated; this tests
feature-grid position consistency, not physical transposition or general
source invariance. The same-network teacher can propagate mistakes and the
constraint can suppress useful pitch evidence. All original labels, including
unresolved source disagreements, remain intact. Sampled sustained pitch sets
do not establish attacks, decays, string assignment, MIDI or live readiness.

Direct verification: synthetic row alignment, excluded edges, stopped teacher
gradients, unchanged step count, persistence/inference identity, fixed spec and
gate flow; one focused static review. Torch checks and recorded fitting run on
GitHub. Small report collected once with server digest verification; model and
predictions remain remote.
