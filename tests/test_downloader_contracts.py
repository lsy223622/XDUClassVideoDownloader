"""Leaf downloader/validator contracts that do not access the network."""


def test_mp4_and_ts_integrity_checks_accept_minimal_valid_headers(tmp_path):
    from xduclassvideodownloader.core.validator import validate_file_integrity

    mp4 = tmp_path / "sample.mp4"
    mp4.write_bytes(b"\x00\x00\x00\x18ftyp" + b"0" * 1024)
    ts = tmp_path / "sample.ts"
    ts.write_bytes(b"\x47" + b"0" * 1024)

    assert validate_file_integrity(str(mp4)) is True
    assert validate_file_integrity(str(ts)) is True


def test_integrity_check_rejects_tiny_or_invalid_files(tmp_path):
    from xduclassvideodownloader.core.validator import validate_file_integrity

    tiny = tmp_path / "tiny.mp4"
    tiny.write_bytes(b"\x00\x00\x00\x18ftyp")
    invalid = tmp_path / "invalid.mp4"
    invalid.write_bytes(b"0" * 2048)

    assert validate_file_integrity(str(tiny)) is False
    assert validate_file_integrity(str(invalid)) is False


def test_existing_complete_mp4_is_skipped_without_auth_or_network(tmp_path):
    from xduclassvideodownloader.core.downloader import download_mp4

    output = tmp_path / "lesson.mp4"
    output.write_bytes(b"\x00\x00\x00\x18ftyp" + b"0" * 2048)

    assert download_mp4("https://example.com/lesson.mp4", output.name, str(tmp_path)) is True


def test_downloader_requires_explicit_auth_when_a_download_is_needed(tmp_path):
    from xduclassvideodownloader.core.downloader import download_mp4

    try:
        download_mp4("https://example.com/lesson.mp4", "missing.mp4", str(tmp_path))
    except ValueError as exc:
        assert "认证" in str(exc)
    else:
        raise AssertionError("a new download must not resolve auth implicitly")


def test_merge_failure_keeps_source_segments(tmp_path, monkeypatch):
    from xduclassvideodownloader.core import downloader

    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    output = tmp_path / "merged.mp4"
    first.write_bytes(b"\x00\x00\x00\x18ftyp" + b"0" * 2048)
    second.write_bytes(b"\x00\x00\x00\x18ftyp" + b"0" * 2048)
    monkeypatch.setattr(downloader, "check_ffmpeg_availability", lambda: True)
    monkeypatch.setattr(downloader.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("ffmpeg failed")))

    assert downloader.merge_videos([str(first), str(second)], str(output)) is False
    assert first.exists() and second.exists()
