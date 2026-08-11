---
name: repair-voice-dashboard
description: Diagnose, initialize, and safely repair the native Windows voice-production dashboard program and multi-project workspace. Use for first-run setup or when the dashboard EXE, desktop shortcut, permissions, changed drive letters or user folders, absolute paths, compatibility junctions, workspace registry, or JSON configuration are missing, invalid, or inaccessible.
---

# 修复配音桌面看板

先检查，确认问题后再修复：

```powershell
py -3 scripts/repair_dashboard.py --workspace-root <工作区> --check
py -3 scripts/repair_dashboard.py --workspace-root <工作区> --repair
```

整体迁移后显式给出路径前缀：

```powershell
py -3 scripts/repair_dashboard.py --workspace-root <工作区> --repair --old-prefix <旧前缀> --new-prefix <新前缀>
```

默认检查当前 Windows 用户桌面。隔离验收或桌面被企业策略重定向时，先设置 `VOICE_DASHBOARD_DESKTOP` 为明确的本地目录；不得借此写入未经用户批准的服务器路径。

## 修复范围

- 检查或重建项目注册表、项目 `.codex` 路径、兼容目录联接。
- 检查 `.codex-dashboard\app\配音任务看板.exe`、配置和桌面快捷方式。
- EXE 丢失且本机有 PyInstaller 时从已安装 skill 源码重建；否则要求重新运行安装包。
- 修改 JSON 前创建带时间戳的 `.bak`。
- 将结果追加到项目 `04_管理与记录\03_问题与改进\看板修复记录.md`。

不得修改媒体内容，不得上传或复制成品，不得创建或依赖 `D:\codex-board`。
