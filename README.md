# 配音工作流工具

面向 Codex 的多项目中文配音生产工具包，包含项目文件系统、Seedance 配音批处理、提示词生成、任务看板、API 配置和修复工具。

## 当前版本

- 稳定基线：`v2.0`
- 下一版本：`v2.1`，按六项需求逐项开发和测试

## 仓库结构

- `package/`：可直接安装的完整本体，包括 7 个 Skills、安装脚本、CC Switch、任务看板和 API 配置工具。
- `docs/`：快速操作说明和详细使用手册。
- `tests/`：可复现的测试代码与测试结果摘要，不包含测试工作区和真实配置。

## 安装

在 Windows PowerShell 中执行：

```powershell
powershell -ExecutionPolicy Bypass -File ".\package\install.ps1" -WorkspaceRoot "D:\配音工作区" -ProjectName "项目名称"
```

同名 Skill 已存在且确认需要更新时，才添加 `-Force`。安装不会调用付费 API，不会上传媒体，也不会创建或复制 `D:\codex-board`。

## 安全边界

仓库不得提交 API Key、`cc-switch.db`、用户 provider 数据库、生产素材、生成视频、MP3、任务运行状态或本地隐藏目录。只允许提交空配置示例。

## 版本流程

稳定版本使用 Git 标签，例如 `v2.0`。新功能在对应版本分支开发，每项修改单独提交并测试，通过全部验收后再合并并发布安装 ZIP。
