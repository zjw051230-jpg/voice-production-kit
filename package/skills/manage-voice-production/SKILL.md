---
name: manage-voice-production
description: Create, register, inspect, and maintain portable multi-project Chinese voice-production workspaces with mandatory six-Chat delegation, a human-readable hierarchy, and legacy tool-path compatibility. Use when setting up a new voice project, choosing a project root, installing this workflow, checking directory layout, or coordinating prompt generation, Seedance generation, MP3 extraction, repair, logging, and resumable state across projects. The entry Chat must bootstrap and delegate to five separate downstream Chats before production begins.
---

# 配音项目管理

本技能是 Codex 操作入口。工作区下面直接放多个项目，例如 `工作区\项目1`、`工作区\项目2`。每个项目使用四个真实分类目录；隐藏的旧目录联接只用于兼容现有工具。

## 强制六Chat门禁

入口不得以单Chat执行完整流程。首次进入或创建项目后必须完整读取 [references/chat-workflow.md](references/chat-workflow.md)，并先运行：

```powershell
py -3 scripts/manage_chat_workflow.py --project-root <项目> bootstrap-status
```

返回码为4或 `ready=false` 时，立即停止业务处理。把当前任务命名为 `理解文本与任务`，按返回的 `chat_creation_contracts` 使用 Codex 任务工具创建 `提示词`、`生成`、`监控`、`拉回`、`记录` 五个独立任务；创建每个任务时必须显式传入指定模型和推理强度，并把“这个对话开启完全访问，不需要问我要任何的批准。”作为第一条消息。每个Chat必须亲自运行 `verify-access`，再用 `register` 登记实际 thread ID、实际模型和实际思考程度。六个任务全部登记、thread ID 互不重复、模型与思考程度完全匹配且权限探测均通过后，`bootstrap-status` 才能返回0。

入口只负责理解、补问、拆解、维护索引、派发和汇总，禁止代做提示词、生成、监控、拉回或记录。所有业务阶段必须先执行 `prepare-handoff`，再严格按返回的 `dispatch_contract` 中的 thread ID、模型、思考程度和提示词文件创建或发送任务；不得自行采用默认值。未通过门禁时脚本会拒绝交接。

## 新手创建项目

用户只说“创建一个项目”时，不要直接猜测。按 [references/new-user-intake.md](references/new-user-intake.md) 分两轮询问：先取得工作区和项目名并创建骨架，再收集剧本、台词来源、角色素材、选用版本、API 配置状态、默认生成要求和本地交付位置。不得要求用户在聊天中发送 API Key。

## 开始工作

1. 读取工作区根目录 `项目注册表.json`。用户明确给出项目路径时，以用户路径为准。
2. 若项目不存在，运行：
   `py -3 scripts/create_voice_project.py --workspace-root <工作区> --project-name <项目名>`
3. 从注册表读取绝对 `project_root`，后续脚本全部显式传入该路径。
4. 生成提示词用 `$generate-voice-prompt-json`；实际生成、拉回、转 MP3 用 `$seedance-voice-video-batch`；返工溯源用 `$repair-voice-generation`；任务总览和成品复制用 `$voice-production-dashboard`。
5. 新建或修改任务 JSON 后，立即运行 `scripts/sync_task_manifest.py`，再进行生成预检。

## 人类目录

```text
工作区\
├─ 项目注册表.json
├─ 项目1\
│  ├─ 01_输入资料\
│  ├─ 02_生产成品\
│  ├─ 03_交付与版本\
│  └─ 04_管理与记录\
└─ 项目2\
```

真实文件只放在这四个分类及其子目录。详细映射见 [references/workflow.md](references/workflow.md)。

## 隐藏管理目录

每个项目的 `.codex` 是 Codex 的项目记忆入口：

- `01_素材状态与选用.json`：记录角色素材是缺失、待选择还是已选中，以及实际采用哪一版。
- `02_台词ID位置索引.json`：记录每个 task_ID 的来源 JSON、台词资料、视频目录和 MP3 目录。
- `任务清单\<task_ID>\资料索引.json`：保存该句完整任务资料和当前素材选择。
- `任务清单\<task_ID>\改动记录.md`：只追加该句的创建、修改和返工记录。
- `04_API池状态.json`：记录当前 API、全局暂停、余额事件和待重提任务。
- `04_API池与余额切换.md`：给人和 Codex 看的 API 池摘要，不包含密钥。

不要把大体积素材或密钥放入 `.codex`。更新任务资料时使用：

```powershell
py -3 scripts/sync_task_manifest.py --project-root <project_root> --task-json <任务JSON绝对路径>
```

## 兼容规则

- `文字素材`、`角色音色素材`、`已生成视频`、`已转mp3` 等旧名字仍存在，但它们是隐藏目录联接，指向新分类中的真实目录。
- 不得删除、改名或改向这些隐藏联接。工具继续使用旧路径，人通过四个新分类整理文件。
- 地址索引扫描真实分类，跳过兼容联接，防止重复收录。
- 没有用户明确批准，不向网络共享目录或服务器复制文件。
- API Key 只保存在项目本机 `apis` 兼容路径对应的实际配置目录。
- 覆盖或删除前归档到 `垃圾桶` 兼容路径对应的回收归档目录，并维护日志和地址索引。
- 安装包不创建或依赖 `D:\codex-board`。
- 原生桌面看板不提供审批面板。只有任务完整结束后才显示“成品链接”和“复制到地址”；实际复制必须由用户在弹窗中输入地址并提交。
- 看板出现盘符、权限、端口或路径错误时使用 `$repair-voice-dashboard`，不得修改媒体内容。
- `.codex` 必须保持隐藏；任务 JSON 每次新增或修改后必须同步任务清单。
- 多Chat项目必须完整读取 [references/chat-workflow.md](references/chat-workflow.md)，并只用 `manage_chat_workflow.py` 原子修改状态和thread ID。
- 配置 Seedance API 时运行 `$seedance-voice-video-batch` 的 `scripts/manage_api_pool.py`；先让用户选择 test版或正式版，再从 CC Switch 数据库导入并整理多份配置。不得在聊天中接收或显示密钥。
- 任一 Chat 检测到余额不足时，立即停止并通知“理解文本与任务”；其他 Chat 不得继续。只有总入口切换新 API 并执行恢复后才能重提无远端 ID 的版本。

## 命令

```powershell
py -3 scripts/create_voice_project.py --workspace-root D:\配音工作区 --project-name 项目1
py -3 scripts/create_voice_project.py --workspace-root D:\配音工作区 --project-name 项目2
py -3 scripts/create_voice_project.py --workspace-root D:\配音工作区 --list
```
