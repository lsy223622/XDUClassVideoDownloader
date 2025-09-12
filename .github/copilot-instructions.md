# XDUClassVideoDownloader

面向西电录直播平台的课程视频下载与批量自动化工具，支持单课程与按学期批量下载。本文是为本仓库配套的开发与测试指南，请以此为唯一权威信息；若运行时行为与此不符，再回退到搜索或临时命令行探查。

## 你将完成的事
- 更新后的说明完全匹配最新代码实现（不再依赖 vsd-upx，改为内置 MP4 下载与 FFmpeg 合并）。
- 给出快速环境准备与常用运行方式（Windows 优先）。
- 明确认证方式与网络依赖、日志与输出产物位置、典型失败与期望表现。
- 规定开发/测试用例命名规范：一律使用 test_*.py（与 .gitignore 约定保持一致）。

---

## 环境准备（Windows 优先）
- Python: 3.8+（已在 3.11/3.12 上使用）
- 依赖安装（约 30-60 秒）：
  ```powershell
  python -m pip install --upgrade pip
  python -m pip install requests tqdm psutil
  # 可选（本地单测）
  # python -m pip install pytest
  ```
- FFmpeg：用于合并相邻节次 MP4（downloader.py 自动调用）。Windows 根目录已提供 `ffmpeg.exe`；若系统 PATH 不可用，请在项目根目录运行或自行配置 PATH。若缺失，可从官网获取或用包管理器安装。

提示：本项目不再依赖 vsd-upx 或 m3u8 下载器，统一走“直下 MP4 + 可选合并”的实现。

## 核心脚本与职责
- XDUClassVideoDownloader.py：单课程下载（交互式或命令行）。
- Automation.py：学期级批量发现课程并下载；会创建/更新 `automation_config.ini`。
- api.py：访问学校接口、解析视频信息、版本检查。
- downloader.py：MP4 断点续传下载、完整性校验、可选 FFmpeg 合并、统计汇总。
- utils.py：日志、输入校验、配置读写、安全文件名、认证 cookies 管理等。

两者启动时会尝试检查更新（api.lsy223622.com）。网络环境受限导致失败是正常的，不影响主流程。

## 运行方式与示例

### 基本帮助（建议先跑）
- 帮助通常在 5-10 秒内完成（包含一次版本检查）。
  ```powershell
  python XDUClassVideoDownloader.py --help
  python Automation.py --help
  ```

### 单课程下载：XDUClassVideoDownloader.py
- 交互式：
  ```powershell
  python XDUClassVideoDownloader.py
  ```
  交互项包括：liveId、下载模式（全部/单节课/半节课）、是否合并、视频类型（both/ppt/teacher）、跳过周数。

- 命令行：
  ```powershell
  # liveId 可选；-s 为单节课，-ss 为半节课；--no-merge 关闭自动合并
  python XDUClassVideoDownloader.py [LIVEID] [-s] [--no-merge] --video-type {both,ppt,teacher}
  ```
  示例：
  ```powershell
  python XDUClassVideoDownloader.py 1234567890 -s --video-type ppt
  python XDUClassVideoDownloader.py 1234567890 --no-merge --video-type both
  ```

输出与产物：
- 保存目录：`{YEAR}年{COURSE_CODE}{COURSE_NAME}`（例如：`2024年CS101计算机导论`）。
- 文件：
  - MP4：`...第{周}周星期{X}第{节}节-pptVideo.mp4` 与 `-teacherTrack.mp4`
  - 自动合并产物：`...第{A}-{B}节-pptVideo.mp4` / `-teacherTrack.mp4`
  - CSV：保存到 `logs/` 目录，文件名为 `{保存目录}.csv`，列包含：month,date,day,jie,days,pptVideo,teacherTrack

提示：脚本仅下载已结束的课程场次；支持断点续传与完整性校验，失败会自动重试有限次数。

### 批量下载：Automation.py
- 命令行：
  ```powershell
  python Automation.py [-u UID] [-y YEAR] [-t {1,2}] [--video-type {both,ppt,teacher}]
  ```
  示例：
  ```powershell
  python Automation.py -u 123456789 -y 2024 -t 1 --video-type both
  ```

- 首次运行会创建 `automation_config.ini`，格式示例：
  ```ini
  [DEFAULT]
  user_id = 123456789
  term_year = 2024
  term_id = 1
  video_type = both

  [course_id]
  course_code = CS101
  course_name = 计算机导论
  live_id = 1234567890
  download = yes
  ```
- 之后运行会扫描课程并“增量更新”该文件（新增课程或信息变化会写入）。
- ALWAYS：每次首跑后请确认 `automation_config.ini` 已生成；如需重置，删除该文件再执行。

