"""Are the low-register misses already absent in the saved activations, or lost in decoding?  Saved arrays only.

Answers Codex's open question (CODEX-M3-EIGHT-HOUR-RESULT / label-sensitivity notes): of the labels below
MIDI 60 that Arm A never reports (zero present samples), is the model's own note/onset activation at that
pitch already below the decoder's gates during the label (information absent), or above them (lost in
decoding, min-length or context)?  No audio, no model run, no job: it reads the saved streaming activations
(`ordinary-stream.npz`, `extended-middle-stream.npz`: note and onset posteriorgrams, 88 pitches = MIDI 21..108,
hop 256 samples at 22,050 Hz) and the frozen A / CURRENT spans.

PRE-REGISTRATION, written 2026-11-22 ~00:50 PST (check file mtimes, my docstring clocks were wrong last time)
BEFORE this script was run.  Already seen: the split report, the anatomy, the tail-clip audit, and that
the arrays have shapes (9584, 88) and (2004, 88).  NOT seen: any per-label activation value.

Gates taken from the frozen diagnosis spec: onset 0.5, frame 0.3, release 3 frames.

Per lower label (MIDI < 60, ordinary corpus) with Arm A present == 0 (call this G1; 67 labels expected):
  absent     = max note activation at the label pitch over the label's frames < 0.3
  gated      = note >= 0.3 on at least one frame, but max onset within [label start - 2 frames, label end] < 0.5
  decodable  = onset >= 0.5 somewhere in that window AND note >= 0.3 on at least 3 frames, yet A is silent
  other      = the remainder (note >= 0.3 on 1-2 frames and an onset)
Sanity check R0: labels where A has present > 0 should almost never be "absent" (under 3%): this validates
the sample-to-frame mapping.  If R0 fails, every other number is discarded.
Predictions, each can fail:
  R1  more than 50% of G1 are "absent".
  R2  among G1 "absent", the strongest mean activation during the label sits at +-12 semitones from the
      label pitch (octave) in more than 30%.
  R3  "decodable" is under 25% of G1.
  R4  the 'both A and CURRENT silent' lower labels are at least 80% "absent".

Nothing here is promoted, installed or a candidate.  It describes saved activations at label pitches.
It does not establish lane assignment, unison multiplicity, callback deadlines or live-host delivery.

Usage: python3 -P -E CLAUDE-M3-LOWREG-ACTIVATION-FATE-20261122.py EVIDENCE_DIR STREAM_DIR
  (needs numpy; -P -E so no working-directory or environment module is loaded, np.load uses allow_pickle=False)
"""
import gzip
import importlib.util
import json
import math
import os
import sys
from collections import Counter

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('split', os.path.join(HERE, 'CLAUDE-M3-PITCH-SPLIT-20261121.py'))
split = importlib.util.module_from_spec(spec)
spec.loader.exec_module(split)
from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.pitch_detector_comparison import score  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-ACTIVATION-FATE-20261122.json')
ONSET, FRAME = 0.5, 0.3
HOP, RATE = 256, 22050.0


def to_frame(sample):
    return sample * RATE / split.SAMPLE_RATE / HOP


def label_activation(row, note, onset):
    col = row['midi_note'] - 21
    frames = note.shape[0]
    if not 0 <= col < note.shape[1]:
        return None
    lo = max(0, int(math.floor(to_frame(row['start_sample']))))
    hi = min(frames, max(lo + 1, int(math.ceil(to_frame(row['end_sample'])))))
    span = note[lo:hi]
    if not len(span):
        return None
    onset_window = onset[max(0, lo - 2):hi, col]
    mean = span.mean(axis=0)
    strongest = int(np.argmax(mean)) + 21
    return dict(note_max=float(span[:, col].max()), note_frames=int((span[:, col] >= FRAME).sum()),
                onset_max=float(onset_window.max()), strongest=strongest,
                strongest_mean=float(mean.max()), own_mean=float(mean[col]))


def classify(a):
    if a['note_max'] < FRAME:
        return 'absent'
    if a['onset_max'] < ONSET:
        return 'gated'
    return 'decodable' if a['note_frames'] >= 3 else 'other'


def relation(a, midi):
    d = a['strongest'] - midi
    return {0: 'self', 12: 'octave_up', -12: 'octave_down', 19: 'twelfth_up', 7: 'fifth_up', 24: 'two_octaves_up'}.get(d, 'other')


