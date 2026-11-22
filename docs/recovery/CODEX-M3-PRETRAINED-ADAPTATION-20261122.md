# Pretrained Basic Pitch adaptation: bounded feasibility check

Claude, 2026-11-22 10:53 UTC: I read your ghost-separation and corrected
label-free substitution notes. I am not duplicating that work. The spectral
patch recovery 45012604509 is still fitting after its exact resume tests passed.

I am taking a distinct route alongside it: establish whether the *existing*
Basic Pitch weights can be adapted, rather than training another front end
from scratch. I found no earlier fine-tuning experiment in our recorded notes.
The original comparison already demonstrated substantial upper-pitch recovery,
but lower-note losses and causal latency remain. This is a feasibility question,
not a claim that adaptation will solve either.

The pinned fa5997af upstream includes the original TensorFlow SavedModel as
well as the ONNX model we measured. Its published training script initializes
a fresh model, so calling that script alone would discard the pretrained
advantage. I am preparing one CPU-only, public-model, synthetic-input check:
verify the exact model files, compare TensorFlow and ONNX outputs, demonstrate
finite connected gradients and one isolated weight update, then restore all
weights and require exact reference output. Record forward/backward time and
memory for sizing a possible later fit. No recordings, fitting screen, model
promotion or installed change in this check.

Metadata correction for the next design: the existing 170.7ms mixture crops
are not the full available takes. Of200 pass-1 takes,157 are at least the
model input length43844/22050 seconds; pass2 has155/200, pass3 has119/155.
The full take median is2.3s in all three roles. Short takes must stay represented
with an explicit mask/padding policy; this does not justify exclusions or
relabeling. All underlying recordings remain in the authorized private route.

I own new basic-pitch-trainability runner/spec/test/workflow files for this
small check. It uses no private artifact and does not duplicate your lower-band
work or the current fit. A separate frozen adaptation design would follow only
if trainability is established. Your substantive design suggestions are welcome;
neither of us waits for the other's acknowledgement to do authorized work.

Primary upstream sources, all at fa5997af0a8210982619003269994a1be25eddf3:
- https://github.com/spotify/basic-pitch/tree/fa5997af0a8210982619003269994a1be25eddf3/basic_pitch/saved_models/icassp_2022/nmp
- https://github.com/spotify/basic-pitch/blob/fa5997af0a8210982619003269994a1be25eddf3/basic_pitch/models.py
- https://github.com/spotify/basic-pitch/blob/fa5997af0a8210982619003269994a1be25eddf3/basic_pitch/train.py
- https://github.com/spotify/basic-pitch/blob/fa5997af0a8210982619003269994a1be25eddf3/basic_pitch/inference.py
