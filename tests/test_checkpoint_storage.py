"""Byte-preserving storage compaction must reject incompatible checkpoints."""
import json, shutil, struct, tempfile, unittest
from pathlib import Path
from tools.deduplicate_frozen_checkpoints import compact, digest


def write(path, encoder, head):
    header = json.dumps({'encoder.weight': {'dtype': 'U8', 'shape': [len(encoder)], 'data_offsets': [0, len(encoder)]},
                         'head.weight': {'dtype': 'U8', 'shape': [len(head)], 'data_offsets': [len(encoder), len(encoder)+len(head)]}}).encode()
    path.write_bytes(struct.pack('<Q', len(header)) + header + encoder + head)


class StorageTests(unittest.TestCase):
    def test_exact_bytes_preserved_with_different_head(self):
        with tempfile.TemporaryDirectory() as directory:
            base, target = Path(directory)/'base', Path(directory)/'target'
            write(base, b'encoder', b'first'); write(target, b'encoder', b'other')
            original, source = target.read_bytes(), base.read_bytes()
            result = compact(base, target, copier=shutil.copyfile)
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(base.read_bytes(), source)
            self.assertEqual(result['sha256'], digest(target))

    def test_encoder_mismatch_leaves_both_files_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            base, target = Path(directory)/'base', Path(directory)/'target'
            write(base, b'encoder', b'first'); write(target, b'changed', b'other')
            before = target.read_bytes()
            with self.assertRaisesRegex(ValueError, 'Encoder differs'): compact(base, target, copier=shutil.copyfile)
            self.assertEqual(target.read_bytes(), before)

    def test_same_path_and_header_change_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base, target = Path(directory)/'base', Path(directory)/'target'
            write(base, b'encoder', b'first'); write(target, b'encoder', b'longer')
            with self.assertRaisesRegex(ValueError, 'must differ'): compact(base, base, copier=shutil.copyfile)
            with self.assertRaisesRegex(ValueError, 'Headers differ'): compact(base, target, copier=shutil.copyfile)


if __name__ == '__main__': unittest.main()
