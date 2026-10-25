"""Local media library indexing for the WebUI."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


VIDEO_RE = re.compile(
    r"^(?P<prefix>.+?)(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<date>\d{1,2})日第(?P<week>[^周]+)周星期(?P<day>.+?)第(?P<jie>\d+(?:-\d+)?)节-(?P<track>pptVideo|teacherTrack)\.(?P<ext>mp4|ts)$"
)
SUBTITLE_RE = re.compile(
    r"^(?P<prefix>.+?)(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<date>\d{1,2})日第(?P<week>[^周]+)周星期(?P<day>.+?)第(?P<jie>\d+(?:-\d+)?)节\.(?P<ext>srt|vtt)$"
)


def _safe_relative_url(path: Path, app_dir: Path) -> str:
    return path.resolve().relative_to(app_dir.resolve()).as_posix()


def _parse_jie_range(value: str) -> Tuple[int, int]:
    if "-" in value:
        start_text, end_text = value.split("-", 1)
        start, end = int(start_text), int(end_text)
    else:
        start = end = int(value)
    return min(start, end), max(start, end)


def _item_key(parts: Dict[str, str]) -> str:
    return "|".join([parts["year"], parts["month"], parts["date"], parts["week"], parts["day"], parts["jie"]])


def _item_title(parts: Dict[str, str]) -> str:
    return f"{parts['year']}年{parts['month']}月{parts['date']}日 第{parts['week']}周 星期{parts['day']} 第{parts['jie']}节"


def _same_lesson_day(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    return all(str(left.get(key)) == str(right.get(key)) for key in ("year", "month", "date", "week", "day"))


def _subtitle_match_score(item: Dict[str, Any], subtitle: Dict[str, Any]) -> Optional[Tuple[int, int, int]]:
    if not _same_lesson_day(item, subtitle):
        return None
    item_start, item_end = int(item["jie_start"]), int(item["jie_end"])
    sub_start, sub_end = int(subtitle["jie_start"]), int(subtitle["jie_end"])
    if sub_start == item_start and sub_end == item_end:
        return 0, sub_start, sub_end
    if item_start <= sub_start and sub_end <= item_end:
        return 1, sub_start, sub_end
    if sub_start <= item_start and item_end <= sub_end:
        return 2, sub_start, sub_end
    if max(item_start, sub_start) <= min(item_end, sub_end):
        return 3, sub_start, sub_end
    return None


def _assign_subtitles(items: Sequence[Dict[str, Any]], subtitles: Sequence[Dict[str, Any]]) -> None:
    for item in items:
        candidates = []
        for subtitle in subtitles:
            score = _subtitle_match_score(item, subtitle)
            if score is not None:
                candidates.append((score, subtitle))
        if not candidates:
            continue
        best_group = min(score[0] for score, _subtitle in candidates)
        matched = [subtitle for score, subtitle in candidates if score[0] == best_group]
        matched.sort(key=lambda subtitle: (int(subtitle["jie_start"]), int(subtitle["jie_end"])))
        item["subtitle_urls"] = [subtitle["url"] for subtitle in matched]
        item["subtitle_url"] = item["subtitle_urls"][0]


def index_local_library(app_dir: Path) -> Dict[str, Any]:
    """Index media below the mutable application directory without escaping it."""

    courses: Dict[str, Dict[str, Any]] = {}
    subtitle_index: Dict[str, List[Dict[str, Any]]] = {}
    for file_path in app_dir.glob("[0-9][0-9][0-9][0-9]年*/**/*"):
        if not file_path.is_file() or file_path.suffix.lower() not in {".mp4", ".ts", ".srt", ".vtt"}:
            continue
        try:
            rel = _safe_relative_url(file_path, app_dir)
        except ValueError:
            continue
        parent = file_path.parent
        course_key = _safe_relative_url(parent, app_dir)
        course = courses.setdefault(
            course_key,
            {"id": course_key, "title": parent.name, "items": {}},
        )
        if file_path.suffix.lower() in {".srt", ".vtt"}:
            match = SUBTITLE_RE.match(file_path.name)
            if not match:
                continue
            parts = match.groupdict()
            jie_start, jie_end = _parse_jie_range(parts["jie"])
            subtitle_index.setdefault(course_key, []).append(
                {
                    **parts,
                    "jie_start": jie_start,
                    "jie_end": jie_end,
                    "url": "/media/" + rel,
                    "filename": file_path.name,
                }
            )
            continue

        match = VIDEO_RE.match(file_path.name)
        if not match:
            continue
        parts = match.groupdict()
        jie_start, jie_end = _parse_jie_range(parts["jie"])
        key = _item_key(parts)
        item = course["items"].setdefault(
            key,
            {
                "id": key,
                "title": _item_title(parts),
                "year": parts["year"],
                "month": parts["month"],
                "date": parts["date"],
                "week": parts["week"],
                "day": parts["day"],
                "jie": parts["jie"],
                "jie_start": jie_start,
                "jie_end": jie_end,
                "tracks": {},
                "subtitle_url": None,
                "subtitle_urls": [],
            },
        )
        item["tracks"][parts["track"]] = {
            "url": "/media/" + rel,
            "filename": file_path.name,
            "size": file_path.stat().st_size,
        }

    course_list = []
    for course_key, course in courses.items():
        items = list(course["items"].values())
        _assign_subtitles(items, subtitle_index.get(course_key, []))
        items.sort(key=lambda item: (int(item["month"]), int(item["date"]), int(item["jie_start"])))
        course_list.append({"id": course["id"], "title": course["title"], "items": items})
    course_list.sort(key=lambda item: item["title"])
    return {"courses": course_list}


__all__ = ["index_local_library"]
