# 配音工作流工具

面向 Codex 的多项目中文配音生产工具包，提供项目文件系统、Seedance 批量配音、提示词生成、监控拉回、MP3 提取、返工溯源和桌面任务看板。

当前开发版本：`v2.2`，适用于 Windows。CC Switch、Seedance API 配置工具、精确模型路由及 Python/ffmpeg 环境管理已独立到 `env4BC`；本仓库只负责配音业务。

安装与更新严格执行“缺什么改什么”，只修改清单声明的工具文件。绝不扫描、整理、迁移、改名、覆盖或删除项目素材、生成视频、MP3、交付版本、日志、隐藏任务记录或用户 API 配置。

## 快速安装

```powershell
powershell -ExecutionPolicy Bypass -File ".\package\install.ps1" -WorkspaceRoot "D:\配音工作区" -ProjectName "项目名称"
```

同名 Skill 已存在且确认需要替换时才添加 `-Force`。安装不会调用付费 API、上传素材或创建 `D:\codex-board`。

安装完成后，对 Codex 说：

```text
我要创建项目，名字叫“项目名称”。
```

Codex 会继续收集剧本、台词、角色音色和 API 状态，并建立六个独立任务完成提示词、生成、监控、拉回和记录。

## 环境依赖

先安装 `env4BC`。CC Switch 只在 env4BC 中精确执行 `gpt-5.5 -> deepseek-v4-pro`；配音包只读取已就绪的环境，不安装、不覆盖、不修改 CC Switch、provider、数据库或 API Key。

## 文档

- [首次安装说明与完整安装指令](docs/首次安装说明.md)
- [快速操作说明](docs/配音工作流使用说明.md)
- [详细用户手册](docs/配音工具详细使用手册.md)
- [v2.1 更新公告与自动更新指令](docs/v2.1更新公告.md)
- 环境配置请阅读 `env4BC` 仓库文档。
- [测试结果](tests/TEST-RESULT.md)

## 安全边界

仓库不包含 API Key、`cc-switch.db`、生产素材、生成视频、MP3 或本地任务状态。服务器和共享目录复制必须另行获得用户批准。
