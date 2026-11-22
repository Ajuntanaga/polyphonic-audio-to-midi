"""Bound: what could a lower onset gate recover below MIDI 60, and what false onset events would it add?

Saved arrays only (no audio, no model run, no job).  A BOUND for Codex's decoder ladder, not a candidate:
it counts onset events on the saved streaming activations and does not implement the installed decoder.

PRE-REGISTRATION: written 2026-11-22 after the fate result and BEFORE this script was run (check file mtimes;
my docstring clocks have been wrong twice, so I give none).  Already seen: the fate result (of 67 lower labels
Arm A never reports, 53 absent, 11 gated, 1 decodable, 2 other; 34 are silent in both A and CURRENT, of which
31 absent, 2 gated, 1 decodable).  NOT seen: any onset-event count per gate.

Definitions.  Onset event at (frame t, column c): onset[t,c] >= gate and onset[t,c] is a local maximum
(>= previous frame, > next frame).  Variant 'onset_and_note' additionally needs note[c] >= 0.3 on at least 3 of
frames t..t+4 (a min-length proxy; the frozen spec's frame gate is 0.3).  An event is TRUE if t lies in
[label start - 2 frames, label end] of a label of the same MIDI pitch, else FALSE (gap, or another pitch's label).
Frame grid: hop 256 at 22,050 Hz, label samples at 96 kHz, as in the fate script.  Gates: 0.5, 0.4, 0.3, 0.2.
Scope: columns for MIDI 21..59 (FALSE events counted for MIDI 32..59 too, the guitar's range).
Recovered = an A-silent lower label (A present == 0, MIDI < 60) with at least one TRUE event.

Predictions, each can fail:
  G0  sanity: at gate 0.5 with the note proxy, at most 3 of the 67 A-silent labels are recovered
      (the fate result says only 3 have an onset >= 0.5 and note frames).
  G1  at gate 0.3 (onset only), between 8 and 14 of the 67 are recovered.
  G2  going from 0.5 to 0.3 (onset and note), FALSE events at MIDI 32..59 grow by more than 10 per extra
      label recovered (ordinary corpus).
  G3  at every gate, at most 3 of the 34 labels silent in both A and CURRENT are recovered with the note
      proxy (the fate result bounds this at 3 by construction at gate 0.5; the test is whether a lower gate adds more).
Nothing here is installed, promoted or a candidate.  It does not establish lane assignment, unison multiplicity,
callback deadlines or live-host delivery, and a TRUE event is only an onset in a labelled window, not a decoded note.

Usage: python3 -P -E CLAUDE-M3-LOWREG-ONSET-GATE-BOUND-20261122.py EVIDENCE_DIR STREAM_DIR
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
from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.pitch_detector_comparison import score  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-ONSET-GATE-BOUND-20261122.json')
GATES = (0.5, 0.4, 0.3, 0.2)
LOW_COLS = split.SPLIT - 21          # columns 0..38 are MIDI 21..59
GUITAR_FIRST = 32 - 21


def events(onset, note, col, gate, need_note):
    o = onset[:, col]
    prev = np.concatenate(([-1.0], o[:-1]))
    nxt = np.concatenate((o[1:], [-1.0]))
    t = np.nonzero((o >= gate) & (o >= prev) & (o > nxt))[0]
    if not need_note:
        return t
    n = note[:, col] >= fate.FRAME
    keep = [x for x in t if int(n[x:x + 5].sum()) >= 3]
    return np.array(keep, dtype=int)


def run(evidence_dir, stream_dir):
    report = json.load(open(split.REPORT))
    baseline = json.load(open(split.BASELINE))
    result = dict(schema='claude_m3_lowreg_onset_gate_bound_v1', datasets={})
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
        windows = {}
        for r in a_rows:
            lo = int(np.floor(fate.to_frame(r['start_sample']))) - 2
            hi = int(np.ceil(fate.to_frame(r['end_sample'])))
            windows.setdefault(r['midi_note'], []).append((lo, hi))
        silent = [(a, c) for a, c in zip(a_rows, c_rows) if a['midi_note'] < split.SPLIT and a['present_samples'] == 0]
        both = [(a, c) for a, c in silent if c['present_samples'] == 0]
        per_gate = {}
        for gate in GATES:
            row = {}
            for variant, need_note in (('onset_only', False), ('onset_and_note', True)):
                true_n = false_n = false_guitar = 0
                for col in range(LOW_COLS):
                    midi = col + 21
                    for t in events(onset, note, col, gate, need_note):
                        if any(lo <= t <= hi for lo, hi in windows.get(midi, ())):
                            true_n += 1
                        else:
                            false_n += 1
                            false_guitar += col >= GUITAR_FIRST
                def got(a):
                    ev = events(onset, note, a['midi_note'] - 21, gate, need_note)
                    lo = int(np.floor(fate.to_frame(a['start_sample']))) - 2
                    hi = int(np.ceil(fate.to_frame(a['end_sample'])))
                    return bool(len(ev) and ((ev >= lo) & (ev <= hi)).any())
                row[variant] = dict(true_events=true_n, false_events=false_n, false_events_midi32_59=false_guitar,
                                    recovered_of_A_silent=sum(got(a) for a, c in silent),
                                    recovered_current_also_silent=sum(got(a) for a, c in both))
            per_gate[str(gate)] = row
        result['datasets'][name] = dict(A_silent_lower=len(silent), both_silent=len(both), gates=per_gate)
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run(sys.argv[1], sys.argv[2])
    for name, r in out['datasets'].items():
        print('==', name, 'A-silent lower', r['A_silent_lower'], 'both silent', r['both_silent'])
        for gate, row in r['gates'].items():
            for variant, v in row.items():
                print('  gate', gate, variant, v)
