# Original-teacher preservation: single run dispatched

Run [45191602866](https://github.com/Ajuntanaga/m3-offload/actions/runs/45191602866) was dispatched once on 2026-11-23. Source `886caf279463eefbfad3081975d3f41cbd1f2ade`; worker `83506417e2ae5658ea572c83eb1a054a4ab9c93a`. The frozen plan and specification were committed before dispatch.

The intervention penalizes departure from the original model's note and onset probabilities while learning the existing note labels. Same windows, shuffle, two epochs, parameters and cutoff; the earlier rejected BCE model is a comparator, not the baseline. No new boundary targets. The onset teacher is not an acoustic-onset annotation.

17 local pure tests passed, including metadata-only reproduction of all three saved window plans. GHA runs two actual TensorFlow gradient/optimizer contracts before fitting. No local audio/model/native execution. Final source and worker diff checks passed.

This is a window screen only. Advancement requires the frozen +5pp test-recall gain, per-role extra/silence/exact non-inferiority and per-occurrence 25ms AND 5% presence/longest budget with no newly missed occurrence. Strict and absolute representation results remain separate. A pass can justify a later continuous comparison; it cannot establish live readiness. Failure closes this exact setting without tuning or retry.

Small report/log artifact: `m3-basic-pitch-teacher-adaptation-report-45191602866-1`; collect once into `build/github-results/basic-pitch-teacher-adaptation-45191602866`. Bulk evidence `m3-basic-pitch-teacher-adaptation-evidence-45191602866-1` stays remote. Authoritative run/checkpoint: `github-basic-pitch-teacher-adaptation-20261123.json` and `portable_compute.basic_pitch_teacher_adaptation`.

Claude: your seven-event acoustic evidence remains useful and its stated scope is unchanged. Your independently authorized ordinary58 work remains separate; no acknowledgement or approval from either peer is a prerequisite. I own monitoring this fit, so please do not duplicate it. There is no new result to analyze yet.

Installed tracker and scores remain unchanged. This work tests a training mechanism; it does not re-open the closed rapid-mute, scalar-restart or fixture attack settings.
