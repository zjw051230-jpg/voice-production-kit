# 配音工作流工具

面向 Codex 的多项目中文配音生产工具包，提供项目文件系统、Seedance 批量配音、提示词生成、监控拉回、MP3 提取、返工溯源和桌面任务看板。

当前开发版本：`v2.1`，适用于 Windows。

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

## CC Switch

`v2.1` 只在工具包内置 CC Switch 的本地代理中精确执行 `gpt-5.5 -> deepseek-v4-pro`。禁止使用 Codex 模型目录、`model_catalog_json`、无条件 body 覆盖或外置代理；其他模型和 provider 必须保持不变。

## 文档

- [快速操作说明](docs/配音工作流使用说明.md)
- [详细用户手册](docs/配音工具详细使用手册.md)
- [v2.1 更新公告与自动更新指令](docs/v2.1更新公告.md)
- [API 与 CC Switch 配置](package/API与CCSwitch配置.md)
- [测试结果](tests/TEST-RESULT.md)

## 安全边界

仓库不包含 API Key、`cc-switch.db`、生产素材、生成视频、MP3 或本地任务状态。服务器和共享目录复制必须另行获得用户批准。
