from __future__ import annotations

import argparse
from pathlib import Path

from cloud_phone_monitor.ai_context import build_ai_context


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Build the safe semantic context used by the Cloud Phone Pricing Intelligence Copilot.")
    parser.add_argument("--data-dir", default=str(root / "dashboard" / "public" / "dashboard_data"))
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    result = build_ai_context(Path(args.data_dir), Path(args.output_dir) if args.output_dir else None)
    print(f"AI context: {result.output_dir}")
    print(f"Data date: {result.data_date}")
    print(f"Data revision: {result.data_revision}")
    for name, count in sorted(result.files.items()):
        print(f"- {name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
