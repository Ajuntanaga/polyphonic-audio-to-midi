"""Print the per-pitch, per-case tables of a release-probe report.json (presentation only; the verdicts are the runner's, as registered).

Usage: python3 CLAUDE-M3-RELEASE-PROBE-TABLES-20261122.py REPORT.json
"""
import json
import sys


def cell(row):
    if row is None:
        return 'n/a'
    if not row['active']:
        return 'undetected'
    mark = '>=' if row['censored'] else ''
    edge = '*' if row.get('edge_affected') else ''
    return '%s%.0f ms%s%s' % (mark, row['delay_ms'], edge, '' if 'level_db' not in row else ' / %s%.1f dB' % ('<=' if row['censored'] else '', row['level_db']))


def tables(report):
    lines = []
    cases = list(report['measurements']['unmodified'])
    pitches = sorted({int(m) for case in report['measurements']['unmodified'].values() for m in case})
    for model in ('unmodified', 'adapted'):
        lines.append('\n%s: release delay after the end (ms) / release level (dB below steady); >= and <= mark censored bounds; * edge-affected' % model)
        lines.append('| case | ' + ' | '.join('MIDI %d' % m for m in pitches) + ' |')
        lines.append('|---|' + '---|' * len(pitches))
        for case in cases:
            rows = report['measurements'][model][case]
            lines.append('| %s | ' % case + ' | '.join(cell(rows.get(str(m))) for m in pitches) + ' |')
    lines.append('\nadapted minus unmodified release delay (ms), where both are active and uncensored')
    lines.append('| case | ' + ' | '.join('MIDI %d' % m for m in pitches) + ' |')
    lines.append('|---|' + '---|' * len(pitches))
    for case in cases:
        out = []
        for m in pitches:
            a, u = (report['measurements'][k][case].get(str(m)) for k in ('adapted', 'unmodified'))
            out.append('n/a' if not (a and u and a['active'] and u['active']) else
                       ('%+.0f' % (a['delay_ms'] - u['delay_ms']) if not a['censored'] and not u['censored']
                        else ('>=%+.0f' % (a['delay_ms'] - u['delay_ms']) if a['censored'] and not u['censored'] else 'censored original')))
        lines.append('| %s | ' % case + ' | '.join(out) + ' |')
    lines.append('\ncontrols: ' + json.dumps(report['controls']))
    lines.append('\nverdicts: ' + json.dumps({k: v['verdict'] for k, v in report['verdicts'].items()}))
    return '\n'.join(lines)


if __name__ == '__main__':
    print(tables(json.loads(open(sys.argv[1]).read())))
