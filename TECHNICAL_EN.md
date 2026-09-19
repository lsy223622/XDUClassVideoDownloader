# XDUClassVideoDownloader Technical Documentation

[中文版](TECHNICAL.md) | [Usage guide](README.md) | [Authentication guide](AUTHENTICATION.md) | [WebUI guide](WEBUI.md) | [Logging guide](LOGGING.md)

## Scope of This Document

This document is for developers who need to read, maintain, or extend the project. It explains the current structure, runtime boundaries, and implementation approach. It describes the code state associated with `VERSION = "5.0.0"` in `api.py`; the recording-platform APIs and response fields are maintained by external platforms, so actual responses and the adaptation code in `api.py` are authoritative when they change.

This document does not replace the user-facing manuals. For startup methods, command-line options, and UI operation, read `README.md` and `WEBUI.md` first. For obtaining authentication credentials, read `AUTHENTICATION.md`.

## Project Purpose and Overall Architecture

XDUClassVideoDownloader is a locally run downloader for course recordings and live replays. It works around a course `liveId`: after using a valid Chaoxing session to retrieve course records and video information, it downloads the courseware view `pptVideo`, the instructor view `teacherTrack`, and available subtitles. The project exposes three entry points, but it does not maintain three download implementations: the CLI, batch automation, and WebUI all ultimately use the same `api.py`, `config.py`, `downloader.py`, and `utils.py` modules.

```text
User input / browser request
        │
        ├─ XDUClassVideoDownloader.py ─┐
        ├─ Automation.py ──────────────┼─ Configuration and authentication: config.py
        └─ WebUI.py ───────────────────┘              │
                                                       ▼
                                     Platform access and parsing: api.py
                                                       │
                                                       ▼
                             Download, subtitles, merging, and storage: downloader.py
                                                       │
                                                       ▼
                    Course directories, logs/, CSV files, INI files, and local media library
```

The important consequence of this layering is that entry points collect parameters and present results, while the shared modules perform business processing. When adding an entry point or changing the WebUI, reuse the existing common functions instead of copying authentication, course-scanning, or download logic.

## Project Structure

The following structure omits virtual environments, PyInstaller output, and runtime-generated files. Those files are normally ignored through `.gitignore`.

```text
.
├─ XDUClassVideoDownloader.py  Single-course CLI entry point
├─ Automation.py               Batch-automation CLI entry point
├─ WebUI.py                    Local Flask service and WebUI API
├─ api.py                      Platform APIs, login, scanning, and update checks
├─ config.py                   INI I/O, authentication, and batch-course configuration
├─ downloader.py               Video/subtitle downloads, integrity checks, and FFmpeg merging
├─ utils.py                    Path, logging, input, exception, and resource helpers
├─ validator.py                Parameter, URL, file, and business-data validation
├─ webui/
│  └─ static/
│     ├─ index.html            Single-page UI structure
│     ├─ app.js                Vanilla-JavaScript state, requests, and player controls
│     └─ styles.css            Responsive styles and dark-mode adaptation
├─ merge/
│  ├─ merge.py                Standalone two-view video-merging helper
│  └─ mergeUsage.md           Separate documentation for that helper
├─ README.md                   Main usage guide and option index
├─ AUTHENTICATION.md           Authentication information guide
├─ WEBUI.md                    WebUI page-operation guide
├─ LOGGING.md                  Log-level and log-file guide
├─ requirements.txt            Python dependency list
├─ *.bat                       Windows source-build launch helpers
└─ *.spec                      Local PyInstaller build specifications, when present
```

| File or directory | Responsibility | Main relationships |
| --- | --- | --- |
| `XDUClassVideoDownloader.py` | Validates command-line or interactive input and starts a single-course download. | Calls `config.get_auth_cookies()` and `downloader.download_course_videos()`. |
| `Automation.py` | Determines the default term, creates or updates course-selection configuration, then processes enabled courses in sequence. | Uses the configuration workflow in `config` and `downloader.process_all_courses()`. |
| `WebUI.py` | Provides the local HTTP service, download-job management, QR jobs, configuration APIs, and media serving. | Reuses the CLI entry point and batch downloader rather than reimplementing downloading. |
| `api.py` | Centralizes HTTP sessions, login, course/video/subtitle requests, old/new API compatibility, and update checks. | Depends on `requests`, parsing libraries, and cookies supplied by `config`. |
| `config.py` | Manages `auth.ini` and `automation_config.ini` and retains an in-process authentication cache. | Calls login or course-scanning capabilities from `api.py`. |
| `downloader.py` | Performs MP4, M3U8/TS, subtitle, CSV, merging, and download-statistics work. | Uses links from `api.py`, authentication from `config.py`, FFmpeg, and validation helpers. |
| `utils.py` / `validator.py` | Provide project-wide foundational behavior and input boundaries. | Used by every business layer to avoid inconsistent validation and logging. |
| `webui/static/` | Static single-page UI with no frontend build tool. | Calls JSON APIs through `fetch` and receives download output through `EventSource`. |

