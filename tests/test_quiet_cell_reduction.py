"""Synthetic arithmetic and streaming contracts; no recordings or replay."""
from dataclasses import replace
import hashlib
import io
import gzip
import json
import math
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from tools.quiet_cell_reduction import (
    CELL_HEADER, OUTPUT_HEADER, Cell, context_windows, interval_projection,
    reduce_stream,
)
from tools.portable_quiet_cell_reduction import HashedLines, checked_member, run


def cell(sample, note=52, *, available=True):
    return Cell(sample, sample//2, 5, note, available,
                1.0 if available else 0.0, 0.99 if available else 0.0,
                tuple((float(h*165), 0.1*h, -0.03*h) if available else (0., 0., 0.)
                      for h in range(1, 7)))


def line(row):
    fields = [row.sample, row.tick, row.quiet, row.note, int(row.available),
              row.power, row.decay]
    fields.extend(value for harmonic in row.harmonics for value in harmonic)
    return '\t'.join(map(str, fields))+'\n'


def text_input(rows):
    return io.StringIO('# m3_outcome_cells_v1\n'+'\t'.join(CELL_HEADER)+'\n'
                       +''.join(line(row) for row in rows))


class IntervalArithmetic(unittest.TestCase):
    def test_matches_direct_sample_recurrence(self):
        # Independently accumulate only the NEW forcing while an unrelated,
        # large old state evolves. No detector/model/audio code is executed.
        a, n = 0.9976, 1920
        old = replace(cell(64), decay=a, power=4.0)
        z = [complex(h[1], h[2]) for h in old.harmonics]
        p = old.power
        forced = [0j]*6
        forced_power = 0.0
        for k in range(1, n+1):
            x = 0.2*math.cos(0.071*k)+0.03*math.sin(0.133*k)
            p = a*p+(1-a)*x*x
            forced_power += (1-a)*a**(n-k)*x*x
            for h in range(6):
                phase = (h+1)*(0.039*k+0.27)
                u = complex(math.cos(phase), -math.sin(phase))
                z[h] = a*z[h]+(1-a)*x*u
                forced[h] += (1-a)*a**(n-k)*x*u
        now = replace(old, sample=old.sample+n, power=p,
                      harmonics=tuple((old.harmonics[h][0], v.real, v.imag)
                                      for h, v in enumerate(z)))
        result = interval_projection(now, old, n)
        self.assertEqual(result['status'], 'ok')
        self.assertAlmostEqual(result['power'], forced_power/(1-a**n), places=12)
        for actual, expected in zip(result['harmonics'], forced):
            self.assertAlmostEqual(actual[0], expected.real/(1-a**n), places=12)
            self.assertAlmostEqual(actual[1], expected.imag/(1-a**n), places=12)

    def test_old_memory_alone_is_not_fresh_energy(self):
        old = replace(cell(0), decay=0.5)
        now = replace(old, sample=8, power=old.power/256,
                      harmonics=tuple((hz, re/256, im/256) for hz, re, im in old.harmonics))
        result = interval_projection(now, old, 8)
        # exp(N*log(a)) can differ from exact repeated binary multiplication
        # by one ulp. Keep the signed residual, including negative cancellation.
        self.assertAlmostEqual(result['power_delta'], 0, places=15)
        self.assertIn(result['status'], ('ok', 'negative_power'))
        self.assertTrue(any(re != 0 for _, re, _ in now.harmonics))
        self.assertTrue(all(abs(value) < 1e-15 for pair in result['harmonics'] for value in pair))

    def test_unavailable_and_configuration_changes_remain_distinct(self):
        old, now = cell(0), cell(20)
        self.assertEqual(interval_projection(now, None, 20)['status'], 'missing_anchor')
        self.assertEqual(interval_projection(cell(20, available=False), old, 20)['status'], 'unavailable_current')
        self.assertEqual(interval_projection(now, cell(0, available=False), 20)['status'], 'unavailable_anchor')
        self.assertEqual(interval_projection(replace(now, decay=.98), old, 20)['status'], 'configuration_changed')
        changed = replace(now, harmonics=((166., .1, .2),)+now.harmonics[1:])
        self.assertEqual(interval_projection(changed, old, 20)['status'], 'configuration_changed')
        with self.assertRaises(ValueError):
            interval_projection(now, cell(1), 20)

    def test_negative_power_is_not_clamped_to_zero(self):
        result = interval_projection(replace(cell(20), power=0), cell(0), 20)
        self.assertEqual(result['status'], 'negative_power')
        self.assertLess(result['power_delta'], 0)
        self.assertIsNone(result['power'])


