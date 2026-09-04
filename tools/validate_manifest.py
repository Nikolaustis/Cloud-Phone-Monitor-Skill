from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import re
from pathlib import Path

try:
    from tools.generate_manifest import generate
except ModuleNotFoundError:  # direct script execution from tools/
    from generate_manifest import generate


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate MANIFEST_SHA256.txt against the current source tree.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    manifest = root / "MANIFEST_SHA256.txt"
    if not manifest.is_file():
        print("Manifest missing:", manifest)
        return 2
    actual = manifest.read_text(encoding="utf-8").replace("\r\n", "\n")
    expected = generate(root)
    if actual != expected:
        actual_lines = set(actual.splitlines())
        expected_lines = set(expected.splitlines())
        print("Manifest validation failed.")
        for line in sorted(expected_lines - actual_lines)[:30]:
            print("MISSING/CHANGED:", re.sub(r"^[0-9a-f]{64}  ", "", line))
        for line in sorted(actual_lines - expected_lines)[:30]:
            print("STALE/EXTRA:", re.sub(r"^[0-9a-f]{64}  ", "", line))
        return 2
    print("Manifest validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
