# XDUClassVideoDownloader 项目技术文档

[English version](TECHNICAL_EN.md) | [使用说明](README.md) | [认证说明](AUTHENTICATION.md) | [WebUI 使用说明](WEBUI.md) | [日志说明](LOGGING.md)

## 文档范围

本文面向需要阅读、维护或扩展代码的开发者，说明当前项目的结构、运行边界和实现方式。它描述的是 `api.py` 中 `VERSION = "5.0.0"` 所对应的代码状态；录直播平台的接口和返回字段由外部平台维护，发生变化时应以实际响应和 `api.py` 中的适配逻辑为准。

本文不替代面向普通用户的使用手册：启动方式、命令行参数和界面操作请优先查看 `README.md` 与 `WEBUI.md`；认证凭证的获取步骤请查看 `AUTHENTICATION.md`。

## 项目定位与总体架构

XDUClassVideoDownloader 是一个在本机运行的课程录直播下载工具。它围绕课程的 `liveId` 工作：先使用有效的超星会话读取课程列表和视频信息，再分别下载课件视角 `pptVideo`、教师视角 `teacherTrack` 及可用字幕。项目提供三个入口，但不维护三套下载实现：命令行、批量自动化和 WebUI 最终都会进入同一组 `api.py`、`config.py`、`downloader.py` 与 `utils.py` 模块。

```text
用户输入 / 浏览器请求
        │
        ├─ XDUClassVideoDownloader.py ─┐
        ├─ Automation.py ──────────────┼─ 配置与认证：config.py
        └─ WebUI.py ───────────────────┘          │
                                                   ▼
                                   平台访问与数据解析：api.py
                                                   │
                                                   ▼
                              下载、字幕、合并与落盘：downloader.py
                                                   │
                                                   ▼
                         课程目录、logs/、CSV、INI 配置与本地媒体库
```

这个分层的要点是：入口负责收集参数和呈现结果，核心模块负责业务处理。因此新增入口或调整 WebUI 时，应优先复用既有公共函数，而不要复制认证、课程扫描或下载逻辑。

## 项目结构

下列结构省略了虚拟环境、PyInstaller 输出和运行期生成文件；这些文件通常由 `.gitignore` 忽略。

```text
.
├─ XDUClassVideoDownloader.py  单课程命令行入口
├─ Automation.py               批量自动化命令行入口
├─ WebUI.py                    本地 Flask 服务与 WebUI API
├─ api.py                      平台接口、登录、课程扫描、版本检查
├─ config.py                   INI 读写、认证与批量课程配置
├─ downloader.py               视频/字幕下载、完整性校验、FFmpeg 合并
├─ utils.py                    路径、日志、输入、异常和资源辅助函数
├─ validator.py                参数、URL、文件和业务数据校验
├─ webui/
│  └─ static/
│     ├─ index.html            单页界面结构
│     ├─ app.js                原生 JavaScript 状态、请求和播放器控制
│     └─ styles.css            响应式样式与深色模式适配
├─ merge/
│  ├─ merge.py                独立的双视角视频合并辅助脚本
│  └─ mergeUsage.md           该脚本的单独说明
├─ README.md                   总体使用说明和参数索引
├─ AUTHENTICATION.md           认证信息说明
├─ WEBUI.md                    WebUI 页面操作说明
├─ LOGGING.md                  日志级别与文件说明
├─ requirements.txt            Python 依赖清单
├─ *.bat                       Windows 源码版启动快捷脚本
└─ *.spec                      本地 PyInstaller 打包描述文件（如存在）
```

| 文件或目录 | 职责 | 主要依赖关系 |
| --- | --- | --- |
| `XDUClassVideoDownloader.py` | 校验命令行或交互输入，发起单课程下载。 | 调用 `config.get_auth_cookies()` 与 `downloader.download_course_videos()`。 |
| `Automation.py` | 计算默认学期、创建或更新课程选择配置，再顺序处理启用课程。 | 调用 `config` 的配置流程和 `downloader.process_all_courses()`。 |
| `WebUI.py` | 提供本地 HTTP 服务、下载任务管理、扫码任务、配置 API 与媒体服务。 | 复用 CLI 入口和批量下载函数，不重新实现下载器。 |
| `api.py` | 集中封装 HTTP 会话、认证登录、课程/视频/字幕请求、旧新接口兼容和更新检查。 | 依赖 `requests`、解析库和 `config` 提供的 Cookie。 |
| `config.py` | 管理 `auth.ini` 与 `automation_config.ini`，并保存运行期认证缓存。 | 调用 `api.py` 的登录或课程扫描能力。 |
| `downloader.py` | 执行 MP4、M3U8/TS、字幕、CSV、合并与下载统计。 | 使用 `api.py` 给出的链接、`config.py` 给出的认证、FFmpeg 和校验函数。 |
| `utils.py` / `validator.py` | 提供全项目统一的基础能力与输入边界。 | 被所有业务层调用，避免各入口出现不一致的校验和日志格式。 |
| `webui/static/` | 不依赖前端构建工具的静态单页界面。 | 通过 `fetch` 调用 JSON API，通过 `EventSource` 接收下载输出。 |

