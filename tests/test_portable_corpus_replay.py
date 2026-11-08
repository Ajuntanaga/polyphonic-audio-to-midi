from pathlib import Path
import unittest

from tools.portable_corpus_replay import command_for, timing_gates


class PortableCorpusTests(unittest.TestCase):
    def test_actual_correction_requires_both_flags_and_leaves_reset_switch_off(self):
        arguments = (Path('/replay'), Path('/corpus'), 'physical-long')
        off = command_for(*arguments, 'off', 32, Path('/off.json'))
        on = command_for(*arguments, 'on', 32, Path('/on.json'))
        for flag in ('--diagnostic-native-partial-cues', '--diagnostic-cue-free-lane-reassignment'):
            self.assertNotIn(flag, off)
            self.assertIn(flag, on)
        self.assertNotIn('--diagnostic-skip-empty-fine-reset', on)
        self.assertIn('--label-details', on)

    def test_fail_closed_timing_allocation_and_scored_identity(self):
        replay = {'output': {'fingerprint': '0123456789abcdef'}}
        timing = dict(schema='m3_replay_core_timing_v1', fingerprint_identical=True,
                      fingerprint='0123456789abcdef', block_samples=32, sample_rate=96000,
                      allocation_guard=True, cpp_allocations=0, cpp_frees=0,
                      c_allocations=0, c_frees=0, p99_ns=166666, maximum_ns=333333,
                      deadline_overruns=0)
        self.assertTrue(all(timing_gates(timing, replay, 32).values()))
        for key in ('p99_ns', 'maximum_ns', 'deadline_overruns'):
            changed = dict(timing, **{key: timing[key] + 1})
            self.assertFalse(timing_gates(changed, replay, 32)['timing_pass'])
        for key in ('cpp_allocations', 'cpp_frees', 'c_allocations', 'c_frees'):
            changed = dict(timing, **{key: 1})
            self.assertFalse(timing_gates(changed, replay, 32)['zero_processing_allocations'])
        self.assertFalse(timing_gates(dict(timing, fingerprint='bad'), replay, 32)['timing_pass'])
        self.assertFalse(timing_gates({}, replay, 32)['zero_processing_allocations'])
        self.assertIsNone(timing_gates(dict(timing, block_samples=512), replay, 512)['timing_pass'])


if __name__ == '__main__':
    unittest.main()
