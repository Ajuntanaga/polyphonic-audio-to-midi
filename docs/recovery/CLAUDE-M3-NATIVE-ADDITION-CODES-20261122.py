"""Which trace dispositions carry the native-only gain at 48 and above?  Tick census of native-confirmed candidates CURRENT does not emit.

Saved data only: no audio, model run, job, native edit or promotion.  CLAUDE-M3-NATIVE-ONLY-UNION-20261122 found that CURRENT union the
native confirmation (`not quiet and selector_pool_member == 1 and direct == 1`) at pitches 60 and above adds +1,789,705 genuine against
+153,262 false pitch-samples with no label losing anything, and that the neural arm filters almost nothing there (consensus keeps 89.6% of the
genuine and 82.6% of the false).  This script asks which selection code (below_threshold, spectral_rejected, dp_evicted, selected,
coasting) those native-confirmed candidates carry at the 64-sample decision ticks when CURRENT's output does not already hold the pitch,
split by truth (the pitch's label is active / the pitch is within the usual tail window of its last label / neither).  It is a tick
census, not the span-level score: ticks are 64-sample decisions and CURRENT's coverage is tested at the tick's own sample.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the upper-register fate census (60-71: dp_evicted 17.9% of true ticks, ~98% true among evicted candidates; 72+: 96.6% of
true ticks below threshold) and the union scores above.  NOT seen: any tick cross-tabulation of native-confirmed candidates by code,
truth and CURRENT emission.  Predictions, each can fail:
  G0  plumbing: confirmed candidate ticks exist at 60+, and every confirmed candidate has a selection code in 1..5.
  G1  among confirmed, true, not-CURRENT-emitted ticks at 60-71, dp_evicted (code 3) is the largest code with at least 50% share.
  G2  tick precision (true / (true + tail + ghost)) of confirmed, not-emitted candidates at 60-71 is at least 85%.
  G3  code 1 (below_threshold) holds less than 20% of confirmed, true, not-emitted ticks at 60-71.
  G4  among non-true confirmed, not-emitted ticks at 60 and above, the tail share exceeds 50%.
  G5  codes 4 and 5 (selected, coasting) together hold less than 25% of confirmed, true, not-emitted ticks at 60-71.
  G6  at 72+, confirmed, true, not-emitted ticks are fewer than 5% of the 60-71 count.
  G7  of the 60+ labels CURRENT never emits, at least 40% have 10 or more confirmed true ticks.
Report everything whatever it shows.  One recording, one corpus, in-sample, descriptive tick counts; ticks within a label are correlated;
the trace is a diagnostic writer's record (not the live callback), CURRENT emission is tested at the tick's own sample, and no lane,
unison, string or live-host claim and no rule worth building follows.

Usage: python3 -P -E CLAUDE-M3-NATIVE-ADDITION-CODES-20261122.py TRACE.tsv.gz
"""
import bisect
import gzip
import importlib.util
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)

from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.candidate_outcome_analysis import _candidates, _frame  # noqa: E402


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gs = load('gs', 'CLAUDE-M3-LOWREG-GHOST-SEPARATION-20261122.py')
BASELINE = os.path.join(REPO, 'docs/recovery/basic-pitch-baseline-20261121.json')
OUT = os.path.join(HERE, 'CLAUDE-M3-NATIVE-ADDITION-CODES-20261122.json')
HORIZON = 10681922
TAIL_TICKS = gs.TAIL_TICKS
BANDS = [(48, 60, '48-59'), (60, 72, '60-71'), (72, 200, '72+')]
CODE_NAMES = {0: 'quiet', 1: 'below_threshold', 2: 'spectral_rejected', 3: 'dp_evicted', 4: 'selected', 5: 'coasting'}


def band_of(note):
    for lo, hi, name in BANDS:
        if lo <= note < hi:
            return name
    return None


def merged(spans):
    out = defaultdict(list)
    for left, right, pitch in sorted(spans, key=lambda s: (s[2], s[0], s[1])):
        iv = out[pitch]
        if iv and left <= iv[-1][1]:
            iv[-1][1] = max(iv[-1][1], right)
        else:
            iv.append([left, right])
    return {p: ([a for a, _ in iv], [b for _, b in iv]) for p, iv in out.items()}


