"""Structured state for the WebUI's serial download queue."""

import logging
import threading
import uuid
from dataclasses import asdict
from typing import Dict, Optional

from ..core import download_course, get_auth_cookies
from ..core.models import CourseDownloadOptions, DownloadStopped
from ..core.platform import FID


logger = logging.getLogger("xdu.webui.downloads")
TRACKS = {"both": ("pptVideo", "teacherTrack"), "ppt": ("pptVideo",), "teacher": ("teacherTrack",)}


def lesson_key(lesson):
    return tuple(lesson[name] for name in ("year", "month", "day", "week", "weekday", "period"))


class DownloadJob:
    def __init__(self, options: CourseDownloadOptions, name: str) -> None:
        self.id = uuid.uuid4().hex
        self.options = options
        self.name = name or f"LiveID {options.live_id}"
        self.code = ""
        self.status = "pending"
        self.phase = ""
        self.errors = []
        self.lessons = {}
        self.merges = []
        self.speed = 0
        self.condition = threading.Condition()
        self.thread: Optional[threading.Thread] = None


    def control(self, action):
        with self.condition:
            if action == "pause" and self.status == "running":
                self.status = "paused"
                self.speed = 0
            elif action == "resume" and self.status == "paused":
                self.status = "running"
            elif action == "stop" and self.status == "pending":
                self.status = "stopped"
            elif action == "stop" and self.status in {"running", "paused"}:
                self.status = "stopping"
                self.speed = 0
            else:
                return
            self.condition.notify_all()

    def checkpoint(self):
        with self.condition:
            self.condition.wait_for(lambda: self.status != "paused")
            if self.status in {"stopping", "stopped"}:
                raise DownloadStopped()

    def observe(self, kind, **event):
        with self.condition:
            if kind == "course":
                self.name, self.code = event["name"], event["code"]
                self.phase = "获取视频链接"
            elif kind == "plan":
                for lesson in event["lessons"]:
                    self.lessons.setdefault(lesson_key(lesson), {**lesson, "tracks": {}})
            elif kind == "error":
                self.errors.append(event)
            else:
                lesson, track = event["lesson"], event["track"]
                key = lesson_key(lesson)
                if kind == "track":
                    item = self.lessons.setdefault(key, {**lesson, "tracks": {}})
                    item["tracks"][track] = {k: v for k, v in event.items() if k not in ("lesson", "track")}
                    if track != "subtitle":
                        self.speed = event.get("speed", 0) if self.status == "running" else 0
                        self.phase = "下载中"
                    if event["status"] == "failed":
                        self.errors.append(event)
                elif kind == "merging":
                    self.phase = "合并中"
                    self.speed = 0
                elif kind == "merged":
                    identity = (key[:-1], track, event["start"], event["end"])
                    if not event.get("existing") or not any(key == identity for key, _ in self.merges):
                        self.merges.append((identity, event))
                    self.phase = "下载中"
                elif kind == "merge_failed":
                    self.errors.append(event)
                    self.phase = "下载中"

    def begin(self):
        with self.condition:
            self.status = "running"
            self.phase = "读取课程"

    def run(self):
        try:
            auth_cookies = get_auth_cookies(fid=FID, interactive=False)
            self.checkpoint()
            success = download_course(
                self.options, auth_cookies=auth_cookies, observer=self.observe, checkpoint=self.checkpoint,
            )
        except DownloadStopped:
            success = False
        except Exception:
            with self.condition:
                if self.status != "stopping":
                    self.errors.append({"message": "启动下载失败，请检查登录状态和网络连接"})
            logger.exception("Download failed for LiveID %s", self.options.live_id)
            success = False
        with self.condition:
            if self.status == "stopping":
                self.status = "stopped"
            else:
                if not success and not self.errors:
                    self.errors.append({"message": "下载任务未能完成"})
                self.status = "success" if success and not self.errors else "failed"
            self.phase = ""
            self.speed = 0

    def snapshot(self):
        with self.condition:
            return dict(
                id=self.id, name=self.name, code=self.code, status=self.status, phase=self.phase,
                options=asdict(self.options), tracks=TRACKS[self.options.video_type], speed=self.speed,
                lessons=[{**item, "tracks": dict(item["tracks"])} for _, item in sorted(self.lessons.items())],
                errors=list(self.errors), merges=[event for _, event in self.merges],
            )


class DownloadJobManager:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._paused = False
        self._jobs: Dict[str, DownloadJob] = {}
        self._worker: Optional[threading.Thread] = None

    def enqueue(self, requests):
        with self._condition:
            new_jobs = [DownloadJob(options, name) for options, name in requests]
            self._jobs.update((job.id, job) for job in new_jobs)
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name="webui-downloads", daemon=True)
                self._worker.start()
            for job in new_jobs:
                job.thread = self._worker
            return [job.id for job in new_jobs]


    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: not self._paused)
                job = next((item for item in self._jobs.values() if item.status == "pending"), None)
                if job is None:
                    self._worker = None
                    return
                job.begin()
            job.run()

    def control(self, action):
        with self._condition:
            active = [job for job in self._jobs.values() if job.status in {"running", "paused"}]
            if action == "pause":
                self._paused = True
                for job in active:
                    job.control("pause")
            elif action == "resume":
                self._paused = False
                for job in active:
                    job.control("resume")
            elif action == "stop":
                self._paused = False
                for job in self._jobs.values():
                    job.control("stop")
            else:
                raise ValueError("无效的下载操作")
            self._condition.notify_all()

    def queue_state(self):
        with self._condition:
            return self._paused, [job.snapshot() for job in self._jobs.values()]

    def get(self, job_id):
        with self._condition:
            return self._jobs.get(job_id)

    def clear_completed(self):
        with self._condition:
            self._jobs = {key: job for key, job in self._jobs.items() if job.status not in {"success", "stopped"}}


jobs = DownloadJobManager()
