#!/usr/bin/env python3
"""Where do stable-note suppressed NoteOns fall relative to annotated note starts? (ordinary recording)

Saved data only: the ledger run 44079653692's tagged MIDI trace and stable-note callback trace (both hash-pinned, fetched by ranged request, ~0.2 MB)
and the ordinary label TSV.  No audio, no native code, no job.  The six corpus traces Codex already analysed (CODEX-M3-STABLE-NOTE-ATTACK-TIMING-20261122)
are NOT re-analysed: that note shows the seven no-NoteOn labels are simultaneous cross-lane handoffs, and I accept it.

Question: among baseline NoteOns, are the ones the stable path suppresses (the On half of a merged Off/On pair) less likely to sit in the attack zone of an annotated
same-pitch label than elsewhere?  If suppressed NoteOns avoid annotated starts, the path removes lane handoffs, not re-plucks.  If they land on annotated starts,
that is attack-specific evidence of harm.  Ordinary labels have annotated start samples (unlike the physical-corpus rows), so this is the first test where the
truth carries a start time.

Zones (pitch must equal the NoteOn's pitch): attack = [start-25 ms, start+100 ms] of a same-pitch label; inside = within a same-pitch label elsewhere; outside = none.
Secondary, descriptive only: attack windows of 50 ms and 200 ms after start.  Annotation start precision is unknown.

PRE-REGISTERED (written and committed before --run; plumbing selftest and --dry only seen):
  P1  removed-rate(attack) < removed-rate(inside)                 65%
  P2  removed-rate(attack) <= 10%                                  50%
  P3  at least 1 labeled start has its attack-zone NoteOn removed  80%
Verdict rule: none.  No exemption, gate, policy or default follows; it is descriptive evidence for the next decision.
Plumbing (identity gate, replaces the ledger emulation I first planned): callbacks = 8,623, suppressed events form reciprocal tagged pairs = 1,614.

Usage: python3 -I this.py [--selftest | --dry | --run]
"""
import csv, gzip, hashlib, json, sys
from collections import Counter, defaultdict
from pathlib import Path

SR = 96000
PRE, POST = int(0.025 * SR), int(0.100 * SR)
ROOT = Path(sys.argv[0]).resolve().parents[2]
LEDGER = ROOT / 'build/github-results/stable-note-traces-20261122-ledger/github-results/stable-note-identity-ledger'
PINS = {'tagged-on/midi-event.tsv.gz': 'bc326a64e081259bfd845758a9294c2be43eb75f89b7ac5e241d67a8e0bb5b4c',
        'stable_note-callbacks.tsv.gz': '650446adbc06505afbb48c5242967bbb0e4b84583dbbf2415c1ab1bece8dcc15'}
LABELS = ROOT / 'build/github-results/upper-fretted-relief-44881108478/evidence/ordinary-current-on-512.tsv'
OUT = Path(__file__).with_suffix('.json')


def read_tsv_gz(path, magic):
    with gzip.open(path, 'rt') as f:
        assert f.readline().rstrip('\n') == magic
        r = csv.reader(f, delimiter='\t')
        head = next(r)
        return head, list(r)


def read_labels(path):
    with open(path) as f:
        lines = f.read().split('\n')
    i = next(k for k, l in enumerate(lines) if l.startswith('label_index\t'))
    cols = lines[i].split('\t')
    ix = {c: cols.index(c) for c in ('start_sample', 'end_sample', 'midi_note')}
    out = []
    for l in lines[i + 1:]:
        if l:
            p = l.split('\t')
            out.append(tuple(int(p[ix[c]]) for c in ('start_sample', 'end_sample', 'midi_note')))
    return out


def suppressed_on_events(tagged_rows, callback_rows):
    """Return (set of suppressed source sequences, pair count, callback count); raises if not reciprocal pairs."""
    src = {int(r[5]): dict(sample=int(r[0]), kind=r[1], note=int(r[2]), voice=int(r[4]), tag=int(r[6])) for r in tagged_rows}
    seen = {int(r[7]) for r in callback_rows}
    missing = set(src) - seen
    rem, pairs = set(missing), 0
    while rem:
        a = min(rem); e = src[a]
        p = [b for b in rem if b != a and src[b]['sample'] == e['sample'] and src[b]['note'] == e['note'] and src[b]['kind'] != e['kind']
             and src[b]['voice'] == e['tag'] and src[b]['tag'] == e['voice'] and src[b]['voice'] != e['voice']]
        if len(p) != 1:
            raise ValueError('suppressed event without unique reciprocal partner')
        rem -= {a, p[0]}; pairs += 1
    return src, missing, pairs, len(callback_rows)


