import copy
import unittest
from tools.portable_vst3_process_timing import SCOPE, assess_measurement


class ProcessTimingTests(unittest.TestCase):
    def setUp(self):
        self.plain = dict(block_samples=32, sample_rate=96000, blocks=10,
                          accepted_events=4, process_measurement=None)
        self.native = dict(self.plain, process_measurement=dict(scope=SCOPE,
            clock='steady_clock', cold_blocks_included=True, allocation_guard=True,
            blocks=10, p99_ns=166666, max_ns=333333, deadline_overruns=0,
            cpp_allocations=0, cpp_frees=0, c_allocations=0, c_frees=0))

    def assess(self, trace='same'):
        return assess_measurement(self.native, self.plain, trace_sha=trace, untimed_trace_sha='same')

    def test_exact_boundaries_pass(self):
        self.assertTrue(self.assess()['gate_pass'])

    def test_each_safety_failure_rejects(self):
        for key, value in (('p99_ns', 166667), ('max_ns', 333334), ('deadline_overruns', 1),
                           ('cpp_allocations', 1), ('cpp_frees', 1), ('c_allocations', 1), ('c_frees', 1)):
            with self.subTest(key=key):
                saved = copy.deepcopy(self.native)
                self.native['process_measurement'][key] = value
                self.assertFalse(self.assess()['gate_pass'])
                self.native = saved

    def test_measurement_must_preserve_output_and_state(self):
        self.assertFalse(self.assess('changed')['gate_pass'])
        self.native['accepted_events'] += 1
        self.assertFalse(self.assess()['gate_pass'])

    def test_missing_or_wrong_scope_is_not_measurement(self):
        for key, value in (('scope', 'detector_only'), ('blocks', 9), ('blocks', True),
                           ('allocation_guard', False), ('cold_blocks_included', False), ('max_ns', -1)):
            with self.subTest(key=key):
                saved = copy.deepcopy(self.native)
                self.native['process_measurement'][key] = value
                with self.assertRaises(ValueError):
                    self.assess()
                self.native = saved

    def test_different_clock_cannot_use_fixed_budget(self):
        self.native['sample_rate'] = 48000
        with self.assertRaises(ValueError):
            self.assess()

    def test_timed_reference_is_not_untimed_pair(self):
        self.plain['process_measurement'] = self.native['process_measurement']
        with self.assertRaises(ValueError):
            self.assess()
