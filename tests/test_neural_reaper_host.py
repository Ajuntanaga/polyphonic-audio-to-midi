import unittest

from tools.portable_neural_reaper_host import evaluate


class HostVerdictTests(unittest.TestCase):
    def fixture(self):
        metrics=dict(failure_count=0,sample_rate=96000,block_size=512,max_block=512,
                     recorded_samples=96000,last_recorded_sample=96000,recording_discontinuities=0,
                     ordinary_wall_seconds=1.5,dry_max_error=0,dry_changed_samples=0,
                     dry_samples=144000,input_peak=.1,nonfinite=0,overflow=0,event_count=2,
                     default_gate=0,default_threshold=.5,restored_gate=1,restored_threshold=.6,
                     panic_before_active=1,panic_after_active=0)
        events=[dict(phase=1,sample=100,offset=0,status=144,note=60,velocity=100),
                dict(phase=3,sample=96000,offset=0,status=128,note=60,velocity=0)]
        return metrics,events

    def test_nonvacuous_delivery_and_cleanup(self):
        m,e=self.fixture()
        self.assertTrue(evaluate(m,e,96000)['passed'])

    def test_silent_or_bypassed_plugin_cannot_pass(self):
        m,_=self.fixture();m.update(event_count=0,panic_before_active=0)
        self.assertFalse(evaluate(m,[],96000)['passed'])

    def test_clipped_recording_and_audio_change_rejected(self):
        for name,value in [('recorded_samples',95999),('dry_max_error',1e-9),
                           ('recording_discontinuities',1),('ordinary_wall_seconds',.1)]:
            m,e=self.fixture();m[name]=value
            self.assertFalse(evaluate(m,e,96000)['passed'],name)

    def test_duplicate_or_orphan_midi_rejected(self):
        m,e=self.fixture();e.insert(1,e[0].copy());m['event_count']=len(e)
        self.assertFalse(evaluate(m,e,96000)['passed'])

    def test_panic_followed_by_new_attack_rejected(self):
        m,e=self.fixture();e.append(dict(e[0],phase=3));m['event_count']=len(e)
        self.assertFalse(evaluate(m,e,96000)['passed'])


if __name__=='__main__':
    unittest.main()
