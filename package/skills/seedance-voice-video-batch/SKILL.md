---
name: seedance-voice-video-batch
description: Batch-produce cloned-voice Seedance dialogue videos and extracted MP3 files from six-field task JSON in a selected voice project. Use for actual generation, sdc, submit-only, resume, pull-back, download, MP3 extraction, reference-material lookup, or re-generation. Prompt-only requests belong primarily to generate-voice-prompt-json.
---

# Seedance 配音批量生产

先用 `$manage-voice-production` 确定唯一 `project_root`。所有命令必须显式传 `--project-root`，禁止依赖旧电脑路径或跨项目搜索素材。

## 必读

- API 操作前读 [references/seedance-api.md](references/seedance-api.md)。
- 新建或校验任务时读 [references/task-format.md](references/task-format.md)。

## 输入和素材

- 任务：`<project_root>\文字素材\<task_id>+N个任务.json`。
- 每项只有六字段：`剧本名字`、`task_ID`、`角色名字`、`台词`、`时长`、`提示词`。
- 参考素材：`<project_root>\角色音色素材\<剧本名字>\<角色名字>`。
- 每次请求至少上传一个视频。有明确要求时按要求选择；否则上传该角色目录中全部支持的 MP3、MP4。
- 每个输出只能保证完整包含指定台词，不要擅自因附加声音删除整个版本；用户明确要求语义裁剪时才裁剪。

## 固定生成参数

- 480p，竖屏 9:16。
- 未指定时长用 4 秒。
- 每句默认四个独立版本。
- 使用 `--max-workers` 并行处理，不得逐项串行生成。

## 执行

首次配置或更换 API：

优先让用户双击桌面的 `Seedance API配置工具`，也可运行项目 `04_管理与记录\01_API配置` 内的同名 EXE。选择项目和 test版/正式版后，在遮罩输入框中逐份添加 API Key；添加、删除和设为当前都立即写盘，底部保存按钮用于确认或重试。程序自动去重、整理 API 池并生成当前配置，密钥不得出现在聊天、索引、隐藏说明或日志中。

命令行兼容入口：

```powershell
py -3 scripts/manage_api_pool.py --project-root <project_root> import
```

程序先让用户选择 test版或正式版，从 CC Switch 导入同线路全部可用 provider，自动整理到 `apis\api_pool`，并把当前项复制为 `apis\doubao_api_config.json`。全程不得输出 API Key。

每次新建或修改任务 JSON 后，先用 `$manage-voice-production` 的 `scripts/sync_task_manifest.py` 同步 `.codex` 任务清单。若对应角色素材状态是 `缺失`、`已有待选择` 或 `待确认`，停止该角色提交并向用户补问；只有 `已选中` 才继续预检。

先只读预检：

```powershell
py -3 scripts/run_pipeline.py --project-root <project_root> --dry-run --task-id <task_id>
```

正常生成并拉回：

```powershell
py -3 scripts/run_pipeline.py --project-root <project_root> --run --direct-mp3 --task-id <task_id> --max-workers 16
```

“拿到 ID 停”：

```powershell
py -3 scripts/run_pipeline.py --project-root <project_root> --submit-only --task-id <task_id> --max-workers 16
```

“拉回”：只查询保存的 ID，不重新提交、不上传素材、不用 `--force-regenerate`。

```powershell
py -3 scripts/run_pipeline.py --project-root <project_root> --resume-only --poll-once --direct-mp3 --task-id <task_id> --max-workers 16
```

输出视频进入 `已生成视频\<任务名>`，完整音轨 MP3 进入 `已转mp3\<任务名>`，远端状态保存在输出目录 `.seedance-state.json`。

## 余额不足

- 流水线明确识别余额不足时退出码为 `42`，写入 `.codex\04_API池状态.json` 并暂停全部Chat。
- 当前Chat必须把程序返回的紧急消息发送给 `理解文本与任务` 的thread ID，然后停止。
- API池有下一份配置时自动激活。总入口运行：

```powershell
py -3 scripts/manage_api_pool.py --project-root <project_root> resume-after-balance
```

- 随后用原任务参数重新提交，不加 `--force-regenerate`。只有没有远端ID的版本会重提；已经成功提交的版本不得重复计费。

## 文件和反馈

- 所有操作追加到 `0日志信息\任务操作日志.md`。
- 新文件、移动、改名、归档后更新 `0日志信息\地址索引.json`。
- 覆盖或删除前把旧文件归档到 `垃圾桶\rbsNNNNNNN.ext`，保留历史路径。
- 返工原因追加到 `问题与改进log\问题建议.md`。
- 未经用户明确批准，不复制到 UNC 路径或共享服务器。
- API Key 只保存在项目本机私有配置中，不输出到聊天或日志。
- 本安装包不使用或创建 `D:\codex-board`。
