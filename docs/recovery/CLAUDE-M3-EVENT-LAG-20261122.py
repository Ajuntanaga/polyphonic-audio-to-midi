"""Per-event lag summary for a Basic Pitch events file, read against the delay budget.  Saved data only; no audio, model run or job.

Lag of an event is emitted_ns - available_ns: how long after the moment its content could be known the tracker actually got it.  The delay
sweeps (CLAUDE-M3-MODEL-DELAY-RESULT-20261122.md, CLAUDE-M3-RESTRICTED-UNION-DELAY-RESULT-20261122.md) say a fixed lag L keeps the full
union ahead of CURRENT on coverage and precision together only up to about 150 ms (precision crosses CURRENT between 150 and 200 ms), and
the pitch >= 60 partition up to about 250 ms (crosses between 250 and 500 ms).  This script reports the observed lag distribution (median
and tail) and the share of events inside each budget; it does not score tracking and is not a gate.  A real distribution with a long tail
does worse than a fixed shift at its median, so the tail shares are the figures to read first.  Run it on the events and the real scoring
(CLAUDE-M3-ADAPTED-SUPPORT-20261122.py, emitted_ns clock) gives the actual effect.

Usage: python3 -P -E CLAUDE-M3-EVENT-LAG-20261122.py EVENTS.json[.gz] [EVENTS2 ...]
"""
import gzip
import json
import math
import sys

BUDGETS_MS = (100, 150, 250, 500)


def read_events(path):
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rt') as stream:
        return json.load(stream)['events']


def quantile(sorted_values, q):
    if not sorted_values:
        return None
    index = min(len(sorted_values) - 1, max(0, math.ceil(q * len(sorted_values)) - 1))
    return sorted_values[index]


def summarize(lags_ms):
    ordered = sorted(lags_ms)
    out = {'events': len(ordered)}
    if not ordered:
        return out
    out.update(
        min_ms=round(ordered[0], 2),
        median_ms=round(quantile(ordered, 0.5), 2),
        p90_ms=round(quantile(ordered, 0.9), 2),
        p99_ms=round(quantile(ordered, 0.99), 2),
        max_ms=round(ordered[-1], 2),
        negative=sum(1 for v in ordered if v < 0),
    )
    for budget in BUDGETS_MS:
        out[f'within_{budget}_ms_pct'] = round(100 * sum(1 for v in ordered if v <= budget) / len(ordered), 1)
    return out


def lag_report(events):
    lags = {'all': [], 'on': [], 'off': []}
    for event in events:
        lag = (event['emitted_ns'] - event['available_ns']) / 1e6
        lags['all'].append(lag)
        if event.get('kind') in lags:
            lags[event['kind']].append(lag)
    return {kind: summarize(values) for kind, values in lags.items()}


def selftest():
    events = [dict(kind='on', emitted_ns=10_000_000 * i + 11_000_000, available_ns=10_000_000 * i) for i in range(100)]
    rep = lag_report(events)['all']
    assert rep['events'] == 100 and rep['median_ms'] == 11.0 and rep['max_ms'] == 11.0 and rep['within_100_ms_pct'] == 100.0, rep
    slow = [dict(kind='off', emitted_ns=int(v * 1e6), available_ns=0) for v in (50, 120, 300, 700)]
    rep = lag_report(slow)['off']
    assert rep['within_100_ms_pct'] == 25.0 and rep['within_150_ms_pct'] == 50.0 and rep['within_250_ms_pct'] == 50.0, rep
    assert rep['within_500_ms_pct'] == 75.0 and rep['median_ms'] == 120.0 and rep['p99_ms'] == 700.0, rep
    assert lag_report([])['all'] == {'events': 0}
    print('selftest ok')


def main(argv):
    if argv == ['--selftest']:
        return selftest()
    if not argv:
        raise SystemExit(__doc__)
    for path in argv:
        print(path)
        for kind, row in lag_report(read_events(path)).items():
            print(' ', kind, json.dumps(row))


if __name__ == '__main__':
    main(sys.argv[1:])
