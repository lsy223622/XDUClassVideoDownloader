"""Compatibility facade for the XDUClassVideoDownloader 5.x API module."""

from typing import Any, Dict, List, Mapping, Optional, Tuple, Union
from threading import Lock

from xduclassvideodownloader.core import auth as _auth
from xduclassvideodownloader.core import platform as _platform
from xduclassvideodownloader.core.platform import *  # noqa: F401,F403


def get_auth_cookies(force_refresh: bool = False) -> Dict[str, str]:
    return _auth.get_auth_cookies(force_refresh=force_refresh)


def has_valid_auth_cookies(cookies: Optional[Mapping[str, str]]) -> bool:
    return _auth.has_valid_auth_cookies(cookies)


def get_authenticated_headers() -> Dict[str, str]:
    return _platform.get_authenticated_headers(_auth.get_auth_cookies())


def get_initial_data(liveid: Union[int, str]) -> List[Dict[str, Any]]:
    return _platform.get_initial_data(liveid, _auth.get_auth_cookies())


def get_video_info_from_html(live_id: Union[int, str], retry_count: int = 0) -> Dict[str, Any]:
    return _platform.get_video_info_from_html(live_id, retry_count, _auth.get_auth_cookies())


def get_mp4_links(live_id: Union[int, str]) -> Tuple[str, str]:
    return _platform.get_mp4_links(live_id, _auth.get_auth_cookies())


def get_video_subtitles_vtt(live_id: Union[int, str]) -> Optional[str]:
    return _platform.get_video_subtitles_vtt(live_id, _auth.get_auth_cookies())


def fetch_data(url: str) -> Optional[Any]:
    return _platform.fetch_data(url, _auth.get_auth_cookies())


def scan_courses(user_id: str, term_year: int, term_id: int) -> Dict[int, Dict[str, Any]]:
    return _platform.scan_courses(user_id, term_year, term_id, _auth.get_auth_cookies())


def fetch_video_links(
    entry: Dict[str, Any], lock: Lock, desc: Any, api_version: str = "new"
) -> Optional[List[Any]]:
    return _platform.fetch_video_links(
        entry, lock, desc, api_version=api_version, auth_cookies=_auth.get_auth_cookies()
    )


def get_m3u8_info_legacy(live_id: Union[int, str], retry_count: int = 0) -> Dict[str, Any]:
    return _platform.get_m3u8_info_legacy(live_id, retry_count, _auth.get_auth_cookies())


def get_m3u8_links_legacy(live_id: Union[int, str]) -> Tuple[str, str]:
    return _platform.get_m3u8_links_legacy(live_id, _auth.get_auth_cookies())


_PLATFORM_FETCH_UPDATE_INFO = _platform.fetch_update_info


def fetch_update_info() -> Dict[str, Any]:
    return _PLATFORM_FETCH_UPDATE_INFO()


def check_update() -> bool:
    """Preserve monkeypatchable legacy update-check behavior."""

    original = _platform.fetch_update_info
    _platform.fetch_update_info = fetch_update_info
    try:
        return _platform.check_update()
    finally:
        _platform.fetch_update_info = original


def get_last_update_info() -> Optional[Dict[str, Any]]:
    return _platform.get_last_update_info()
