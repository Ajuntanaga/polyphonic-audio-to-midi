"""Synthetic restart-table contracts; no audio, model or corpus input."""
import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from tools.quiet_cell_reduction import OUTPUT_HEADER
from tools.quiet_cell_restart_analysis import (
    FEATURES, analyze, accumulator, auc_groups, expected_ticks, make_units,
    observe, parse_row, summary, weighted_auc,
)
from tools.portable_quiet_cell_restart_analysis import run


def fixture():
    labels = [dict(label_index=1, midi_note=60, start_sample=2111, end_sample=4000,
                   current_present_samples=1000, current_longest_present_samples=800),
              dict(label_index=2, midi_note=52, start_sample=1900, end_sample=2800,
                   current_present_samples=500, current_longest_present_samples=400)]
    mask = dict(rate=96000, horizon=6000, marked_intervals=[[1983, 2111]],
                comparison=dict(label_deltas=labels))
    census = dict(rate=96000, horizon=6000, marked_runs=1, positive_labels=[1],
        truncated_spans=[dict(pitch=n, span=[1800, 5000], start=1800, cut=1983,
                             run_end=2111, cls='positive' if n == 60 else 'negative')
                         for n in (48, 52, 60)])
    return census, mask


def row(sample, note, *, status='ok', available=True, power=4, recent_power=4):
    values = dict.fromkeys(OUTPUT_HEADER, '')
    values.update(sample=sample, tick=(sample+1)//64, quiet=5 if sample < 2111 else 0,
                  note=note, available=int(available), input_power=power if available else 0,
                  decay=.99 if available else 0, window_ids='0',
                  anchor_sample=sample-1920, interval_samples=1920, interval_status=status)
    for h in range(1, 7):
        values.update({f'h{h}_hz': 200 if h == 1 and available else 0,
                       f'h{h}_real': 1 if h == 1 and available else 0, f'h{h}_imag': 0})
    if status in ('ok', 'negative_power'):
        values.update(interval_power_delta=1 if status == 'ok' else -1,
                      interval_power=recent_power if status == 'ok' else '')
        for h in range(1, 7):
            values[f'h{h}_interval_real'] = (2 if note == 60 else .2) if h == 1 else 0
            values[f'h{h}_interval_imag'] = 0
    return [str(values[key]) for key in OUTPUT_HEADER]


def table():
    rows = [row(sample, note) for sample in (1919, 1983, 2047, 2111, 2175)
            for note in (48, 52, 60)]
    return '# m3_quiet_cell_intervals_v1\n'+'\t'.join(OUTPUT_HEADER)+'\n'+''.join(
        '\t'.join(fields)+'\n' for fields in rows)


class Measurements(unittest.TestCase):
    def test_energy_ratios_enabled_harmonics_and_missing_are_distinct(self):
        _, _, _, values = parse_row(row(1983, 60))
        self.assertEqual(values, dict(zip(FEATURES, (1., 1., 4., .25))))
        for status in ('missing_anchor', 'negative_power', 'configuration_changed'):
            _, _, _, values = parse_row(row(1983, 60, status=status))
            self.assertIsNone(values[FEATURES[0]])
            self.assertIsNone(values[FEATURES[2]])
            self.assertEqual(values[FEATURES[3]], .25)
        _, _, _, values = parse_row(row(1983, 60, status='unavailable_current', available=False))
        self.assertTrue(all(value is None for value in values.values()))

    def test_zero_denominator_and_invalid_rows(self):
        _, _, _, values = parse_row(row(1983, 60, power=0, recent_power=0))
        self.assertIsNone(values[FEATURES[0]])
        self.assertIsNone(values[FEATURES[3]])
        for key, value in (('interval_power', 'nan'), ('interval_samples', '1'),
                           ('window_ids', '0,0'), ('interval_power_delta', '-1')):
            fields = row(1983, 60)
            fields[OUTPUT_HEADER.index(key)] = value
            with self.assertRaises(ValueError):
                parse_row(fields)

    def test_half_open_causal_maximum_and_missing_counts(self):
        acc = accumulator(1983, 2111)
        self.assertEqual(expected_ticks(1983, 2111), 2)
        self.assertEqual(expected_ticks(1984, 2047), 0)
        for sample, value in ((1919, 100), (1983, 2), (2047, None), (2111, 999)):
            observe(acc, sample, 5, 'ok', dict.fromkeys(FEATURES, value))
        self.assertEqual(acc['rows'], 2)
        self.assertEqual(acc['features'][FEATURES[0]], dict(count=1, maximum=2, maximum_sample=1983))

    def test_every_run_in_span_and_continuing_label(self):
        census, mask = fixture()
        mask['marked_intervals'].append([3007, 3135])
        census['marked_runs'] = 2
        units, original = make_units(census, mask)
        self.assertEqual(len(units), 6)
        self.assertEqual(original, {'negative': 2, 'positive': 1})
        first = [u for u in units if u['run_id'] == 0]
        self.assertEqual([u['classification'] for u in first], ['negative', 'continuing', 'positive'])
        self.assertEqual(first[-1]['by_25ms']['end'], 3007)
        self.assertEqual(first[-1]['labels'][0]['budget_samples'], 40)
        self.assertEqual(first[-1]['labels'][0]['measurements']['end'], 2152)
        second = [u for u in units if u['run_id'] == 1 and u['note'] == 60][0]
        self.assertEqual(second['classification'], 'continuing')


