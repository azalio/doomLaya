"""Check tracked/publication candidates without printing secret values."""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(rb"(?:sk-or-v1-[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
PRIVATE_PATH = re.compile(rb"/(?:Users|home)/[A-Za-z0-9_-]+/")
FORBIDDEN = {".env", ".venv", ".map", "runs", "checkpoints", "dist", "archive", "__pycache__"}


def main():
    candidates = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    errors = []
    registry = json.loads((ROOT / "training/datasets.json").read_text())
    total = 0
    files = sorted(set(filter(None, candidates)))
    for name in files:
        path = ROOT / name
        if path.is_symlink():
            errors.append(f"symlink: {name}")
            continue
        if not path.is_file():
            errors.append(f"missing: {name}")
            continue
        if any(part in FORBIDDEN for part in path.relative_to(ROOT).parts) or (path.name.startswith(".env.") and path.name != ".env.example"):
            errors.append(f"private/generated file: {name}")
        if path.suffix in {".safetensors", ".pt", ".pth", ".wad", ".mp4", ".tar"}:
            errors.append(f"binary artifact: {name}")
        size = path.stat().st_size
        total += size
        # Registered datasets retain raw observations and questions for API replay.
        dataset = name in registry and name.startswith("training/") and name.endswith(("/train.json", "/validation.json"))
        limit_mib = 12 if dataset else 10
        if size > limit_mib * 1024 * 1024:
            errors.append(f"file exceeds source budget of {limit_mib} MiB: {name}")
            continue
        content = path.read_bytes()
        if SECRET.search(content):
            errors.append(f"secret pattern: {name}")
        if PRIVATE_PATH.search(content):
            errors.append(f"private absolute path: {name}")
        if path.suffix == ".md":
            for link in re.findall(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", content.decode()):
                target = link.split("#", 1)[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                if not (path.parent / target).exists():
                    errors.append(f"broken relative link in {name}: {target}")
    print(json.dumps({"passed": not errors, "files": len(files), "bytes": total, "errors": errors}, indent=2))
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
