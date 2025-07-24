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

## 🎉🎉 2.0+ 版本重大更新：增加 `Automation.py`，实现全学期课程全自动下载！🎉🎉

本项目经过重大更新，引入了强大的自动化功能。全新的 `Automation.py` 脚本能够实现全自动下载您整个学期的所有课程。它能够智能管理配置文件、自动发现新课程、跳过已下载的视频，让您随时运行，轻松追更新。

- [XDUClassVideoDownloader](#xduclassvideodownloader)
  - [🎉🎉 2.0+ 版本重大更新：增加 `Automation.py`，实现全学期课程全自动下载！🎉🎉](#-20-版本重大更新增加-automationpy实现全学期课程全自动下载)
  - [**使用须知**](#使用须知)
  - [**项目简介**](#项目简介)
  - [**核心功能**](#核心功能)
  - [**环境准备**](#环境准备)
  - [**使用方法**](#使用方法)
    - [**Windows 用户看这里！（懒人包）**](#windows-用户看这里懒人包)
    - [**通过 Python 脚本运行**](#通过-python-脚本运行)
      - [**`XDUClassVideoDownloader.py`** (按 `liveId` 下载)](#xduclassvideodownloaderpy-按-liveid-下载)
      - [**`Automation.py`** (全自动下载)](#automationpy-全自动下载)
      - [**辅助工具：`ConvertTStoMP4`**](#辅助工具converttstomp4)
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
    > `liveId` 是课程直播的唯一标识，可以在课程直播页面的 URL 中找到。例如：`http://newesxidian.chaoxing.com/live/viewNewCourseLive1?liveId=12345678` 中的 `12345678`。

- **`Automation.py`**：强大的自动化脚本，通过您的超星 `UID` 来自动发现并下载当前学期的所有课程。
    > 您的超星 `UID` 可以在浏览器开发者工具中查看 `chaoxing.com` 域下的 Cookie 找到。

## **核心功能**

- **全自动批量下载**：运行 `Automation.py`，输入一次 `UID`，即可自动下载该学期所有已订阅的课程。
- **智能化配置文件**：首次运行 `Automation.py` 会生成 `config.ini` 文件，列出您的所有课程。您可以自由编辑此文件，决定哪些课程需要下载。
- **新课程自动发现**：自动化脚本能自动检测到您课表中的新课程，并将其添加到配置文件中，提醒您进行确认。
- **自动增量下载**：自动跳过已存在的视频文件，您可以随时运行脚本来下载新增的录播视频，无需担心重复下载。
- **视频智能合并**：自动将同一节课的上下两个部分（`pptVideo` 和 `teacherTrack`）合并为一个文件，方便观看。
- **M3U8 链接导出**：在下载的同时，会将所有视频的 `m3u8` 链接保存到对应的 `.csv` 文件中，方便您使用其他下载工具。
- **性能优化**：根据系统负载（CPU、内存）动态调整并发线程数，在保证系统稳定性的前提下，最大化下载效率。
- **自动更新检查**：启动时会检查项目是否有新版本，并给出提示。

## **环境准备**

1. **Python**: 建议使用 `Python 3.8+` 版本（作者开发时使用 3.11.7）。[从 Python 官网下载](https://www.python.org/downloads/)
2. **依赖库**: 使用 `pip` 安装所需的库：

    ```shell
    pip install requests tqdm psutil
    ```

3. **FFmpeg (可选)**: 如果您需要使用 `ConvertTStoMP4(NeedFFmpeg).bat` 脚本将视频从 `.ts` 格式转换为 `.mp4`，则必须安装 [FFmpeg](https://ffmpeg.org/download.html) 并将其添加到系统环境变量 `PATH` 中。

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
        - `y` (或直接回车): 下载该 `liveId` 对应的**单节课**（上下两集）。
        - `n`: 下载这门课的**所有视频**。
        - `s`: 仅下载该 `liveId` 对应的**单集视频**（半节课）。
    4. 选择是否自动合并视频。
    5. (可选) 输入一个周数，脚本将跳过下载前几周的视频（例如，输入 `3` 将跳过前三周）。直接回车则从头开始。

#### **`Automation.py`** (全自动下载)

这是推荐的使用方式，可以一劳永逸地管理您的所有课程视频。

- **使用流程**:
    1. 在 Windows 上双击 `automation.bat`，或在其他系统上运行 `python Automation.py`。
    2. **首次运行**:
        - 程序会提示您输入超星 `UID`。
        - 输入后，脚本会自动扫描您当前学期的所有课程，并生成一个 `config.ini` 文件。
        - 此时，您可以打开 `config.ini` 文件，将不希望下载的课程对应的 `download` 字段从 `yes` 改为 `no`。
        - 保存配置文件后，回到程序窗口按回车键，即可开始下载。
    3. **后续运行**:
        - 程序会自动读取 `config.ini`，并检查是否有新课程加入。
        - 如果发现新课程，会将其添加到配置文件中并提示您修改。确认后即可开始增量下载。
        - 若要重新扫描所有课程或更换学期，只需删除 `config.ini` 文件后重新运行脚本即可。

#### **辅助工具：`ConvertTStoMP4`**

项目中提供了一个 Windows 批处理脚本 `ConvertTStoMP4(NeedFFmpeg).bat`。

- **功能**: 此脚本可以批量将当前目录及其所有子目录下的 `.ts` 视频文件转换为 `.mp4` 格式。转换过程采用流拷贝模式，速度极快且无画质损失。
- **使用**: 直接双击运行即可。
- **安全机制**: 脚本在转换后会校验生成的 `.mp4` 文件大小是否超过原 `.ts` 文件的一半，确认无误后才会删除原文件，防止因转换失败导致文件丢失。

## **命令行参数详解**

两个核心脚本都支持命令行参数，方便进阶用户或自动化调用。打包的 `.exe` 程序同样支持这些参数。

### `XDUClassVideoDownloader.py` 参数

```shell
# 用法
python XDUClassVideoDownloader.py [LIVEID] [-s] [-c COMMAND] [--no-merge]
```

- `LIVEID` (可选): 课程的 `liveId`。如果省略，将进入交互模式。
- `-s` (可选):
  - `-s`: 仅下载单节课视频。
  - `-ss`: 仅下载单集（半节课）视频。
- `--no-merge` (可选): 禁止自动合并上下半节课的视频。
- `-c COMMAND` (可选): 使用自定义的下载命令。可用占位符: `{url}`, `{save_dir}`, `{filename}`。

**示例:**

```shell
# 使用 exe 下载 liveId 为 1234567890 的单节课，且不合并
XDUClassVideoDownloader.exe 1234567890 -s --no-merge
```

### `Automation.py` 参数

```shell
# 用法
python Automation.py [-u UID] [-y YEAR] [-t TERM]
```

- `-u UID` (可选): 您的超星 `UID`。
- `-y YEAR` (可选): 指定学年（如 `2024`）。默认为当前学年。
- `-t TERM` (可选): 指定学期（`1` 代表秋季学期，`2` 代表春季学期）。默认为当前学期。

**示例:**

```shell
# 使用 exe 自动下载 2024 年秋季学期的课程，并指定 UID
Automation.exe -u 123456789 -y 2024 -t 1
```

## **注意事项**

- 本项目下载的视频仅供个人学习使用，请勿用于任何商业用途或在公共平台传播。
- 请遵守相关法律法规及学校的规定。
- 开发者不对使用本项目可能导致的任何问题负责。

## **依赖的二进制文件**

- 本项目依赖 `vsd` 进行下载和合并操作，来自 [clitic/vsd](https://github.com/clitic/vsd)。
- 为了减小体积，二进制文件经过了 [upx/upx](https://github.com/upx/upx) 压缩。
