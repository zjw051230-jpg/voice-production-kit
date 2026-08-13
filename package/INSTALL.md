# v3.0 安装与更新

前置环境统一由 `env4BC` 安装和维护。本包只安装七个配音 skill、创建或补齐多项目工作区，并部署原生 `配音任务看板.exe`。

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -WorkspaceRoot "D:\配音工作区" -ProjectName "项目名"
```

安装器检测 `%LOCALAPPDATA%\env4BC\install-state.json`；缺失时只警告。它不会读取或修改 CC Switch 用户数据库、provider、API Key 或环境程序。新项目使用 v3 的“声音本体 + 项目文件夹”结构；旧项目保留原四大目录和兼容映射，不自动迁移。

更新只处理清单声明的工具文件。同名 skill 只有用户批准并使用 `-Force` 时才先备份后替换。更新由 Codex 自动从官方 Release 下载并校验所需内容；已有素材只建立新分类快捷方式和索引，不移动、不改名、不覆盖。项目素材、成品、交付、历史版本、日志、隐藏任务清单和 API 私有配置永不作为安装或更新目标，更新器会在本地检查这些受保护内容未发生变化。

环境缺失时三级处理：已安装 env4BC、本机带 SHA-256 的可信包、官方 env4BC GitHub Release。三者都失败时必须停止并提示用户联系维护人员，禁止搜索或安装第三方来源。
