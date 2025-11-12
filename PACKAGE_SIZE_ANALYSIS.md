# PyInstaller 打包体积分析

## M3U8下载功能实现方案

程序使用**内置轻量级实现**来处理M3U8下载，无需额外的Python依赖库。

## 体积影响估算

### Python库部分

- **内置M3U8下载器**: 0 MB（无额外依赖）

**总计**: **0 MB** 额外体积

### FFmpeg 部分（可选，用于TS到MP4转换）

⚠️ **重要提示**: 如果需要TS到MP4格式转换，可以选择打包FFmpeg

如果要打包 FFmpeg 到可执行文件中：
- **最小编译版FFmpeg** (仅H264/AAC支持): ~10-20 MB
- **完整版ffmpeg.exe** (Windows): ~60-100 MB
- **完整版ffmpeg** (Linux): ~50-80 MB
- **完整版ffmpeg** (macOS): ~50-80 MB

**推荐**: 使用最小编译版FFmpeg，仅包含H264视频和AAC音频编解码器，体积可控制在10-20MB。

### 总体积影响

| 配置 | 额外体积 | 说明 |
|-----|----------|------|
| **仅内置下载器** | 0 MB | 不包含FFmpeg，TS格式视频 |
| **打包最小FFmpeg** | ~10-20 MB | 支持TS到MP4转换，推荐配置 |
| **打包完整FFmpeg** | ~50-100 MB | 包含完整FFmpeg功能 |

## 实现方案对比

| 实现方式 | 额外依赖 | 体积增加 | 功能完整性 |
|---------|---------|---------|-----------|
| **内置下载器（当前）** | 0个额外库 | 0 MB | ✅ 完整（非加密M3U8） |
| **+ 最小FFmpeg** | 仅FFmpeg二进制 | 10-20 MB | ✅ 完整 + TS转MP4 |
| **外部库方案** | 3个库 + FFmpeg | 15-120 MB | ✅ 完整（加密支持） |

## 推荐配置方案

### 方案1: 不打包FFmpeg（最轻量）

**配置**:
- 仅内置M3U8下载器
- 不打包FFmpeg二进制
- 体积增加：0 MB

**优势**:
- 体积最小
- 无额外依赖
- 适合技术用户

**缺点**:
- 输出为TS格式
- 需要用户自行转换或安装FFmpeg

### 方案2: 打包最小FFmpeg（推荐）

**配置**:
- 内置M3U8下载器
- 打包最小编译版FFmpeg（仅H264/AAC）
- 体积增加：~10-20 MB

**优势**:
- 体积适中
- 自动TS到MP4转换
- 开箱即用

**推荐**: 这是最佳平衡方案，提供完整功能的同时保持较小体积。

### 方案3: 打包完整FFmpeg

**配置**:
- 内置M3U8下载器
- 打包完整版FFmpeg
- 体积增加：~50-100 MB

**优势**:
- 功能最完整
- 支持所有FFmpeg操作

**缺点**:
- 体积较大
- 大部分功能用不到

## PyInstaller配置示例

### 不打包FFmpeg（最小体积）

```python
# build.spec
a = Analysis(
    ['main.py'],
    binaries=[],  # 不包含FFmpeg二进制
    ...
)
```

程序会在运行时从系统PATH查找FFmpeg。

### 打包最小FFmpeg（推荐）

```python
# build.spec
a = Analysis(
    ['main.py'],
    binaries=[
        ('path/to/ffmpeg_min.exe', '.'),  # Windows最小版
        # 或
        ('path/to/ffmpeg_min', '.'),      # Linux/macOS最小版
    ],
    ...
)
```

**如何获取最小FFmpeg**:
1. 从 https://github.com/BtbN/FFmpeg-Builds/releases 下载
2. 选择带有 `lgpl` 和 `shared` 标签的版本（体积较小）
3. 或者自行编译，仅包含 libx264 和 libfdk-aac

### 打包完整FFmpeg

```python
# build.spec
a = Analysis(
    ['main.py'],
    binaries=[
        ('path/to/ffmpeg.exe', '.'),  # Windows完整版
        # 或
        ('path/to/ffmpeg', '.'),      # Linux/macOS完整版
    ],
    ...
)
```

## 实测数据参考

基于实际打包的预估数据：

| 配置 | 原始大小 | 内置下载器 | FFmpeg | 总大小 |
|-----|----------|-----------|--------|--------|
| **仅内置下载器** | ~30 MB | +0 MB | - | ~30 MB |
| **+ 最小FFmpeg** | ~30 MB | +0 MB | +15 MB | ~45 MB |
| **+ 完整FFmpeg** | ~30 MB | +0 MB | +70 MB | ~100 MB |

## 推荐配置

### 对于GitHub发布

推荐提供两个版本：

1. **标准版（推荐）**:
   - 内置M3U8下载器
   - 打包最小FFmpeg
   - 体积: ~45 MB
   - 支持TS到MP4自动转换
   - 适合大多数用户

2. **Lite版**:
   - 内置M3U8下载器
   - 不打包FFmpeg
   - 体积: ~30 MB
   - 输出TS格式（用户可自行转换）
   - 适合技术用户

### 使用说明

在README中说明：
```markdown
## 下载M3U8视频（2024及以前的课程）

程序使用内置M3U8下载器，无需安装额外Python库。

### 标准版（推荐）
- 自动下载并转换为MP4格式
- 开箱即用，无需额外配置

### Lite版
- 下载TS格式视频
- 如需转换为MP4，请安装FFmpeg: https://ffmpeg.org/download.html
- 使用程序提供的转换功能或FFmpeg命令行工具
```

## 结论

使用内置M3U8下载器的优势：

- **零依赖**: 0 MB Python库依赖
- **轻量级**: 不打包FFmpeg时仅 ~30 MB
- **推荐配置**: 打包最小FFmpeg，总体积 ~45 MB
- **灵活性**: 用户可以选择是否需要格式转换

**当前实现**:
- ✅ 内置轻量级M3U8下载器（无额外依赖）
- ✅ 可选的FFmpeg转封装支持
- ✅ 适合PyInstaller打包
- ✅ 体积可控（0-45 MB额外体积）