def zone(sample, note, labels, post):
    inside = False
    for s, e, n in labels:
        if n != note:
            continue
        if s - PRE <= sample <= s + post:
            return 'attack'
        if s + post < sample <= e:
            inside = True
    return 'inside' if inside else 'outside'


def analyse(src, missing, labels, post=POST):
    by = defaultdict(Counter)
    attack_labels = defaultdict(lambda: [0, 0])  # label -> [NoteOns in attack zone, removed]
    for q, e in src.items():
        if e['kind'] != 'on':
            continue
        z = zone(e['sample'], e['note'], labels, post)
        by[z]['ons'] += 1
        by[z]['removed'] += q in missing
        by[z]['tagged'] += e['tag'] != 255
        if z == 'attack':
            for k, (s, en, n) in enumerate(labels):
                if n == e['note'] and s - PRE <= e['sample'] <= s + post:
                    attack_labels[k][0] += 1; attack_labels[k][1] += q in missing
    res = {z: dict(by[z], removed_rate=(by[z]['removed'] / by[z]['ons'] if by[z]['ons'] else None)) for z in ('attack', 'inside', 'outside')}
    starts_with_on = sum(1 for v in attack_labels.values() if v[0])
    starts_removed = sum(1 for v in attack_labels.values() if v[1])
    return dict(zones=res, labels_with_attack_zone_noteon=starts_with_on, labels_with_removed_attack_noteon=starts_removed,
                labels_total=len(labels))


def selftest():
    # plumbing only: 2 notes, one reciprocal merged pair at sample 15000 (note 50, voices 1->2)
    rows = [['100', 'on', '50', '30', '1', '0', '255'], ['15000', 'off', '50', '0', '1', '1', '2'], ['15000', 'on', '50', '30', '2', '2', '1'],
            ['9000', 'on', '60', '30', '3', '3', '255']]
    cb = [['100', 'source', 'on', '50', '30', '0', '1', '0'], ['9000', 'source', 'on', '60', '30', '3', '2', '3']]
    src, miss, pairs, ncb = suppressed_on_events(rows, cb)
    assert miss == {1, 2} and pairs == 1 and ncb == 2
    lab = [(0, 20000, 50), (8900, 30000, 60)]
    r = analyse(src, miss, lab)
    assert r['zones']['inside']['removed'] == 1 and r['zones']['attack']['ons'] == 2 and r['zones']['attack']['removed'] == 0, r
    try:
        suppressed_on_events(rows, cb[:1])
        raise SystemExit('selftest: missing event should have failed')
    except ValueError:
        pass
    print('selftest ok')


def load():
    for name, want in PINS.items():
        got = hashlib.sha256((LEDGER / name).read_bytes()).hexdigest()
        assert got == want, name
    _, trows = read_tsv_gz(LEDGER / 'tagged-on/midi-event.tsv.gz', '# m3_midi_events_v2')
    _, crows = read_tsv_gz(LEDGER / 'stable_note-callbacks.tsv.gz', '# m3_ledger_callbacks_v1')
    src, miss, pairs, ncb = suppressed_on_events(trows, crows)
    return src, miss, pairs, ncb, len(trows), read_labels(LABELS)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode == '--selftest':
        return selftest()
    src, miss, pairs, ncb, nev, labels = load()
    plumbing = dict(events=nev, callbacks=ncb, merged_pairs=pairs, labels=len(labels))
    assert (nev, ncb, pairs) == (11851, 8623, 1614), plumbing
    if mode == '--dry':
        print('plumbing ok', plumbing); return
    assert mode == '--run' and not OUT.exists(), 'use --run once; refuses to overwrite'
    result = dict(schema='claude_m3_stable_note_attack_zone_v1', plumbing=plumbing,
                  primary=analyse(src, miss, labels), sensitivity_50ms=analyse(src, miss, labels, int(0.05 * SR)),
                  sensitivity_200ms=analyse(src, miss, labels, int(0.2 * SR)))
    OUT.write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps(result, indent=1))


main() if __name__ == '__main__' else None
