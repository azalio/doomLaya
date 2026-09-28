"""Protect reproducible datasets and the boundary of the public model bundle."""
import contextlib
import io
import hashlib
import json
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from scripts.package_model import REQUIRED, package

ROOT = Path(__file__).resolve().parents[1]


class PublicationTest(unittest.TestCase):
    def test_public_entry_points_import_without_local_diagnostics(self):
        for name in ("agent.py", "tools/verify_run.py", "tools/regression_suite.py", "tools/run_comparison.py", "tools/render_comparison.py", "serve_doom_laya.py", "training/finetune.py"):
            with self.subTest(name=name), patch.object(sys, "argv", [name, "--help"]), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    runpy.run_path(str(ROOT / name), run_name="__main__")
                self.assertEqual(result.exception.code, 0)

    def test_run_source_snapshot_imports_without_checkout(self):
        import agent

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('agent.py', 'serve_doom_laya.py'):
                shutil.copy2(ROOT / name, root / name)
            shutil.copytree(ROOT / 'doomlib', root / 'doomlib',
                            ignore=shutil.ignore_patterns('__pycache__'))
            with patch.object(agent, 'ROOT', root), \
                    patch.object(sys, 'argv', ['agent.py', '--dry']), \
                    patch.object(agent, 'make_game', side_effect=KeyboardInterrupt), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(agent.main(), 0)
            run = next((root / 'runs').iterdir())
            snapshot = run / 'source'
            result = subprocess.run(
                [sys.executable, '-E', '-B', str(snapshot / 'agent.py'), '--help'],
                cwd=snapshot, capture_output=True, text=True, encoding='utf-8', timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            config = json.loads((run / 'config.json').read_text())
            for name in ('doomlib/command_keys.py', 'doomlib/command_facts.py', 'doomlib/numeric_command.py', 'doomlib/numeric_item.py', 'doomlib/numeric_movement.py'):
                self.assertEqual(config['source_sha256'][name], hashlib.sha256((snapshot / name).read_bytes()).hexdigest())
            self.assertEqual(
                config['source_sha256']['doomlib/__init__.py'],
                hashlib.sha256((snapshot / 'doomlib/__init__.py').read_bytes()).hexdigest(),
            )

    def test_comparison_reads_unicode_run_path_with_windows_locale(self):
        read_text = Path.read_text
        for encoding in ('cp1251', 'cp1252'):
            with self.subTest(encoding=encoding), tempfile.TemporaryDirectory() as tmp:
                run = Path(tmp) / 'José_Иван'
                run.mkdir()
                (run / 'config.json').write_text(json.dumps({'source_sha256': {}}))

                def launch(command, *, stdout, stderr):
                    stdout.buffer.write(f'RUN {run}\n'.encode('utf-8'))
                    stdout.flush()
                    return Mock(wait=Mock(return_value=0))

                def read_with_locale(path, *args, **kwargs):
                    if path.suffix == '.log' and not args and kwargs.get('encoding') is None:
                        kwargs['encoding'] = encoding
                    return read_text(path, *args, **kwargs)

                result = {'passed': True, 'experiment_valid': True, 'summary': {}}
                with contextlib.chdir(tmp), \
                        patch.object(sys, 'argv', ['run_comparison', '--models', 'doom-adapted']), \
                        patch('subprocess.Popen', side_effect=launch), \
                        patch.object(Path, 'read_text', read_with_locale), \
                        patch('diagnostics.verify_model_run.verify', return_value=result) as verify, \
                        patch('tools.summarize_authority.summarize', return_value={}), \
                        contextlib.redirect_stdout(io.StringIO()):
                    runpy.run_path(str(ROOT / 'tools/run_comparison.py'), run_name='__main__')
                verify.assert_called_once_with(run)
                entries = json.loads(next((Path(tmp) / 'runs').glob('*/runs.json')).read_text())
                self.assertEqual(entries[0]['path'], str(run))

    def test_frozen_training_data_hashes_and_holdout(self):
        manifest = json.loads((ROOT / 'training/datasets.json').read_text())
        sources = {}
        for name, expected in manifest.items():
            content = (ROOT / name).read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), expected['sha256'], name)
            rows = json.loads(content)
            self.assertEqual(len(rows), expected['questions'])
            sources[name] = {r['source_run'] for r in rows if 'source_run' in r}
            for row in rows:
                if 'source_run' not in row:
                    self.assertTrue(row.get('synthetic'))
                    self.assertIsInstance(row.get('generator_seed'), int)
                    self.assertIsInstance(row.get('source_index'), int)
                self.assertIn(row['label'], row['question']['criteria'])
                if expected.get('evaluation_scope') == 'same_map_development':
                    self.assertTrue(name.startswith('training/v031-'))
                    self.assertIn('no held-out', expected['note'])
                else:
                    self.assertNotIn('48', row['source_run'].rsplit('-', 1)[-1])
        for base in ('training', 'training/v3'):
            self.assertFalse(sources[base + '/train.json'] & sources[base + '/validation.json'])

    def test_bundle_excludes_secrets_and_scrubs_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / 'checkpoint', Path(tmp) / 'model'
            for name in REQUIRED:
                p = source / name
                p.parent.mkdir(parents=True, exist_ok=True)
                if name.endswith('.json'):
                    private = '/' + 'Users' + '/example/private/checkpoint'
                    p.write_text(json.dumps({'base_checkpoint': private}))
                else:
                    p.write_bytes(b'tiny test weights')
            (source / '.env').write_text('PRIVATE=must not escape')
            (source / 'unrelated.log').write_text('not public')
            package(source, output, archive=True)
            self.assertFalse((output / '.env').exists())
            self.assertFalse((output / 'unrelated.log').exists())
            config = json.loads((output / 'rl_agent_config.json').read_text())
            self.assertEqual(config['base_checkpoint'], 'checkpoint')
            self.assertEqual((output / 'model.safetensors').read_bytes(), (source / 'model.safetensors').read_bytes())
            for line in (output / 'SHA256SUMS').read_text().splitlines():
                digest, name = line.split('  ', 1)
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)
            with tarfile.open(output.with_suffix('.tar')) as archive:
                self.assertTrue(all(m.name.startswith('model/') and m.isfile() for m in archive.getmembers()))
                self.assertNotIn('model/.env', archive.getnames())
            with self.assertRaises(FileExistsError):
                package(source, output)


if __name__ == '__main__':
    unittest.main()
