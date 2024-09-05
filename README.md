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

## 🎉🎉 2.0 版本更新 增加 Automation.py 随时自动下载全学期课程！🎉🎉

- [XDUClassVideoDownloader](#xduclassvideodownloader)
  - [🎉🎉 2.0 版本更新 增加 Automation.py 随时自动下载全学期课程！🎉🎉](#-20-版本更新-增加-automationpy-随时自动下载全学期课程)
  - [使用须知](#使用须知)
  - [项目简介](#项目简介)
  - [使用方法](#使用方法)
    - [**Windows 用户看这里！**](#windows-用户看这里)
    - [使用前的准备步骤](#使用前的准备步骤)
    - [XDUClassVideoDownloader.py](#xduclassvideodownloaderpy)
      - [命令行参数](#命令行参数)
        - [示例](#示例)
    - [Automation.py](#automationpy)
  - [注意事项](#注意事项)
  - [使用的二进制文件](#使用的二进制文件)
  - [各种语言的版本](#各种语言的版本)

## 使用须知

- 请先阅读此 README 再使用本项目。
- 如果遇到问题可以联系上面的 QQ。
- 欢迎提出建议和改进意见，能 PR 的话就更好啦。
- 如果觉得好用请给个 Star 哦。

## 项目简介

- 本项目是一个用于下载西安电子科技大学录直播平台课程视频的工具。
- 只需运行 `XDUClassVideoDownloader.py`，输入任意一节课的 `liveId`，即可自动下载 `单节课` / `单集（半节课）` / `该课程的所有视频`。

   > `liveId` 是课程直播的唯一标识，可以在课程直播页面的 URL 中找到。如：`http://newesxidian.chaoxing.com/live/viewNewCourseLive1?liveId=12345678` 中的 `12345678`。

- 同时会保存选择下载的范围内所有视频的 `m3u8` 链接到对应的 `csv` 表格中，方便使用其他方式下载。
- 2.0 版本增加 `Automation.py`，只需输入超星用户 UID，即可自动下载本学期目前所有课程。

   > 超星用户 UID 可以在 `chaoxing.com` 的 cookies 中找到，`UID` 的值就是超星用户 UID。

- 下载时会自动检查之前是否下载过同一节课，如果已经下载则会跳过。所以可以在一学期中的多个时候随时下载新增的录播视频。
- 下载的视频按照课程和时间整理，下载多个课程的视频也不会冲突。
- 文件夹和 `csv` 表格命名规则：年份-课程号-课程名。
- 课程视频命名规则：课程号-课程名-年月日-周次-节号-视频来源。

## 使用方法

### **Windows 用户看这里！**

- 可以从 [Releases](https://github.com/lsy223622/XDUClassVideoDownloader/releases/latest) 直接下载打包好的 exe 程序，无需以下所有准备步骤，打开 `XDUClassVideoDownloader.exe` 后输入 `liveId`，或打开 `Automation.exe` 后输入 `UID`，下面的选项参考下方 [使用](#xduclassvideodownloaderpy) 部分。

### 使用前的准备步骤

1. 安装 `Python`（我用的 3.11.7）。[Python 官网下载页面](https://www.python.org/downloads/)
   - 检查 Python 版本：

   ```shell
   python --version
   ```

2. 在命令行中输入以下命令来使用 `pip` 安装依赖：`requests`, `tqdm`。~~如果缺别的依赖那就装别的依赖~~

   ```shell
   pip install requests tqdm
   ```

### XDUClassVideoDownloader.py

1. 下载本项目。
2. 运行程序：
   - Windows 用户：双击 `windows_run.bat`。
   - Linux 用户：运行 `XDUClassVideoDownloader.py`。
3. 输入 `liveId` 并回车。
4. 输入 `y/n/s` 并回车。
   - `y`：下载 `liveId` 对应单节课的视频。
   - `n`：下载这门课程的所有视频。
   - `s`：下载 `liveId` 对应的单集（半节课）视频。
   - 不输入直接回车：效果同 `y`。
5. 输入 `y/n` 并回车。
   - `y`：合并上下半节视频。
   - `n`：不合并上下半节视频。
   - 不输入直接回车：效果同 `y`。
6. 等待程序执行结束，下载的视频会保存在同目录下对应的文件夹中。

#### 命令行参数

```shell
python XDUClassVideoDownloader.py [LIVEID] [-c COMMAND] [-s] [--no-merge]
```

- `LIVEID` （可选）：课程的 liveId，不输入则采用交互式方式获取。
- `-c COMMAND` （可选）：自定义下载命令。使用 `{url}`, `{save_dir}`, `{filename}` 作为替换标记。
- `-s` （可选）：仅下载单节课视频（`-ss`：半节课视频）。
- `--no-merge` （可选）：不合并上下半节课视频。

命令行参数对 Releases 中打包的 exe 程序也有效，在运行 exe 程序时可以直接在后面加上参数。

##### 示例

- 在 Windows 上运行打包的 exe 使用默认的下载命令仅下载单节课视频

   ```shell
   XDUClassVideoDownloader.exe 1234567890 -s
   ```

- 在 Linux 上运行源码使用自定义下载命令下载一门课程的所有视频

   ```shell
   python XDUClassVideoDownloader.py 1234567890 -c './vsd-upx save {url} -o {save_dir}\{filename} --retry-count 32 -t 16'
   ```

### Automation.py

1. 下载本项目。
2. 运行程序：
   - Windows 用户：双击 `automation.bat`。
   - Linux 用户：运行 `Automation.py`。
3. 输入 `UID` 并回车。
4. 等待程序执行结束，下载的视频会保存在同目录下对应的文件夹中。

## 注意事项

- 使用本项目下载的视频仅供个人学习使用，请勿传播或用于商业用途。
- 开发者不对使用本项目导致的任何问题负责。
- 请遵守相关法律法规，下载视频时请遵守学校相关规定。

## 使用的二进制文件

- `vsd-upx.exe`, `vsd-upx`
- `vsd.exe`, `vsd` 来自 [clitic/vsd](https://github.com/clitic/vsd)
- 使用 `upx` 压缩，来自 [upx/upx](https://github.com/upx/upx)

## 各种语言的版本

> 欢迎重写😋

| 语言 | 项目地址 |
| --- | --- |
| Python | [lsy223622/XDUClassVideoDownloader](https://github.com/lsy223622/XDUClassVideoDownloader) |
| Rust | [canxin121/live_class_downloader](https://github.com/canxin121/live_class_downloader) |
| Java | [NanCunChild/XDUClassVideoDownloader](https://github.com/NanCunChild/XDUClassVideoDownloader/tree/java-version) |