## The Three Runtime Entry Points

### Single-course CLI entry point

`XDUClassVideoDownloader.py` targets one course `liveId`. Without a positional argument, it asks for download scope, merging, video type, and skipped weeks. With arguments, `argparse` parses the same choices and passes them through the shared checks in `validator.py`.

The entry point checks for updates first and then initializes authentication. Once authentication succeeds, it calls `download_course_videos()`. The internal download-mode values are `0` for all completed course segments, `1` for the lesson on the target date, and `2` for one half-lesson segment. `--skip-weeks` is parsed into a set of week numbers; files are not downloaded and then deleted afterwards.

### Batch-automation entry point

`Automation.py` maintains a course set by term. Its default academic year and term are derived from local time: September through the following February map to the first term, March through August to the second term, and the academic year is decremented for January through August. On first use, the program scans courses and creates `automation_config.ini`; on later runs, it scans again and updates newly discovered or changed course information while retaining existing `download` selections.

Batch downloading itself iterates through enabled courses sequentially rather than allowing multiple courses to compete for network and disk resources at once. Within each course, link resolution and conditional chunk downloads remain concurrent.

### Local WebUI entry point

`WebUI.py` starts a local Flask service, listening on `127.0.0.1:5050` by default. If the starting port is occupied, it searches following ports for an available one. Startup options can also override the bind address, starting port, and automatic browser opening. Static pages are served directly from `webui/static/`; there is no Node.js, bundler, or extra frontend runtime.

The WebUI passes single-course requests to `XDUClassVideoDownloader.main()` and batch requests to `process_all_courses()`. This keeps CLI and browser behavior consistent for authentication, filenames, download strategy, and output directories.

## Core Download Pipeline

### 1. Authentication and HTTP sessions

All platform requests that require permission obtain Cookie headers through `get_authenticated_headers()`. `api.create_session()` configures a `requests.Session` with a consistent User-Agent, timeouts, and retry behavior; common transient status codes receive limited retries. The `rate_limit` decorator also inserts short randomized intervals between platform API calls to avoid excessively dense access.

The in-process authentication cache resides in `config.py`. Once complete authentication information has been obtained, later requests in the same process reuse it. Login or interactive input is requested again only when no usable cache exists, configuration is incomplete, or a refresh is explicitly requested.

### 2. Course discovery and API compatibility

A single-course download first retrieves course records by `liveId`. The program retains only completed course segments, sorts them by month, date, weekday, lesson number, and week number, and then filters them according to the selected mode and skipped weeks.

The project keeps handling paths for both new and old course APIs. When course records indicate an academic year no later than 2024, it attempts the older course API and processes the course through the legacy M3U8/TS path; other courses use the MP4-link flow. This decision is centralized in `api.py` and `downloader.py`, so entry points do not need to understand platform-format differences.

For MP4 courses, the program reads video information from the playback page, URL-decodes and JSON-parses it, and extracts `pptVideo` and `teacherTrack` links. For known pages such as replay generation in progress, login required, or access denied, the code raises explicit exceptions or shows clear messages instead of treating an error page as video metadata.

Batch course scanning takes a user ID, academic year, and term. It retrieves course data week by week, scans at most 20 weeks, and stops after two consecutive empty weeks. Only the first occurrence of each course is retained as a configuration source.

### 3. Concurrent link resolution and download strategy

Before files are downloaded, `download_course_videos()` resolves playback links for completed segments concurrently through a thread pool. The worker count is calculated by `utils.calculate_optimal_threads()` from CPU usage, memory usage, and processor count, and is constrained to the range from 1 through 32.

The MP4 downloader works as follows:

