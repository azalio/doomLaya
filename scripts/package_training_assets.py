"""Package the fixed parents, semantic caches and retention traces for v0.3.1."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.check_publication import PRIVATE_PATH, SECRET
from scripts.package_model import REQUIRED, digest

PARENTS = (
    'laya-v031-command-finish-retained-v1',
    'laya-v031-item-consistent-v1',
    'laya-map3-compact-movement-v1',
    'laya-v031-switch-collected-v1',
    'laya-v031-enemy-visibility-v1',
    'laya-v031-weapon-boundary-v1',
)
CACHES = ('v031-command-key-return-cache.json', 'v031-item-balanced-v2-cache.json',
          'v031-movement-numeric-cache.json', 'v031-switch-teacher-semantic-cache.json')
TRACES = ('20260928_060838_897203_v031-finish-retained-map03-seed54',
          '20260928_061517_586603_v031-finish-retained-map01-seed48')


def package(output, clone_weights=False):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    if clone_weights and sys.platform != 'darwin':
        raise ValueError('APFS clones require macOS')
    registry = json.loads((ROOT / 'training/datasets.json').read_text())
    registered = {entry['sha256'] for entry in registry.values()}
    for name in CACHES:
        identity = json.loads((ROOT / 'runs' / name).read_text())['identity']
        if not set(identity['data'].values()) <= registered:
            raise ValueError('Cache data is not registered for publication: ' + name)
    files = []
    for name in PARENTS:
        source = ROOT / 'checkpoints' / name
        names = list(REQUIRED)
        config = json.loads((source / 'rl_agent_config.json').read_text())
        if config.get('doom_adaptation', {}).get('numeric_residual'):
            names += ['numeric-residual.json', 'numeric-residual.safetensors']
        files.extend((source / f, Path('parents') / name / f) for f in names)
    files.extend((ROOT / 'runs' / f, Path('caches') / f) for f in CACHES)
    files.extend((ROOT / 'runs' / n / 'decisions.jsonl', Path('retention') / n / 'decisions.jsonl') for n in TRACES)
    # Check text before copying anything. Keep its exact bytes: cache identity
    # includes the parent's config hash, including whitespace and the newline.
    for source, _ in files:
        if not source.is_file() or source.is_symlink():
            raise ValueError('Missing or symlinked source: ' + str(source.relative_to(ROOT)))
        if source.suffix != '.safetensors':
            content = source.read_bytes()
            if SECRET.search(content) or PRIVATE_PATH.search(content):
                raise ValueError('Unsafe publication text: ' + str(source.relative_to(ROOT)))
    output.mkdir(parents=True)
    manifest = {}
    for source, relative in files:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if clone_weights:
            subprocess.run(['/bin/cp', '-c', str(source), str(target)], check=True)
        else:
            shutil.copyfile(source, target)
        expected = digest(source)
        if digest(target) != expected:
            raise ValueError('Copy differs: ' + str(relative))
        manifest[relative.as_posix()] = expected
    (output / 'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name, value in sorted(manifest.items())))
    print(json.dumps({'output': str(output), 'files': len(manifest), 'parents': len(PARENTS)}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--clone-weights', action='store_true')
    a = p.parse_args()
    package(a.output, a.clone_weights)