def run(path):
    base = json.load(open(BASELINE))['datasets']['ordinary']
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), HORIZON)
    cur = merged(clip_spans(base['pitch_spans'], HORIZON))

    def emitted_at(pitch, sample):
        iv = cur.get(pitch)
        if not iv:
            return False
        i = bisect.bisect_right(iv[0], sample) - 1
        return i >= 0 and iv[1][i] > sample

    last_label = {}
    cross = defaultdict(Counter)       # (band, truth, emitted) -> Counter(code)
    label_true = Counter()             # label_index -> confirmed true not-emitted ticks
    label_any = Counter()              # label_index -> confirmed true ticks (emitted or not)
    bad_code = 0
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        stream.readline()
        stream.readline()
        for line in stream:
            frame = _frame('\t'.join(line.rstrip('\n').split('\t')[:8]))
            tick, sample = frame['tick'], frame['sample']
            active = {row[1]: row[0] for row in frame['labels']}
            for note in active:
                last_label[note] = tick
            if frame['quiet']:
                continue
            for note, cand in _candidates(frame).items():
                band = band_of(note)
                if not band or cand['selector_pool_member'] != 1 or cand['direct'] != 1:
                    continue
                code = cand['selection']
                if code not in (1, 2, 3, 4, 5):
                    bad_code += 1
                    continue
                if note in active:
                    truth = 'true'
                elif tick - last_label.get(note, -10 ** 9) <= TAIL_TICKS:
                    truth = 'tail'
                else:
                    truth = 'ghost'
                emitted = emitted_at(note, sample)
                cross[(band, truth, 'emitted' if emitted else 'not_emitted')][code] += 1
                if truth == 'true':
                    label_any[active[note]] += 1
                    if not emitted:
                        label_true[active[note]] += 1
    result = dict(horizon=HORIZON, bad_code_rows=bad_code, tail_ticks=TAIL_TICKS, cross={}, labels={})
    for (band, truth, em), counter in sorted(cross.items()):
        total = sum(counter.values())
        result['cross'][f'{band}|{truth}|{em}'] = dict(
            ticks=total, by_code={CODE_NAMES[k]: v for k, v in sorted(counter.items())},
            code_share={CODE_NAMES[k]: round(v / total, 4) for k, v in sorted(counter.items())})
    # tick precision of not-emitted confirmed candidates
    result['not_emitted_precision'] = {}
    for _, _, band in BANDS:
        t = sum(result['cross'].get(f'{band}|true|not_emitted', {}).get('ticks', 0) for _ in (0,))
        n = sum(result['cross'].get(f'{band}|{x}|not_emitted', {}).get('ticks', 0) for x in ('tail', 'ghost'))
        result['not_emitted_precision'][band] = dict(true=t, tail=sum(result['cross'].get(f'{band}|tail|not_emitted', {}).get('ticks', 0) for _ in (0,)),
                                                     ghost=sum(result['cross'].get(f'{band}|ghost|not_emitted', {}).get('ticks', 0) for _ in (0,)),
                                                     precision=round(t / (t + n), 4) if t + n else None)
    # label potential: 60+ labels that CURRENT never emits
    def never_emitted(label):
        iv = cur.get(label['midi_note'])
        if not iv:
            return True
        i = bisect.bisect_right(iv[0], label['start_sample']) - 1
        for j in range(max(0, i), len(iv[0])):
            if iv[0][j] >= label['end_sample']:
                break
            if iv[1][j] > label['start_sample']:
                return False
        return True

    for _, _, band in BANDS:
        in_band = [r for r in labels if band_of(r['midi_note']) == band]
        never = [r for r in in_band if never_emitted(r)]
        counts = [label_true.get(r['label_index'], 0) for r in never]
        result['labels'][band] = dict(
            labels=len(in_band), never_emitted=len(never),
            never_with_ge1=sum(1 for c in counts if c >= 1), never_with_ge10=sum(1 for c in counts if c >= 10),
            never_with_ge100=sum(1 for c in counts if c >= 100),
            emitted_labels_with_ge10_extra_ticks=sum(1 for r in in_band if r not in never and label_true.get(r['label_index'], 0) >= 10))
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run(sys.argv[1])
    print('bad_code_rows', out['bad_code_rows'])
    for key, v in out['cross'].items():
        print(key, v['ticks'], v['code_share'])
    print('precision', json.dumps(out['not_emitted_precision']))
    print('labels', json.dumps(out['labels']))
