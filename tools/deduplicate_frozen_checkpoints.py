"""Share unchanged safetensors storage with APFS clones; preserve exact file bytes."""
import argparse, hashlib, json, os, shutil, struct, subprocess, tempfile
from pathlib import Path


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def header(path):
    with Path(path).open('rb') as handle:
        prefix = handle.read(8)
        size = struct.unpack('<Q', prefix)[0]
        if size > 16 * 1024 * 1024: raise ValueError('Unexpected safetensors header size')
        raw = handle.read(size)
        if len(raw) != size: raise ValueError('Truncated header')
    return prefix + raw, json.loads(raw)


def clone(source, destination):
    subprocess.run(['/bin/cp', '-c', str(source), str(destination)], check=True)


def compact(base, target, copier=clone):
    base, target = Path(base).resolve(), Path(target).resolve()
    if base == target: raise ValueError('Base and target must differ')
    before = target.stat()
    if before.st_nlink != 1: raise ValueError('Refusing a multiply linked target')
    base_header, base_tensors = header(base)
    target_header, target_tensors = header(target)
    if base_header != target_header: raise ValueError('Headers differ; cannot preserve offsets with a clone')
    if base.stat().st_size != before.st_size: raise ValueError('File sizes differ')
    expected = digest(target)
    # Verify every frozen tensor before creating or replacing anything.
    with base.open('rb') as original, target.open('rb') as source:
        for name, info in target_tensors.items():
            if not name.startswith('encoder.'): continue
            start, end = info['data_offsets']; offset = len(target_header) + start
            original.seek(offset); source.seek(offset)
            remaining = end - start
            while remaining:
                size = min(1024 * 1024, remaining)
                if original.read(size) != source.read(size): raise ValueError('Encoder differs: ' + name)
                remaining -= size
    free_before = shutil.disk_usage(target.parent).free
    with tempfile.TemporaryDirectory(prefix='.clone-', dir=target.parent) as directory:
        temporary = Path(directory) / target.name
        copier(base, temporary)
        with target.open('rb') as source, temporary.open('r+b') as destination:
            for name, info in target_tensors.items():
                if name == '__metadata__' or name.startswith('encoder.'): continue
                start, end = info['data_offsets']; offset = len(target_header) + start
                source.seek(offset); destination.seek(offset)
                remaining = end - start
                while remaining:
                    size = min(1024 * 1024, remaining)
                    block = source.read(size)
                    if len(block) != size: raise ValueError('Truncated tensor')
                    destination.write(block); remaining -= size
            destination.flush(); os.fsync(destination.fileno())
        if digest(temporary) != expected: raise ValueError('Reconstructed checkpoint hash differs')
        current = target.stat()
        if (current.st_ino, current.st_size, current.st_mtime_ns) != (before.st_ino, before.st_size, before.st_mtime_ns):
            raise ValueError('Target changed during compaction')
        shutil.copystat(target, temporary)
        os.replace(temporary, target)
    if digest(target) != expected: raise ValueError('Final checkpoint hash differs')
    return dict(base=str(base), target=str(target), sha256=expected, bytes=before.st_size,
                filesystem_free_delta=shutil.disk_usage(target.parent).free-free_before)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--targets', type=Path, nargs='+', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists(): parser.error('Report exists')
    report = []
    for target in args.targets:
        report.append(compact(args.base, target))
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        print(target.parent.name, report[-1]['filesystem_free_delta'], flush=True)


if __name__ == '__main__': main()
