"""At the ticks where CURRENT sounds a lower ghost beside an uncovered related label, is that label's own pitch a candidate?  Saved trace only.

No audio, model run or job.  The oracle substitution result (CLAUDE-M3-LOWREG-ORACLE-SUBSTITUTION-20261122) bounds what a
label-aware corrector could gain by pointing an orphan at an uncovered related label; the ambiguity result found the target
unique in 69.6% of those stretches.  A label-free corrector needs the target pitch to exist in the tracker's own candidate
table.  Here, on the v5 trace of the unfiltered-observation run (ordinary, CURRENT ON, block 512):

  subject tick = a selected candidate of a rendered note n below MIDI 60 with no same-pitch label active now and none in the
                 previous 1.5 s (the `ghost` class of the tail-state and ghost-separation work);
  substitution tick = a subject tick with some active label L (pitch p, class octave / twelfth-like / near of n) that no
                 voice in that frame renders; p is taken by (class order, |d|) as in the oracle.

For substitution ticks, report whether the candidate table holds a candidate whose note is p, whether it is selected, how
its features compare with the ghost's own candidate (fund_ratio, band_fund, fund_energy, direct), and the base rate at which
a lower-band pitch that is NOT an active label has a candidate on the same ticks (chance of existence).  Ticks in one span
are strongly correlated, so these are descriptive tick-level numbers, not span-level evidence.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the oracle, ambiguity, null and ghost-separation results and Codex's prior-controls note.  NOT seen: any
candidate-existence count.  Predictions, each can fail:
  R1  at least 50% of substitution ticks have a candidate for the label's pitch in the table.
  R2  among those, at least 50% are not emitted (they exist but lose or are skipped).  "Emitted" means disposition
      selected or coasting (trace codes 4 and 5); the first run of this script treated any non-quiet code as selected,
      which was a code error that made R2 uninterpretable, so R2 is judged on the corrected run only.  R1, R3, R4 and R5
      do not depend on the disposition and their first-run values stand.
  R3  where both are observed, the label's candidate has the larger fund_ratio than the ghost's own in at least 60% of ticks.
  R4  the existence rate for the label's pitch is at least three times the base rate for non-label lower-band pitches.
  R5  the same R1 existence rate is at least 50% for the octave class alone.
Report the whole table whatever it shows.  Pitch occupancy at decision-tick resolution; no lane, unison, callback or
live-host claim.  Nothing here selects a native rule.

Usage: python3 -P -E CLAUDE-M3-LOWREG-SUBSTITUTE-CANDIDATE-20261122.py TRACE.tsv.gz
"""
import gzip
import importlib.util
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
spec = importlib.util.spec_from_file_location('oracle', os.path.join(HERE, 'CLAUDE-M3-LOWREG-ORACLE-SUBSTITUTION-20261122.py'))
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)
spec = importlib.util.spec_from_file_location('tailstate', os.path.join(HERE, 'CLAUDE-M3-LOWREG-TAIL-STATE-20261122.py'))
tailstate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tailstate)
split = tailstate.split
rel_class = oracle.rel_class
from tools.candidate_outcome_analysis import _candidates, _frame  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-SUBSTITUTE-CANDIDATE-20261122.json')
TAIL_TICKS = tailstate.TAIL_TICKS
LOW_RANGE = range(32, split.SPLIT)          # M3 open low string is MIDI 32; the band is below MIDI 60
CLASSES = ('octave', 'fifth', 'near')
DISPOSITION = ('quiet', 'below_threshold', 'spectral_rejected', 'dp_evicted', 'selected', 'coasting')
EMITTED = (4, 5)        # selected or coasting: the dispositions of a candidate that is an output voice


