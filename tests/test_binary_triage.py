import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cloud.kaggle.binary_triage import run
from cloud.kaggle.prepare_analysis import prepare


class BinaryTriageTests(unittest.TestCase):
    def test_smoke_preparation_is_private_offline_and_upload_free(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'prepared'
            receipt = prepare('example', 'static-smoke', output, smoke=True)
            metadata = json.loads((output / 'kernel/kernel-metadata.json').read_text())
            self.assertTrue(metadata['is_private'])
            self.assertFalse(metadata['enable_gpu'])
            self.assertFalse(metadata['enable_internet'])
            self.assertEqual(metadata['dataset_sources'], [])
            self.assertFalse(receipt['uploaded'])
            self.assertEqual(receipt['input_count'], 0)
            compile((output / 'kernel/analysis.py').read_text(), 'analysis.py', 'exec')

    def test_explicit_input_is_neutrally_named_and_hash_checked_before_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / 'private-project-name.bin'
            sample.write_bytes(b'\x7fELF' + b'original')
            prepared = root / 'prepared'
            prepare('example', 'static-fixture', prepared, [sample])
            self.assertFalse((prepared / 'dataset/private-project-name.bin').exists())
            source = (prepared / 'kernel/analysis.py').read_text()
            self.assertNotIn(str(sample), source)
            from cloud.kaggle.binary_triage import digest
            expected = {'smoke': False, 'files': [{'name': 'sample-0.bin',
                        'bytes': sample.stat().st_size, 'sha256': digest(sample)}]}
            (prepared / 'dataset/sample-0.bin').write_bytes(b'\x7fELF' + b'modified')
            with patch('cloud.kaggle.binary_triage.shutil.which', return_value='/tool'), \
                 patch('cloud.kaggle.binary_triage.command_result') as command:
                with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                    run(expected, prepared / 'dataset', root / 'results')
                command.assert_not_called()
            report = json.loads((root / 'results/report.json').read_text())
            self.assertEqual(report['state'], 'failed')
            self.assertTrue(report['final'])

    def test_bounded_tool_failure_remains_a_final_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / 'sample.bin'
            binary.write_bytes(b'\x7fELFfixture')
            from cloud.kaggle.binary_triage import digest
            config = {'smoke': False, 'files': [{'name': binary.name,
                      'bytes': binary.stat().st_size, 'sha256': digest(binary)}]}
            with patch('cloud.kaggle.binary_triage.shutil.which', return_value='/tool'), \
                 patch('cloud.kaggle.binary_triage.command_result',
                       return_value={'passed': False, 'output_limit_reached': True}) as command:
                with self.assertRaisesRegex(RuntimeError, 'Static inspection failed'):
                    run(config, root, root / 'results')
                for call in command.call_args_list:
                    self.assertIn(call.args[0][0], ('file', 'objdump', 'strings', 'readelf'))
            report = json.loads((root / 'results/report.json').read_text())
            self.assertTrue(report['final'])
            self.assertEqual(report['state'], 'failed')
            self.assertFalse(report['sample_execution'])
            self.assertFalse(report['llm_inference'])


if __name__ == '__main__':
    unittest.main()
