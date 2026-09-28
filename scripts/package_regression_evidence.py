"""Export verified regression videos and allowlisted telemetry for a release."""
import argparse
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.check_publication import PRIVATE_PATH, SECRET
from scripts.package_model import clean, digest


def public_bytes(path):
    data = path.read_bytes()
    if SECRET.search(data):
        raise ValueError('Secret pattern in ' + path.name)
    if PRIVATE_PATH.search(data):
        if path.suffix != '.json':
            raise ValueError('Private path in non-metadata file: ' + path.name)
        data = (json.dumps(clean(json.loads(data)), indent=2) + '\n').encode()
    if SECRET.search(data) or PRIVATE_PATH.search(data):
        raise ValueError('Unsafe publication text: ' + path.name)
    return data


def package(report, output, clone_videos=False):
    import hashlib
    report, output = Path(report), Path(output)
    data = json.loads(report.read_text())
    if not data['passed'] or len(data['results']) != 3:
        raise ValueError('Expected a successful three-map series')
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    exported = {}
    for result in data['results']:
        name = result['map'].lower()
        run = ROOT / result['run']
        config = json.loads((run / 'config.json').read_text())
        video = run / 'video.mp4'
        if digest(video) != result['artifacts']['video.mp4']['sha256']:
            raise ValueError('Video differs from accepted report')
        target = output / ('laya-' + name + '.mp4')
        if clone_videos and sys.platform == 'darwin':
            subprocess.run(['/bin/cp', '-c', str(video), str(target)], check=True)
        else:
            shutil.copyfile(video, target)
        names = ['config.json', 'summary.json', 'verification.json', 'authority-verification.json',
                 'decisions.jsonl', 'telemetry.jsonl', 'events.jsonl']
        names += ['source/' + n for n in config['source_sha256']]
        members = {}
        archive = output / (name + '-evidence.tar.gz')
        with tarfile.open(archive, 'w:gz', compresslevel=6) as tar:
            for filename in names:
                source = run / filename
                if filename.startswith('source/') and digest(source) != config['source_sha256'][filename[7:]]:
                    raise ValueError('Source snapshot changed: ' + filename)
                content = public_bytes(source)
                info = tarfile.TarInfo(run.name + '/' + filename)
                info.size = len(content)
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(content))
                members[filename] = dict(original_sha256=digest(source),
                                         published_sha256=hashlib.sha256(content).hexdigest())
        exported[result['map']] = dict(run=run.name, video=target.name, archive=archive.name, files=members)
    (output / 'evidence-files.json').write_text(json.dumps(exported, indent=2) + '\n')
    shutil.copyfile(report, output / 'regression.json')
    hashes = {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()}
    (output / 'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name, value in hashes.items()))
    print(json.dumps({'output': str(output), 'files': len(hashes)}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, default=ROOT / 'reports/v031-regression.json')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--clone-videos', action='store_true')
    a = p.parse_args()
    package(a.report, a.output, a.clone_videos)