class StreamingContract(unittest.TestCase):
    def test_union_windows_and_exact_anchor_preserve_all_original_fields(self):
        rows = [cell(s, note) for s in range(0, 42, 2) for note in (52, 60)]
        output = io.StringIO()
        report = reduce_stream(text_input(rows), output, marked=[[12, 16], [20, 24]],
                               horizon=40, lag_samples=8, before_samples=4, after_samples=8)
        lines = output.getvalue().splitlines()
        self.assertEqual(lines[1].split('\t'), OUTPUT_HEADER)
        retained = [row for row in rows if 8 <= row.sample < 32]
        self.assertEqual(report['retained_rows'], len(retained))
        self.assertEqual(report['status_counts'], {'ok': len(retained)})
        self.assertLessEqual(report['max_history_rows'], 10)
        for actual, original in zip(lines[2:], retained):
            fields = actual.split('\t')
            self.assertEqual(fields[:25], line(original).rstrip('\n').split('\t'))
            self.assertEqual(fields[26], str(original.sample-8))
            if 16 <= original.sample < 24:
                self.assertEqual(fields[25], '0,1')

    def test_sparse_rows_do_not_fabricate_an_anchor(self):
        output = io.StringIO()
        report = reduce_stream(text_input([cell(0), cell(18), cell(20), cell(40)]),
                               output, marked=[[18, 41]], horizon=42, lag_samples=20,
                               before_samples=0, after_samples=0)
        self.assertEqual(report['status_counts'], {'missing_anchor': 1, 'ok': 2})

    def test_rejects_order_header_and_malformed_measurements(self):
        for rows in ([cell(2), cell(0)], [cell(2), cell(2)]):
            with self.assertRaises(ValueError):
                reduce_stream(text_input(rows), io.StringIO(), marked=[[0, 4]],
                              horizon=4, lag_samples=2, before_samples=0, after_samples=0)
        with self.assertRaises(ValueError):
            reduce_stream(io.StringIO('wrong\n'), io.StringIO(), marked=[],
                          horizon=4, lag_samples=2, before_samples=0, after_samples=0)
        for row in (replace(cell(0), power=float('nan')),
                    replace(cell(0, available=False), power=1.0)):
            with self.assertRaises(ValueError):
                Cell.parse(line(row).rstrip('\n').split('\t'))
        with self.assertRaises(ValueError):
            context_windows([[0, 3], [2, 4]], 4, 0, 0)

    def test_half_open_windows_at_boundaries(self):
        windows = context_windows([[2, 4], [8, 10]], 10, 4, 4)
        self.assertEqual([(w['begin'], w['end']) for w in windows], [(0, 8), (4, 10)])
        output = io.StringIO()
        report = reduce_stream(text_input([cell(s) for s in range(0, 12, 2)]), output,
                               marked=[[2, 4], [8, 10]], horizon=10, lag_samples=2,
                               before_samples=4, after_samples=4)
        self.assertEqual(report['retained_rows'], 5)
        self.assertEqual(output.getvalue().splitlines()[-1].split('\t')[25], '1')


