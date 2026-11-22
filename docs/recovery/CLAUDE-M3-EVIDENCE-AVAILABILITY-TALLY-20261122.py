"""Plumbing tally for the erratum to the restart-evidence census: where does the saved v5 trace carry per-pitch evidence?  Saved data only; no model, audio, job or native edit.

Question.  The restart-evidence census note (CLAUDE-M3-RESTART-EVIDENCE-CENSUS-RESULT-20261122.md, commit 7aa79a1) said every decision inside a removed part carries a candidate record and
named a "run-interior onset/energy census" as the next check.  That inference was unchecked.  This script counts, per quiet-disposition code of the decision, how many candidate records
exist and how many have the evidence fields observed:

  * energy_observed  (trace field `energy_observed`; with `score_energy` and `fund_energy`) -- set only when the detector evaluated the spectrum for that decision;
  * onset_observed   (trace field `onset_observed`; with `onset`)                          -- the string/fret-posterior onset evidence, set only inside the same evaluation.

The detector (native/src/polyphonic_pitch_detector.cpp at commit 7aa79a1) runs the per-candidate spectral scoring loop only when `!quiet || capture_floor_reentry`; its header says the
pre-selection energy fields are "valid only when the spectrum was evaluated; quiet defaults are unavailable".  Quiet code 5 is the rapid-mute disposition, so the decisions inside a marked
run (the census's removed parts that begin in a run) are exactly the ones where these fields would be unobserved.  This tally measures that on the two pinned traces.

There are no class labels, no labels at all, and no cue-versus-class number here: counts of fields by quiet code only.  The pinned traces are read through the rapid-mute check module's
own pins (SHA-256 of the decompressed trace, verified after the pass; a mismatch aborts before anything is written).

Usage: python3 -P -E CLAUDE-M3-EVIDENCE-AVAILABILITY-TALLY-20261122.py --run
"""
import collections
import csv
import gzip
import hashlib
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
OUT = os.path.join(HERE, 'CLAUDE-M3-EVIDENCE-AVAILABILITY-TALLY-20261122.json')
RECORDINGS = ('ordinary', 'extended-middle')


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tally(rm, candidates, name):
    pin = rm.chk.PINS[name]
    path = os.path.join(ROOT, pin['trace'])
    digest = hashlib.sha256()          # the pin is the SHA-256 of the decompressed trace, as in the support-events check
    rows = collections.defaultdict(collections.Counter)
    with gzip.open(path, 'rb') as stream:
        def lines():
            for raw in stream:
                digest.update(raw)
                yield raw.decode('utf-8')
        text = lines()
        if next(text).strip() != '# m3_candidate_outcome_v5':
            raise SystemExit('unexpected trace header')
        for row in csv.DictReader(text, delimiter='\t'):
            counts = rows[int(row['quiet'])]
            counts['decisions'] += 1
            records = candidates({'candidate_text': row['candidates']})
            if records:
                counts['decisions_with_records'] += 1
            for record in records.values():
                counts['records'] += 1
                counts['energy_observed'] += int(record.get('energy_observed') == 1)
                counts['onset_observed'] += int(record.get('onset_observed') == 1)
                if record['active'] == 1:
                    counts['active_records'] += 1
                    counts['active_energy_observed'] += int(record.get('energy_observed') == 1)
                    counts['active_onset_observed'] += int(record.get('onset_observed') == 1)
                    counts['active_onset_positive'] += int(record.get('onset_observed') == 1 and record['onset'] > 0)
    if digest.hexdigest() != pin['sha']:
        raise SystemExit('trace %s differs from its pin' % name)
    return pin['sha'], {str(code): dict(counts) for code, counts in sorted(rows.items())}


def main():
    rm = load('rm', 'CLAUDE-M3-RAPID-MUTE-CHECK-20261122.py')
    from tools.candidate_outcome_analysis import _candidates
    result = {}
    for name in RECORDINGS:
        sha, by_code = tally(rm, _candidates, name)
        result[name] = dict(trace_sha256_decompressed=sha, by_quiet_code=by_code)
    rapid = {name: result[name]['by_quiet_code'].get('5', {}) for name in RECORDINGS}
    out = dict(schema='m3_evidence_availability_tally_v1', note='counts of record fields by quiet-disposition code; quiet code 5 = rapid_mute_ratio; no class labels',
               recordings=result,
               rapid_mute_summary={name: dict(decisions=v.get('decisions', 0), records=v.get('records', 0), active_records=v.get('active_records', 0),
                                              energy_observed=v.get('energy_observed', 0), onset_observed=v.get('onset_observed', 0)) for name, v in rapid.items()})
    if os.path.exists(OUT):
        raise SystemExit('refusing to overwrite ' + OUT)
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    for name in RECORDINGS:
        for code, counts in result[name]['by_quiet_code'].items():
            print(name, 'quiet', code, json.dumps(counts))


if __name__ == '__main__':
    if sys.argv[1:] == ['--run']:
        main()
    else:
        raise SystemExit(__doc__)
