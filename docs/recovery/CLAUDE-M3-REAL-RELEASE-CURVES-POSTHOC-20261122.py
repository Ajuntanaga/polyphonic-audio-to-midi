"""POST HOC readings of the real-audio release curves (not registered; every number here is labelled post hoc in the note).

Reuses the registered definitions of CLAUDE-M3-REAL-RELEASE-CURVES-20261122.py and its saved tapes.  Adds: the four detection groups over every
evaluable end, absolute release delays per arm, the adapted-only population, the share of ends released later than the corpus's typical 102 ms
gap, and a polyphony count that includes labels ending at the same sample (the registered `others` excludes them, so it was 0 for every end of
a chord that ends together).

Usage: python3 CLAUDE-M3-REAL-RELEASE-CURVES-POSTHOC-20261122.py UNMODIFIED_DIR ADAPTED_DIR [OUT.json]
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


main = load('rc', 'CLAUDE-M3-REAL-RELEASE-CURVES-20261122.py')
np = main.np
GAP_MS = 102
DECODER_CONFIRM_MS = 2 * main.FRAME_HOP / main.MODEL_RATE * 1000     # the decoder emits 'off' on the third frame of the run


def quantiles(values):
    if not len(values):
        return None
    return {q: round(float(np.percentile(values, q)), 1) for q in (10, 25, 50, 75, 90)}


def share_at_least(values, bound):
    return None if not len(values) else round(sum(v >= bound for v in values) / len(values), 3)


def others_inclusive(labels, row):
    """Other-pitch union spans sounding just before the end: start < E <= end (so labels that end with this one count)."""
    unions = main.union_by_pitch(labels)
    return sum(1 for n, s in unions.items() if n != row['midi_note'] for a, b in s if a < row['end'] <= b)


def arm_summary(rows, arm):
    detected = [r for r in rows if r[arm]['detected']]
    delays = [r[arm]['delay_ms'] for r in detected if not r[arm]['censored']]
    return dict(detected=len(detected), censored=sum(r[arm]['censored'] for r in detected), delay_ms=quantiles(delays),
                share_delay_ge_gap=share_at_least(delays, GAP_MS), share_delay_ge_gap_minus_confirm=share_at_least(delays, GAP_MS - DECODER_CONFIRM_MS),
                plateau=quantiles([r[arm]['plateau'] for r in detected]), early_plateau=quantiles([r[arm]['early_plateau'] for r in detected]))


def alive_at(spans, note, sample):
    return any(a <= sample < b for a, b, n in spans if n == note)


def event_clock_crosscheck(rows, directories, name, horizon):
    """Apply the earlier definition (an event-clock run of the same pitch still active at the end of a 102 ms gap, availability clock) to the same
    ends, and cross-tabulate it with the tape's presence at the label end.  Pure arithmetic on the saved events."""
    from tools.basic_pitch_streaming import emission_spans
    result = {}
    for arm, directory in directories.items():
        events = main.load_events(os.path.join(directory, name + '-events.json'))
        spans, _ = emission_spans(events, 'available_ns', horizon)
        table = dict(detected_alive=0, detected_not_alive=0, undetected_alive=0, undetected_not_alive=0)
        by_pitch = {}
        for a, b, n in spans:
            by_pitch.setdefault(n, []).append((a, b, n))
        for r in rows:
            t = r['end'] + GAP_MS * main.SOURCE_RATE // 1000
            if t >= horizon:
                continue
            alive = alive_at(by_pitch.get(r['midi_note'], []), r['midi_note'], t)
            key = ('detected' if r[arm]['detected'] else 'undetected') + ('_alive' if alive else '_not_alive')
            table[key] += 1
        total = sum(table.values())
        table['alive_share'] = round((table['detected_alive'] + table['undetected_alive']) / total, 3) if total else None
        table['tape_detected_share'] = round((table['detected_alive'] + table['detected_not_alive']) / total, 3) if total else None
        table['agreement_share'] = round((table['detected_alive'] + table['undetected_not_alive']) / total, 3) if total else None
        result[arm] = table
    return result


