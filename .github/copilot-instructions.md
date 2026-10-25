## XDUClassVideoDownloader – AI Agent 快速协作指令

面向西电录直播平台：单课/按学期批量下载；已切换为“直下 MP4 + 可选 FFmpeg 无损合并”。

### 1. 架构概览

```
XDUClassVideoDownloader.py / Automation.py / WebUI.py
    ↓ 兼容启动器
xduclassvideodownloader.cli / xduclassvideodownloader.web
    ↓ 仅调用公开 Core facade
xduclassvideodownloader.core
    ├─ config / auth / platform
    ├─ downloader / courses / services
    └─ utils / validator / paths
```

根目录的三个入口和 `api.py`、`config.py`、`downloader.py`、`utils.py`、`validator.py` 保留 5.x 兼容名称；新代码必须依赖包内模块，不得反向依赖根目录兼容 shim。

### 2. 模块职责与依赖边界

| 模块 | 职责 |
|------|------|
| **core.platform** | HTTP 请求、重试、频率限制、平台数据解析与更新检查；不得导入 `core.config` |
| **core.auth** | IDS/超星/二维码认证协议、认证缓存与持久化协调 |
| **core.config** | INI 读写、备份、认证设置和自动化课程选择持久化；不得承载网络登录 |
| **core.downloader** | MP4/M3U8 下载、校验、字幕与 FFmpeg 合并；认证状态由服务层显式传入 |
| **core.services/courses** | 默认学期、课程扫描、单课和批量下载编排 |
| **core.utils/validator/paths** | 叶子工具、业务校验、运行目录与打包资源路径 |
| **cli** | argparse、交互提示、用户输出和退出码；实际操作调用 Core facade |
| **web** | Flask 工厂、访问控制、认证/下载/设置/媒体库路由；不得访问 Core 私有符号 |

Core 不得 import Flask 或 `xduclassvideodownloader.web`。Web/CLI 不得 import Core 私有名称、直接修改认证缓存、直接调用 `core.downloader` 或根目录业务模块。

### 3. 不可破坏的约定

- Python 最低版本为 3.8，推荐 3.11。
- 保持 `python XDUClassVideoDownloader.py`、`python Automation.py`、`python WebUI.py` 以及三个 `.bat` 文件的用途。
- 输出目录命名：`{YEAR}年{COURSECODE}{COURSENAME}`。
- 文件名保留周、星期、节次以及 `pptVideo` / `teacherTrack` 契约。
- 仅下载“已结束”场次；失败有限次重试后输出清晰日志。
- 合并失败不删除原始分段；成功后才清理源分段。
- `auth.ini` 的 `_d`、`UID`、`vc3` 键保持兼容。
- `merge/` 独立于主程序，除非明确要求，否则不修改。
- 不引入数据库、ORM、依赖注入容器、异步框架、React/Vue/Node 构建链或新的 Web 框架。

### 4. 安全和实现规则

- 网络调用统一放在 Core 的 platform/auth，必须有超时和有限重试。
- 配置写入使用 `safe_write_config(..., backup=True)`，禁止绕过 Core 直接写配置。
- 日志、异常、测试输出不得包含完整 Cookie、密码或认证请求体。
- `--help` 必须快速返回，不触发登录或长时间网络阻塞。
- 保持 `remove_invalid_chars`、文件完整性校验、断点续传和现有媒体命名行为。
- 运行期可变文件（配置、日志、下载目录）与只读打包资源（Web 静态文件）必须使用不同路径解析。

### 5. 修改后自检

- [ ] 新代码是否位于正确的 package 模块？
- [ ] Core 是否保持无 Flask/Web 依赖？
- [ ] Web/CLI 是否只调用公开 Core facade？
- [ ] 配置写入和认证缓存是否走 Core 公共接口？
- [ ] 参数校验、文件名和重试行为是否保持兼容？
- [ ] 非网络测试是否覆盖失败路径和旧配置？