## 三个运行入口

### 单课程命令行入口

`XDUClassVideoDownloader.py` 面向一个课程 `liveId`。在无位置参数时，它依次询问下载范围、是否合并、视频类型和跳过周数；在带参数时，`argparse` 解析相同的选择并交由 `validator.py` 统一校验。

入口会先进行版本检查，再初始化认证；认证成功后调用 `download_course_videos()`。下载模式的内部值为：`0` 表示课程全部已结束片段，`1` 表示目标日期的单节课，`2` 表示单个半节片段。`--skip-weeks` 会被解析为周数集合，而不是在下载结束后删除文件。

### 自动化批量入口

`Automation.py` 用于按学期维护课程集合。默认学年和学期按本地日期推导：9 月至次年 2 月对应第一学期，3 月至 8 月对应第二学期，1 月至 8 月的学年会回退一年。首次运行时，程序扫描课程并生成 `automation_config.ini`；后续运行会再次扫描，将新发现或信息变化的课程更新到配置中，同时保留已有课程的 `download` 选择。

批量下载本身是顺序遍历已启用课程，而不是同时让多门课程彼此竞争网络和磁盘资源。每门课程内部仍会并发解析视频链接和按条件分片下载。

### 本地 WebUI 入口

`WebUI.py` 启动 Flask 本地服务，默认监听 `127.0.0.1:5050`。如果起始端口已被占用，会在后续端口中寻找可用端口；启动参数也允许覆盖监听地址、起始端口和自动打开浏览器的行为。静态页面由 `webui/static/` 直接提供，不使用 Node.js、打包器或额外的前端运行时。

WebUI 将单课程请求转发给 `XDUClassVideoDownloader.main()`，将批量请求转发给 `process_all_courses()`。这保证了 CLI 与网页在认证、文件名、下载策略和输出目录上的行为一致。

## 核心下载链路

### 1. 认证和 HTTP 会话

所有需要平台权限的请求都通过 `get_authenticated_headers()` 取得 Cookie 请求头。`api.create_session()` 为 `requests.Session` 配置统一的 User-Agent、超时和重试策略；对常见临时状态码会进行有限重试。`rate_limit` 装饰器还会在平台 API 请求之间加入随机的短间隔，避免短时间内过于密集地访问平台。

认证 Cookie 的运行期缓存位于 `config.py`。一次进程运行中，已获得且完整的认证信息会被后续请求复用；只有没有可用缓存、配置不完整或显式要求刷新时才重新登录或提示输入。

### 2. 课程发现与接口兼容

单课程下载先按 `liveId` 请求课程记录。程序会只保留已经结束的课程片段，按月、日、星期、节次和周数排序，再按下载模式和跳过周数筛选。

项目同时保留新旧课程接口的处理路径：当课程记录表明学年不晚于 2024 时，会尝试旧版课程接口，并将该课程按旧版 M3U8/TS 方式处理；其他课程使用 MP4 链接流程。这个判断集中在 `api.py` 与 `downloader.py`，入口层不需要关心平台格式差异。

对于 MP4 课程，程序会读取播放页中的视频信息字段，完成 URL 解码和 JSON 解析后提取 `pptVideo` 与 `teacherTrack` 链接。对于“回看生成中”、未登录、访问被拒绝等已知页面，代码使用明确异常或提示中止当前片段，避免把错误页当作视频元数据继续解析。

批量课程扫描以用户 ID、学年和学期为输入，逐周读取课程数据；扫描最多检查 20 周，并在连续两周没有课程时停止。每门课程只保留首次出现的记录作为配置来源。

### 3. 并发链接解析与下载策略

在真正下载前，`download_course_videos()` 使用线程池并发解析每个已结束片段的播放链接。工作线程数由 `utils.calculate_optimal_threads()` 根据 CPU、内存和处理器数量计算，范围被限制在 1 至 32，避免无限制创建线程。

