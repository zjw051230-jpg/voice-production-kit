# 配音生产工具

这是一套面向 Windows 的中文配音工作流，支持多个项目并行管理，包括台词与角色整理、批量生成、任务监控、MP3 提取和返工追踪。当前版本为 `v3.0`。

仓库只保存工具和文档。音频、视频、API Key、交付文件和本机任务状态都留在本地工作区。

## 安装

先安装 [media-production-env](https://github.com/zjw051230-jpg/media-production-env)，然后在仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File ".\package\install.ps1" `
  -WorkspaceRoot "D:\配音工作区" `
  -ProjectName "项目名称"
```

同名 Skill 确实需要替换时再加 `-Force`。安装器只更新清单中的工具文件，不会改动已有素材和成品。

## 使用方式

安装后，可以在 Codex 中直接创建项目：

```text
创建一个名为“项目名称”的配音项目。
```

后续按项目提供剧本、台词、角色音色和生成要求即可。提示词、提交、监控、拉回与返工会分别记录，方便继续处理。

## 更新

从 [voice-production-kit](https://github.com/zjw051230-jpg/voice-production-kit) 获取最新 Release，或在本地仓库执行常规 Git 更新。环境配置由 `media-production-env` 维护，本仓库不修改本机密钥和模型路由。

## 文档

- [首次安装说明](docs/首次安装说明.md)
- [快速操作说明](docs/配音工作流使用说明.md)
- [详细用户手册](docs/配音工具详细使用手册.md)
- [架构说明](docs/新架构设计-v3.md)
- [测试结果](tests/TEST-RESULT.md)
