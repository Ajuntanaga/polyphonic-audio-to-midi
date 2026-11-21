#!/usr/bin/env python3
"""Which saved-table rule reproduces the lane the EXISTING selection DP gives a rendered upper note? (saved v5 table only: no audio, no dispatch, no replay)

  python3 -I CLAUDE-M3-DP-LANE-RULE-CHECK-20261120.py PROJECT_ROOT V5_TABLE.tsv.gz OUT.json

Why: my lane analysis assumed the DP gives a note its lowest-fret free lane and predicted a ~5% match with the annotation in the relief-eligible frames,
but the rejected screen realized 13,412 correct-lane matched frames against +7,810 wrong-string frames (63% correct by frames). The assumption has to be
tested on frames where the DP really did assign a lane, not guessed.

PREDECLARED BEFORE ANY NUMBER WAS COMPUTED (exploratory, associations only, one CURRENT configuration, annotation is not audibility):
  Population R = (tick, voice) pairs of the table with voice outcome in {0 correct_voice, 2 wrong_string} (a labeled pitch is rendered), rendered note
    61..84, not a quiet tick, and a candidate row for the voice's detected note (voice[0]). voice[2] is the string the DP gave it (0..7, open = 32+4*s).
  Rival lane rules, each computed from the same tick's saved fields only (no fitting, no threshold):
    R_minfret  = highest set bit of playable_mask & ~(strings of the other voices of the tick)       (min-fret free lane; the rule I assumed)
    R_cal      = best_string, only when cal_mask != 0 and best_string is in playable_mask             (calibration pick)
    R_option   = highest set bit of selector_option_mask                                               (strings the selector offered)
    R_positive = highest set bit of selector_positive_mask                                             (strings with a positive adjusted score)
    R_lowfret  = highest set bit of playable_mask                                                      (min-fret playable, ignoring other voices)
  Reported per rule: n where it is defined; agreement with voice[2]; and, by outcome (0 vs 2), the agreement, so a rule that merely tracks the DP is
  separated from one that tracks the annotation. Also reported: the share of R with outcome 0, by band 61-71 and 72-84, by number of voices in the
  tick (1, 2, 3+), and by annotated string. Annotated lane count of labels is reported only for outcome-2 voices (their label mask).
  Nothing is tuned; any rule this suggests needs its own predeclaration and a separately authorized screen.
"""
import collections, json, sys

PROJ, TABLE, OUT = sys.argv[1:4]
sys.argv = [sys.argv[0], PROJ]
import importlib.util
spec = importlib.util.spec_from_file_location('m3an', PROJ + '/docs/recovery/CLAUDE-M3-OBSERVATION-ANALYSIS-20261120.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def hb(mask):
    return mask.bit_length() - 1 if mask else None


def main():
    tot = collections.Counter()
    agree = collections.defaultdict(collections.Counter)    # rule -> counters
    share = collections.defaultdict(collections.Counter)    # slice -> {'n','o0'}
    assigned_hist = collections.Counter()
    outcome2_ann = collections.Counter()
    for fr in m.load_new(TABLE):
        if fr['quiet']:
            continue
        voices = fr['voices']
        lab_by_note = {}
        for (lid, note, mask) in fr['labels']:
            lab_by_note.setdefault(note, mask)
        for i, v in enumerate(voices):
            det, ren, s, out = v[0], v[1], v[2], v[3]
            if out not in (0, 2) or not 61 <= ren <= 84:
                continue
            c = fr['rows'].get(det)
            if c is None:
                tot['no_candidate_row'] += 1
                continue
            tot['R'] += 1
            band = '61-71' if ren <= 71 else '72-84'
            nv = '1' if len(voices) == 1 else '2' if len(voices) == 2 else '3+'
            for key in (band, 'voices=' + nv, 'string=%d' % s, 'all'):
                share[key]['n'] += 1
                share[key]['o0'] += 1 if out == 0 else 0
            assigned_hist[s] += 1
            if out == 2:
                mk = lab_by_note.get(ren, 0)
                outcome2_ann[str(sorted(b for b in range(8) if mk >> b & 1))] += 1
            others = 0
            for j, w in enumerate(voices):
                if j != i:
                    others |= 1 << w[2]
            play = c['playable_mask']
            rules = {
                'R_minfret': hb(play & ~others),
                'R_cal': c['best_string'] if (c['cal_mask'] != 0 and play >> c['best_string'] & 1) else None,
                'R_option': hb(c['selector_option_mask']),
                'R_positive': hb(c['selector_positive_mask']),
                'R_lowfret': hb(play),
            }
            for name, pick in rules.items():
                if pick is None:
                    agree[name]['undefined'] += 1
                    continue
                a = agree[name]
                a['n'] += 1
                hit = pick == s
                a['agree'] += 1 if hit else 0
                a['n_out%d' % out] += 1
                a['agree_out%d' % out] += 1 if hit else 0
    rep = dict(counts=dict(tot), rules={k: dict(v) for k, v in agree.items()},
               outcome0_share={k: dict(v) for k, v in sorted(share.items())},
               assigned_string_hist=dict(sorted(assigned_hist.items())), outcome2_annotated_lanes=dict(outcome2_ann.most_common(12)))
    json.dump(rep, open(OUT, 'w'), indent=1, default=str)
    print(json.dumps(rep, indent=1, default=str))


main()
