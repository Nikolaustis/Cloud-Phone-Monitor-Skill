from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cloud_phone_monitor.ai_context import AI_CONTEXT_SCHEMA_VERSION, build_ai_context


REQUIRED_DASHBOARD_ASSETS = {
    "frontend_price_overview.json",
    "pairing_matrix.json",
    "duration_price_comparison.json",
    "price_trends.json",
    "price_change_tracking.json",
    "product_text_changes.json",
    "metric_definitions.json",
    "schedule_status.json",
    "meta.json",
}

# Demo preparation is intentionally destructive only inside these local runtime
# sandboxes, or inside the OS/CI temporary directory.  This prevents a typo in
# output_root from deleting source, auth, baselines, or an arbitrary user folder.
_LOCAL_CONTROLLED_OUTPUTS = (
    Path("output") / "demo_runtime",
    Path("output") / "verification_demo_runtime",
    Path("output") / "release_demo_runtime",
)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _allowed_external_bases() -> list[Path]:
    bases: list[Path] = []
    for raw in (
        tempfile.gettempdir(),
        os.getenv("TMP"),
        os.getenv("TEMP"),
        os.getenv("RUNNER_TEMP"),
    ):
        if not raw:
            continue
        try:
            resolved = Path(raw).expanduser().resolve()
        except Exception:
            continue
        if resolved not in bases:
            bases.append(resolved)
    return bases


def _owned_external_runtime(path: Path, source_root: Path) -> bool:
    marker = path / "demo_runtime_manifest.json"
    if not marker.is_file():
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except Exception:
        return False
    return (
        payload.get("schema_version") == "demo-runtime-v1"
        and payload.get("safe_data_only") is True
        and Path(str(payload.get("source_root", ""))).expanduser().resolve() == source_root
    )


def validate_output_root(source_root: Path, output_root: Path) -> Path:
    source_root = source_root.expanduser().resolve()
    output_root = output_root.expanduser().resolve()

    # Never delete source itself, an ancestor of source, or a source subtree
    # other than the explicitly controlled local demo sandboxes.
    if output_root == source_root or _is_relative_to(source_root, output_root):
        raise RuntimeError(
            f"Unsafe demo output path: {output_root}. Output must never be the source root or an ancestor of it."
        )

    if _is_relative_to(output_root, source_root):
        controlled = [(source_root / rel).resolve() for rel in _LOCAL_CONTROLLED_OUTPUTS]
        if not any(output_root == base or _is_relative_to(output_root, base) for base in controlled):
            raise RuntimeError(
                "Unsafe demo output path inside source tree: "
                f"{output_root}. Allowed local roots: "
                + ", ".join(str(path) for path in controlled)
            )
        return output_root

    # Outside the repository, require a *strict descendant* of an OS/CI temp
    # directory. The temp root itself is never a legal deletion target.
    external_bases = _allowed_external_bases()
    matching_base = next(
        (base for base in external_bases if output_root != base and _is_relative_to(output_root, base)),
        None,
    )
    if matching_base is None:
        raise RuntimeError(
            f"Unsafe external demo output path: {output_root}. "
            "Use the project's controlled output roots or a dedicated child directory under OS/CI temp."
        )

    # A new dedicated temp child is safe to create. If it already exists, only
    # reuse/delete it when our own runtime marker proves ownership. This avoids
    # wiping another program's pre-existing temp directory.
    if output_root.exists() and not _owned_external_runtime(output_root, source_root):
        raise RuntimeError(
            f"Refusing to delete pre-existing unowned temp directory: {output_root}. "
            "Choose a new dedicated temp child or a previously generated demo runtime."
        )
    return output_root


def _safe_rmtree(path: Path, source_root: Path) -> None:
    validated = validate_output_root(source_root, path)
    if validated.exists():
        shutil.rmtree(validated)


def _copy_dashboard(source: Path, destination: Path) -> None:
    if destination.exists():
        raise RuntimeError(f"Demo dashboard destination unexpectedly exists after runtime reset: {destination}")

    def ignore(directory: str, names: list[str]) -> set[str]:
        path = Path(directory)
        ignored = {"node_modules", "dist", "__pycache__", ".pytest_cache"}
        if path.name == "public":
            ignored.add("dashboard_data")
        return {name for name in names if name in ignored}

    shutil.copytree(source, destination, ignore=ignore)


def _validate_demo_assets(demo_data: Path) -> None:
    missing = sorted(name for name in REQUIRED_DASHBOARD_ASSETS if not (demo_data / name).is_file())
    if missing:
        raise RuntimeError("Demo dashboard dataset is incomplete: " + ", ".join(missing))

    meta = json.loads((demo_data / "meta.json").read_text(encoding="utf-8"))
    if meta.get("safe_data_only") is not True:
        raise RuntimeError("Demo meta.json must assert safe_data_only=true")
    if meta.get("is_demo_data") is not True:
        raise RuntimeError("Demo meta.json must assert is_demo_data=true")


def prepare_demo_runtime(source_root: Path, output_root: Path) -> dict[str, str | int | bool]:
    source_root = source_root.expanduser().resolve()
    output_root = validate_output_root(source_root, output_root)
    dashboard_source = source_root / "dashboard"
    demo_data = source_root / "demo" / "dashboard_data"

    if not dashboard_source.is_dir():
        raise RuntimeError(f"Dashboard source directory is missing: {dashboard_source}")
    if not demo_data.is_dir():
        raise RuntimeError(f"Demo dashboard data is missing: {demo_data}")

    _validate_demo_assets(demo_data)

    _safe_rmtree(output_root, source_root)
    output_root.mkdir(parents=True, exist_ok=True)

    dashboard_runtime = output_root / "dashboard"
    _copy_dashboard(dashboard_source, dashboard_runtime)

    runtime_data = dashboard_runtime / "public" / "dashboard_data"
    runtime_data.mkdir(parents=True, exist_ok=True)
    for source in sorted(demo_data.iterdir()):
        if source.is_file():
            shutil.copy2(source, runtime_data / source.name)

    ai_dir = runtime_data / "ai"
    result = build_ai_context(runtime_data, ai_dir)
    manifest_path = ai_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != AI_CONTEXT_SCHEMA_VERSION:
        raise RuntimeError(f"Unexpected AI context schema: {manifest.get('schema_version')}")
    if manifest.get("safe_data_only") is not True:
        raise RuntimeError("Generated demo AI context is not marked safe_data_only=true")

    runtime_manifest = {
        "schema_version": "demo-runtime-v1",
        "safe_data_only": True,
        "is_demo_data": True,
        "source_root": str(source_root),
        "dashboard_root": str(dashboard_runtime),
        "dashboard_data_dir": str(runtime_data),
        "ai_context_dir": str(ai_dir),
        "ai_context_schema": manifest.get("schema_version"),
        "data_date": manifest.get("data_date"),
        "data_revision": manifest.get("data_revision"),
        "dashboard_asset_count": len(REQUIRED_DASHBOARD_ASSETS),
    }
    (output_root / "demo_runtime_manifest.json").write_text(
        json.dumps(runtime_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return runtime_manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare an isolated synthetic Dashboard + AI demo runtime without touching real dashboard data."
    )
    parser.add_argument("source_root", nargs="?", default=str(ROOT))
    parser.add_argument("output_root")
    args = parser.parse_args()
    result = prepare_demo_runtime(Path(args.source_root), Path(args.output_root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