MP4 下载器的工作过程如下：

1. 先发起 `HEAD` 请求，读取文件长度和服务器是否支持 `Range`。
2. 对支持 Range 且大小至少为 10 MiB 的文件，按约 10 MiB 分片并发下载，每个文件最多使用 32 个分片线程；任意分片最终失败时，清理分片并回退到单线程下载。
3. 其他文件使用单线程流式下载。若发现未完成的 `.tmp` 文件且长度有效，会使用 Range 从已有位置继续。
4. 下载完成后校验临时文件，再以移动/重命名方式成为最终文件；达到最终重试次数仍失败时清理未完成临时文件。

旧版 M3U8 下载器会解析播放列表中的 TS 分片，将分片并发取回并按原始索引顺序写入临时文件。单个 M3U8 文件最多使用 8 个分片下载工作线程；若缺失分片超过总数的 20%，该次下载视为失败。

### 4. 完整性、命名、CSV 与增量行为

每个输出文件在复用、合并或最终落盘前都会经过基础完整性检查：文件必须达到最小大小；若已知内容长度则检查大小差异；MP4 检查文件头中的 `ftyp` 标识，TS 检查同步字节 `0x47`。这是轻量级的传输完整性验证，不等同于对整段视频进行解码验证。

课程目录按年份、课程代码和清洗后的课程名命名。视频文件名保留日期、周数、星期、节次和轨道类型；课程名会清除文件系统非法字符、控制字符、保留名称和过长部分。稳定的命名格式既支持“文件已存在则跳过”的增量下载，也为 WebUI 本地媒体库的识别提供依据。

每次成功解析出的行数据会写入 `logs/` 下对应课程的 CSV，其中包含日期信息、两个视频链接和 `liveId`。CSV 是运行元数据与排障辅助信息，不是继续下载时唯一的状态来源；下载器以本地目标文件是否存在且通过校验为准。

### 5. 字幕与视频合并

对于每个课程片段，下载器会尝试从播放页取得字幕所需标识，再请求 VTT 字幕。有效 VTT 会转换为 SRT 并与相应视频放在课程目录中；没有字幕、平台未提供字幕或请求失败并不会使视频下载任务失败。

当启用自动合并且存在可合并的相邻片段时，项目使用本地 FFmpeg 的 concat 流复制方式合并同一轨道的视频，避免重新编码。合并前会验证输入文件，合并后会验证输出文件；只有成功后才删除原始片段。字幕合并会按前段媒体时长调整后续字幕时间轴，从而与合并视频保持连续。媒体时长通过 FFmpeg 输出解析，打包版本不依赖额外的 `ffprobe`。

FFmpeg 的查找顺序是程序目录中的精简版或常规版可执行文件，然后是系统 `PATH`。因此下载旧课程或使用合并功能的源码运行方式需要可用 FFmpeg；打包发行版会随程序携带所需组件。

## 认证与配置管理

### 认证方式与配置语义

认证层支持四种方式：西电统一身份认证登录（`ids`）、超星账号密码登录（`chaoxing`）、学在西电 App 扫码登录（`chaoxing_qr`）和手动 Cookie（`cookies`）。它们最终都需要得到 `_d`、`UID`、`vc3` 三个 Cookie 值，供下载与扫描请求使用。

`auth.ini` 由程序维护，典型逻辑结构如下。示例中的内容只是字段形状，不应填入或提交真实凭证。

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

一个配置文件不会同时需要所有认证段：选择统一身份认证或超星账号密码时保存相应账号段；扫码或手动 Cookie 时保存 `[AUTH]`。为了兼容旧文件，读取认证配置时会把旧的 `password` 认证方式和 `[CREDENTIALS]` 段迁移为当前的超星账号密码结构。

### 批量课程配置

`automation_config.ini` 将学期默认项与课程选择放在同一个 INI 文件中：

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

`term_id` 为 `1` 或 `2`，`video_type` 为 `both`、`ppt` 或 `teacher`，每个课程段的 `download` 控制该课程是否参与批量任务。CLI 更新配置时会保留既有 `download` 选择；WebUI 的“临时勾选后下载”则会复制一份内存配置运行，只有用户明确保存选择时才写回文件。

### 安全写入与敏感数据

配置写入由 `safe_write_config()` 统一处理：先在同一目录创建 UTF-8 临时文件，再移动为目标文件，尽可能避免半写入配置；需要覆盖敏感 WebUI 设置时还会把旧配置备份到 `logs/`。在 POSIX 系统上，认证文件会尝试限制为仅当前用户可读写；Windows 上仍应依赖账户权限并自行保护文件。