def run(path):
    last_label = {}
    count = Counter()
    by_class = {c: Counter() for c in CLASSES}
    compare = Counter()
    base_hits = base_trials = 0
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        stream.readline()
        stream.readline()
        for line in stream:
            frame = _frame('\t'.join(line.rstrip('\n').split('\t')[:8]))
            tick = frame['tick']
            active = {row[1] for row in frame['labels']}
            for note in active:
                last_label[note] = tick
            voices = frame['voices']
            lows = [v for v in voices if v[1] < split.SPLIT]
            if not lows:
                continue
            cands = _candidates(frame)
            rendered = {v[1] for v in voices}
            for voice in lows:
                n = voice[1]
                if n in active or tick - last_label.get(n, -10 ** 9) <= TAIL_TICKS:
                    continue
                own = cands.get(voice[0])
                if own is None or own['selection'] == 0:
                    continue
                count['ghost_selected_ticks'] += 1
                related = []
                for p in active:
                    rc = rel_class(n - p)
                    if rc is not None:
                        related.append((rc[0], abs(n - p), p, rc[1]))
                if not related:
                    continue
                count['ghost_with_related_label'] += 1
                uncovered = sorted(r for r in related if r[2] not in rendered)
                if not uncovered:
                    count['ghost_related_but_covered'] += 1
                    continue
                count['substitution_ticks'] += 1
                if len(uncovered) == 1:
                    count['substitution_unique'] += 1
                _order, _dist, p, cls = uncovered[0]
                by_class[cls]['ticks'] += 1
                target = cands.get(p)
                if target is None:
                    count['target_absent'] += 1
                    continue
                count['target_present'] += 1
                by_class[cls]['present'] += 1
                count['target_' + DISPOSITION[target['selection']]] += 1
                emitted = target['selection'] in EMITTED
                count['target_emitted' if emitted else 'target_not_emitted'] += 1
                if not emitted:
                    by_class[cls]['unselected'] += 1
                if voice[0] == p:
                    count['target_is_the_ghosts_own_detected_note'] += 1
                elif any(v[0] == p for v in voices):
                    count['target_is_another_voices_detected_note'] += 1
                count['own_' + DISPOSITION[own['selection']]] += 1
                for f in ('fund_ratio', 'band_fund'):
                    compare[f + '_n'] += 1
                    compare[f + '_target_greater'] += target[f] > own[f]
                compare['direct_n'] += 1
                compare['direct_target_greater'] += target['direct'] > own['direct']
                compare['direct_target_equal'] += target['direct'] == own['direct']
                if target.get('energy_observed') == 1 and own.get('energy_observed') == 1:
                    compare['fund_energy_n'] += 1
                    compare['fund_energy_target_greater'] += target['fund_energy'] > own['fund_energy']
                # base rate: lower-band pitches that are not active labels and are not this ghost's own pitch
                for q in LOW_RANGE:
                    if q in active or q == n:
                        continue
                    base_trials += 1
                    base_hits += q in cands
    sub = count['substitution_ticks']
    present = count['target_present']
    out = dict(counts={k: count[k] for k in ('ghost_selected_ticks', 'ghost_with_related_label', 'ghost_related_but_covered',
                                             'substitution_ticks', 'substitution_unique', 'target_present', 'target_absent',
                                             'target_emitted', 'target_not_emitted',
                                             'target_is_the_ghosts_own_detected_note',
                                             'target_is_another_voices_detected_note')},
               target_disposition={name: count['target_' + name] for name in DISPOSITION},
               ghost_own_candidate_disposition={name: count['own_' + name] for name in DISPOSITION},
               existence_rate=round(present / sub, 3) if sub else None,
               not_emitted_share_of_present=round(count['target_not_emitted'] / present, 3) if present else None,
               base_rate_non_label_lower_pitch=round(base_hits / base_trials, 4) if base_trials else None,
               existence_over_base=round((present / sub) / (base_hits / base_trials), 2) if sub and base_hits else None,
               by_class={c: dict(ticks=by_class[c]['ticks'], present=by_class[c]['present'], unselected=by_class[c]['unselected'],
                                 existence_rate=round(by_class[c]['present'] / by_class[c]['ticks'], 3) if by_class[c]['ticks'] else None)
                         for c in CLASSES},
               target_greater_share={f: round(compare[f + '_target_greater'] / compare[f + '_n'], 3) if compare[f + '_n'] else None
                                     for f in ('fund_ratio', 'band_fund', 'direct', 'fund_energy')},
               direct_target_equal_share=round(compare['direct_target_equal'] / compare['direct_n'], 3) if compare['direct_n'] else None,
               compared_ticks={f: compare[f + '_n'] for f in ('fund_ratio', 'band_fund', 'direct', 'fund_energy')})
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    return out


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), indent=1))
