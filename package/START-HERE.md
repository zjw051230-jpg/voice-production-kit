# 新电脑 Codex 从这里开始 v2.0

请完整执行，不要只复述命令。

1. 若用户未提供，询问工作区绝对路径和第一个项目名。工作区默认放本机数据盘，不默认放服务器。
2. 运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -WorkspaceRoot <工作区> -ProjectName <项目名>
```

安装器同时部署包内 CC Switch 3.18.0 程序本体和桌面快捷方式，但不启动程序、不复制用户数据库。检测到已有不同版本时默认保留；说明会备份后，获得同意才能加 `-Force`。同名 skill 也遵循相同的批准规则。安装不调用付费 API、不上传文件、不创建或依赖 `D:\codex-board`。

3. 完整读取 `详细使用手册.md` 和 `API与CCSwitch配置.md`。优先让用户打开 `Seedance API配置工具`，选择项目和 test版/正式版，在遮罩输入框本地添加一份或多份 API；添加、删除和设为当前都会立即写盘，不得输出密钥。`配置Seedance API.ps1` 只作为兼容入口。让用户按文档完成只允许 `5.5 -> dpskv4` 的模型映射。
4. 所有Chat必须读取项目 `.codex\04_API池状态.json`。任何Chat发现余额不足时打断全部流程，只通知“理解文本与任务”；自动切换下一API后，只重提没有远端ID的版本。
5. 使用 `$manage-voice-production` 收集剧本、台词、角色音色、选用版本、API 是否就绪、默认生成参数和本地交付位置。
6. 按项目 `.codex\03_codexchat对应表.json` 初始化理解、提示词、生成、监控、拉回、记录六个独立 Chat，登记互不重复的 thread ID，并逐个验证完全访问权限。运行 `manage_chat_workflow.py bootstrap-status`，只有返回 `ready=true` 才能开始生产；入口 Chat 禁止代做下游五个阶段。
7. 安装器会部署原生 Windows 看板和 `Seedance API配置工具.exe`，并创建桌面快捷方式；API 工具也会放进项目 `04_管理与记录\01_API配置`。两个程序都不需要浏览器或本地服务器；API 工具只在本机写配置，不会在配置阶段调用网络。

看板无审批功能。只有完整完成的任务显示“成品链接”和“复制到地址”。复制必须由用户在弹窗输入地址并按提交，禁止双引号、移动、删除和覆盖。