1. It sends a `HEAD` request to determine file length and `Range` support.
2. For a Range-capable file of at least 10 MiB, it concurrently downloads roughly 10 MiB chunks, using at most 32 chunk threads per file. If any chunk ultimately fails, it removes chunks and falls back to a single-thread download.
3. Other files use single-thread streaming. When a valid unfinished `.tmp` file exists, the downloader resumes from the existing position through Range.
4. After download, it validates the temporary file and then moves/renames it into the final file. If the final retry fails, it removes unfinished temporary files.

The legacy M3U8 downloader parses TS segments from the playlist, retrieves them concurrently, and writes them in original-index order to a temporary file. A single M3U8 file uses at most eight segment-download workers; if more than 20% of segments are missing, that attempt is considered failed.

### 4. Integrity, naming, CSV, and incremental behavior

Every output file is given a basic integrity check before reuse, merging, or final placement. The file must exceed a minimum size; when content length is known, its size is compared; MP4 files are checked for an `ftyp` header marker and TS files for the `0x47` sync byte. This is lightweight transfer-integrity validation, not a full media-decoding validation.

Course directories are named from the year, course code, and sanitized course name. Video filenames retain date, week, weekday, lesson number, and track type. Course names are cleaned of filesystem-invalid characters, control characters, reserved names, and excessive length. This stable naming supports both incremental “existing file means skip” behavior and WebUI local-library indexing.

Each set of successfully resolved rows is written to a corresponding CSV under `logs/`, including date fields, both video links, and the `liveId`. CSV is runtime metadata and a troubleshooting aid, not the only source of resume state; the downloader decides from the existence and validation of local target files.

### 5. Subtitles and video merging

For each course segment, the downloader attempts to obtain the identifier required for subtitles from the playback page and then requests VTT subtitles. Valid VTT is converted to SRT and stored with the corresponding video in the course directory. No subtitle, absent platform subtitles, or a subtitle-request failure does not fail the video download task.

When automatic merging is enabled and mergeable adjacent segments exist, the project uses local FFmpeg concat stream copying to merge video from the same track without re-encoding. Input files are validated before merging and output is validated afterwards; original segments are deleted only after success. Subtitle merging offsets later subtitle timelines by earlier media duration so that the merged subtitle remains continuous. Media duration is parsed from FFmpeg output, so packaged builds do not depend on an additional `ffprobe` binary.

FFmpeg lookup first checks compact or regular executables in the application directory and then the system `PATH`. Therefore, source runs need an available FFmpeg when downloading old courses or using merging, while packaged releases carry the required component.

## Authentication and Configuration Management

### Authentication methods and configuration semantics

The authentication layer supports four methods: Xidian unified-identity login (`ids`), Chaoxing account/password login (`chaoxing`), Xuexi Xidian App QR login (`chaoxing_qr`), and manual Cookie input (`cookies`). All methods ultimately need the three Cookie values `_d`, `UID`, and `vc3`, which are used for download and scanning requests.

`auth.ini` is maintained by the program. Its typical logical structure is shown below. The example shows field shape only; real credentials must never be inserted into documentation or committed.

```ini
[SETTINGS]
auth_method = ids
save_auth_info = True

[IDS_CREDENTIALS]
username = <student-id>
password = <password>

[AUTH]
_d = <cookie-value>
UID = <cookie-value>
vc3 = <cookie-value>

[WEBUI]
bind_host = 127.0.0.1
allowed_clients =
password_hash = <optional-password-hash>
```

One configuration file does not need every authentication section at the same time. Unified identity or Chaoxing account/password stores the corresponding account section; QR or manual Cookie authentication stores `[AUTH]`. For compatibility with old files, reading authentication configuration migrates the older `password` method and `[CREDENTIALS]` section to the current Chaoxing account/password layout.

### Batch-course configuration

`automation_config.ini` keeps term defaults and course selection in one INI file:

```ini
[DEFAULT]
user_id = <uid>
term_year = <academic-year>
term_id = 1
video_type = both

[<course-id>]
course_code = <course-code>
course_name = <sanitized-course-name>
live_id = <live-id>
download = yes
```

`term_id` is `1` or `2`; `video_type` is `both`, `ppt`, or `teacher`; and each course section's `download` controls whether it joins a batch task. CLI updates preserve existing `download` choices. In contrast, a WebUI “select temporarily and download” action runs from an in-memory configuration copy; it writes the selection back only when the user explicitly saves it.

