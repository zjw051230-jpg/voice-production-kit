# Codex 安装入口 v2.1

新电脑让 Codex 完整读取 `START-HERE.md`。手工安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -WorkspaceRoot D:\配音工作区 -ProjectName 第一个项目 -Force
```

安装器会安装七个 skill、创建多项目工作区和隐藏索引，并部署原生 `配音任务看板.exe`、`Seedance API配置工具.exe`、CC Switch 3.18.0 内部精确路由版和三个桌面快捷方式。`-Force` 会在替换已有 CC Switch 程序前生成同目录备份，但不会覆盖用户数据库。API 工具同时进入每个项目的 `04_管理与记录\01_API配置`。安装过程不调用 Seedance、不上传文件、不包含 CC Switch 用户数据库或密钥，也不创建或复制 `D:\codex-board`。

首次打开 CC Switch 后按 `详细使用手册.md` 和 `API与CCSwitch配置.md` 配置一份或多份 provider。运行工作区 `.codex-tools\配置Seedance API.ps1`，先选择 test版或正式版，再自动整理同线路API。API Key 不得发到聊天。任何Chat发现余额不足时暂停全部流程、切换下一API并只通知“理解文本与任务”。模型脚本仍只允许映射 `5.5 -> deepseek-v4-pro`。

看板故障检查：

```powershell
py -3 "$env:USERPROFILE\.codex\skills\repair-voice-dashboard\scripts\repair_dashboard.py" --workspace-root D:\配音工作区 --check
```

安装后重启 Codex，使新 skill 被发现。
