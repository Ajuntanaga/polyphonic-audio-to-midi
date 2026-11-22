import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.portable_basic_pitch_graph_optimization import assess, run, runtime_gates, validate_spec


class GraphOptimizationTest(unittest.TestCase):
    def test_frozen_limits_reject_mutations(self):
        path = Path(__file__).resolve().parents[1]/'docs/recovery/basic-pitch-graph-optimization-20261122.json'
        spec = json.loads(path.read_text())
        validate_spec(spec)
        for key, value in [('max_absolute', .001), ('graph_modes', ['all']),
                           ('service_p99_limit_ns', 21_000_000), ('queue_max_limit_ns', 30_000_000)]:
            changed = copy.deepcopy(spec)
            changed[key] = value
            with self.assertRaises(ValueError):
                validate_spec(changed)

    def test_runtime_is_not_note_acceptance_and_each_gate_is_required(self):
        timing = dict(inference_block_service_ns=dict(p99=20_000_000),
                      queued_before_service_ns=dict(maximum=26_666_667))
        row = dict(disabled_reference_parity=dict(parity_pass=True),
                   optimized_vs_disabled=dict(parity_pass=True),
                   optimized_vs_corrected_tensorflow=dict(parity_pass=True),
                   source_availability_scores_identical=True, all=dict(timing=timing))
        datasets = dict(ordinary=dict(weights=dict(unmodified=row)))
        result = assess(datasets, True)
        self.assertTrue(result['runtime_change_screen_pass'])
        self.assertFalse(result['promotion_accepted'])
        self.assertFalse(result['prior_adaptation_quality_pass'])
        for name in ('disabled_reference_parity', 'optimized_vs_disabled', 'optimized_vs_corrected_tensorflow'):
            changed = copy.deepcopy(datasets)
            changed['ordinary']['weights']['unmodified'][name]['parity_pass'] = False
            self.assertFalse(assess(changed, True)['runtime_change_screen_pass'])
        self.assertFalse(assess(datasets, False)['runtime_change_screen_pass'])
        timing['inference_block_service_ns']['p99'] += 1
        self.assertFalse(runtime_gates(timing)['service_p99_under_20ms'])
        self.assertFalse(assess(datasets, True)['runtime_change_screen_pass'])

    def test_local_model_execution_is_blocked_before_path_access(self):
        with patch.dict('os.environ', {'GITHUB_ACTIONS': 'false'}):
            with self.assertRaises(RuntimeError):
                run(Path('not-read.json'), Path('not-created'))


if __name__ == '__main__':
    unittest.main()
