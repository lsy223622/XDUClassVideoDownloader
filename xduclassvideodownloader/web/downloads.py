"""Background download jobs used by the WebUI."""

import io
import logging
import sys
import threading
import time
import uuid
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Tuple

from ..core import download_course, download_courses
from ..core.config import AUTOMATION_CONFIG_FILE, safe_read_config
from ..core.models import CourseDownloadOptions
from ..core.utils import setup_logging


logger = setup_logging("webui")
DOWNLOAD_ACTIVE_STATUSES = {"pending", "running"}


class QueueWriter(io.TextIOBase):
    def __init__(self, emit: Callable[[str], None]) -> None:
        self.emit = emit

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        if not value:
            return 0
        self.emit(str(value))
        return len(value)

    def flush(self) -> None:
        return None


class WritableTextStream(Protocol):
    def write(self, text: str, /) -> int:
        ...

    def flush(self) -> None:
        ...


class ThreadBoundStream(io.TextIOBase):
    def __init__(self, target_thread_id: int, target: WritableTextStream, fallback: WritableTextStream) -> None:
        self.target_thread_id = target_thread_id
        self.target = target
        self.fallback = fallback

    def _stream(self) -> WritableTextStream:
        return self.target if threading.get_ident() == self.target_thread_id else self.fallback

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        return self._stream().write(value)

    def flush(self) -> None:
        self._stream().flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.fallback, name)


class QueueLogHandler(logging.Handler):
    def __init__(self, emit: Callable[[str], None]) -> None:
        super().__init__(logging.ERROR)
        self.emit_output = emit
        self.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.emit_output(self.format(record) + "\n")
        except Exception:
            pass


class DownloadJob:
    def __init__(self, target: Any, args: Tuple[Any, ...]) -> None:
        self.id = uuid.uuid4().hex
        self.target = target
        self.args = args
        self.history: List[str] = []
        self.condition = threading.Condition()
        self.status = "pending"
        self.success: Optional[bool] = None
        self.error: Optional[str] = None
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.thread = threading.Thread(target=self._run, name=f"webui-download-{self.id}", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def emit_output(self, text: str) -> None:
        with self.condition:
            self.history.append(text)
            if len(self.history) > 5000:
                self.history = self.history[-5000:]
            self.condition.notify_all()

    def finish(self) -> None:
        with self.condition:
            self.condition.notify_all()

    def _run(self) -> None:
        self.status = "running"
        self.started_at = time.time()
        writer = QueueWriter(self.emit_output)
        handler = QueueLogHandler(self.emit_output)
        root = logging.getLogger("xdu")
        root.addHandler(handler)
        stdout_proxy = ThreadBoundStream(threading.get_ident(), writer, sys.stdout)
        stderr_proxy = ThreadBoundStream(threading.get_ident(), writer, sys.stderr)
        original_stdout, original_stderr = sys.stdout, sys.stderr
        try:
            sys.stdout = stdout_proxy
            sys.stderr = stderr_proxy
            self.success = bool(self.target(*self.args))
            self.status = "success" if self.success else "failed"
        except Exception as exc:
            self.success = False
            self.error = str(exc)
            self.status = "failed"
            self.emit_output(f"ERROR: {exc}\n")
            logger.exception("WebUI download job failed")
        finally:
            if sys.stdout is stdout_proxy:
                sys.stdout = original_stdout
            if sys.stderr is stderr_proxy:
                sys.stderr = original_stderr
            writer.flush()
            root.removeHandler(handler)
            self.finished_at = time.time()
            self.finish()


class DownloadJobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, DownloadJob] = {}
        self._active_job_id: Optional[str] = None

    def start(self, target: Any, args: Tuple[Any, ...]) -> DownloadJob:
        with self._lock:
            if self._active_job_id:
                active = self._jobs.get(self._active_job_id)
                if active and active.status in DOWNLOAD_ACTIVE_STATUSES:
                    raise RuntimeError("已有下载任务正在运行")
                self._active_job_id = None
            job = DownloadJob(target, args)
            self._jobs[job.id] = job
            self._active_job_id = job.id
            job.start()
            return job

    def get(self, job_id: str) -> Optional[DownloadJob]:
        return self._jobs.get(job_id)

    def active(self) -> Optional[DownloadJob]:
        with self._lock:
            if not self._active_job_id:
                return None
            job = self._jobs.get(self._active_job_id)
            if job and job.status in DOWNLOAD_ACTIVE_STATUSES:
                return job
            return None


def run_single_download(
    live_id: str, single: int, merge: bool, video_type: str, skip_weeks_text: str
) -> bool:
    return download_course(
        CourseDownloadOptions(
            live_id=live_id,
            single=single,
            merge=merge,
            video_type=video_type,
            skip_weeks=skip_weeks_text,
        )
    )


def run_batch_download(selected_sections: Iterable[str], video_type: str) -> bool:
    config = safe_read_config(AUTOMATION_CONFIG_FILE)
    selected = {str(section) for section in selected_sections}
    return download_courses(config, selected_sections=selected, video_type=video_type)


jobs = DownloadJobManager()


__all__ = [
    "DOWNLOAD_ACTIVE_STATUSES",
    "DownloadJob",
    "DownloadJobManager",
    "jobs",
    "run_batch_download",
    "run_single_download",
]
