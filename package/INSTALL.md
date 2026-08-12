# v2.2 安装

前置环境统一由 `env4BC` 安装和维护。本包只安装七个配音 skill、创建或补齐多项目工作区，并部署原生 `配音任务看板.exe`。

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -WorkspaceRoot "D:\配音工作区" -ProjectName "项目名"
```

安装器检测 `%LOCALAPPDATA%\env4BC\install-state.json`；缺失时只警告。它不会读取或修改 CC Switch 用户数据库、provider、API Key 或环境程序。

更新只处理清单声明的工具文件。同名 skill 只有用户批准并使用 `-Force` 时才先备份后替换。项目素材、成品、交付、历史版本、日志、隐藏任务清单和 API 私有配置永不作为安装或更新目标。
