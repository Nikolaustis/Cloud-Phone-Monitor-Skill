from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import tempfile
from pathlib import Path

try:
    from tools.build_release_staging import build
    from tools.generate_manifest import generate
    from tools.validate_source_package import validate
except ModuleNotFoundError:
    from build_release_staging import build
    from generate_manifest import generate
    from validate_source_package import validate


def validate_release(source: Path, manifest_path: Path | None = None) -> list[str]:
    source = source.resolve()
    manifest_path = manifest_path.resolve() if manifest_path else source / "MANIFEST_SHA256.txt"
    problems: list[str] = []

    with tempfile.TemporaryDirectory(prefix="cloud_phone_public_release_") as tmp:
        stage = Path(tmp) / "stage"
        build(source, stage)
        problems.extend(validate(stage, require_exact_public_tree=True))
        expected_manifest = generate(stage)

    if not manifest_path.is_file():
        problems.append(f"committed public manifest missing: {manifest_path}")
    else:
        actual = manifest_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        if actual != expected_manifest:
            problems.append("committed MANIFEST_SHA256.txt does not match a freshly built public staging tree")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the public GitHub release contract from a working tree.")
    parser.add_argument("source", nargs="?", default=".")
    parser.add_argument("--manifest", default=None)
    args = parser.parse_args()
    source = Path(args.source)
    manifest = Path(args.manifest) if args.manifest else None
    problems = validate_release(source, manifest)
    if problems:
        print("Public release validation failed:")
        for problem in problems:
            print("-", problem)
        return 2
    print("Public release validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
