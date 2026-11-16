import subprocess
import unittest
from unittest.mock import patch

from tests import test_portable_completion_midi_retention_timing as fixtures
from tools import portable_sample_observation_comparison as runner


class SampleObservationComparisonTests(unittest.TestCase):
    def exercise(self, *, mutate_run=None, mutate_reference=None, reduction=5):
        def paired_run(binary, corpus, manifest, reference, output, **kwargs):
            baseline = corpus / 'baseline'
            baseline.write_text('separate fixed baseline; never executed locally')
            return runner.run(baseline, binary, corpus, manifest, reference, output)

        def measurements(index, timing, out):
            candidate = index in (1, 2, 5)
            timing['total_ns'] = 3200000
            timing['thread_cpu'].update(total_ns=3200000 * (100 - reduction) // 100
                if candidate else 3200000, p99_ns=95000 if candidate else 100000,
                maximum_ns=190000, deadline_overruns=0)
            if mutate_run:
                mutate_run(index, timing, out)

        with patch('tests.test_portable_completion_midi_retention_timing.run', paired_run), \
             patch.object(runner, 'verify_inputs') as verify:
            result = fixtures.CompletionTimingTests().exercise(
                mutate_run=measurements, mutate_reference=mutate_reference)
            return (*result[:4], verify.call_args_list)

    def test_fixed_pairs_alternate_order_and_require_useful_improvement_without_acceptance(self):
        passed, report, error, commands, verified = self.exercise()
        self.assertIsNone(error)
        self.assertTrue(passed)
        self.assertEqual([call.args[2] for call in verified], ['ordinary', 'physical-long'])
        self.assertEqual(len(commands), 6)
        for case, (dataset, mode) in zip(report['cases'], runner.CASES):
            self.assertEqual((case['dataset'], case['mode']), (dataset, mode))
            self.assertEqual(case['cpu_total_reduction_percent'], 5)
            self.assertEqual(case['cpu_p99_delta_ns'], -5000)
            for row in case['runs'].values():
                self.assertTrue(row['recorded_reference_bit_identical'])
                self.assertTrue(row['observation_verified'])
                command = row['command']
                self.assertEqual(command[command.index('--block') + 1], '32')
                self.assertEqual([arg for arg in command if arg.startswith('--diagnostic-')],
                    ['--diagnostic-core-timing', *dict(runner.CONDITIONS)[mode],
                     '--diagnostic-thread-cpu'])
        self.assertEqual([case['execution_order'] for case in report['cases']],
            [['baseline', 'candidate'], ['candidate', 'baseline'], ['baseline', 'candidate']])
        self.assertTrue(report['collection_pass'])
        self.assertTrue(report['usefulness_screen_pass'])
        self.assertFalse(report['native_gate_pass'])
        self.assertFalse(report['promotion_accepted'])

    def test_insufficient_total_reduction_or_any_p99_increase_rejects(self):
        for reduction in (0, 1, -5):
            passed, report, error, commands, _ = self.exercise(reduction=reduction)
            self.assertIsNone(error)
            self.assertFalse(passed)
            self.assertEqual(len(commands), 6)
            self.assertEqual(report['state'], 'completed')
        def increase_p99(index, timing, out):
            if index == 2:
                timing['thread_cpu']['p99_ns'] = 100001
        passed, _, error, _, _ = self.exercise(mutate_run=increase_p99)
        self.assertIsNone(error)
        self.assertFalse(passed)
        self.assertTrue(self.exercise(reduction=2)[0])

    def test_identity_allocations_clock_scope_and_probe_failures_stop_without_retry(self):
        changes = (
            lambda i, t, out: out.write('\n'),
            lambda i, t, out: t.update(cpp_allocations=1),
            lambda i, t, out: t.update(c_frees=1),
            lambda i, t, out: t.update(blocks=33),
            lambda i, t, out: t.update(stage_cpu={}),
            lambda i, t, out: t.update(measurement_scope='wrong'),
            lambda i, t, out: t['thread_cpu'].update(block_resolution_pass=False),
            lambda i, t, out: t['thread_cpu'].update(total_ns=0),
            lambda i, t, out: t['thread_cpu'].update(p99_ns=True))
        for change in changes:
            _, report, error, commands, _ = self.exercise(mutate_run=change)
            self.assertIsInstance(error, ValueError)
            self.assertEqual(len(commands), 1)
            self.assertTrue(report['final'])
            self.assertFalse(report['collection_pass'])
            self.assertFalse(report['usefulness_screen_pass'])

    def test_bad_reference_stops_before_replay_and_timeout_preserves_partial_pair(self):
        _, report, error, commands, _ = self.exercise(mutate_reference=lambda r:
            r['source'].update(input_bundle_sha256='wrong'))
        self.assertIsInstance(error, ValueError)
        self.assertEqual(commands, [])
        def timeout(index, timing, out):
            if index == 1:
                raise subprocess.TimeoutExpired('mock', 900)
        _, report, error, commands, _ = self.exercise(mutate_run=timeout)
        self.assertIsInstance(error, subprocess.TimeoutExpired)
        self.assertEqual(len(commands), 2)
        self.assertEqual(list(report['cases'][0]['runs']), ['baseline'])
        self.assertEqual(report['state'], 'failed')
        self.assertFalse(report['usefulness_screen_pass'])


if __name__ == '__main__':
    unittest.main()