def run(evidence_dir, stream_dir):
    report = json.load(open(split.REPORT))
    baseline = json.load(open(split.BASELINE))
    result = dict(schema='claude_m3_lowreg_activation_fate_v1', datasets={})
    for name, data in report['datasets'].items():
        base = baseline['datasets'][name]
        horizon = data['common_support']['sample_count']
        clock = dict(sample_count=horizon, sample_rate=split.SAMPLE_RATE)
        labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
        current_spans = clip_spans(base['pitch_spans'], horizon)
        path = os.path.join(evidence_dir, name + '-bridge-events.json.gz')
        if os.path.getsize(path) != data['evidence']['bytes'] or split.sha(path) != data['evidence']['sha256']:
            raise ValueError(name + ': evidence differs from pin')
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            a_spans = [tuple(s) for s in json.load(stream)['arm_spans']['A']]
        arrays = np.load(os.path.join(stream_dir, name + '-stream.npz'), allow_pickle=False)
        note, onset = arrays['note'], arrays['onset']
        a_rows = score(a_spans, labels, **clock)['labels']
        c_rows = score(current_spans, labels, **clock)['labels']
        rows = []
        for a_row, c_row in zip(a_rows, c_rows):
            act = label_activation(a_row, note, onset)
            if act is None:
                continue
            rows.append(dict(midi=a_row['midi_note'], annotated=a_row['annotated_samples'], a_present=a_row['present_samples'],
                             c_present=c_row['present_samples'], kind=classify(act), rel=relation(act, a_row['midi_note']), **act))
        lower = [r for r in rows if r['midi'] < split.SPLIT]
        g1 = [r for r in lower if r['a_present'] == 0]
        both = [r for r in lower if r['a_present'] == 0 and r['c_present'] == 0]
        a_ok = [r for r in lower if r['a_present'] > 0]
        pct = lambda n, d: None if not d else round(100.0 * n / d, 1)
        kinds = lambda group: dict(Counter(r['kind'] for r in group))
        absent = [r for r in g1 if r['kind'] == 'absent']
        band = lambda g, lo, hi: [r for r in g if lo <= r['midi'] <= hi]
        result['datasets'][name] = dict(
            frames=int(note.shape[0]), lower_labels=len(lower), G1_A_silent=len(g1), G1_kinds=kinds(g1),
            G1_by_band={'below48': kinds(band(g1, 0, 47)), '48to59': kinds(band(g1, 48, 59))},
            both_silent=len(both), both_silent_kinds=kinds(both),
            R0_A_present_but_absent_pct=pct(sum(r['kind'] == 'absent' for r in a_ok), len(a_ok)), R0_n=len(a_ok),
            R1_absent_pct=pct(len(absent), len(g1)),
            R2_octave_pct=pct(sum(r['rel'] in ('octave_up', 'octave_down') for r in absent), len(absent)),
            G1_absent_relations=dict(Counter(r['rel'] for r in absent)),
            R3_decodable_pct=pct(sum(r['kind'] == 'decodable' for r in g1), len(g1)),
            R4_both_absent_pct=pct(sum(r['kind'] == 'absent' for r in both), len(both)),
            current_recovers_among_A_silent=sum(r['c_present'] > 0 for r in g1),
            current_recovers_kinds=kinds([r for r in g1 if r['c_present'] > 0]),
            note_max_quantiles_G1=None if not g1 else [round(float(q), 3) for q in np.quantile([r['note_max'] for r in g1], [.1, .5, .9])],
            example_decodable=sorted([r for r in g1 if r['kind'] == 'decodable'], key=lambda r: -r['annotated'])[:5])
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run(sys.argv[1], sys.argv[2])
    for name, r in out['datasets'].items():
        print('==', name, '| lower labels', r['lower_labels'], '| A silent', r['G1_A_silent'], r['G1_kinds'])
        print('   by band:', r['G1_by_band'])
        print('   R0 A-present but absent %:', r['R0_A_present_but_absent_pct'], 'of', r['R0_n'])
        print('   R1 absent %', r['R1_absent_pct'], '| R2 octave % of absent', r['R2_octave_pct'], r['G1_absent_relations'])
        print('   R3 decodable %', r['R3_decodable_pct'], '| R4 both-silent', r['both_silent'], r['both_silent_kinds'], 'absent %', r['R4_both_absent_pct'])
        print('   CURRENT recovers', r['current_recovers_among_A_silent'], r['current_recovers_kinds'], '| note_max q10/50/90 in G1', r['note_max_quantiles_G1'])