`auth.ini`、`automation_config.ini` 以及常见的日志和 CSV 生成文件已在 `.gitignore` 中忽略，但这不等于它们可以安全分享。尤其是 `auth.ini` 可能保存账号密码或有效 Cookie，提交代码、打包日志或寻求帮助前都应先检查和脱敏。

## WebUI 技术实现

### 前后端通信模型

WebUI 是一个由 Flask 提供静态文件和 JSON 接口的本地单页应用。`index.html` 提供下载、查看、设置三个页面骨架，`app.js` 用原生 DOM API 管理状态和事件，`styles.css` 负责布局、响应式显示与主题适配。前端不引入框架、Node.js 或构建步骤。

普通数据交互使用 JSON：后端要求写操作使用 `application/json` 请求体，并以 `{ "ok": true/false, ... }` 返回。下载日志则使用 Server-Sent Events（SSE）：前端以 `EventSource` 连到任务的流地址，页面刷新后也会查询活动任务并重新连接输出流。

| 接口类别 | 代表路径 | 作用 |
| --- | --- | --- |
| 应用与访问控制 | `/api/app/info`、`/api/webui/access/*` | 读取版本提示、查询或提交 WebUI 访问密码。 |
| 批量配置 | `/api/automation/config`、`/api/automation/config/init`、`/api/automation/config/selection` | 读取、扫描、刷新和保存批量课程选择。 |
| 下载任务 | `/api/download/start`、`/api/download/active`、`/api/download/jobs/<id>/stream` | 创建下载任务、恢复状态并持续接收输出。 |
| 本地媒体库 | `/api/library`、`/media/<path>` | 索引已下载媒体并在受控路径下提供播放内容。 |
| 认证与扫码 | `/api/settings/auth`、`/api/settings/qr/*` | 读写认证配置，启动、轮询和取消扫码任务。 |
| WebUI 设置 | `/api/settings/webui-password` | 查询、设置或清除网页访问密码。 |

### 下载任务和控制台输出桥接

已有下载核心会向标准输出打印进度，也会把错误写入项目日志。`DownloadJob` 因此在后台守护线程中运行实际下载函数，并使用 `QueueWriter` 收集该线程的标准输出与标准错误；`QueueLogHandler` 同时把错误级别日志转入相同队列。`ThreadBoundStream` 只劫持任务线程的输出，其他线程仍写向原来的控制台，避免全局替换 `sys.stdout` 时误捕获 Flask 或其他线程的内容。

每个任务保留最近 5000 段输出并通过条件变量唤醒 SSE 生成器。`DownloadJobManager` 同一时间只允许一个 `pending` 或 `running` 下载任务，这一限制既避免两个任务同时改写同一课程目录，也避免多个任务竞争同一份认证和终端输出。

### 扫码、媒体库与播放器

WebUI 扫码登录是独立的后台 `QRLoginJob`：它生成二维码文件，定期轮询登录状态，成功后提取 Cookie 并写入认证配置；任务可取消，等待时间受限，失败或过期会返回状态信息给前端。

本地媒体库只扫描应用目录下受支持的 `.mp4`、`.ts`、`.srt` 和 `.vtt` 文件。后端依据下载器的标准文件名归类课程、日期、节次和视频轨道，并把字幕与视频进行匹配；媒体路由同样限制在应用目录及允许的扩展名范围内。前端可同时创建 PPT 与教师两个 HTML5 视频元素，用公共进度条协调播放、暂停、跳转和速度，并在页面字幕区域处理字幕时间偏移、字号和粗体。

### WebUI 访问边界

默认监听地址为回环地址，因此只能在本机浏览器访问。若通过 `--host` 或 `[WEBUI] bind_host` 开放到局域网，可用 `allowed_clients` 配置 IPv4/IPv6 单地址或 CIDR 网段白名单。白名单为空时不额外限制客户端 IP。

WebUI 访问密码不会以明文新格式保存：代码使用带随机盐的 PBKDF2-HMAC-SHA256，迭代次数为 120000，并用恒定时间比较校验。Flask 会话密钥在每次启动时随机生成，因此正在登录的 WebUI 会话不会跨进程重启保留。旧的明文密码字段只为兼容已有配置而读取，写入新密码时会转换为哈希字段。

这仍是本地工具而不是公网服务：服务使用 HTTP，未配置 TLS、反向代理信任或公开部署防护。将监听地址开放到非受控网络并不在当前设计范围内；如确有局域网需求，应设置强访问密码、最小化 `allowed_clients`、配置系统防火墙并避免通过端口映射暴露到互联网。

