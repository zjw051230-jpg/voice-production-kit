---
name: repair-voice-generation
description: Trace a supplied voice or video file through the selected voice project's provenance and hidden Codex task records, recover the exact source dialogue and prompt, record user feedback, and prepare or generate repaired Seedance versions. Use for 修复、返工、重生、重做 or changes to emotion, voice, pace, pauses, wording, or performance.
---

# 配音返工与修复

先用 `$manage-voice-production` 确定唯一 `project_root`。不得搜索其他项目补齐同名角色或台词。

## 定位来源

优先读取：

1. `<project_root>\.codex\02_台词ID位置索引.json`
2. `<project_root>\.codex\任务清单\<task_ID>\资料索引.json`
3. `<project_root>\0日志信息\地址索引.json`
4. 原六字段任务 JSON

必要时运行：

```powershell
py -3 scripts/resolve_repair_source.py --project-root <project_root> --file <用户文件绝对路径>
```

只有来源 task_ID、角色、台词和原提示词一致时才能返工。存在冲突时停止并让用户确认。

## 修复流程

1. 记录用户指出的问题和希望保留的部分。
2. 复制原任务资料，不改台词，除非用户明确要求改词。
3. 只修改与反馈相关的提示词维度；音色素材沿用 `.codex\01_素材状态与选用.json` 中已选中版本。
4. 新建或修改任务 JSON 后运行 `sync_task_manifest.py`。
5. 默认生成四份；用户指定数量时按用户要求。
6. 返工结果追加到该句 `改动记录.md`，同时追加项目问题日志和操作日志。
7. 覆盖旧成品前先归档到 `垃圾桶` 兼容路径对应的回收归档目录。

实际提交和拉回必须使用 `$seedance-voice-video-batch` 并显式传 `--project-root`。