### Safe writes and sensitive data

All configuration writes go through `safe_write_config()`: it first creates a UTF-8 temporary file in the same directory and then moves it to the target, minimizing the chance of a partially written configuration. When sensitive WebUI settings are overwritten, the previous configuration is also backed up under `logs/`. On POSIX systems, the authentication file is additionally restricted to the current user where possible. On Windows, account permissions still need to protect the file.

`auth.ini`, `automation_config.ini`, and common generated log and CSV files are ignored in `.gitignore`, but that does not make them safe to share. In particular, `auth.ini` can contain account passwords or valid Cookies. Before committing code, packaging logs, or requesting support, inspect and redact those files.

## WebUI Implementation

### Frontend-backend communication model

The WebUI is a local single-page application served by Flask through static files and JSON APIs. `index.html` provides the download, viewer, and settings page skeletons; `app.js` manages state and events with native DOM APIs; and `styles.css` handles layout, responsiveness, and theme adaptation. No framework, Node.js, or build step is introduced.

Normal data interaction uses JSON. The backend requires write operations to use an `application/json` body and returns `{ "ok": true/false, ... }`. Download logs use Server-Sent Events (SSE): the frontend connects to a job stream through `EventSource`; after a page refresh it also queries the active job and reconnects to its output stream.

| API category | Representative paths | Purpose |
| --- | --- | --- |
| Application and access control | `/api/app/info`, `/api/webui/access/*` | Read version notices and query or submit the WebUI access password. |
| Batch configuration | `/api/automation/config`, `/api/automation/config/init`, `/api/automation/config/selection` | Read, scan, refresh, and save batch-course selection. |
| Download jobs | `/api/download/start`, `/api/download/active`, `/api/download/jobs/<id>/stream` | Create jobs, restore status, and continuously receive output. |
| Local media library | `/api/library`, `/media/<path>` | Index downloaded media and serve playable content from controlled paths. |
| Authentication and QR login | `/api/settings/auth`, `/api/settings/qr/*` | Read/write authentication settings and start, poll, or cancel QR jobs. |
| WebUI settings | `/api/settings/webui-password` | Query, set, or clear the page access password. |

### Download jobs and console-output bridging

The existing download core prints progress to standard output and writes errors to project logs. `DownloadJob` therefore runs the real download function in a background daemon thread and uses `QueueWriter` to collect that thread's standard output and standard error. `QueueLogHandler` also directs error-level log records into the same queue. `ThreadBoundStream` redirects only the job thread's output; other threads still write to the original console, avoiding accidental capture of Flask or other thread output when `sys.stdout` is replaced.

Each job retains its latest 5,000 output fragments and wakes the SSE generator through a condition variable. `DownloadJobManager` permits only one `pending` or `running` download job at a time. This prevents two jobs from simultaneously modifying the same course directory and prevents multiple jobs from competing for the same authentication state and terminal output.

### QR login, media library, and player

WebUI QR login runs as a separate background `QRLoginJob`: it creates a QR image file, periodically polls login status, extracts Cookies after success, and writes them to authentication configuration. The job can be cancelled, has a bounded waiting period, and reports failure or expiration state to the frontend.

The local media library scans only supported `.mp4`, `.ts`, `.srt`, and `.vtt` files under the application directory. The backend classifies courses, dates, lessons, and tracks using the downloader's standard filenames and matches subtitles to videos. The media route is likewise constrained to the application directory and allowed filename extensions. The frontend can create PPT and instructor HTML5 video elements together, coordinate play, pause, seeking, and speed with one shared progress bar, and handle subtitle offset, font size, and boldness in the page subtitle area.

### WebUI access boundaries

The default bind address is loopback, so only a local browser can access it. When `--host` or `[WEBUI] bind_host` opens it to a LAN, `allowed_clients` can define an IPv4/IPv6 single-address or CIDR allowlist. An empty allowlist does not add a client-IP restriction.

New WebUI access passwords are not stored in plaintext: the code uses PBKDF2-HMAC-SHA256 with a random salt and 120,000 iterations, and verifies it with constant-time comparison. The Flask session key is randomly generated on every start, so logged-in WebUI sessions do not survive a process restart. An older plaintext password field is read only for compatibility; writing a new password replaces it with the hash field.

