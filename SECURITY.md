# 安全说明

不要在 Issue、提交、Pull Request 或聊天中发送 API Key、访问令牌、CC Switch 数据库或生产素材。

允许进入仓库的配置只能是无密钥示例。发布前必须检查：

- 不含 `doubao_api_config.json`、`.env`、数据库和 API 池运行数据。
- 不含 `.codex`、`.codex-dashboard`、`.codex-tools` 等本机状态。
- 不含测试工作区、生产音视频、日志、缓存或桌面快捷方式。
- CC Switch 模型映射只能修改显示名严格等于 `5.5` 的一项。
