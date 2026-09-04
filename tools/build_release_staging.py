from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import shutil
from pathlib import Path

try:
    from tools.public_release_policy import (
        is_public_source_path,
        required_public_paths,
        write_sanitized_deployment_contract,
    )
except ModuleNotFoundError:
    from public_release_policy import (
        is_public_source_path,
        required_public_paths,
        write_sanitized_deployment_contract,
    )


def build(source: Path, destination: Path) -> list[str]:
    source = source.resolve()
    destination = destination.resolve()
    try:
        destination.relative_to(source)
    except ValueError:
        pass
    else:
        raise RuntimeError("release staging destination must be outside the source tree")

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    copied: list[str] = []
    sanitized_contract_fields: list[str] = []
    for path in sorted(source.rglob("*")):
        rel = path.relative_to(source).as_posix()
        if path.is_symlink():
            if is_public_source_path(rel):
                raise RuntimeError(f"public release path must not be a symlink: {rel}")
            continue
        if not path.is_file():
            continue
        if not is_public_source_path(rel):
            continue
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel == "deployment_contract.json":
            sanitized_contract_fields = write_sanitized_deployment_contract(path, target)
        else:
            shutil.copy2(path, target)
        copied.append(rel)

    missing = sorted(rel for rel in required_public_paths() if not (destination / rel).is_file())
    if missing:
        raise RuntimeError("required public files missing from staging: " + ", ".join(missing))

    if sanitized_contract_fields:
        print(f"Sanitized {len(sanitized_contract_fields)} private/non-public deployment_contract field(s).")
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an explicit-allowlist public source staging tree.")
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()
    copied = build(Path(args.source), Path(args.destination))
    print(f"Release staging built: {Path(args.destination).resolve()}")
    print(f"Files copied: {len(copied)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