## 校验、日志和错误处理

`validator.py` 集中检查 `liveId`、用户 ID、学期、下载模式、视频类型、URL、文件完整性以及课程/视频数据形状。入口、WebUI API 和核心下载函数都在进入耗时操作前调用这些检查，以避免非法输入直接进入平台请求、线程池或文件名构造。

`utils.py` 为所有模块建立以 `xdu` 为根的日志体系：控制台默认只显示 `ERROR` 及以上，总日志 `logs/all.log` 与各模块文件记录 `INFO` 及以上；传入 `--debug` 后会额外启用 `logs/debug.log`，其中包含更细的调试信息和网络请求记录。控制台过滤器会去除 traceback，使用户看到简洁错误，而文件日志保留定位所需的调用位置和异常信息。

网络超时、连接异常、HTTP 状态、数据格式和文件操作异常会由统一异常处理函数转换为可读提示，同时写入详细日志。用户排障时应优先保留错误时间、入口参数（但不要包含 Cookie）和相关 `logs/<module>.log` 片段。

## 依赖、打包与运行期路径

`requirements.txt` 中的依赖可按功能划分：

| 依赖 | 用途 |
| --- | --- |
| `requests` | 平台请求、连接池和重试适配。 |
| `beautifulsoup4` | 登录页和部分 HTML 字段解析。 |
| `pycryptodome`、`numpy`、`pillow` | 统一身份认证及滑块验证码相关处理。 |
| `tqdm` | CLI 下载与链接解析进度显示。 |
| `psutil` | 根据本机负载计算链接解析并发度。 |
| `flask` | 本地 WebUI 服务、JSON API、会话与静态文件。 |

FFmpeg 是外部二进制而非 Python 依赖。它用于旧版视频链路和视频/字幕合并；项目在源码与 PyInstaller 运行时都会通过 `get_app_path()` 定位可写的应用目录，通过 `get_bundled_app_path()` 优先定位 PyInstaller 解包资源。这样在打包为 `.exe` 后，配置、日志和下载目录仍放在可执行文件旁，而静态前端资源可从 PyInstaller 的资源目录读取。

`XDUClassVideoDownloader.spec`、`Automation.spec` 与 `WebUI.spec`（本地存在时）分别描述三个入口的 PyInstaller 打包方式。WebUI 打包还会携带 `webui/static/`，三个入口会携带精简 FFmpeg 文件。构建目录和发行目录属于生成物，不应作为业务源码修改。

## 维护与扩展建议

1. **新增下载能力时从共享链路进入。** 优先扩展 `api.py` 的数据获取与 `downloader.py` 的落盘逻辑，再让三个入口传递必要参数；不要只在 WebUI 或某个 CLI 中实现一套例外流程。
2. **平台变更先定位数据边界。** 课程列表、播放页、`videoPath`、字幕和扫码都是外部接口边界。先在 `api.py` 增加明确的解析、异常和日志，再考虑 UI 表现。
3. **保持配置向后兼容。** 新字段应有默认值，更新配置时应保留用户的课程选择；涉及认证文件格式时使用现有备份和迁移模式。
4. **不要破坏文件命名契约。** WebUI 媒体库和字幕匹配依赖下载器生成的文件名。若需要调整命名，同时更新下载器、正则索引与文档，并考虑已有文件的兼容策略。
5. **WebUI 任务必须保持串行。** 新的长耗时操作若会写入同一配置、认证或课程目录，应纳入任务管理器，提供状态和输出，而不是直接在 Flask 请求线程中执行。
6. **日志中避免泄露凭证。** 调试日志会记录较多请求上下文；新增日志时不得输出账号密码、完整 Cookie 或可直接复用的下载授权信息。

## 当前边界与已知约束

- 项目依赖学校与超星平台的现有行为。课程权限不足、Cookie 过期、回看尚在生成、接口字段变化或网络限制都可能使单个片段失败。
- 完整性检查旨在拦截明显不完整文件，不能证明视频内容一定可播放或音画完全正确。
- 自动合并要求本机存在可用 FFmpeg，且输入媒体能够以流复制方式连接；不能合并时原始片段会保留。
- WebUI 的媒体库面向本项目生成的文件名和应用目录，不是通用文件管理器；手动改名或移出目录会影响索引和字幕匹配。

以上边界有助于将故障区分为本地配置、网络传输、平台权限、媒体处理或界面索引问题，并使后续修改保持三个入口的一致行为。
