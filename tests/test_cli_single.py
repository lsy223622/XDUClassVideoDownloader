"""Single-course CLI facade contracts."""


def test_cli_builds_core_download_options(monkeypatch):
    from xduclassvideodownloader.cli import single

    captured = {}
    monkeypatch.setattr(
        single,
        "download_course",
        lambda options: captured.__setitem__("options", options) or True,
    )

    assert single.main("12345", single=1, merge=False, video_type="ppt", skip_weeks="2") is True
    assert captured["options"].live_id == "12345"
    assert captured["options"].single == 1
    assert captured["options"].merge is False
    assert captured["options"].skip_weeks == "2"


def test_cli_keyboard_interrupt_returns_false(monkeypatch):
    from xduclassvideodownloader.cli import single

    monkeypatch.setattr(single, "download_course", lambda options: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert single.main("12345") is False
