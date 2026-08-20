# 配音工作流工具

当前正式版本：`v3.0`。官方 GitHub 地址是：<https://github.com/zjw051230-jpg/voice-production-toolkit4bingchuan>。首次安装和后续更新都由 Codex 从这个地址获取。

环境资源不足时执行三级钩子：先使用已安装 env4BC；再尝试带 SHA-256 的本机 env4BC 包或官方 `zjw051230-jpg/env4BC` Release；仍无法安全补齐则立即停止并提示联系维护人员。禁止从第三方站点下载。

面向 Codex 的多项目中文配音生产工具包，提供项目文件系统、Seedance 批量配音、提示词生成、监控拉回、MP3 提取、返工溯源和桌面任务看板。

v3.0 还包含可选的 BaaS 协作应用原型：安装后位于工作区隐藏目录 `.voice-production-collab`，用于多人任务状态和成品协作；本机执行器继续负责 D 盘文件、Seedance、ffmpeg 和快捷方式。

当前开发版本：`v3.0`，适用于 Windows。CC Switch、Seedance API 配置工具、精确模型路由及 Python/ffmpeg 环境管理已独立到 `env4BC`；本仓库只负责配音业务。

安装与更新严格执行“缺什么改什么”，只修改清单声明的工具文件。绝不扫描、整理、迁移、改名、覆盖或删除项目素材、生成视频、MP3、交付版本、日志、隐藏任务记录或用户 API 配置。

## 快速安装

新电脑直接把下面这句话发给 Codex，安装 GitHub 上的最新正式版本：

```text
在“https://github.com/zjw051230-jpg/voice-production-toolkit4bingchuan”上安装最新配音工具
```

```powershell
powershell -ExecutionPolicy Bypass -File ".\package\install.ps1" -WorkspaceRoot "D:\配音工作区" -ProjectName "项目名称"
```

同名 Skill 已存在且确认需要替换时才添加 `-Force`。安装不会调用付费 API、上传素材或创建 `D:\codex-board`。

安装完成后，对 Codex 说：

```text
我要创建项目，名字叫“项目名称”。
```

Codex 会继续收集剧本、台词、角色音色和 API 状态，并建立六个独立任务完成提示词、生成、监控、拉回和记录。

## 一句话更新

```text
在“https://github.com/zjw051230-jpg/voice-production-toolkit4bingchuan”上执行最新更新
```

指定轮次或 Release 标签：

```text
在“https://github.com/zjw051230-jpg/voice-production-toolkit4bingchuan”上执行20260813轮更新
```

“最新”读取 GitHub `releases/latest`；指定轮次读取同名 Release 标签。

## 环境依赖

先安装 `env4BC`。CC Switch 只在 env4BC 中精确执行 `gpt-5.5 -> deepseek-v4-pro`；配音包只读取已就绪的环境，不安装、不覆盖、不修改 CC Switch、provider、数据库或 API Key。

## 文档

- [首次安装说明与完整安装指令](docs/首次安装说明.md)
- [快速操作说明](docs/配音工作流使用说明.md)
- [详细用户手册](docs/配音工具详细使用手册.md)
- [v2.1 更新公告与自动更新指令](docs/v2.1更新公告.md)
- [新架构设计 v3：声音本体、项目文件夹与快捷方式](docs/新架构设计-v3.md)
- [BaaS 配音应用架构 v3](docs/BaaS应用架构-v3.md)
- 环境配置请阅读 `env4BC` 仓库文档。
- [测试结果](tests/TEST-RESULT.md)

## 安全边界

仓库不包含 API Key、`cc-switch.db`、生产素材、生成视频、MP3 或本地任务状态。服务器和共享目录复制必须另行获得用户批准。