## 认证与安全
- 脚本首次需要访问课程数据时，会引导创建 `auth.ini` 并写入所需 cookies：`_d`, `UID`, `vc3`（从已登录超星网站浏览器中拷贝）。
- 程序通过 `utils.get_auth_cookies()` 加载并注入到请求头；仅用于访问 `chaoxing` 相关接口。
- 切勿泄露个人 `auth.ini` 内容；不要在公开场合粘贴日志中的敏感字段。

## 网络依赖与期望行为
- 版本检查：`https://api.lsy223622.com/xcvd.php?version=...`（可能失败，属正常）。
- 课程/视频数据：
  - `http://newes.chaoxing.com/xidianpj/live/listSignleCourse`
  - `http://newes.chaoxing.com/xidianpj/frontLive/playVideo2Keda`
  - `https://newesxidian.chaoxing.com/frontLive/listStudentCourseLivePage`
- 不在校/无内网或认证过期时，可能出现网络错误、空数据、403/404，程序会尽量给出友好提示并不中断其他流程。

## 合并与 FFmpeg
- 合并策略：当同一天相邻节次（如第3节与第4节）均存在且单文件有效时，调用 FFmpeg “无损拼接”（-c copy）。
- 失败兜底：
  - 未安装或调用失败时，合并将被跳过，不影响已下载单文件。
  - 合并成功后，会清理参与合并的源文件。

## 日志与文件布局
- 日志目录：`logs/`（含 `main_downloader.log`, `automation.log`, `xdu_downloader.log` 等）。
- 临时/备份：写配置会在 `logs/` 生成时间戳备份；下载时用 `.tmp`/`.part*` 临时文件并自动清理。
- Windows 批处理：`windows_run.bat`（单课）、`automation.bat`（自动化）。

## 手动验证场景（建议）
- 基础：
  - `--help` 两个脚本都能在 10 秒内返回说明。
  - 在无有效网络/认证的环境下，用假参数运行，应该得到明确的错误提示而非崩溃。
- 自动化：
  - 首次运行后确认生成 `automation_config.ini`。
  - 二次运行如有新课程应提示“发现新课程/更新课程”，并写回配置。
- 下载：
  - 有效 liveId 下，能看到保存目录、CSV、MP4 文件；启用合并时出现 `第A-B节-*.mp4`。

## 开发与测试最佳实践
- 测试命名约定：一律使用 `test_*.py`。建议放到 `tests/` 目录（可自建），与仓库 `.gitignore` 约定保持一致，避免临时测试文件被提交。
- 单测建议：
  - 避免真实网络：对 `api` 层做最小桩/模拟，或仅做参数/错误分支测试。
  - 非交互：调用带参数的入口（避免 `input()`）。
  - 快速失败：小范围、短超时；不要长时间下载真实视频。
- 运行（可选）：
  ```powershell
  # 若使用 pytest
  # python -m pytest -q
  # 直接执行某个轻量测试
  # python tests/test_downloader_smoke.py
  ```

## 已知限制
- 需要个人在超星平台的登录 cookies（`auth.ini`）。
- 学校平台接口可能受网络/权限限制；校外或非学期内数据会为空或报错。
- 版本检查受 DNS/网络影响，失败不影响主功能。

## 资料速览（当前仓库结构）
```
.
├── XDUClassVideoDownloader.py        # 单课程下载（交互或命令行）
├── Automation.py                     # 按学期批量扫描与下载
├── api.py                            # 服务端交互、视频信息解析、更新检查
├── downloader.py                     # MP4 下载、合并、统计、课程处理
├── utils.py                          # 日志/配置/认证/工具函数
├── config.py                         # 配置文件管理、认证、课程配置
├── validator.py                      # 输入验证、参数检查、错误处理
├── auth.ini                          # 认证（本地生成/维护，勿泄露）
├── automation_config.ini             # 自动化配置（运行时生成/更新）
├── ffmpeg.exe                        # Windows 平台 FFmpeg 可执行文件
├── logs/                             # 日志与配置备份
├── merge/                            # 备用合并脚本与说明（如有）
├── *.bat                             # Windows 批处理辅助
└── __pycache__/ / build/             # 运行/构建产物
```

## 故障排查速表
- 版本检查卡住/失败：直接忽略或断网重试，不影响核心功能。
- 下载 403/404：多为认证过期或链接失效；更新 `auth.ini` 后重试。
- 合并失败：确认 `ffmpeg.exe` 存在并可执行；或手动将其加入 PATH。
- 目录/文件名异常：课程名可能含非法字符，`utils.remove_invalid_chars` 会做清洗；如仍异常，检查磁盘权限与路径长度。

—— 以上内容已根据最新代码实现全面同步，供本仓库与 Copilot 代理在开发/测试时遵循。