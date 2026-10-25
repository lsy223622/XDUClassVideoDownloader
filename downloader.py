"""Compatibility facade for the XDUClassVideoDownloader 5.x downloader."""

from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Union
from pathlib import Path

from xduclassvideodownloader.core import auth as _auth
from xduclassvideodownloader.core import downloader as _core_downloader
from xduclassvideodownloader.core.downloader import *  # noqa: F401,F403
from xduclassvideodownloader.core.downloader import _build_base_filename  # noqa: F401


def download_mp4(
    url: str,
    filename: str,
    save_dir: str,
    max_attempts: int = MAX_DOWNLOAD_RETRIES,
) -> bool:
    output = Path(save_dir) / get_safe_filename(filename)
    cookies = None
    if not output.exists() or not verify_file_integrity(str(output)):
        cookies = _auth.get_auth_cookies()
    return _core_downloader.download_mp4(
        url, filename, save_dir, max_attempts=max_attempts, auth_cookies=cookies
    )


def download_m3u8(
    m3u8_url: str,
    filename: str,
    save_dir: str,
    max_attempts: int = MAX_DOWNLOAD_RETRIES,
) -> bool:
    return _core_downloader.download_m3u8(
        m3u8_url,
        filename,
        save_dir,
        max_attempts=max_attempts,
        auth_cookies=_auth.get_auth_cookies(),
    )


def download_subtitle_for_row(
    row: List[Any], course_code: str, course_name: str, year: int, save_dir: str
):
    return _core_downloader.download_subtitle_for_row(
        row, course_code, course_name, year, save_dir, auth_cookies=_auth.get_auth_cookies()
    )


def download_single_video(
    row: List[Any],
    course_code: str,
    course_name: str,
    year: int,
    save_dir: str,
    video_type: str,
) -> bool:
    return _core_downloader.download_single_video(
        row,
        course_code,
        course_name,
        year,
        save_dir,
        video_type,
        _auth.get_auth_cookies(),
    )


def process_rows(
    rows: List[List[Any]],
    course_code: str,
    course_name: str,
    year: int,
    save_dir: str,
    merge: bool = True,
    video_type: str = "both",
    api_version: str = "new",
) -> Dict[str, int]:
    return _core_downloader.process_rows(
        rows,
        course_code,
        course_name,
        year,
        save_dir,
        merge,
        video_type,
        api_version,
        _auth.get_auth_cookies(),
    )


def download_course_videos(
    live_id: Union[int, str],
    single: int = 0,
    merge: bool = True,
    video_type: str = "both",
    skip_weeks: Optional[Set[int]] = None,
) -> bool:
    return _core_downloader.download_course_videos(
        live_id,
        single,
        merge,
        video_type,
        skip_weeks,
        auth_cookies=_auth.get_auth_cookies(),
    )


def process_all_courses(config, video_type: str = "both") -> bool:
    return _core_downloader.process_all_courses(
        config, video_type, _auth.get_auth_cookies()
    )
