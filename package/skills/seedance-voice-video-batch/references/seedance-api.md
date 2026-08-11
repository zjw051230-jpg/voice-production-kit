# q1 Seedance 2.0 API 操作规范

## 配置与鉴权

使用 `manage_api_pool.py import` 先选择 test版或正式版，再从 CC Switch 数据库导入。多份配置整理在 `apis\api_pool\<线路>`，当前活动配置固定复制到项目 `apis\doubao_api_config.json`：

```json
{
  "api_key": "你的API_KEY",
  "base_url": "https://chat.q1.com/v1",
  "model": "doubao-seedance-2.0"
}
```

API Key 只能保存在本地。所有请求携带 `Authorization: Bearer <API_KEY>`；不得在聊天、代码、日志或版本库中暴露密钥或完整鉴权头。

API池索引和 `.codex\04_API池与余额切换.md` 不得包含密钥。明确余额不足时必须立即停止所有Chat流程，自动切换下一份配置并通知“理解文本与任务”；恢复后只重提没有远端ID的版本。

## 上传素材

上传接口不带 `/v1`。

每次流水线运行都重新上传参考素材，不复用前一次运行的上传 URL。角色目录有 `reference.json` 时按其要求选择；没有时上传该角色目录内全部支持的本地音视频。无论音频素材如何，每个生成请求都必须引用一个本轮已上传的视频；API 的 `reference_video` 与 `reference_audio` 是单值字段，多份参考素材通过四个版本轮换使用，不能擅自改成数组。

- 视频：`POST https://chat.q1.com/api/upload/video`，multipart 字段为 `file=<MP4/MOV>`、`convert=false`。
- 音频：`POST https://chat.q1.com/api/upload/audio`，multipart 字段为 `file=<MP3/WAV>`、`convert=false`、`compress=false`。
- 读取返回 JSON 中的 `filename`，并将其作为生成接口的参考素材 URL。

## 提交生成

`POST https://chat.q1.com/v1/videos`，请求体：

```json
{
  "model": "doubao-seedance-2.0",
  "prompt": "生成要求和台词约束",
  "n": 1,
  "size": "480x854",
  "seconds": "4",
  "aspect_ratio": "9:16",
  "quality": "480p",
  "generate_audio": true,
  "reference_video": "上传视频返回的filename",
  "reference_audio": "上传音频返回的filename"
}
```

固定 `n: 1`，四版通过四个并行请求产生。`seconds` 必须是字符串；缺省为 `"4"`。保存每个成功响应的任务 `id`。服务可能根据参考视频保留接近原始尺寸，所以下载后仍需检查实际画幅。

## 查询与下载

- 状态：`GET https://chat.q1.com/v1/videos/{任务ID}`。
- 状态值：`queued`、`in_progress`、`completed`、`failed`。
- 每 10–15 秒查询一次；进度不变不代表失败，不得重复提交。
- 下载：`GET https://chat.q1.com/v1/videos/{任务ID}/content`，携带鉴权并允许重定向，保存为 MP4。

## 异常

- `401/403`：检查密钥、权限或余额。
- `404`：检查地址；上传接口不能拼在 `/v1` 后。
- `422`：检查字段类型、尺寸、时长和素材 URL。
- `failed`：记录返回的 `error`，修改相关提示词/参数后只重做失败版本。
- 网络超时：先用已保存 ID 查询，不直接重新生成。
- 中文统一使用 UTF-8。
