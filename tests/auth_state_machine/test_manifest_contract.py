from pathlib import Path

from tools.generate_manifest import generate


def test_manifest_generator_is_deterministic_and_uses_public_allowlist(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("public readme", encoding="utf-8")
    (tmp_path / "cloud_phone_monitor").mkdir()
    (tmp_path / "cloud_phone_monitor" / "sample.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "patch_external_ugphone_preflight.py").write_text("private", encoding="utf-8")
    (tmp_path / ".venv" / "Scripts").mkdir(parents=True)
    (tmp_path / ".venv" / "Scripts" / "python.exe").write_bytes(b"private-runtime")
    (tmp_path / "output" / "auth").mkdir(parents=True)
    (tmp_path / "output" / "auth" / "ugphone_state.json").write_text("secret", encoding="utf-8")

    first = generate(tmp_path)
    second = generate(tmp_path)
    assert first == second
    assert "  README.md\n" in first
    assert "  cloud_phone_monitor/sample.py\n" in first
    assert "patch_external_ugphone_preflight.py" not in first
    assert ".venv/" not in first
    assert "output/" not in first


def test_manifest_generator_excludes_manifest_itself(tmp_path: Path) -> None:
    (tmp_path / "MANIFEST_SHA256.txt").write_text("stale", encoding="utf-8")
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    result = generate(tmp_path)
    assert "MANIFEST_SHA256.txt" not in result
    assert "README.md" in result


def test_release_zip_is_deterministic(tmp_path: Path) -> None:
    from tools.build_release_zip import build_zip

    source = tmp_path / "stage"
    source.mkdir()
    (source / "README.md").write_text("same bytes\n", encoding="utf-8")
    (source / "MANIFEST_SHA256.txt").write_text("manifest\n", encoding="utf-8")
    first = tmp_path / "a.zip"
    second = tmp_path / "b.zip"
    build_zip(source, first)
    build_zip(source, second)
    assert first.read_bytes() == second.read_bytes()


def test_release_zip_rejects_unexpected_stage_files(tmp_path: Path) -> None:
    from tools.build_release_zip import build_zip

    source = tmp_path / "stage"
    source.mkdir()
    (source / "README.md").write_text("public\n", encoding="utf-8")
    (source / "MANIFEST_SHA256.txt").write_text("manifest\n", encoding="utf-8")
    cache = source / "tools" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "policy.pyc").write_bytes(b"bytecode")
    try:
        build_zip(source, tmp_path / "bad.zip")
    except RuntimeError as exc:
        assert "outside the explicit public allowlist" in str(exc)
    else:
        raise AssertionError("release ZIP must reject unexpected staging files")
