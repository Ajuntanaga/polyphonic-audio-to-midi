from pathlib import Path
import tempfile
import unittest

from tools.portable_recovery import inventory, bundle


class PortableRecoveryTests(unittest.TestCase):
    def test_presence_and_new_hash_do_not_claim_historical_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            present = root / 'present'
            present.write_bytes(b'reconstructed input')
            files = {'present.wav': present, 'absent.tsv': root / 'absent'}
            report = inventory(files, hash_files=True)
            self.assertEqual(report['missing'], ['absent.tsv'])
            self.assertEqual(report['files']['present.wav']['state'], 'present-new-hash-no-historical-reference')
            with self.assertRaises(ValueError):
                bundle(files, report, root / 'bundle.tar')
            self.assertFalse((root / 'bundle.tar').exists())

    def test_hash_mismatch_blocks_bundle_and_match_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.write_bytes(b'original')
            files = {'ordinary.wav': source}
            original = inventory(files, hash_files=True)
            matching = inventory(files, hash_files=True, expected=original['files'])
            self.assertEqual(matching['files']['ordinary.wav']['state'], 'historical-hash-match')
            source.write_bytes(b'replacement')
            changed = inventory(files, hash_files=True, expected=original['files'])
            self.assertEqual(changed['files']['ordinary.wav']['state'], 'historical-hash-mismatch')
            with self.assertRaises(ValueError):
                bundle(files, changed, root / 'bundle.tar')


if __name__ == '__main__':
    unittest.main()
