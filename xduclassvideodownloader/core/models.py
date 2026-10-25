"""Small data models shared by Core frontends."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CourseDownloadOptions:
    live_id: str
    single: int = 0
    merge: bool = True
    video_type: str = "both"
    skip_weeks: str = ""
