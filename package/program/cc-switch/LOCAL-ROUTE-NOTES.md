# CC Switch 内部精确模型路由版

- 上游项目：<https://github.com/farion1231/cc-switch>
- 上游版本：`v3.18.0`
- 许可：MIT，见同目录 `LICENSE`
- 本地扩展标记：`cc-switch-local-proxy-exact-model-routes-v1`

本工具包只扩展 CC Switch 自带本地代理的 `localProxyRequestOverrides`：新增 `modelRoutes` 字符串映射表，并以原始入站 `model` 做区分大小写的完全相等匹配。匹配后只替换最终上游请求体的 `model`；未命中请求保持不变。

工具包配置脚本只写入：

```json
{"localProxyRequestOverrides":{"modelRoutes":{"gpt-5.5":"deepseek-v4-pro"}}}
```

它不使用 Codex `model_catalog_json`，不创建模型目录，不使用无条件 body 覆盖，也不启动外置代理。
