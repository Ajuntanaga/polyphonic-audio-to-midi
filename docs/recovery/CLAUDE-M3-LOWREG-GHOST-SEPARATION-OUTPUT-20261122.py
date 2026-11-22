"""The ghost-separation question again, on voices that actually reach CURRENT's MIDI output.  Saved trace and saved spans only.

No audio, model run or job.  CLAUDE-M3-LOWREG-GHOST-SEPARATION-20261122 computed ghost-versus-true AUCs over every lower voice in the
v5 trace's `voices` list.  That list is the detector's rendered voices, not CURRENT's output: 38,698 of its 92,957 ghost voice-ticks
(41.6%) are not occupied in CURRENT's saved pitch spans at their tick, against 11.3% for true.  Those unconfirmed ghosts are mostly
age-0 flickers with weak candidates, so they may be the easy ones to separate.  Here the subject and the partner must both be
occupied in the saved spans at the tick's sample, and everything else (classes, partnering rule, features, AUC with the direction
chosen to be at least 0.5, ghost TPR at a 5% false-positive rate on true) is the original's, imported from it.  A secondary run keeps
the occupied subject but lets any rendered voice be the partner.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the original table (best AUC 0.827 for band_fund; direct 0.795; ghost partnered 47.9%, true 30.0%; best ghost TPR
0.499) and the emission split of the classes.  NOT seen: any AUC, partnered share or count on output-only voices.
Predictions, each can fail:
  O0  the occupied subject counts are 54,259 ghost and 203,528 true voice-ticks (the EMITTED note's counts; plumbing).
  O1  the best single feature's AUC (primary run) is below 0.827.
  O2  the best feature's ghost TPR at 5% false-positive rate (primary run) is below 0.499.
  O3  the occupied ghost class's partnered share (primary run) is within 5 points of the original 47.9%.
  O4  at least one feature still reaches AUC 0.80 (primary run).
  O5  `direct` has AUC below its original 0.795 (primary run).
Report everything whatever it shows.  Ticks in one span are strongly correlated: descriptive tick-level numbers, no confidence
interval.  One recording, one corpus.  Nothing here selects a rule, and no lane, unison, callback or live-host claim.

Usage: python3 -P -E CLAUDE-M3-LOWREG-GHOST-SEPARATION-OUTPUT-20261122.py TRACE.tsv.gz
"""
import bisect
import gzip
import importlib.util
import json
import math
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gs = load('gs', 'CLAUDE-M3-LOWREG-GHOST-SEPARATION-20261122.py')
em = load('em', 'CLAUDE-M3-LOWREG-RERENDER-EMITTED-20261122.py')
split = gs.split
OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-GHOST-SEPARATION-OUTPUT-20261122.json')
FEATURES, TAIL_TICKS = gs.FEATURES, gs.TAIL_TICKS


def run(path):
    report = json.load(open(split.REPORT))
    base = json.load(open(split.BASELINE))['datasets']['ordinary']
    horizon = report['datasets']['ordinary']['common_support']['sample_count']
    base_spans = em.clip_spans(base['pitch_spans'], horizon)
    occ = defaultdict(list)
    for left, right, pitch in base_spans:
        occ[pitch].append((left, right))
    for pitch in occ:
        occ[pitch].sort()

    def occupied(pitch, sample):
        iv = occ.get(pitch)
        if not iv:
            return False
        i = bisect.bisect_right(iv, (sample, 10 ** 12)) - 1
        return i >= 0 and iv[i][0] <= sample < iv[i][1]

    last_label = {}
    rows = {'primary': {'true': [], 'ghost': []}, 'secondary': {'true': [], 'ghost': []}}
    subject = Counter()
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        stream.readline()
        stream.readline()
        for line in stream:
            frame = gs._frame('\t'.join(line.rstrip('\n').split('\t')[:8]))
            tick, sample = frame['tick'], frame['sample']
            active = {row[1] for row in frame['labels']}
            for note in active:
                last_label[note] = tick
            voices = frame['voices']
            lows = [v for v in voices if v[1] < split.SPLIT]
            if not lows:
                continue
            cands = gs._candidates(frame)
            for voice in lows:
                note = voice[1]
                if note in active:
                    kind = 'true'
                elif tick - last_label.get(note, -10 ** 9) > TAIL_TICKS:
                    kind = 'ghost'
                else:
                    continue
                cand = cands.get(voice[0])
                if cand is None or cand['selection'] == 0 or not occupied(note, sample):
                    continue
                subject[kind] += 1
                for run_name in ('primary', 'secondary'):
                    partners = [(abs(note - o[1]), o) for o in voices
                                if o is not voice and o[1] != note and (note - o[1]) % 12 in (0, 7) and abs(note - o[1]) <= 36
                                and (run_name == 'secondary' or occupied(o[1], sample))]
                    if not partners:
                        continue
                    subject[f'{run_name}_{kind}_partnered'] += 1
                    partner = min(partners, key=lambda x: x[0])[1]
                    pc = cands.get(partner[0])
                    logr = float('nan')
                    if (cand.get('energy_observed') == 1 and pc is not None and pc.get('energy_observed') == 1
                            and cand['fund_energy'] > 0 and pc['fund_energy'] > 0):
                        logr = math.log10(cand['fund_energy'] / pc['fund_energy'])
                    rows[run_name][kind].append([cand[f] if f != 'LOGR' else logr for f in FEATURES])
    result = dict(subject_ticks={k: subject[k] for k in ('true', 'ghost')})
    for run_name in ('primary', 'secondary'):
        table = {}
        for i, name in enumerate(FEATURES):
            g = [r[i] for r in rows[run_name]['ghost'] if not (isinstance(r[i], float) and math.isnan(r[i]))]
            t = [r[i] for r in rows[run_name]['true'] if not (isinstance(r[i], float) and math.isnan(r[i]))]
            stats = gs.auc_and_tpr(g, t)
            if stats:
                stats.update(n_ghost=len(g), n_true=len(t))
            table[name] = stats
        result[run_name] = dict(
            partnered={k: subject[f'{run_name}_{k}_partnered'] for k in ('true', 'ghost')},
            partnered_share={k: round(subject[f'{run_name}_{k}_partnered'] / subject[k], 3) for k in ('true', 'ghost') if subject[k]},
            features=table)
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), indent=1))
