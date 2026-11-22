"""POST-HOC check after CLAUDE-M3-LOWREG-ONSET-GATE-BOUND-20261122 (declared post-hoc, not pre-registered).

The bound found onset-only events at gate 0.3 reach 40 of the 67 A-silent lower labels but the note-supported
variant reaches 1.  Why?  Describe, for the A-silent lower labels grouped by the fate class, the label-pitch onset
maximum and the number of frames with note >= 0.3, and how many have onset >= 0.5 / 0.3.  Saved arrays only.
Usage as the bound script (python3 -P -E ... EVIDENCE_DIR STREAM_DIR); ordinary corpus only.
"""
import gzip
import importlib.util
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('fate', os.path.join(HERE, 'CLAUDE-M3-LOWREG-ACTIVATION-FATE-20261122.py'))
fate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fate)
split = fate.split
from tools.basic_pitch_cached_diagnosis import clip_labels, labels_from_measurement  # noqa: E402
from tools.pitch_detector_comparison import score  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-ONSET-GATE-POSTHOC-20261122.json')


def run(evidence_dir, stream_dir):
    report = json.load(open(split.REPORT))
    baseline = json.load(open(split.BASELINE))
    data = report['datasets']['ordinary']
    base = baseline['datasets']['ordinary']
    horizon = data['common_support']['sample_count']
    clock = dict(sample_count=horizon, sample_rate=split.SAMPLE_RATE)
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    with gzip.open(os.path.join(evidence_dir, 'ordinary-bridge-events.json.gz'), 'rt', encoding='utf-8') as stream:
        a_spans = [tuple(s) for s in json.load(stream)['arm_spans']['A']]
    arrays = np.load(os.path.join(stream_dir, 'ordinary-stream.npz'), allow_pickle=False)
    note, onset = arrays['note'], arrays['onset']
    groups = {}
    for row in score(a_spans, labels, **clock)['labels']:
        if row['midi_note'] >= split.SPLIT or row['present_samples'] != 0:
            continue
        act = fate.label_activation(row, note, onset)
        if act:
            groups.setdefault(fate.classify(act), []).append(act)
    q = lambda xs: [round(float(v), 3) for v in np.quantile(xs, [0, .5, 1])] if len(xs) else None
    out = {}
    for kind, acts in sorted(groups.items()):
        out[kind] = dict(n=len(acts),
                         onset_max_min_med_max=q([a['onset_max'] for a in acts]),
                         note_frames_min_med_max=q([a['note_frames'] for a in acts]),
                         onset_ge_0_5=sum(a['onset_max'] >= 0.5 for a in acts),
                         onset_ge_0_3=sum(a['onset_max'] >= 0.3 for a in acts),
                         note_frames_ge_3=sum(a['note_frames'] >= 3 for a in acts))
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    return out


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1], sys.argv[2]), indent=1))
