"""Package the exact checkpoint set from a verified run without local artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.package_model import REQUIRED, clean, digest


def package(checkpoints, routing, output, card=None):
    checkpoints, output = Path(checkpoints), Path(output)
    metadata = json.loads(Path(routing).read_text())
    heads = metadata['question_heads']
    expected = hashlib.sha256(json.dumps(heads, sort_keys=True).encode()).hexdigest()
    if metadata['weights_sha256'] != expected:
        raise ValueError('Question-head manifest hash mismatch')
    names = set()
    for question, entry in heads.items():
        if question == 'shared_encoder_verified':
            continue
        name = entry['checkpoint']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError('Invalid checkpoint directory name')
        for filename in REQUIRED:
            if not (checkpoints / name / filename).is_file():
                raise FileNotFoundError(checkpoints / name / filename)
        if digest(checkpoints / name / 'model.safetensors') != entry['weights_sha256']:
            raise ValueError('Checkpoint weights differ from verified run: ' + question)
        names.add(name)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.bundle-') as tmp:
        staged = Path(tmp) / output.name
        staged.mkdir()
        for name in sorted(names):
            for filename in REQUIRED:
                source, target = checkpoints / name / filename, staged / name / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                if filename.endswith('.json'):
                    target.write_text(json.dumps(clean(json.loads(source.read_text())), indent=2) + '\n')
                else:
                    shutil.copyfile(source, target)
        for name in ('LICENSE', 'NOTICE'):
            shutil.copyfile(ROOT / name, staged / name)
        shutil.copyfile(card or ROOT / 'model-card/MAP02.md', staged / 'README.md')
        (staged / 'question-heads.json').write_text(json.dumps(clean(metadata), indent=2) + '\n')
        manifest = {p.relative_to(staged).as_posix(): digest(p)
                    for p in sorted(staged.rglob('*')) if p.is_file()}
        (staged / 'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name, value in manifest.items()))
        staged.rename(output)
    print(json.dumps({'bundle': str(output), 'checkpoints': len(names), 'files': len(manifest),
                      'weights_sha256': expected}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoints', type=Path, default=ROOT / 'checkpoints')
    parser.add_argument('--routing', type=Path, default=ROOT / 'reports/map02-model.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/laya-doom-map02')
    args = parser.parse_args()
    package(args.checkpoints, args.routing, args.output)
