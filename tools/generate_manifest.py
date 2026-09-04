from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import hashlib
from pathlib import Path

try:
    from tools.public_release_policy import is_public_source_path
except ModuleNotFoundError:
    from public_release_policy import is_public_source_path


def included_files(root: Path):
    root = root.resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if is_public_source_path(rel.as_posix()):
            yield rel, path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def generate(root: Path) -> str:
    return "".join(f"{sha256(path)}  {rel.as_posix()}\n" for rel, path in included_files(root))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic SHA-256 manifest for the explicit public release allowlist.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    out = root / "MANIFEST_SHA256.txt"
    out.write_text(generate(root), encoding="utf-8", newline="\n")
    print(f"Manifest generated: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
