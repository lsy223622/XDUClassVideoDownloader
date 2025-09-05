# 新版认证说明

## 重要更新

由于学校录播平台API更新，现在需要用户提供身份验证信息才能下载视频。

## 如何获取认证信息

### 步骤 / Steps:

1. **打开浏览器并登录**
   - 访问 <https://chaoxing.com/>，使用您的超星账号登录
   - 或者访问 <https://learning.xidian.edu.cn>，使用您的学校账号登录

2. **打开录直播平台**
   - 访问 <https://i.mooc.chaoxing.com/>

3. **打开 Cookies 菜单**
   - 点击浏览器地址栏左侧的锁形图标
   - 选择 "Cookies" 选项

4. **复制 Cookie 信息**
   - 在 `chaoxing.com` 的 Cookies 中找到以下三个值：
     - `_d`
     - `UID`
     - `vc3`

### 示例 Cookie 格式

```text
_d=114514; UID=1919810; vc3=qwertyuiop
```

## 使用说明

### 首次运行

1. 运行程序：`python XDUClassVideoDownloader.py` 或 `python Automation.py`
2. 程序会提示您输入三个认证值
3. 按顺序输入：_d, UID, vc3
4. 信息会自动保存到 `auth.ini` 文件中

### 后续运行

- 程序会自动读取已保存的认证信息
- 无需再次输入，除非认证信息过期

## 注意事项

1. **保护您的认证信息**
   - 不要与他人分享您的 Cookie 信息
   - `auth.ini` 文件包含敏感信息，请妥善保管

2. **认证信息过期**
   - Cookie 可能会过期，如果下载失败请重新获取
   - 删除 `auth.ini` 文件可以重新设置认证信息

3. **新的视频格式**
   - 视频现在直接下载为 MP4 格式
   - 如果需要合并视频，需要 FFmpeg

4. **配置文件**
   - `auth.ini`: 存储认证信息
   - `config.ini`: 存储课程配置（自动化模式）

## 故障排除

### 如果遇到认证错误

1. 确认您已正确登录录播平台
2. 重新获取 Cookie 信息（可能已过期）
3. 删除 `auth.ini` 文件并重新运行程序
4. 确保复制的 Cookie 值完整且正确

### 如果下载失败

1. 检查网络连接
2. 确认课程视频确实存在
3. 尝试重新获取认证信息
4. 检查是否有新的 API 变更

## 技术变更说明

- **新API端点**: `http://newes.chaoxing.com/xidianpj/frontLive/playVideo2Keda`
- **视频格式**: 直接 MP4 文件而非 M3U8 流
- **认证方式**: 基于 Cookie 的身份验证
- **下载方式**: Python 直接下载，无需外部工具
