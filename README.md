# XDUClassVideoDownloader

[![GitHub repo size](https://img.shields.io/github/repo-size/lsy223622/XDUClassVideoDownloader)](https://github.com/lsy223622/XDUClassVideoDownloader/archive/refs/heads/main.zip)
[![GitHub License](https://img.shields.io/github/license/lsy223622/XDUClassVideoDownloader)](https://github.com/lsy223622/XDUClassVideoDownloader?tab=GPL-3.0-1-ov-file)
[![GitHub Repo stars](https://img.shields.io/github/stars/lsy223622/XDUClassVideoDownloader)](https://github.com/lsy223622/XDUClassVideoDownloader/stargazers)

[![GitHub Tag](https://img.shields.io/github/v/tag/lsy223622/XDUClassVideoDownloader)](https://github.com/lsy223622/XDUClassVideoDownloader/tags)
[![GitHub Release Date](https://img.shields.io/github/release-date-pre/lsy223622/XDUClassVideoDownloader)](https://github.com/lsy223622/XDUClassVideoDownloader/releases)
[![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/lsy223622/XDUClassVideoDownloader/total)](https://github.com/lsy223622/XDUClassVideoDownloader/releases)

![Static Badge](https://img.shields.io/badge/QQ-2413282135-white?logo=tencentqq&logoColor=white&labelColor=blue)
[![Static Badge](https://img.shields.io/badge/HOME-lsy223622.com-white?labelColor=396aa9)](https://lsy223622.com)
[![Static Badge](https://img.shields.io/badge/BLOG-blog.lsy223622.com-white?labelColor=a6c4c2)](https://blog.lsy223622.com)

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/lsy223622/XDUClassVideoDownloader)

## 🎉🎉 4.0 版本重大更新：新学期和过往学期的课程都能下载了 🎉🎉

本项目经过重大更新，同时适配新版和旧版录直播平台接口，并且全面重构代码，大幅优化了下载速度和用户体验。

- [XDUClassVideoDownloader](#xduclassvideodownloader)
  - [🎉🎉 4.0 版本重大更新：新学期和过往学期的课程都能下载了 🎉🎉](#-40-版本重大更新新学期和过往学期的课程都能下载了-)
  - [**使用须知**](#使用须知)
  - [**项目简介**](#项目简介)
  - [**核心功能**](#核心功能)
  - [**环境准备**](#环境准备)
  - [**使用方法**](#使用方法)
    - [**Windows 用户看这里！（懒人包）**](#windows-用户看这里懒人包)
    - [**通过 Python 脚本运行**](#通过-python-脚本运行)
      - [**`XDUClassVideoDownloader.py`** (按 `liveId` 下载)](#xduclassvideodownloaderpy-按-liveid-下载)
      - [**`Automation.py`** (全自动下载)](#automationpy-全自动下载)
  - [**命令行参数详解**](#命令行参数详解)
    - [`XDUClassVideoDownloader.py` 参数](#xduclassvideodownloaderpy-参数)
    - [`Automation.py` 参数](#automationpy-参数)
  - [**注意事项**](#注意事项)
  - [**依赖的二进制文件**](#依赖的二进制文件)

## **使用须知**

- 请先阅读此 README 再使用本项目。
- 如果遇到问题可以联系上面的 QQ。
- 欢迎提出建议和改进意见，能 PR 的话就更好啦。
- 如果觉得好用请给个 Star 哦。

## **项目简介**

本项目是为西安电子科技大学录播平台设计的课程视频下载工具，包含两个核心脚本：

- **`XDUClassVideoDownloader.py`**：基础下载脚本，通过课程的 `liveId` 来下载指定视频。您可以选择下载单节课（上下两集）、单集（半节课）或该课程的全部视频。

  > `liveId` 是课程直播的唯一标识，可以在课程直播页面的 URL 中找到。例如：`http://newes.chaoxing.com/xidianpj/live/viewNewCourseLive1?isStudent=1&liveId=12345678` 中的 `12345678`。

- **`Automation.py`**：强大的自动化脚本，通过您的超星 `UID` 来自动发现并下载当前学期的所有课程。
  > 您的超星 `UID` 可以通过访问 `https://i.mooc.chaoxing.com/settings/info` 在页面中的 `id` 字段找到。

## **核心功能**

- **全自动批量下载**：运行 `Automation.py`，只有第一次需要输入一次 `UID` 和超星平台的鉴权 cookies，即可自动下载该学期所有已订阅的课程。
- **支持多种登录方式**：支持“统一身份认证登录（推荐，自动解决滑块验证码）”、“超星账号密码登录”或“手动输入 Cookies”。详见 `AUTHENTICATION.md`。
- **智能化配置文件**：首次运行 `Automation.py` 会生成 `automation_config.ini` 文件，列出您的所有课程。您可以自由编辑此文件，决定哪些课程需要下载。
- **新课程自动发现**：自动化脚本能自动检测到您课表中的新课程，并将其添加到配置文件中，提醒您进行确认。
- **自动增量下载**：自动跳过已存在的视频文件，您可以随时运行脚本来下载新增的录播视频，无需担心重复下载。
- **灵活的视频类型选择**：支持选择下载 pptVideo（课件视频）、teacherTrack（教师视频），或两种视频都下载。默认为两种都下载。
- **视频智能合并**：自动对同一节课的上下半节或相邻节次（同一轨道）进行无损合并（FFmpeg `-c copy`），方便观看。
- **视频链接导出**：在下载的同时，会将所有视频的下载链接保存到对应的 `.csv` 文件中，方便您使用其他下载工具。
- **性能优化**：根据系统负载（CPU、内存）动态调整并发线程数，在保证系统稳定性的前提下，最大化下载效率。
- **自动更新检查**：启动时会检查项目是否有新版本，并给出提示。

## **环境准备**

1. **Python**: 建议使用 `Python 3.8+` 版本（作者开发时使用 3.11.7）。[从 Python 官网下载](https://www.python.org/downloads/)
2. **依赖库**: 使用 `pip` 安装所需的库：

   ```shell
   pip install requests tqdm psutil beautifulsoup4 pycryptodome numpy pillow
   ```

3. **FFmpeg (可选)**: 如果您需要下载 2024 学年及以前的课程，或者使用上下半节视频合并功能，则需要下载 [FFmpeg](https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.7z)（这是 Windows 版本下载链接），并将 `ffmpeg` 可执行程序放在下载程序同目录下或者添加到系统环境变量 `PATH` 中。也可以在 [Releases](https://github.com/lsy223622/XDUClassVideoDownloader/releases) 页面找到专门编译的超小体积版本 `ffmpeg_min.exe`。

## **使用方法**

### **Windows 用户看这里！（懒人包）**

您可以直接从项目的 [**Releases**](https://github.com/lsy223622/XDUClassVideoDownloader/releases/latest) 页面下载打包好的 `exe` 程序。该版本无需安装 Python 和任何依赖库，开箱即用。

- 要下载特定课程，运行 `XDUClassVideoDownloader.exe`。
- 要全自动下载所有课程，运行 `Automation.exe`。

然后根据下方的说明操作即可。

### **通过 Python 脚本运行**

#### **`XDUClassVideoDownloader.py`** (按 `liveId` 下载)

此脚本适用于下载特定的一门课或一节课。

- **交互模式**:
  1. 在 Windows 上双击 `windows_run.bat`，或在其他系统上运行 `python XDUClassVideoDownloader.py`。
  2. 根据提示输入 `liveId`。
  3. 选择下载范围:
     - `1` (或直接回车): 下载这门课的**所有视频**。
     - `2`: 下载该 `liveId` 对应的**单节课**（上下两集）。
     - `3`: 仅下载该 `liveId` 对应的**单集视频**（半节课）。
  4. 选择是否自动合并视频：
     - `1` (或直接回车): 自动合并视频。
     - `2`: 不自动合并视频。
  5. 选择要下载的视频类型:
     - `1` (或直接回车): 下载两种视频（pptVideo 和 teacherTrack，默认）。
     - `2`: 仅下载 pptVideo（课件视频）。
     - `3`: 仅下载 teacherTrack（教师视频）。
  6. 可选：输入要跳过的周数，支持以下格式（直接回车则不跳过）：
     - 单个周数：`5` （跳过第5周）
     - 范围：`1-5` （跳过第1到5周）
     - 逗号分隔：`1,3,5` （跳过第1、3、5周）
     - 组合：`1-3,7,9-11` （跳过1-3周、第7周、9-11周）
  7. 首次运行会进入认证向导：
     - 选择“统一身份认证登录（推荐）”输入学号和密码自动获取 Cookies，或
     - 选择“超星账号密码登录”输入超星账号密码获取 Cookies，或
     - 选择“手动输入 Cookies”并依次输入 `_d`、`UID`、`vc3`。

#### **`Automation.py`** (全自动下载)

这是推荐的使用方式，可以一劳永逸地管理您的所有课程视频。

- **使用流程**:
  1. 在 Windows 上双击 `automation.bat`，或在其他系统上运行 `python Automation.py`。
  1. **首次运行**:
     - 程序会先进行认证（可选统一身份认证登录、超星账号密码登录或手动 Cookies）。
     - 随后提示输入超星 `UID`，并扫描当前学期课程，生成一个 `automation_config.ini` 文件。
     - 您可以打开 `automation_config.ini`，将不希望下载的课程对应的 `download` 字段从 `yes` 改为 `no`。
     - 配置文件中的 `video_type` 字段控制全局视频类型（`both`/`ppt`/`teacher`），默认为 `both`。
     - 保存配置文件后，回到程序窗口按回车键，即可开始下载。
  1. **后续运行**:
     - 程序会自动读取 `automation_config.ini`，并检查是否有新课程加入。
     - 如果发现新课程，会将其添加到配置文件中并提示您修改。确认后即可开始增量下载。
     - 程序会自动检查并更新旧版本的配置文件，确保包含 `video_type` 参数。
     - 若要重新扫描所有课程或更换学期，只需删除 `automation_config.ini` 文件后重新运行脚本即可。

## **命令行参数详解**

两个核心脚本都支持命令行参数，方便进阶用户或自动化调用。打包的 `.exe` 程序同样支持这些参数。

### `XDUClassVideoDownloader.py` 参数

```shell
# 用法
python XDUClassVideoDownloader.py [LIVEID] [-s | -ss] [--no-merge] [--video-type {both,ppt,teacher}] [--skip-weeks WEEKS] [--debug]
```

- `LIVEID` (可选): 课程的 `liveId`。如果省略，将进入交互模式。
- `-s` (可选):
  - `-s`: 仅下载单节课视频。
  - `-ss`: 仅下载单集（半节课）视频。
- `--no-merge` (可选): 禁止自动合并上下半节课的视频。
- `--video-type` (可选): 选择要下载的视频类型:
  - `both`: 下载两种视频（pptVideo 和 teacherTrack，默认）
  - `ppt`: 仅下载 pptVideo（课件视频）
  - `teacher`: 仅下载 teacherTrack（教师视频）
- `--skip-weeks WEEKS` (可选): 跳过特定周数的视频，支持多种格式:
  - 单个周数：`--skip-weeks 5` （跳过第5周）
  - 范围：`--skip-weeks 1-5` （跳过第1到5周）
  - 逗号分隔：`--skip-weeks "1,3,5"` （跳过第1、3、5周）
  - 组合：`--skip-weeks "1-3,7,9-11"` （跳过1-3周、第7周、9-11周）
- `--debug` (可选): 启用调试日志（写入 `logs/debug.log`）。

**示例:**

```shell
# 使用 exe 下载 liveId 为 1234567890 的单节课，且不合并，仅下载课件视频
XDUClassVideoDownloader.exe 1234567890 -s --no-merge --video-type ppt

# 仅下载教师视频
XDUClassVideoDownloader.exe 1234567890 --video-type teacher

# 跳过前5周，下载所有视频
XDUClassVideoDownloader.exe 1234567890 --skip-weeks 1-5

# 跳过第1、3、5周和第7-9周
XDUClassVideoDownloader.exe 1234567890 --skip-weeks "1,3,5,7-9"
```

### `Automation.py` 参数

```shell
# 用法
python Automation.py [-u UID] [-y YEAR] [-t TERM] [--video-type {both,ppt,teacher}] [--debug]
```

- `-u UID` (可选): 您的超星 `UID`。
- `-y YEAR` (可选): 指定学年（如 `2025`）。默认为当前学年。
- `-t TERM` (可选): 指定学期（`1` 代表上半学期，`2` 代表下半学期）。默认为当前学期。
- `--video-type` (可选): 选择要下载的视频类型:
  - `both`: 下载两种视频（pptVideo 和 teacherTrack，默认）
  - `ppt`: 仅下载 pptVideo（课件视频）
  - `teacher`: 仅下载 teacherTrack（教师视频）
- `--debug` (可选): 启用调试日志（写入 `logs/debug.log`）。

**示例:**

```shell
# 使用 exe 自动下载 2024 年秋季学期的课程，并指定 UID，仅下载课件视频
Automation.exe -u 123456789 -y 2024 -t 1 --video-type ppt

# 仅下载教师视频
Automation.exe --video-type teacher
```

## **注意事项**

- 本项目下载的视频仅供个人学习使用，请勿用于任何商业用途或在公共平台传播。
- 请遵守相关法律法规及学校的规定。
- 开发者不对使用本项目可能导致的任何问题负责。

## **依赖的二进制文件**

- 合并 ts 片段（2024 学年及以前的课程需要）或者上下半节视频使用本地 `ffmpeg`（可在项目根目录放置 `ffmpeg` 可执行程序，或将系统 FFmpeg 加入 PATH）。也可以在 [Releases](https://github.com/lsy223622/XDUClassVideoDownloader/releases) 页面找到专门编译的超小体积版本 `ffmpeg_min.exe`。
