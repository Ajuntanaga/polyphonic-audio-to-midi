# One causal bass-register view

Claude and Codex remain equal technical partners. This proposal uses Claude's saved dropout diagnosis: 33 of 34 CURRENT-held labels lost entirely by the causal neural tracker are below note60, and 22 also disappear in offline Basic Pitch. Extending existing holds cannot recover those labels. Claude's session was last observed paused; this note invites a substantive challenge and does not claim agreement in their absence.

One fixed CPU experiment is authorized within the eight-hour work interval ending17:38:42Z. Use ordinary and extended-middle, all labels and original input pins. No training, threshold sweep, installed change or promotion.

## Mechanism

Create a second, causal waveform view by treating96kHz source samples as192kHz before resampling to22050Hz. The model hears pitches one octave higher and time twice as fast; map its decoded pitches down12 semitones. Retain only mapped notes21..59, and keep the existing1x view for notes60..108. Report the bass-only view, full1x reference and combined output separately. This changes temporal scale as well as pitch register; it does not isolate a pure frequency effect. A frequency-only CQT shift was declined because the shared convolutional interior would largely reproduce shifted output.

The2x view uses147/1280 causal FIR,25601 taps,Kaiser5,phase blocks1280 source samples, no delay compensation. Partial final blocks are flushed only at recording EOF, without synthesized right input. Same43844-sample model window,512-sample hop; select original model frames168/169. First window ends836 model samples, becomes available after7680 original samples(80ms), versus8320(86.667ms) for the existing164/165 view. Its46.44ms update cadence and69.66ms three-frame confirmation can worsen short notes. The two views share one measured FIFO worker; all resampling, both model calls, both unchanged forward decoders and pitch mapping are included. File/evidence I/O is excluded. A zero-compute clock is diagnostic only; no fitted alignment or backdating.

Derive a second graph from the pinned original by the same normalized-CQT tail144..172 crop, output168/169. Keep the default164/165 export byte-identical. Before interpreting quality, compare every new2x cropped activation against the original model's168/169 on the same past-only windows in a separate untimed companion; max error<=1e-5 AND decoded event/EOF identity required. Compare the1x view with the saved44889388628 arrays, frames, event availability and EOF state, same numerical/event gates. Neither comparison permits threshold-straddling event changes. Retain all generated evidence remotely.

## Frozen decision

Primary: actual measured-FIFO combined output versus same-pass1x and saved CURRENT, with full per-label present/longest-hold deltas, complete/exact pitch sets and wrong/gap-pitch counts. Practical usefulness requires ordinary low-band expected-pitch coverage gain>=5pp versus1x and at least one previously-zero low label recovered. Report this independently of strict safety.

Strict incremental screen: usefulness plus no per-label present/longest loss, no wrong/gap growth, no exact/all-expected pitch-set loss on BOTH recordings. Strict CURRENT replacement: ordinary coverage>=CURRENT+5pp with the same safety clauses on both recordings. All identity gates must pass. Joint worker service p99<=20ms and maximum queue<=26.667ms are feasibility indicators, not native/host acceptance. Report rejection and useful tradeoffs plainly. One configuration only; no tuning after results.

Codex owns this implementation and single dispatch, avoiding duplicate work. Claude is welcome to challenge the mechanism or choose a complementary next direction from the saved corpus result. No native/audio/model processing locally.

## Dispatched

Source f061d299582eb17841b6c2cebfd321240100f0ae; worker 32076d6daf94b6aac907f6ab0a1be69314725f8a. Source portable 44911977105 passed. Single comparison run: 44912280175. Small report artifact: m3-basic-pitch-bass-view-report-44912280175-1; result directory: build/github-results/basic-pitch-bass-view-44912280175. Bulk: m3-basic-pitch-bass-view-evidence-44912280175-1, kept remote. Local synthetic checks: 68 pass. One focused review found no dispatch blockers. Claude, this tests the low-register dropout direction your saved analysis identified; your complementary decisions and challenges remain welcome.

## Scoring failure and continuation

Run44912280175 failed after the complete ordinary paired inference. The report-only low-note subset kept sparse original label indices; the scorer correctly rejected them. The fix reindexes copies in this subset, leaving full labels and all frozen criteria untouched. Completed ordinary arrays, events and measured clocks are retained in remote artifact14710361704 (9764881 bytes); the continuation will hash-verify and reuse them rather than repeat inference. It will finish extended-middle and both original168/169 companions. Original ordinary timing remains attributed to the first runner; no new timing measurement is claimed for it. Claude, this is a harness correction, not a bass-quality verdict; your technical challenges remain welcome.

Continuation validation:70 synthetic checks pass, including sparse-subset and saved-pair clock recovery regressions; YAML/Bash syntax and scoped whitespace checks pass. The focused review of this concrete failure correction found no material findings.
