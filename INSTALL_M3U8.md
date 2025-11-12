# M3U8下载功能说明

## 概述

程序支持下载2024及以前学年的课程，这些课程使用M3U8流媒体格式。

程序使用内置的轻量级M3U8下载实现，无需额外的Python依赖。

## FFmpeg依赖

如果需要将下载的TS格式转换为MP4格式，需要安装FFmpeg：

- **Windows**: 从 https://ffmpeg.org/download.html 下载并添加到PATH
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg` (Ubuntu/Debian) 或 `sudo yum install ffmpeg` (CentOS/RHEL)

**注意**：FFmpeg仅用于格式转换（remuxing），不进行重新编码，因此转换速度非常快且不损失画质。

## 功能特性

### 内置M3U8下载器

- ✅ 多线程并发下载TS分片
- ✅ 自动合并分片为完整视频
- ✅ 智能错误重试机制
- ✅ 支持特殊URL格式（如`cloud://`）
- ✅ 无需额外Python依赖
- ✅ 轻量级实现（0额外体积）

### 可选的FFmpeg转封装

- ✅ TS到MP4格式转换（使用`-c copy`，无损转换）
- ✅ 优化的MP4文件结构（支持流媒体播放）
- ✅ 快速转换（不重新编码）

## 测试

运行测试脚本验证M3U8下载功能：

```bash
python test_m3u8_download.py
```

测试脚本会：
1. 使用内置下载器下载示例M3U8视频
2. 显示下载结果和文件信息

## 使用说明

程序会自动检测课程的学年：

- **2024及以前**: 自动使用M3U8格式下载
- **2025及之后**: 使用MP4格式下载

无需手动配置，程序会根据课程数据自动选择合适的下载方式。

## 故障排除

### 问题：M3U8下载失败，提示404错误

**原因**：URL拼接问题或cookies过期

**解决**：
1. 确保已正确配置认证信息（_d, UID, vc3 cookies）
2. 检查网络连接
3. 查看日志文件了解详细错误信息

### 问题：需要将TS格式转换为MP4

**解决**：使用程序提供的`remux_ts_to_mp4()`函数：

```python
from downloader import remux_ts_to_mp4

# 转换TS到MP4
success = remux_ts_to_mp4("video.ts", "video.mp4", remove_ts=False)
```

### 问题：FFmpeg not found

**原因**：未安装FFmpeg或未添加到PATH

**解决**：
1. 安装FFmpeg（见上方安装说明）
2. 确保FFmpeg在系统PATH中：
   ```bash
   ffmpeg -version
   ```

## 更多信息

- [FFmpeg官网](https://ffmpeg.org/)
- [FFmpeg下载页面](https://ffmpeg.org/download.html)
- [M3U8规范](https://datatracker.ietf.org/doc/html/rfc8216)