class CollectionContract(unittest.TestCase):
    def test_generated_archive_runs_through_the_remote_pipeline(self):
        import tools.portable_quiet_cell_reduction as runner
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = text_input([cell(64), cell(1984)]).getvalue().encode()
            compressed = gzip.compress(raw, mtime=0)
            pin = dict(bytes=len(compressed), sha256=hashlib.sha256(compressed).hexdigest(),
                       raw_bytes=len(raw), raw_sha256=hashlib.sha256(raw).hexdigest())
            names = ('ordinary', 'extended-middle')
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as bundle:
                for name in names:
                    bundle.writestr(name+'.tsv.gz', compressed)
            archive = buffer.getvalue()
            mask = root/'mask.json'
            mask.write_text(json.dumps(dict(datasets={name:dict(rate=96000, horizon=2000,
                              marked_intervals=[[1980, 1990]]) for name in names})))
            artifact = dict(id=123, name='synthetic', run_id=456, worker_commit='b'*40,
                            bytes=len(archive), sha256=hashlib.sha256(archive).hexdigest())
            spec = dict(schema='m3_quiet_cell_reduction_spec_v1', policy_change=False,
                        automatic_retry=False, interval_samples=1920, before_samples=1920,
                        after_samples=9600, artifact=artifact,
                        mask=dict(path=str(mask), sha256=hashlib.sha256(mask.read_bytes()).hexdigest()),
                        datasets={name:dict(rows=2,horizon=2000,member=dict(pin,path=name+'.tsv.gz'))
                                  for name in names})
            spec_path = root/'spec.json'
            spec_path.write_text(json.dumps(spec))
            calls = []
            def captured(endpoint, destination, timeout):
                calls.append(endpoint)
                if endpoint.endswith('/zip'):
                    destination.write_bytes(archive)
                else:
                    destination.write_text(json.dumps(dict(id=123,name='synthetic',expired=False,
                        size_in_bytes=len(archive),digest='sha256:'+artifact['sha256'],
                        workflow_run=dict(id=456,head_sha='b'*40))))
            env = dict(GITHUB_ACTIONS='true', GITHUB_REPOSITORY='Ajuntanaga/m3-offload',
                       SOURCE_SHA='a'*40, GITHUB_SHA='c'*40, GITHUB_RUN_ID='789')
            with patch.dict(os.environ, env, clear=True), \
                    patch.object(runner.subprocess, 'run', return_value=SimpleNamespace(stdout='a'*40+'\n')), \
                    patch.object(runner, 'captured_api', side_effect=captured):
                report = run(spec_path, root/'output')
            self.assertEqual(len(calls), 2)
            self.assertTrue(report['final'])
            self.assertEqual(report['state'], 'complete')
            self.assertTrue(report['archive_verified'])
            for name in names:
                row = report['datasets'][name]
                self.assertTrue(row['input_verified'])
                self.assertEqual(row['status_counts'], {'missing_anchor': 1, 'ok': 1})
                table = root/'output/tables'/row['table']['path']
                self.assertEqual(hashlib.sha256(table.read_bytes()).hexdigest(), row['table']['sha256'])
                self.assertEqual(len(gzip.decompress(table.read_bytes()).splitlines()), 4)

    def test_hashes_the_exact_uncompressed_bytes(self):
        data = b'header\r\n1\t2\n'
        lines = HashedLines(io.BytesIO(data))
        self.assertEqual(''.join(lines).encode(), data)
        self.assertEqual(lines.size, len(data))
        self.assertEqual(lines.hash.hexdigest(), hashlib.sha256(data).hexdigest())

    def test_member_must_be_exactly_named_and_sized(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'fixture.zip'
            with zipfile.ZipFile(path, 'w') as bundle:
                bundle.writestr('cells.tsv.gz', b'fixture')
            with zipfile.ZipFile(path) as bundle:
                self.assertEqual(checked_member(bundle, dict(path='cells.tsv.gz', bytes=7)).filename,
                                 'cells.tsv.gz')
                for name, size in [('cells.tsv.gz', 8), ('../cells.tsv.gz', 7), ('missing.tsv.gz', 7)]:
                    with self.assertRaises(ValueError):
                        checked_member(bundle, dict(path=name, bytes=size))

    def test_runner_refuses_local_execution_before_reading_files(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'GitHub worker only'):
                run(Path('/not-read'), Path('/not-created'))


if __name__ == '__main__':
    unittest.main()