class Statistics(unittest.TestCase):
    def test_auc_ties_and_cluster_weights(self):
        groups = auc_groups([(1., 'positive', 0), (1., 'negative', 1),
                             (2., 'positive', 2), (3., 'negative', 1)])
        self.assertAlmostEqual(weighted_auc(groups, {0: 1, 1: 1, 2: 1}), .375)
        self.assertAlmostEqual(weighted_auc(groups, {0: 2, 1: 1, 2: 1}), 1/3)
        self.assertIsNone(weighted_auc(groups, {0: 1}))

    def test_one_class_and_missing_observations_never_pass(self):
        census, mask = fixture()
        units, _ = make_units(census, mask)
        negative = [u for u in units if u['classification'] == 'negative']
        dst = negative[0]['by_25ms']['features'][FEATURES[0]]
        dst.update(count=1, maximum=1., maximum_sample=1983)
        result = summary(negative, 'by_25ms', FEATURES[0], bootstraps=20)
        self.assertIsNone(result['auc'])
        self.assertFalse(result['design_bar'])
        result = summary(units, 'by_25ms', FEATURES[0], bootstraps=20)
        self.assertEqual(result['coverage']['positive'], 0)
        self.assertFalse(result['design_bar'])

    def test_stream_preserves_population_deadlines_and_primary_comparison(self):
        census, mask = fixture()
        result = analyze(iter(io.StringIO(table())), census=census, mask=mask,
                         expected_rows=15, bootstraps=20)
        self.assertEqual(result['pair_classes'], {'negative': 1, 'continuing': 1, 'positive': 1})
        self.assertEqual(result['covered_positive_labels'], [1])
        self.assertEqual(result['missing_positive_labels'], [])
        positive = result['units'][2]
        self.assertEqual(positive['in_run']['rows'], 2)
        self.assertEqual(positive['labels'][0]['measurements']['rows'], 3)
        self.assertEqual(result['primary_auc_gain_over_raw'], .5)
        self.assertTrue(result['primary_supported'])
        self.assertFalse(result['promotion_accepted'])

    def test_duplicate_row_order_sample_grid_and_row_count_fail_closed(self):
        census, mask = fixture()
        text = table()
        for bad, rows in ((text+text.splitlines()[-1]+'\n', 16),
                          (text.replace('1919\t', '1918\t', 1), 15), (text, 14)):
            with self.assertRaises(ValueError):
                analyze(iter(io.StringIO(bad)), census=census, mask=mask,
                        expected_rows=rows, bootstraps=0)


class RemoteContract(unittest.TestCase):
    def test_generated_archive_through_runner_and_identity_failure(self):
        import tools.portable_quiet_cell_restart_analysis as runner
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            census, mask = fixture()
            spec = dict(schema='m3_quiet_cell_restart_spec_v1', policy_change=False,
                        automatic_retry=False, bootstraps=2000, seed=20261122, datasets={})
            for key, data in (('census', census), ('mask', mask)):
                path = root/(key+'.json')
                path.write_text(json.dumps({'datasets': {name: data for name in ('ordinary', 'extended-middle')}}))
                spec[key] = dict(path=str(path), sha256=runner.digest(path))
            archive = root/'source.zip'
            compressed = gzip.compress(table().encode(), mtime=0)
            with zipfile.ZipFile(archive, 'w') as bundle:
                for name in ('ordinary', 'extended-middle'):
                    member = name+'.tsv.gz'
                    bundle.writestr(member, compressed)
                    spec['datasets'][name] = dict(rows=15, horizon=6000, original_spans=3,
                        status_counts={'ok': 15}, member=dict(path=member, bytes=len(compressed),
                        sha256=hashlib.sha256(compressed).hexdigest()))
            spec['artifact'] = dict(id=7, name='synthetic', run_id=8, worker_commit='worker',
                                   bytes=archive.stat().st_size, sha256=runner.digest(archive))
            metadata = dict(id=7, name='synthetic', workflow_run=dict(id=8, head_sha='worker'),
                            digest='sha256:'+spec['artifact']['sha256'],
                            size_in_bytes=archive.stat().st_size, expired=False)
            spec_path = root/'spec.json'
            spec_path.write_text(json.dumps(spec))
            def api(endpoint, path, timeout):
                path.write_bytes(archive.read_bytes() if endpoint.endswith('/zip') else json.dumps(metadata).encode())
            env = dict(GITHUB_ACTIONS='true', GITHUB_REPOSITORY='Ajuntanaga/m3-offload',
                       SOURCE_SHA='source', GITHUB_SHA='worker', GITHUB_RUN_ID='9')
            with patch.dict(os.environ, env), patch.object(runner, 'captured_api', api), \
                    patch.object(runner.subprocess, 'run', return_value=SimpleNamespace(stdout='source\n')):
                report = run(spec_path, root/'result')
                self.assertEqual(report['state'], 'complete')
                self.assertTrue(report['archive_verified'])
                self.assertEqual(report['datasets']['ordinary']['rows'], 15)
                metadata['digest'] = 'sha256:wrong'
                with self.assertRaises(ValueError):
                    run(spec_path, root/'bad')
                failed = json.loads((root/'bad/report/report.json').read_text())
                self.assertEqual(failed['state'], 'failed')
                self.assertTrue(failed['final'])

    def test_local_corpus_runner_refused(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}):
            with self.assertRaises(RuntimeError):
                run(Path('not-read'), Path('not-created'))


if __name__ == '__main__':
    unittest.main()
