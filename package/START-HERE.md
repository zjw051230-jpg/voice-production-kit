# 新电脑 Codex 从这里开始 v3.0

1. 先安装独立环境包 `env4BC`。API Key 只在 env4BC 本机程序中输入，不得发送到聊天。
2. 运行本目录 `install.ps1`，安装配音 skills、多项目工作区和配音任务看板。
3. 对 Codex 说：`我要创建项目，名字叫 XXX`。
4. Codex 先确认工作区和项目名，再按 v3 架构创建“声音本体”和“项目文件夹”；不明确时必须询问，不能猜测。
5. Codex 按项目隐藏索引初始化六个固定 Chat，再执行提示词、生成、监控、拉回和记录。

新架构说明见 `新架构设计-v3.md`。声音本体只放工具、Skills、模板、短索引和日志；素材、台词、提示词、视频和 MP3 只放项目文件夹，跨目录只使用快捷方式。

以后安装或更新只需把下面一句话发给 Codex，完成后无需继续操作。

安装最新正式版本：

`在“https://github.com/zjw051230-jpg/voice-production-toolkit4bingchuan”上安装最新配音工具`

更新最新正式版本：

`在“https://github.com/zjw051230-jpg/voice-production-toolkit4bingchuan”上执行最新更新`

更新指定轮次：

`在“https://github.com/zjw051230-jpg/voice-production-toolkit4bingchuan”上执行20260813轮更新`

本次更新会先保留 `源文件夹-旧`，再在同名副本上处理。官方 Skills 会与官网同步覆盖，用户 Skills 保留在 `声音本体\01_程序与工具\用户Skills`，更新永不覆盖。

本安装器只检测 env4BC，不安装或修改 CC Switch、模型路由、API 配置工具、Python 或 ffmpeg。

首次安装后官方 GitHub 地址会保存在工作区隐藏目录。以后用户只需说“更新配音工具”；Codex 必须使用其中的 `Update-Toolkit.ps1`，不得对整个工作区执行 Git 同步、镜像复制或目录清理。

所有操作严格执行“缺什么改什么”。不得扫描、整理、迁移、改名、覆盖或删除已有素材、生成视频、MP3、交付版本、日志、隐藏任务记录和 API 私有配置。
