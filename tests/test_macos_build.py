import os

from squint.platforms.macos.build import is_stale


def test_missing_target_is_stale(tmp_path):
    source = tmp_path / "a.swift"
    source.write_text("")
    assert is_stale(tmp_path / "bin", [source])


def test_target_newer_than_sources_is_fresh(tmp_path):
    source, target = tmp_path / "a.swift", tmp_path / "bin"
    source.write_text("")
    target.write_text("")
    os.utime(source, (100, 100))
    os.utime(target, (200, 200))
    assert not is_stale(target, [source])


def test_any_newer_source_makes_target_stale(tmp_path):
    a, b, target = tmp_path / "a.swift", tmp_path / "b.swift", tmp_path / "bin"
    for path, t in ((a, 100), (target, 200), (b, 300)):
        path.write_text("")
        os.utime(path, (t, t))
    assert is_stale(target, [a, b])


def test_prebuilt_helper_is_used_without_compiling(tmp_path, monkeypatch):
    from squint.platforms.macos import build

    (tmp_path / "squint-ocr").write_text("")
    monkeypatch.setenv(build.BIN_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(build.subprocess, "run", None)  # any compile attempt would fail
    out = build.compile_swift(
        [tmp_path / "missing.swift"], tmp_path / "cache" / "squint-ocr"
    )
    assert out == tmp_path / "squint-ocr"
