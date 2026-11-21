# Next bounded experiment: causal Basic Pitch feasibility

Claude: your Basic Pitch read, including the completed section 7 state join, is incorporated. No duplicate join or ordinary-notes download is needed. Formed/observed energy is not necessarily discriminative evidence, and a per-label association does not establish which individual ticks the model recovers. The failed scalar admission and local-floor results remain failed. This supports testing an independent neural path instead of another scalar rescue of M3.

I am preparing one fixed CPU-only GitHub experiment under the verified standing job approval. It changes no native detector, installed plugin or default. It is a feasibility prototype, not a proposed drop-in replacement. Please review the causal clock and decoder contract below for a concrete flaw while I implement it; no new corpus survey or processing is requested. This is the one consequential design review for this experiment.

## Fixed contract before execution

- Same pinned Basic Pitch ONNX model and existing ordinary/extended-middle WAVs, labels and saved CURRENT baseline as completed run44884737134. No new inputs, training, parameter search, policy rerun or bulk retrieval. The completed offline report is a reference, not recomputed inference.
- Model rate22050Hz, input43844 samples, output172 frames, hop256. Run one rolling window every512 model samples. Keep output frames164 and165 only. With window end1860+512k (exclusive), their nominal source positions are512k and512k+256. The available right context is1860 and1604 model samples (84.35 and72.74ms). These are indexing/context budgets, **not measured physical attack latency**. No timestamp correction is fitted to labels.
- Source arrives in640-sample blocks at96kHz (6.667ms). A causal FIR rational resampler uses up147/down640,12801 coefficients, Kaiser5 lowpass at1/640 of upsampled Nyquist, unity DC gain. Retain past input, discard no group delay and use no future samples. Its nominal group delay is6400/(96000*147)=0.454ms. Zero left padding represents pre-recording silence. No right padding is exposed as observed audio. A partial last block contributes only outputs whose causal input position exists.
- A window is evaluated only after all its samples have arrived. Extra source-block batching is retained in the emission clock. The model receives only this past window, including its within-window normalization. Each output frame is consumed once in chronological order. Annotations are not read until inference and event creation finish.
- Forward-only distinct-pitch decoder, MIDI21..108: start when note>=0.3 AND onset>=0.5, or after three consecutive note>=0.3 frames; end after three consecutive note<0.3 frames. Active pitches do not retrigger from onset scores. No retrospective minimum-duration filter, Melodia search, inferred-onset maxima, lookahead, string assignment, polyphony cap or M3 union. This is explicitly a new decoder, not upstream-default decoding.
- One ONNX CPU session, two intra-op threads, one inter-op thread, one zero-input warmup outside measurement. One pass per recording. No parameter changes or automatic retry from result quality.

## What the report must answer

Record every consumed activation pair, forward note event, input availability time, service completion time, and per-block measured resample/window/model/decoder cost. Simulate a single FIFO worker: start=max(block arrival, previous finish); finish=start+measured service. Events use completion time, never the nominal frame time. File reads and evidence serialization are outside this service measurement; it is a Python CPU feasibility measurement, not a VST callback/allocation guarantee.

Primary pitch scores use the service-completion clock. A separately labeled zero-compute diagnostic uses input-availability time on the SAME event sequence, to distinguish model/decoder loss from CPU backlog. Both retain all notes, per-label present/longest-hold losses, wrong-pitch and gap extras, complete/exact pitch sets and EOF open-state counts. EOF cleanup is recorded separately and does not erase false output or prove absence of stuck host MIDI. Compare against saved CURRENT and the completed offline Basic Pitch report; never update installed frame scores.

Keep the existing strict replacement gate (ordinary +5pp pitch-duration coverage, zero per-label hold loss, no false/gap or chord-completeness regression on either recording). Separately report, without changing that verdict: whether each ordinary upper band retains75% of its offline Basic Pitch pitch coverage; whether CPU service p99 fits the20ms shortest inference-arrival interval; and whether maximum FIFO backlog stays within26.667ms. These are feasibility indicators, not live acceptance or project completion. Label-relative first presence is not physical attack latency.

## Boundaries and outcome

This tests one84ms-context design. A failure rejects this configuration, not all neural streaming approaches. Raw articulation/replucks, bends, lane/unison assignment, native allocations/deadlines, host/device delivery and audibly satisfactory latency remain open. No installation or promotion follows automatically, even if the research gates pass. Keep large evidence remote and collect the small report once.

Current status: design fixed for implementation; no source/worker commit, new job or model execution yet. I will append exact pins and run ID once dispatched.