This is still a local tool rather than a public web service. It uses HTTP and does not configure TLS, reverse-proxy trust, or public-deployment hardening. Opening the bind address to an uncontrolled network is outside the current design. For a genuine LAN requirement, use a strong access password, minimize `allowed_clients`, configure the system firewall, and do not expose it to the Internet through port mapping.

## Validation, Logging, and Error Handling

`validator.py` centralizes checks for `liveId`, user ID, term, download mode, video type, URLs, file integrity, and course/video data shape. Entry points, WebUI APIs, and core download functions all call these checks before entering costly operations, preventing invalid input from reaching platform requests, thread pools, or filename construction.

`utils.py` establishes an `xdu`-rooted logging system for all modules. The console displays `ERROR` and above by default; the aggregate file `logs/all.log` and module files record `INFO` and above. Passing `--debug` additionally enables `logs/debug.log`, including finer debugging information and network-request records. A console filter removes tracebacks so users see concise failures while file logs retain call locations and exception details needed for diagnosis.

Network timeouts, connection errors, HTTP statuses, data-format problems, and filesystem errors are converted to readable prompts through a common exception handler while detailed information is written to logs. For troubleshooting, retain the failure time, entry-point arguments without Cookies, and relevant snippets from `logs/<module>.log`.

## Dependencies, Packaging, and Runtime Paths

The dependencies in `requirements.txt` can be grouped by purpose:

| Dependency | Purpose |
| --- | --- |
| `requests` | Platform requests, connection pooling, and retry adaptation. |
| `beautifulsoup4` | Login-page and selected HTML-field parsing. |
| `pycryptodome`, `numpy`, `pillow` | Unified-identity and slider-captcha related processing. |
| `tqdm` | CLI progress for downloads and link resolution. |
| `psutil` | Calculate link-resolution concurrency from local load. |
| `flask` | Local WebUI service, JSON APIs, sessions, and static files. |

FFmpeg is an external binary rather than a Python dependency. It is used by the legacy video path and video/subtitle merging. In both source and PyInstaller runs, the project uses `get_app_path()` to locate the writable application directory and `get_bundled_app_path()` to prefer PyInstaller-extracted resources. Thus, after packaging as `.exe`, configuration, logs, and download folders remain beside the executable while static frontend assets can be read from PyInstaller's resource directory.

`XDUClassVideoDownloader.spec`, `Automation.spec`, and `WebUI.spec`, when present locally, describe PyInstaller packaging for the three entry points. WebUI packaging also carries `webui/static/`, while the three entry points carry the compact FFmpeg file. Build and distribution directories are generated artifacts and should not be edited as business source.

## Maintenance and Extension Guidance

1. **Enter new download capability through the shared pipeline.** Extend data access in `api.py` and storage behavior in `downloader.py` first, then let all three entry points pass the necessary parameters. Do not implement an exceptional path only in WebUI or one CLI.
2. **Locate platform changes at the data boundary first.** Course lists, playback pages, `videoPath`, subtitles, and QR login are external boundaries. Add clear parsing, exceptions, and logging in `api.py` before considering UI presentation.
3. **Keep configuration backward compatible.** New fields need defaults; configuration updates should preserve course selections. For authentication-format changes, use the existing backup and migration pattern.
4. **Do not break the filename contract.** WebUI library indexing and subtitle matching depend on downloader-generated names. If naming must change, update the downloader, regex indexer, and documentation together, and consider existing-file compatibility.
5. **Keep WebUI jobs serialized.** A new long-running action that writes shared configuration, authentication, or course folders should enter the job manager and provide status/output, rather than running directly in a Flask request thread.
6. **Do not leak credentials in logs.** Debug logs contain substantial request context. New logging must not print account passwords, full Cookies, or reusable download authorization data.

## Current Boundaries and Known Constraints

- The project depends on current behavior of Xidian and Chaoxing platforms. Insufficient course permission, expired Cookies, replay generation in progress, changed API fields, or network restrictions can fail individual segments.
- Integrity checks are intended to reject clearly incomplete files; they cannot prove that every video is playable or that audio and video are perfectly correct.
- Automatic merging requires an available local FFmpeg and input media that can be concatenated through stream copying. When merging cannot proceed, original segments remain.
- The WebUI media library targets the application's generated filenames and directory. Manual renaming or moving files affects indexing and subtitle matching.

These boundaries help classify failures as local configuration, network transport, platform permission, media processing, or UI indexing problems, and help future changes preserve consistent behavior across all three entry points.
