"""Protect exact verified model weights and exclude private checkpoint files."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from scripts.package_model import REQUIRED, digest
from scripts.package_question_heads import package


class QuestionHeadPackageTest(unittest.TestCase):
    def test_bundle_preserves_verified_weights_and_rejects_a_changed_head(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'checkpoints'
            heads = {}
            for kind in ('default', 'item'):
                name = 'checkpoint-' + kind
                for filename in REQUIRED:
                    path = source / name / filename
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({'path': '/' + 'Users' + '/example/private/checkpoint'})
                                    if filename.endswith('.json') else 'test-' + kind)
                (source / name / '.env').write_text('PRIVATE=excluded')
                heads[kind] = dict(checkpoint=name, weights_sha256=digest(source / name / 'model.safetensors'))
            heads['shared_encoder_verified'] = True
            routing = root / 'routing.json'
            routing.write_text(json.dumps(dict(question_heads=heads,
                weights_sha256=hashlib.sha256(json.dumps(heads, sort_keys=True).encode()).hexdigest())))
            card = root / 'card.md'
            card.write_text('Model card fixture')
            output = root / 'bundle'
            package(source, routing, output, card)
            self.assertFalse(list(output.rglob('.env')))
            for kind in ('default', 'item'):
                name = 'checkpoint-' + kind
                self.assertEqual(digest(output / name / 'model.safetensors'), heads[kind]['weights_sha256'])
                self.assertEqual(json.loads((output / name / 'rl_agent_config.json').read_text())['path'], 'checkpoint')
            for line in (output / 'SHA256SUMS').read_text().splitlines():
                expected, name = line.split('  ', 1)
                self.assertEqual(digest(output / name), expected)
            (source / 'checkpoint-item/model.safetensors').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'weights differ'):
                package(source, routing, root / 'invalid', card)
            self.assertFalse((root / 'invalid').exists())
