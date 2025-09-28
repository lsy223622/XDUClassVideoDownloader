## XDUClassVideoDownloader – AI Agent 快速协作指令 (精简版)
面向西电录直播平台：单课/按学期批量下载；已完全切换为“直下 MP4 + 可选 FFmpeg 无损合并”。

### 1. 体系/数据流（理解后再改）
CLI (XDUClassVideoDownloader.py / Automation.py) → 参数与交互 → 验证 (validator) → 认证与配置 (config:get_auth_cookies / safe_write_config) → 接口调用 (api: rate_limit + Retry session) → 视频信息解析 → 下载 (downloader: 断点续传/多线程分片/校验/可选合并) → 输出目录 & CSV → 日志 (logs/*.log)。

### 2. 核心模块职责
api.py：请求封装 + 重试 + rate_limit + HTML/JSON 提取 + 登录获取三 Cookie。
downloader.py：HEAD 探测 → (可多线程 Range) 下载 .tmp/.partN → 完整性校验 → 原子 rename → 条件 FFmpeg 拼接 (-c copy)。
config.py：认证/自动化配置读写；安全写入 + logs 目录时间戳备份；向后兼容增量字段。
utils.py：日志统一 setup_logging；文件名清洗 remove_invalid_chars；线程数自适应；通用异常 handle_exception。
validator.py：集中参数与输入合法性；复用避免散落的 if 检查。

### 3. 约定/不可破坏的行为
输出目录命名：`{YEAR}年{COURSECODE}{COURSENAME}`；文件名模式保持（周/星期/节次 + -pptVideo / -teacherTrack）。
仅下载“已结束”场次；失败需有限次数重试，再输出清晰日志而非静默。
合并失败不影响原始分段文件；成功后清理源分段。
不要改变 auth.ini 的键：`_d`,`UID`,`vc3`；新增认证字段需保持兼容回落。
merge 文件夹中的两个文件独立于主要程序，除非需求明确指出，否则所有修改指令默认不涉及该文件夹。

### 4. 新增功能时遵循的模式
网络：使用 create_session() + get_authenticated_headers(); 若需新端点，沿用现有异常与重试结构。
写配置：通过 safe_write_config(…, backup=True)；不能直接 open().write()。
下载扩展：保持 verify_file_integrity 流程；多线程逻辑只在 Accept-Ranges 且 size≥MIN_SIZE_FOR_MULTITHREAD 时启用。
日志：始终用 setup_logging(模块名)；仅用户交互允许 print，业务错误走 logger + 友好提示。
CLI 变更：新增参数需保证 --help <10s 返回；默认不阻塞在网络检查失败。

### 5. 测试与验证
测试文件命名：test_*.py；不提交一次性脚本。

### 6. 常见坑与处理
403/404：多为认证过期 → 触发重新获取 cookies；切勿“自动重试无上限”。
版本检查失败：忽略；不得中断主逻辑。
非法文件名：依赖 remove_invalid_chars；不要自造替换正则。
合并失败：仅记录 warning，不回滚已完成下载。

### 7. 快速本地环境 (Windows 优先)
Python 3.8+；依赖：requests tqdm psutil；可选 pytest。
FFmpeg 放根目录或 PATH（downloader 自动检测，缺失则跳过合并）。

### 8. 可安全扩展点示例
新增视频类型筛选：扩展 CLI 枚举 → 传递到下载过滤 → 保持 CSV 列顺序不变（可追加列末尾）。
增加健康检查命令：独立子命令读取 auth/探测关键 URL HEAD，返回结构化 JSON（勿触发实际大文件下载）。

### 9. 禁止事项
禁止引入未讨论的重量级依赖 / GUI / 数据库存储。
禁止在日志或异常中回显完整 Cookie/密码。
禁止改写现有文件命名/目录模式（影响增量与去重）。
除一次性 test_*.py，不要新增其他文件；若需输出任务总结等 Markdown，写入 `copilot_reports` 目录，该目录已在 `.gitignore` 中排除，不要提交。

### 10. 快速核对清单（修改后自检）
参数验证集中在 validator? 日志是否使用统一 logger? 配置写入是否走 safe_write_config? 新网络调用是否有超时与重试? 文件名是否经 remove_invalid_chars? 失败路径是否有清晰用户级提示? 新增依赖是否同步更新 `requirements.txt` 并在反馈中注明测试情况?

### 11. 注释与说明要求
注释仅描述当前代码逻辑，不要记录“把什么改成了什么”之类的历史信息。
除通常以英文表达的专有名词外，注释统一使用中文。汉字与英文、汉字与阿拉伯数字之间需添加一个空格；汉字标点与英文或阿拉伯数字之间不加空格；汉字与半角标点之间不加空格。
在回复用户或提交变更说明时，需要逐项解释每处修改的目的与价值，让原因清晰可追溯。

反馈：若需要更详细长文档，可查看历史提交；本文件保持精简。请指出任何含糊或缺失点以便迭代。