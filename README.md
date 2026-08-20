# 配音工作流工具

面向 Windows 的多项目中文配音工作流，支持台词与角色整理、Seedance 批量生成、监控拉回、MP3 提取、返工追踪和任务看板。当前版本为 `v3.0`。

官方仓库：<https://github.com/zjw051230-jpg/voice-production-kit>

仓库只保存工具和文档。音频、视频、API Key、交付文件和本机任务状态都留在本地工作区。

## 安装

新电脑直接把下面这句话发给 Codex，安装 GitHub 上的最新正式版本：

```text
在“https://github.com/zjw051230-jpg/voice-production-kit”上安装最新配音工具
```

也可以在仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File ".\package\install.ps1" -WorkspaceRoot "D:\配音工作区" -ProjectName "项目名称"
```

安装器不会上传素材、读取 API Key、创建 `D:\codex-board` 或修改 CC Switch。

## 使用

安装完成后，对 Codex 说：

```text
我要创建项目，名字叫“项目名称”。
```

Codex 会继续收集剧本、台词、角色音色和 API 状态，并建立提示词、生成、监控、拉回和记录分工。

v3.0 还包含可选的 BaaS 协作应用原型，安装后位于工作区隐藏目录 `.voice-production-collab`。网页负责多人任务状态，本地代理继续负责 D 盘、Seedance、ffmpeg 和快捷方式。

打开协作应用后，还可以在“台词生成器”中填写自己的兼容 OpenAI API、模型、剧本和台词要求，在线返回可复制台词。API Key 只在当前页面内存中使用，刷新后清空；遇到 CORS 错误时需要改用支持跨域的 API 或配置后端代理。

仓库还包含 GitHub Pages 发布流程。将包含 `.github/workflows/deploy-dialogue-app.yml` 的变更合并到 `main` 并在仓库设置中启用 Pages（Source 选择 GitHub Actions）后，可直接打开 `https://<账号>.github.io/<仓库>/` 使用台词生成器。

## 更新

更新 GitHub 最新正式版本：

```text
在“https://github.com/zjw051230-jpg/voice-production-kit”上执行最新更新
```

更新指定轮次或 Release 标签：

```text
在“https://github.com/zjw051230-jpg/voice-production-kit”上执行20260813轮更新
```

“最新”读取 GitHub `releases/latest`；指定轮次读取同名 Release 标签。更新只覆盖官方工具，用户 Skills 和素材受保护。

## 文档

- [首次安装说明](docs/首次安装说明.md)
- [快速操作说明](docs/配音工作流使用说明.md)
- [详细用户手册](docs/配音工具详细使用手册.md)
- [新架构设计 v3](docs/新架构设计-v3.md)
- [BaaS 配音应用架构 v3](docs/BaaS应用架构-v3.md)
- [测试结果](tests/TEST-RESULT.md)

## 安全边界

仓库不包含 API Key、`cc-switch.db`、生产媒体、交付版本或本地任务状态。需要服务器或共享目录复制时，必须另行获得用户批准。