def corpus(unmodified_dir, adapted_dir, name, support):
    tapes = {}
    for arm, directory in (('unmodified', unmodified_dir), ('adapted', adapted_dir)):
        check, tapes[arm] = main.mapping_check(directory, name)
        assert check['c0a'] and check['c0b'] is not False
    ctx = support.dataset_context(name)
    labels, horizon = ctx['labels'], ctx['horizon']
    _, rows = main.analyse(tapes, labels, horizon)
    for r in rows:
        r['others_inclusive'] = others_inclusive(labels, r)
    groups = dict(both=[r for r in rows if r['unmodified']['detected'] and r['adapted']['detected']],
                  adapted_only=[r for r in rows if not r['unmodified']['detected'] and r['adapted']['detected']],
                  unmodified_only=[r for r in rows if r['unmodified']['detected'] and not r['adapted']['detected']],
                  neither=[r for r in rows if not r['unmodified']['detected'] and not r['adapted']['detected']])
    out = dict(evaluable=len(rows), groups={k: len(v) for k, v in groups.items()},
               event_clock_crosscheck=event_clock_crosscheck(rows, dict(unmodified=unmodified_dir, adapted=adapted_dir), name, horizon),
               unmodified=arm_summary(rows, 'unmodified'), adapted=arm_summary(rows, 'adapted'))
    # Adapted-only: what the adapted model does at ends the unmodified model has already released.
    ao = groups['adapted_only']
    out['adapted_only'] = dict(n=len(ao), delay_ms=quantiles([r['adapted']['delay_ms'] for r in ao if not r['adapted']['censored']]),
                               plateau=quantiles([r['adapted']['plateau'] for r in ao]),
                               unmodified_plateau=quantiles([r['unmodified']['plateau'] for r in ao]),
                               unmodified_early_plateau=quantiles([r['unmodified']['early_plateau'] for r in ao]),
                               share_delay_ge_gap=share_at_least([r['adapted']['delay_ms'] for r in ao if not r['adapted']['censored']], GAP_MS))
    # Polyphony, inclusive count, over paired ends: median adapted-minus-unmodified delay per group, and over adapted-only ends the adapted delay.
    both = groups['both']

    def diffs(selector):
        values = [r['adapted']['delay_ms'] - r['unmodified']['delay_ms'] for r in both
                  if selector(r['others_inclusive']) and not r['adapted']['censored'] and not r['unmodified']['censored']]
        return dict(pairs=len(values), median_ms=None if not values else round(float(np.median(values)), 1))
    out['polyphony_inclusive_paired'] = {k: diffs(f) for k, f in (('0', lambda x: x == 0), ('1-2', lambda x: 1 <= x <= 2), ('3+', lambda x: x >= 3))}
    out['polyphony_distribution_evaluable'] = {k: sum(f(r['others_inclusive']) for r in rows) for k, f in
                                               (('0', lambda x: x == 0), ('1-2', lambda x: 1 <= x <= 2), ('3+', lambda x: x >= 3))}
    out['detected_share_by_polyphony'] = {k: dict(n=sum(f(r['others_inclusive']) for r in rows),
                                                 unmodified=sum(f(r['others_inclusive']) and r['unmodified']['detected'] for r in rows),
                                                 adapted=sum(f(r['others_inclusive']) and r['adapted']['detected'] for r in rows))
                                          for k, f in (('0', lambda x: x == 0), ('1-2', lambda x: 1 <= x <= 2), ('3+', lambda x: x >= 3))}
    # The registered quantities on the earlier stratum: ends whose next label (any pitch) follows within the corpus's ~102 ms gap are unknown here;
    # label ends sorted by length of the span, short vs long, to see whether the hold depends on how long the note was.
    lengths = sorted(r['end'] - r['start'] for r in rows)
    cut = lengths[len(lengths) // 2] if lengths else 0
    for label, selector in (('short_half', lambda r: r['end'] - r['start'] < cut), ('long_half', lambda r: r['end'] - r['start'] >= cut)):
        sub = [r for r in rows if selector(r)]
        out['by_note_length_' + label] = dict(n=len(sub), detected_unmodified=sum(r['unmodified']['detected'] for r in sub),
                                              detected_adapted=sum(r['adapted']['detected'] for r in sub))
    out['note_length_median_ms'] = round(cut / 96, 1)
    return out


def run(unmodified_dir, adapted_dir, out=None):
    support = main.load_module('asup', 'CLAUDE-M3-ADAPTED-SUPPORT-20261122.py')
    result = {name: corpus(unmodified_dir, adapted_dir, name, support) for name in ('ordinary', 'extended-middle')}
    result['decoder_confirm_ms'] = round(DECODER_CONFIRM_MS, 2)
    text = json.dumps(result, indent=1)
    if out:
        open(out, 'w').write(text + '\n')
    print(text)


if __name__ == '__main__':
    run(*sys.argv[1:4])
