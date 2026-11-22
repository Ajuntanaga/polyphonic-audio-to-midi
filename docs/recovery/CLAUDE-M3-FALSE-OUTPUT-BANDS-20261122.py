"""Where CURRENT's wrong-pitch output sits, by pitch register (descriptive, saved data, no filter).

Asked because a register-split veto (filter only the notes at or above a boundary pitch, pass CURRENT through below it) would remove every
lower-register label loser of the support filter (the five D = 220 losers are pitches 33, 33, 34, 42, 42 and 60) if the false output lived
at or above the boundary.  This splits CURRENT's saved pitch spans into pitch bands and scores each band against the same labels with the
same scorer, so present, extra-pitch-voice and gap-voice samples add up to CURRENT's totals.  No support, no hold, no model.
Usage: python3 -P -E CLAUDE-M3-FALSE-OUTPUT-BANDS-20261122.py   (writes CLAUDE-M3-FALSE-OUTPUT-BANDS-20261122.json next to this file)
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('ad', os.path.join(HERE, 'CLAUDE-M3-ADAPTED-SUPPORT-20261122.py'))
ad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ad)
from tools.pitch_detector_comparison import score  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-FALSE-OUTPUT-BANDS-20261122.json')
EDGES = [0, 40, 45, 53, 57, 60, 61, 64, 72, 200]


def main():
    out = {}
    for dataset in ('ordinary', 'extended-middle'):
        ctx = ad.dataset_context(dataset)
        t = ctx['current']['pitch_sets']['totals']
        total = dict(present=t['present_pitch_samples'], extra=t['extra_pitch_voice_samples'],
                     gap=ctx['current']['pitch_sets']['unlabeled_gap_voice_samples'])
        bands = []
        for lo, hi in zip(EDGES[:-1], EDGES[1:]):
            spans = [s for s in ctx['cur_spans'] if lo <= s[2] < hi]
            sc = score(spans, ctx['labels'], **ctx['clock'])
            bt = sc['pitch_sets']['totals']
            bands.append(dict(band=[lo, hi], spans=len(spans), present=bt['present_pitch_samples'],
                              extra=bt['extra_pitch_voice_samples'], gap=sc['pitch_sets']['unlabeled_gap_voice_samples']))
        below = [b for b in bands if b['band'][1] <= 60]
        out[dataset] = dict(label_pitches=sorted({lab['midi_note'] for lab in ctx['current']['labels']}), current=total, bands=bands,
                            share_below_60=dict(extra=round(sum(b['extra'] for b in below) / max(1, total['extra']), 4),
                                                gap=round(sum(b['gap'] for b in below) / max(1, total['gap']), 4)),
                            band_sums_equal_current=[sum(b[k] for b in bands) for k in ('present', 'extra', 'gap')] == [total['present'], total['extra'], total['gap']])
        print(dataset, json.dumps(dict(current=total, share_below_60=out[dataset]['share_below_60'], sums_equal=out[dataset]['band_sums_equal_current'])))
        for b in bands:
            print('  ', json.dumps(b))
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)


if __name__ == '__main__':
    main()
