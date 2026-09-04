from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import zipfile
from pathlib import Path

try:
    from tools.public_release_policy import is_public_source_path
except ModuleNotFoundError:
    from public_release_policy import is_public_source_path

FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
MANIFEST_NAME = "MANIFEST_SHA256.txt"


def _release_files(source: Path) -> list[tuple[str, Path]]:
    source = source.resolve()
    included: list[tuple[str, Path]] = []
    unexpected: list[str] = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            unexpected.append(path.relative_to(source).as_posix() + " (symlink)")
            continue
        if not path.is_file():
            continue
        rel = path.relative_to(source).as_posix()
        if rel == MANIFEST_NAME or is_public_source_path(rel):
            included.append((rel, path))
        else:
            unexpected.append(rel)
    if unexpected:
        preview = ", ".join(unexpected[:20])
        raise RuntimeError(
            "release staging contains files outside the explicit public allowlist; "
            f"refusing to package: {preview}"
        )
    if not (source / MANIFEST_NAME).is_file():
        raise RuntimeError(f"validated release staging is missing {MANIFEST_NAME}")
    return included


def build_zip(source: Path, destination: Path) -> None:
    source = source.resolve()
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    release_files = _release_files(source)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel, path in release_files:
            info = zipfile.ZipInfo(rel, date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic public release ZIP from a validated staging tree.")
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()
    build_zip(Path(args.source), Path(args.destination))
    print(f"Deterministic release ZIP: {Path(args.destination).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
