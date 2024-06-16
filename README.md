# XDUClassVideoDownloader

![GitHub repo size](https://img.shields.io/github/repo-size/lsy223622/XDUClassVideoDownloader)
![GitHub Repo stars](https://img.shields.io/github/stars/lsy223622/XDUClassVideoDownloader)

![Static Badge](https://img.shields.io/badge/QQ-2413282135-white?logo=tencentqq&logoColor=white&labelColor=blue)
![Static Badge](https://img.shields.io/badge/HOME-lsy223622.com-white?labelColor=396aa9)
![Static Badge](https://img.shields.io/badge/BLOG-blog.lsy223622.com-white?labelColor=a6c4c2)

## 使用须知

- 请先阅读此 README 再使用本项目。
- 如果遇到问题可以联系上面的 QQ。
- 欢迎提出建议和改进意见，能 PR 的话就更好啦。
- 如果觉得好用请给个 Star 哦。

## 项目简介

- 本项目是一个用于下载西安电子科技大学录直播平台课程视频的工具。
- 只需输入任意一节课的 `liveId`，即可自动下载该课程的所有视频。

> `liveId` 是课程直播的唯一标识，可以在课程直播页面的 URL 中找到，如：`http://newesxidian.chaoxing.com/live/viewNewCourseLive1?liveId=12345678` 中的 `12345678`。

- 同时会保存所有视频的 `m3u8` 链接到对应的 `csv` 表格中，方便使用其他方式下载。
- 下载时会自动检查之前是否下载过同一节课，如果已经下载则会跳过。所以可以在一学期中的多个时候随时下载新增的录播视频。
- 下载的视频按照课程和时间整理，下载多个课程的视频也不会冲突。
- 文件夹和 `csv` 表格命名规则：年份-课程号-课程名。
- 课程视频命名规则：课程号-课程名-年月日-周次-节号-视频来源。

## 使用方法

### 使用前的准备步骤

1. 安装 `Python`（我用的 3.12）。
2. 使用 `pip` 安装依赖：`requests` , `tqdm`。~~如果缺别的依赖那就装别的依赖~~
3. 安装 `ffmpeg` 并将其添加到环境变量。

### 使用

1. 下载本项目。
2. 运行程序：
   - Linux 用户：运行 `XDUClassVideoDownloader.py`。
   - Windows 用户：双击 `windows_run.bat`。
3. 输入 `liveId` 并回车。
4. 等待程序执行结束，下载的视频会保存在同目录下对应的文件夹中。

## 命令行参数

```shell
python XDUClassVideoDownloader.py [LIVEID] [-c COMMAND] [-s]
```

- `LIVEID` （可选）：直播ID。如果不输入，将采用交互式方式获取。
- `-c COMMAND` （可选）：自定义下载命令。使用 `{url}`, `{save_dir}`, `{filename}` 作为替换标记。
- `-s` （可选）：仅下载单集视频。

示例:

```shell
# 在 Windows 上仅下载单集视频
python XDUClassVideoDownloader.py 1234567890 -c "N_m3u8DL-RE.exe \"{url}\" --save-dir \"{save_dir}\" --save-name \"{filename}\" --check-segments-count False --binary-merge True" -s

# 在 Linux 上下载一门课程的所有视频
python XDUClassVideoDownloader.py 1234567890 -c './N_m3u8DL-RE "{url}" --save-dir "{save_dir}" --save-name "{filename}" --check-segments-count False --binary-merge True'
```

## 注意事项

- 使用本项目下载的视频仅供个人学习使用，请勿传播或用于商业用途。
- 开发者不对使用本项目导致的任何问题负责。
- 请遵守相关法律法规，下载视频时请遵守学校相关规定。

## 使用的二进制文件

- `N_m3u8DL-RE.exe` , `N_m3u8DL-RE` 来自 [nilaoda/N_m3u8DL-RE](https://github.com/nilaoda/N_m3u8DL-RE)

## 各种语言的版本

> 欢迎重写😋

| 语言 | 项目地址 |
| --- | --- |
| Python | [lsy223622/XDUClassVideoDownloader](https://github.com/lsy223622/XDUClassVideoDownloader) |
| Rust | [canxin121/live_class_downloader](https://github.com/canxin121/live_class_downloader) |
| Java | [NanCunChild/XDUClassVideoDownloader](https://github.com/NanCunChild/XDUClassVideoDownloader/tree/java-version) |
