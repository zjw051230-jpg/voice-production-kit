---
name: voice-production-dashboard
description: Install, launch, inspect, and operate the native Windows multi-project voice-production task dashboard. Use when users ask to view all voice task statuses in a desktop program, open completed output folders, copy completed deliverables through the guarded address dialog, rebuild the dashboard EXE, or configure its workspace.
---

# 配音任务桌面看板

这是 Windows 桌面程序，不是网页服务。安装后的入口为：

```text
<工作区>\.codex-dashboard\app\配音任务看板.exe
```

安装器同时创建桌面快捷方式 `配音任务看板.lnk`。程序读取工作区 `项目注册表.json`，每 2 秒扫描所有项目的任务 JSON、`.seedance-state.json`、视频和 MP3。

## 操作规则

- 不显示审批面板。
- 每句配音任务显示项目、剧本、角色、台词、素材状态，以及终态、成功、失败、运行中、已下载五项计数。
- 远端终态固定按 `成功数 + 失败数 = 总数` 判断。部分失败但仍有运行项时保持“生成中”，不能提前判整批失败或开始拉回。
- 整批终态后，只要至少一个成功版本且全部成功版本均为 `downloaded`、视频和 MP3 实际存在，就显示两个按钮：`成品链接`、`复制到地址`；失败版本不要求媒体文件。
- `成品链接` 打开对应 MP3 成品文件夹。
- `复制到地址` 打开独立输入弹窗。只有按 `提交并复制` 才执行复制。
- 输入阶段删除双引号，执行阶段再次拒绝双引号。
- 只复制，不移动、不删除、不覆盖；目标任务文件夹已存在时整体拒绝。

## Codex 操作

启动：

```powershell
Start-Process '<工作区>\.codex-dashboard\app\配音任务看板.exe'
```

离线扫描验收可运行：

```powershell
py -3 scripts/voice_dashboard.py --workspace-root <工作区> --scan-json
```

权限、盘符、配置、快捷方式或程序损坏时使用 `$repair-voice-dashboard`。不得创建或依赖 `D:\codex-board`；该目录只能作为外观和程序结构参考，不能打进安装包。
