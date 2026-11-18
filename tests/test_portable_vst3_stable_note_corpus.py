import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tools import portable_vst3_stable_note_corpus as runner
from tools.portable_vst3_process_timing import SCOPE
from tests.test_portable_vst3_corpus_replay import HEADER


class CorpusRunnerTests(unittest.TestCase):
    def exercise(self, fail_timing=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'fixture.tsv').write_text('start_sample\tend_sample\tmidi_note\tstring_mask\n0\t80\t60\t1\n')
            (root / 'manifest.json').write_text(json.dumps({'source': {'commit': 'a'*40}}))
            (root / 'reference.json').write_text(json.dumps({'datasets': {'fixture': {'current-on': {
                'sample_count': 100, 'sample_rate': 96000}}}}))
            binary = root / 'binary'
            binary.write_bytes(b'fixture only')
            args = SimpleNamespace(binary=binary, corpus=root, manifest=root/'manifest.json',
                reference=root/'reference.json', source_sha='a'*40, output=root/'output')
            def native(command, stdout, stderr, **kwargs):
                block = int(command[command.index('--block')+1])
                bits = int(command[command.index('--sample-bits')+1])
                stable = command[command.index('--stable-note-identity')+1] == '1'
                trace = Path(command[command.index('--events')+1])
                trace.write_text(HEADER + '0\ton\t60\t0.75\t-1060\t0\n80\toff\t60\t0\t-1060\t0\n')
                data = dict(schema='m3_vst3_corpus_native_v1', routing='per_voice',
                    sample_bits=bits, block_samples=block, trial=True, sample_count=100, sample_rate=96000,
                    processed_samples=100, blocks=(100+block-1)//block, detector_samples=100,
                    detector_transitions=2, queue_rejections=0, event_add_attempts=2, accepted_events=2,
                    output_blocked_blocks=0, dry_audio_mismatches=0, process_failures=0,
                    output_blocked_at_eof=False, calibration_merge_matches=True, invalid_event=False,
                    trace_write_failed=False, first_blocked_sample=None, stable_note_identity=stable,
                    transferred_pairs=0, completion_midi_retention=False, process_measurement=None)
                if '--measure-process' in command:
                    data['process_measurement'] = dict(scope=SCOPE, clock='steady_clock',
                        cold_blocks_included=True, allocation_guard=True, blocks=data['blocks'],
                        p99_ns=100, max_ns=400000 if fail_timing else 200, deadline_overruns=int(fail_timing),
                        cpp_allocations=0, cpp_frees=0, c_allocations=0, c_frees=0)
                stdout.write(json.dumps(data))
                return SimpleNamespace(returncode=0)
            with patch.object(runner, 'DATASETS', {'fixture': {}}), patch.object(runner, 'verify_references', return_value=4), \
                    patch.object(runner.subprocess, 'check_output', return_value='a'*40+'\n'), \
                    patch.object(runner.subprocess, 'run', side_effect=native) as process:
                result = runner.run(args)
            self.assertEqual(process.call_count, 16)
            self.assertEqual(json.loads((args.output/'report.json').read_text()), result)
            self.assertFalse(result['promotion_accepted'])
            return result

    def test_full_matrix_aggregates_and_persists(self):
        self.assertTrue(self.exercise()['corpus_gate_pass'])

    def test_timing_failure_prevents_corpus_acceptance(self):
        self.assertFalse(self.exercise(fail_timing=True)['corpus_gate_pass'])

    def test_labels_cannot_exceed_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'labels.tsv'
            path.write_text('start_sample\tend_sample\tmidi_note\tstring_mask\n0\t101\t60\t1\n')
            with self.assertRaises(ValueError):
                runner.read_labels(path, 100)
