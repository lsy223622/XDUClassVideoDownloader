"""Course-scan and semester helpers shared by CLI and WebUI."""

import time
from time import struct_time
from typing import Any, Dict, Mapping, Optional, Tuple

from . import platform as platform_module


def default_term(now: Optional[struct_time] = None) -> Tuple[int, int]:
    current = now or time.localtime()
    term_year = current.tm_year
    term_id = 1 if current.tm_mon >= 9 or current.tm_mon < 3 else 2
    if current.tm_mon < 9:
        term_year -= 1
    return term_year, term_id


def scan_term_courses(
    user_id: str,
    term_year: int,
    term_id: int,
    auth_cookies: Optional[Mapping[str, str]] = None,
) -> Dict[int, Dict[str, Any]]:
    return platform_module.scan_courses(
        user_id, term_year, term_id, auth_cookies=auth_cookies
    )


__all__ = ["default_term", "scan_term_courses"]
