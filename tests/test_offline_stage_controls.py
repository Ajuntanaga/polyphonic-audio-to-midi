"""Exercise the stage-enabled replay CLI on GitHub, using generated audio only."""
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import wave


@unittest.skipUnless(os.environ.get('M3_STAGE_REPLAY_BINARY'), 'stage binary runs on GitHub only')
class OfflineStageControlsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.binary = str(Path(os.environ['M3_STAGE_REPLAY_BINARY']).resolve())
        self.wav, self.labels = self.root / 'audio.wav', self.root / 'labels.tsv'
        with wave.open(str(self.wav), 'wb') as stream:
            stream.setparams((1, 2, 96000, 8192, 'NONE', 'not compressed'))
            stream.writeframes(b''.join(struct.pack('<h', round(
                6000 * math.sin(2 * math.pi * 220 * i / 96000))) for i in range(8192)))
        self.labels.write_text('start_sample\tend_sample\tmidi_note\tstring_mask\n0\t8192\t57\t2\n')

    def invoke(self, samples, *, thread_cpu=True, core=True, block=32):
        timing = self.root / 'timing.json'
        timing.unlink(missing_ok=True)
        command = [self.binary, '--wav', str(self.wav), '--labels', str(self.labels),
                   '--block', str(block), '--label-details']
        if core:
            command.extend(('--diagnostic-core-timing', str(timing)))
        if thread_cpu:
            command.append('--diagnostic-thread-cpu')
        for sample in samples:
            command.extend(('--diagnostic-stage-end-sample', str(sample)))
        result = subprocess.run(command, capture_output=True, timeout=30)
        return result, json.loads(timing.read_text()) if timing.exists() else None

    def test_retention_at_sixteen_positions_preserves_scored_output(self):
        plain, plain_timing = self.invoke([])
        self.assertEqual(plain.returncode, 0, plain.stderr.decode())
        samples = [32 * i for i in range(1, 16)] + [8192]
        measured, timing = self.invoke(samples)
        self.assertEqual(measured.returncode, 0, measured.stderr.decode())
        self.assertEqual(measured.stdout, plain.stdout)
        self.assertEqual(timing['fingerprint'], plain_timing['fingerprint'])
        self.assertTrue(timing['fingerprint_identical'])
        self.assertTrue(timing['stage_cpu']['valid'])
        controls = timing['stage_cpu']['control_cpu_blocks']
        self.assertEqual([row['end_sample'] for row in controls], samples)
        for row in controls:
            self.assertEqual(sum(stage['ns'] for stage in row['stages'].values())
                             + row['unattributed_cpu_ns'], row['cpu_ns'])
        for key in ('cpp_allocations', 'cpp_frees', 'c_allocations', 'c_frees'):
            self.assertEqual(timing[key], 0)

    def test_invalid_controls_fail_before_measurement(self):
        invalid = ([0], [-32], [33], [32, 32], [64, 32], [8224],
                   list(range(32, 32 * 18, 32)), ['bad'], [2 ** 64])
        for samples in invalid:
            with self.subTest(samples=samples):
                result, timing = self.invoke(samples)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(timing)
        for options in (dict(thread_cpu=False), dict(core=False), dict(block=64)):
            with self.subTest(options=options):
                result, timing = self.invoke([32], **options)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(timing)


if __name__ == '__main__':
    unittest.main()
