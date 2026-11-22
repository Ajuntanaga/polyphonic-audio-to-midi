import unittest

from tools.portable_basic_pitch_operator_profile import summarize_profile


class OperatorProfileTests(unittest.TestCase):
    def test_excludes_warmup_and_non_kernel_events(self):
        events = []
        for tick in range(3):
            start = tick * 100
            events += [dict(name='model_run', ph='X', ts=start, dur=90),
                dict(name='conv_kernel_time', cat='Node', ph='X', ts=start+10, dur=40,
                     args={'op_name': 'Conv', 'provider': 'CPUExecutionProvider'}),
                dict(name='add_kernel_time', cat='Node', ph='X', ts=start+60, dur=10,
                     args={'op_name': 'Add', 'provider': 'CPUExecutionProvider'}),
                dict(name='conv_fence_before', cat='Node', ph='X', ts=start+1, dur=3)]
        result = summarize_profile(events, 2)
        self.assertEqual(result['total_kernel_us'], 100)
        self.assertEqual(result['nodes'][0]['calls'], 2)
        self.assertEqual(result['nodes'][0]['share_of_kernel_duration'], .8)
        self.assertEqual(result['profiled_model_run_us'], [90, 90])

    def test_missing_call_fails(self):
        with self.assertRaises(ValueError):
            summarize_profile([], 16)

    def test_missing_kernels_fails(self):
        events = [dict(name='model_run', ph='X', ts=i*100, dur=90) for i in range(2)]
        with self.assertRaises(ValueError):
            summarize_profile(events, 1)


if __name__ == '__main__':
    unittest.main()
