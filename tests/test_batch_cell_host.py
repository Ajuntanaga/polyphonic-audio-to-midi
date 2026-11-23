import unittest

from tools.portable_batch_cell_host import check_compile_modes, compare_arms, evaluate_arm


class BatchCellHostTests(unittest.TestCase):
    def fixture(self):
        metrics = dict(host_exit=0, failure_count=0, audio_running_at_play=1, audio_mode='JACK',
                       sample_rate=96000, block_size=512, max_block=512,
                       recorded_samples=96000, last_recorded_sample=96000,
                       recording_discontinuities=0, ordinary_wall_seconds=1.5,
                       dry_max_error=0, dry_changed_samples=0, dry_samples=144000,
                       input_peak=.1, nonfinite=0, overflow=0, event_count=2,
                       parameter_image_matches=1, restored_trim=.625,
                       panic_before_active=1, panic_after_active=0, panic_ready=0, final_active=0)
        events = [dict(phase=1, sample=127, offset=127, status=144, note=60, velocity=100),
                  dict(phase=3, sample=96000, offset=0, status=128, note=60, velocity=0)]
        return metrics, events

    def test_nonvacuous_host_delivery(self):
        metrics, events = self.fixture()
        self.assertTrue(evaluate_arm(metrics, events, 96000)['passed'])
        self.assertTrue(compare_arms(events, events, 96000)['passed'])
        self.assertFalse(compare_arms([], [], 96000)['passed'])
        metrics.update(event_count=0, panic_before_active=0)
        self.assertFalse(evaluate_arm(metrics, [], 96000)['passed'])

    def test_one_sample_or_lane_or_velocity_or_order_difference_fails(self):
        _, events = self.fixture()
        for key, value in (('sample', 128), ('offset', 128), ('status', 145),
                           ('note', 61), ('velocity', 99)):
            changed = [dict(events[0], **{key: value}), events[1]]
            self.assertFalse(compare_arms(events, changed, 96000)['passed'], key)
        second = dict(events[0], sample=255, offset=255, note=61)
        self.assertFalse(compare_arms([events[0], second], [second, events[0]], 96000)['passed'])

    def test_tail_control_not_clock_aligned_but_cannot_hide_in_recording_change(self):
        _, events = self.fixture()
        self.assertTrue(compare_arms(events, [events[0], dict(events[1], sample=97000)], 96000)['passed'])
        extra = dict(events[0], sample=96000, offset=256)
        self.assertTrue(compare_arms(events, events+[extra], 96000)['passed'])
        extra['sample'] -= 1
        self.assertFalse(compare_arms(events, events+[extra], 96000)['passed'])

    def test_host_integrity_failure_cannot_pass(self):
        for key, value in (
            ('host_exit', 1), ('failure_count', 1), ('audio_running_at_play', 0),
            ('audio_mode', 'unavailable'), ('max_block', 1024), ('recorded_samples', 95999),
            ('recording_discontinuities', 1), ('ordinary_wall_seconds', .1),
            ('dry_max_error', 1e-12), ('overflow', 1), ('event_count', 3),
            ('parameter_image_matches', 0), ('restored_trim', .5), ('panic_ready', 1),
            ('panic_after_active', 1), ('final_active', 1),
        ):
            metrics, events = self.fixture()
            metrics[key] = value
            self.assertFalse(evaluate_arm(metrics, events, 96000)['passed'], key)

    def test_preserved_pairing_defect_is_reported_not_an_optimization_claim(self):
        metrics, events = self.fixture()
        events.insert(1, events[0].copy())
        metrics['event_count'] = len(events)
        result = evaluate_arm(metrics, events, 96000)
        self.assertTrue(result['passed'])
        self.assertEqual(result['raw_pairing']['duplicate_ons'], 1)

    def test_new_attack_during_panic_or_invalid_offset_fails(self):
        metrics, events = self.fixture()
        events.append(dict(events[0], phase=3))
        metrics['event_count'] = 3
        self.assertFalse(evaluate_arm(metrics, events, 96000)['passed'])
        metrics, events = self.fixture()
        events[0]['offset'] = 512
        self.assertFalse(evaluate_arm(metrics, events, 96000)['passed'])

    def compile_commands(self):
        return [dict(file='/source/native/src/polyphonic_pitch_detector.cpp',
                     command=f'c++ {definition} -o CMakeFiles/{target}.dir/native/src/polyphonic_pitch_detector.cpp.o')
                for target, definition in (
                    ('m3_vst3_production', '-DM3_VST3_PRODUCTION_BUILD'),
                    ('m3_vst3_batch_cell_lab', '-DM3_BATCH_CELL_LAB=1'),
                    ('m3_vst3_realtime_tests', '-DM3_TESTING'),
                    ('m3_batch_cell_realtime_tests', '-DM3_TESTING -DM3_BATCH_CELL_LAB=1'))]

    def test_actual_compile_commands_must_select_distinct_production_modes(self):
        entries = self.compile_commands()
        self.assertEqual(len(check_compile_modes(entries)), 4)
        for replacement in ('', '-DM3_OFFLINE_REPLAY_DIAGNOSTICS=1'):
            entries = self.compile_commands()
            entries[1]['command'] = entries[1]['command'].replace('-DM3_BATCH_CELL_LAB=1', replacement)
            with self.assertRaises(ValueError):
                check_compile_modes(entries)
        entries = self.compile_commands()
        entries[1]['command'] += ' -DM3_OFFLINE_REPLAY_DIAGNOSTICS=1'
        with self.assertRaises(ValueError):
            check_compile_modes(entries)
        with self.assertRaises(ValueError):
            check_compile_modes(entries[:1])


if __name__ == '__main__':
    unittest.main()
