import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import portable_basic_pitch_trainability as probe


class TrainabilityEnvelopeTests(unittest.TestCase):
    def test_model_guard_precedes_files_imports_and_network(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'absent'
            result = subprocess.run([sys.executable, '-m', 'tools.portable_basic_pitch_trainability',
                '--spec', 'absent', '--output', str(output)], capture_output=True, text=True,
                env={key: value for key, value in os.environ.items() if key != 'GITHUB_ACTIONS'})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires GitHub Actions', result.stderr)
            self.assertFalse(output.exists())

    def test_modified_or_truncated_public_model_rejected(self):
        data = b'public model bytes'
        pin = dict(bytes=len(data), git_blob_sha1=hashlib.sha1(b'blob 18\0'+data).hexdigest(),
                   sha256=hashlib.sha256(data).hexdigest())
        self.assertEqual(probe.checked_blob(data, pin)['bytes'], len(data))
        for invalid in (data[:-1], b'X'+data[1:]):
            with self.assertRaises(ValueError):
                probe.checked_blob(invalid, pin)
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            probe.checked_blob(data, dict(pin, sha256='0'*64))

    def test_model_path_escape_rejected_before_network(self):
        spec = dict(upstream_commit='a'*40, files={'../../outside': {}})
        with patch.object(probe, 'remote_only'), patch.object(probe.urllib.request, 'urlopen') as fetch:
            with self.assertRaisesRegex(ValueError, 'path'):
                probe.download_files(spec, Path('unused'))
            fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
