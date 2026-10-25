"""连续节次合并与字幕回归测试。"""

from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from xduclassvideodownloader.core import downloader


PREFIX = "CS101测试课2026年10月19日第8周星期一"
MP4_HEADER = b"\x00\x00\x00\x18ftyp" + b"\x00" * 1024


def write_video(path, periods):
    header = b"\x47" + b"\x00" * 1031 if path.suffix == ".ts" else MP4_HEADER
    path.write_bytes(header + bytes(periods))


def lesson_row(period):
    return [10, 19, 1, period, 8, f"https://example.com/{period}",
            f"https://example.com/{period}", period]


@pytest.fixture
def local_media(monkeypatch):
    def download(url, filename, save_dir, **kwargs):
        write_video(Path(save_dir) / filename, [int(url.rsplit("/", 1)[1])])
        return True

    def run_ffmpeg(command, **kwargs):
        input_path = Path(command[command.index("-i") + 1])
        if "concat" in command:
            filelist = input_path.read_text(encoding="utf-8")
            sources = [Path(line[6:-1].replace("\\'", "'")) for line in filelist.splitlines()]
        else:
            sources = [input_path]
        payload = b"".join(source.read_bytes()[1032:] for source in sources)
        Path(command[-1]).write_bytes(MP4_HEADER + payload)
        return SimpleNamespace(stderr="")

    monkeypatch.setattr(downloader, "download_mp4", download)
    monkeypatch.setattr(downloader, "download_m3u8", download)
    monkeypatch.setattr(downloader, "check_ffmpeg_availability", lambda: True)
    monkeypatch.setattr(downloader, "get_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(downloader.subprocess, "run", run_ffmpeg)
    monkeypatch.setattr(
        downloader, "_get_media_duration_seconds",
        lambda video: len(Path(video).read_bytes()[1032:]) * 60,
    )
    monkeypatch.setattr(
        downloader, "get_video_subtitles_vtt",
        lambda live_id, **kwargs: f"WEBVTT\n\n00:01.000 --> 00:02.000\n第{live_id}节\n",
    )


@pytest.mark.parametrize("api_version", ["new", "legacy"])
@pytest.mark.parametrize("periods", [(9, 10), (9, 10, 11), (9, 10, 11, 12), (11, 10, 9)])
def test_contiguous_lessons_merge_in_order_with_subtitles(tmp_path, local_media, api_version, periods):
    stats = downloader.process_rows(
        [lesson_row(period) for period in periods], "CS101", "测试课", 2026,
        str(tmp_path), api_version=api_version,
    )

    span = f"{min(periods)}-{max(periods)}"
    assert sorted(path.name for path in tmp_path.glob("*.mp4")) == [
        f"{PREFIX}第{span}节-pptVideo.mp4",
        f"{PREFIX}第{span}节-teacherTrack.mp4",
    ]
    for video in tmp_path.glob("*.mp4"):
        assert video.read_bytes()[1032:] == bytes(sorted(periods))
    assert not list(tmp_path.glob("*.ts"))
    subtitles = list(tmp_path.glob("*.srt"))
    assert [path.name for path in subtitles] == [f"{PREFIX}第{span}节.srt"]
    cues = downloader._parse_srt_cues(subtitles[0].read_text(encoding="utf-8"))
    assert [cue["text"] for cue in cues] == [[f"第{period}节"] for period in sorted(periods)]
    assert [cue["start"] for cue in cues] == [1000, 61000, 121000, 181000][:len(periods)]
    assert stats["failed"] == 0


def test_existing_merged_range_extends_without_redownloading(tmp_path, local_media, monkeypatch):
    write_video(tmp_path / f"{PREFIX}第9-10节-pptVideo.mp4", [9, 10])
    write_video(tmp_path / f"{PREFIX}第11节-pptVideo.mp4", [11])
    (tmp_path / f"{PREFIX}第9-10节.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\n第9节\n\n"
        "2\n00:01:01,000 --> 00:01:02,000\n第10节\n", encoding="utf-8",
    )

    def unexpected_download(*args, **kwargs):
        pytest.fail("已有视频不应重新下载")

    monkeypatch.setattr(downloader, "download_mp4", unexpected_download)
    downloader.process_rows(
        [lesson_row(period) for period in (9, 10, 11)],
        "CS101", "测试课", 2026, str(tmp_path), video_type="ppt",
    )

    assert sorted(path.name for path in tmp_path.iterdir()) == [
        f"{PREFIX}第9-11节-pptVideo.mp4", f"{PREFIX}第9-11节.srt",
    ]
    assert (tmp_path / f"{PREFIX}第9-11节-pptVideo.mp4").read_bytes()[1032:] == bytes([9, 10, 11])
    assert "00:02:01,000" in (tmp_path / f"{PREFIX}第9-11节.srt").read_text(encoding="utf-8")


def test_merge_only_joins_contiguous_ranges_with_matching_prefix_and_track(tmp_path, local_media):
    write_video(tmp_path / f"{PREFIX}第9-10节-pptVideo.mp4", [9, 10])
    write_video(tmp_path / f"{PREFIX}第12-13节-pptVideo.mp4", [12, 13])
    excluded = [
        f"{PREFIX}第15节-pptVideo.mp4",
        f"{PREFIX}第14节-teacherTrack.mp4",
        f"{PREFIX.replace('19日', '20日')}第14节-pptVideo.mp4",
        f"{PREFIX.replace('第8周', '第9周')}第14节-pptVideo.mp4",
        f"{PREFIX.replace('CS101', 'CS102')}第14节-pptVideo.mp4",
        f"{PREFIX.replace('测试课', '其他课')}第14节-pptVideo.mp4",
    ]
    for name in excluded:
        write_video(tmp_path / name, [14])
    invalid = tmp_path / f"{PREFIX}第14节-pptVideo.mp4"
    invalid.write_bytes(b"broken")

    downloader.process_rows([lesson_row(11)], "CS101", "测试课", 2026, str(tmp_path), video_type="ppt")

    assert (tmp_path / f"{PREFIX}第9-13节-pptVideo.mp4").read_bytes()[1032:] == bytes([9, 10, 11, 12, 13])
    assert all((tmp_path / name).exists() for name in excluded)
    assert invalid.read_bytes() == b"broken"


def test_merge_disabled_keeps_individual_lessons(tmp_path, local_media):
    downloader.process_rows(
        [lesson_row(period) for period in (9, 10, 11)], "CS101", "测试课", 2026,
        str(tmp_path), merge=False, video_type="teacher",
    )
    assert sorted(path.name for path in tmp_path.glob("*.mp4")) == [
        f"{PREFIX}第10节-teacherTrack.mp4", f"{PREFIX}第11节-teacherTrack.mp4",
        f"{PREFIX}第9节-teacherTrack.mp4",
    ]


@pytest.mark.parametrize("failure_stage", ["remux", "concat"])
def test_mixed_container_merge_failure_keeps_sources(tmp_path, local_media, monkeypatch, failure_stage):
    previous = tmp_path / f"{PREFIX}第9-10节-pptVideo.mp4"
    current = tmp_path / f"{PREFIX}第11节-pptVideo.ts"
    write_video(previous, [9, 10])
    write_video(current, [11])
    original_sources = {path: path.read_bytes() for path in (previous, current)}
    run_ffmpeg = downloader.subprocess.run

    def fail_ffmpeg(command, **kwargs):
        stage = "concat" if "concat" in command else "remux"
        if stage == failure_stage:
            raise RuntimeError("ffmpeg failed")
        return run_ffmpeg(command, **kwargs)

    monkeypatch.setattr(downloader.subprocess, "run", fail_ffmpeg)
    stats = downloader.process_rows(
        [lesson_row(11)], "CS101", "测试课", 2026, str(tmp_path),
        api_version="legacy", video_type="ppt",
    )

    assert stats["merged"] == 0
    assert all(path.read_bytes() == content for path, content in original_sources.items())
    assert not (tmp_path / f"{PREFIX}第9-11节-pptVideo.mp4").exists()
    assert not list(tmp_path.glob(".*"))


def test_single_lesson_mode_keeps_all_three_periods(tmp_path, local_media, monkeypatch):
    monkeypatch.chdir(tmp_path)
    entries = [
        {"id": period, "courseCode": "CS101", "courseName": "测试课",
         "startTime": {"time": 1792368000000, "month": 9, "date": 19},
         "endTime": {"time": 1792371600000}, "jie": period, "days": 8}
        for period in (9, 10, 11)
    ]
    monkeypatch.setattr(downloader, "get_initial_data", lambda *args, **kwargs: entries)
    monkeypatch.setattr(downloader, "detect_api_version", lambda data: "new")
    monkeypatch.setattr(downloader, "fetch_video_links", lambda entry, *args: lesson_row(entry["id"]))
    monkeypatch.setattr(downloader, "get_app_path", lambda *parts: tmp_path.joinpath(*parts))

    assert downloader.download_course_videos(9, single=1, video_type="ppt") is True
    output = tmp_path / "2026年CS101测试课" / f"{PREFIX}第9-11节-pptVideo.mp4"
    assert output.exists()
    assert output.read_bytes()[1032:] == bytes([9, 10, 11])


def test_ts_lessons_extend_mp4_range_without_timebase_gaps(tmp_path, monkeypatch):
    bundled_ffmpeg = Path(__file__).resolve().parents[1] / "ffmpeg.exe"
    ffmpeg = str(bundled_ffmpeg) if bundled_ffmpeg.is_file() else shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("需要完整 FFmpeg 生成媒体样本")

    for period, color in [(9, "red"), (10, "green"), (11, "blue")]:
        subprocess.run([
            ffmpeg, "-loglevel", "error", "-f", "lavfi", "-i",
            f"color=c={color}:s=64x64:r=10:d=1", "-f", "lavfi", "-i",
            f"sine=frequency={period * 100}:duration=1", "-c:v", "libx264",
            "-preset", "ultrafast", "-c:a", "aac", "-shortest", "-f", "mpegts",
            "-y", str(tmp_path / f"{period}.ts"),
        ], check=True, capture_output=True, timeout=30)

    def download(url, filename, save_dir, **kwargs):
        shutil.copyfile(tmp_path / f"{url.rsplit('/', 1)[1]}.ts", Path(save_dir) / filename)
        return True

    monkeypatch.setattr(downloader, "get_ffmpeg_path", lambda: ffmpeg)
    monkeypatch.setattr(downloader, "download_m3u8", download)
    monkeypatch.setattr(downloader, "get_video_subtitles_vtt", lambda *args, **kwargs: None)
    destination = tmp_path / "output"
    downloader.process_rows(
        [lesson_row(period) for period in (9, 10, 11)], "CS101", "测试课", 2026,
        str(destination), api_version="legacy", video_type="ppt",
    )

    output = destination / f"{PREFIX}第9-11节-pptVideo.mp4"
    assert [path.name for path in destination.iterdir()] == [output.name]
    assert 2.9 <= downloader._get_media_duration_seconds(output) <= 3.6
    for timestamp, channel in [(0.5, 0), (1.5, 1), (2.5, 2)]:
        frame = subprocess.run([
            ffmpeg, "-loglevel", "error", "-ss", str(timestamp), "-i", str(output),
            "-frames:v", "1", "-vf", "scale=1:1", "-pix_fmt", "rgb24",
            "-f", "rawvideo", "pipe:1",
        ], check=True, capture_output=True, timeout=30).stdout
        assert len(frame) == 3
        assert max(range(3), key=lambda index: frame[index]) == channel
