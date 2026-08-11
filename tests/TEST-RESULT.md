# 配音工具 v2.0 完整验收结果

日期：2026-08-06

结论：通过。v2.0 安装包、文档和测试文件系统一致，可作为新电脑安装基线。本轮没有调用 Seedance 网络 API、没有上传素材、没有使用真实 API Key、没有写入真实桌面或服务器。

## 安装与目录

- 完整隔离安装通过：安装七个 skill、两个原生 EXE、CC Switch 3.18.0、多项目工作区和三个隔离快捷方式。
- 首个项目 `测试项目` 和安装后新增的 `项目2` 均自动获得 `04_管理与记录\01_API配置\Seedance API配置工具.exe` 与工作区定位配置。
- 两个项目的旧工具目录映射、隐藏 `.codex`、任务清单、Chat 表、API 状态和日志基础文件通过总校验。
- 重复安装保护通过：未使用 `-Force` 时保留已有 skill 并明确停止。
- `test\v2.0` 顶层只显示 `codex-home`、`工作区` 和本报告；测试附件保存在隐藏 `.test-artifacts`。

## 桌面程序

- `配音任务看板.exe` 原生窗口启动成功，标题正确；扫描两个项目成功。
- `Seedance API配置工具.exe` 从项目目录启动成功，标题正确；兼容 PowerShell 入口也能启动 GUI。
- 安装包、工作区工具目录和两个项目内的 API EXE 哈希一致；看板安装副本与安装包哈希一致。
- 三个快捷方式目标均存在，隔离测试没有触碰真实桌面。
- 看板修复 skill 检查通过；新增本地 `VOICE_DASHBOARD_DESKTOP` 重定向用于隔离验收和企业桌面重定向场景。

## API 与余额

- 界面“添加 API”实际调用后立即生成 `doubao_api_config.json`，不是只写内存。
- 重复 API 自动忽略；删除、设为当前立即写盘；旧配置进入归档；保存按钮在默认窗口内完整可见。
- test 地址固定为 `https://chat-test.q1.com/v1`，正式地址固定为 `https://chat.q1.com/v1`。
- 假 CC Switch provider 数据库导入通过：test 三条去重为两条，正式线路一条，当前 provider 优先激活。
- 余额不足处理通过：标记旧 API、切换备用 API、暂停全部 Chat、只唤醒“理解文本与任务”、新 API 加入后恢复。
- 索引、隐藏说明和日志不包含测试密钥；配置测试全程未调用网络。

## 工作流与技能

- 安装包七个 skill 和安装后的七个 skill 共执行 14 次 `quick_validate.py`，全部通过。
- Seedance 流水线离线 `--self-test` 通过。
- 六 Chat 注册、完全访问校验、status 0/1、忙碌后五分钟重试、完成清零、余额暂停门禁和紧急回总入口均通过。
- Seedance 配音提示词 JSON 保存、严格六字段校验、单句约束和覆盖保护通过。
- TTS 情绪提示词 JSON 保存及音色/视听禁词约束通过。
- 任务清单同步、单一角色素材自动选中、逐句资料索引和改动记录通过。
- 地址双向索引、派生文件来源关联、历史路径反查和返工源 JSON 精确恢复通过。
- 任务日志和问题改进记录追加通过。

## CC Switch

- 程序本体产品版本为 3.18.0，安装包不包含用户数据库。
- 假数据库 dry-run 不写入；正式执行前自动备份，执行后 `PRAGMA integrity_check` 为 `ok`。
- 只有显示名严格等于 `5.5` 的模型改为 `deepseek-v4-pro`；`5.6-sol`、其他模型、其他 provider、API Key、base URL 和附加字段全部保持不变。
- 映射通过 provider `config` 中的 `model_catalog_json` 引用持久化；数据库、目录文件和实时 `config.toml` 分别备份并校验。

## 文档与发布清洁

- 人类快速说明已重新按真实操作顺序整理为九个步骤，包含可直接发送给 Codex 的安装、建项目、生成、监控、拉回、返工和修复指令；Markdown 标题、代码块和相对链接校验通过。
- `START-HERE.md`、`INSTALL.md`、`API与CCSwitch配置.md`、安装包详细手册、精简说明和文档版详细手册均存在并标注 v2.0。
- 文档覆盖项目创建、API 立即写盘、项目内 EXE、余额不足、CC Switch 严格映射、看板和常见错误；没有 v1.0.9 残留。
- 安装包详细手册与文档目录详细手册字节一致；精简说明短于详细手册。
- 17 个 Python 文件、6 个 PowerShell 文件和全部 JSON 通过语法或解析检查；PowerShell 文件统一为 Windows PowerShell 5 可识别的 UTF-8 BOM。
- 安装包无 `__pycache__`、`.pyc`、实时数据库、真实密钥、生产素材、服务器上传或 `D:\codex-board` 工具内容。

## v2.1 问题1：强制六Chat分工

- 新项目映射表初始为 `bootstrap_required=true`、`workflow_ready=false`。
- `bootstrap-status` 在任一 Chat 缺少 thread ID、完全访问未验证或 thread ID 重复时返回失败。
- `prepare-handoff` 在六个独立 Chat 全部就绪前拒绝业务交接。
- 六个 Chat 全部登记且权限验证后，交接、忙碌重试和余额暂停流程继续正常工作。
- `manage-voice-production` 通过 Skill 校验；完整离线工作流测试通过且未调用网络。

## v2.1 问题2：模型与思考程度派发合同

- 主 Chat 创建六个固定 Chat 时必须显式指定映射表中的模型和思考程度，禁止采用默认值。
- `register` 强制登记实际模型与实际思考程度；错误模型和错误思考程度测试均被拒绝。
- `bootstrap-status` 将模型验证纳入硬门禁；只登记 thread ID 和权限仍不能开始生产。
- `prepare-handoff` 返回含 thread ID、host ID、模型、思考程度和提示词文件的 `dispatch_contract`。
- 六个 Chat 按各自精确配置登记后完整离线回归通过，`model_contract=OK`，未调用网络。

## v2.1 问题3：完全访问初始化与探测

- 六个固定 Chat 的创建合同和角色提示词均包含固定第一条消息：“这个对话开启完全访问，不需要问我要任何的批准。”
- 新增 `verify-access`，必须由每个目标 Chat 自己完成临时文件写入、读回和删除探测。
- 取消通过 `register --full-access-verified true` 自报权限；没有成功探测的 Chat 无法通过启动门禁。
- 探测临时文件会在命令结束前删除；六个 Chat 全部探测后完整离线回归通过，`full_access_probe=OK`。
- 手册明确说明聊天文字不能绕过应用、Windows或组织策略；反复要求批准时应在任务界面切换完全访问后重试。

## v2.1 问题4：单任务租约、等待反馈与定时重试

- `prepare-handoff` 为目标Chat创建唯一 `lease_id` 和 `active_task`；同一Chat存在活动任务时拒绝第二条交接。
- 缺失或错误租约不能运行 `complete`，活动任务也不能用 `set-status 0` 绕过清理。
- 主对话派发后写入 `waiting_for_feedback` 并返回 `must_stop_and_wait=true`；反馈未完成且未运行 `ack-feedback` 前拒绝继续派发。
- 目标忙碌时把5分钟单次 `retry_contract` 写入 `pending_retries`，合同包含原始交接参数；到点只能重试同一任务，仍忙继续循环。
- API余额不足触发全局中断时，活动租约会进入 `last_interrupted_task`，并清除所有 `active_task` 和等待状态，避免恢复后永久忙碌。
- 完整离线回归通过，`single_task_lease=OK`、`owner_waits_for_feedback=OK`，未调用网络。

## v2.1 问题5：记录Chat单向终止

- `记录` 固定为 `feedback_required=false`、`feedback_to=null`、`next_chat=null`；误改任一项都会被启动门禁拒绝。
- 记录Chat禁止调用 `prepare-handoff`，不能向主线程或任何其他Chat发送汇报。
- 记录完成只关闭自己的任务租约，`feedback_contract=null`；主对话收到 `one_way_terminal=true` 后不进入等待。
- 主对话和记录Chat的角色提示词均明确该例外，完整离线回归通过，`record_one_way_terminal=OK`。

## v2.1 问题6：整批终态后拉回

- 监控阶段只允许单次查询，不上传、不重提、不下载局部成功结果。
- 只有 `成功数 + 失败数 = 总数` 才能把任务交给拉回 Chat。
- 交接前和实际拉回前都有独立终态门禁；仍有运行版本时均拒绝拉回。
- 完整离线回归通过，`remote_terminal_gate=OK`、`pullback_terminal_gate=OK`。

## v2.1 问题7：看板智能状态与展示

- 原生 Windows 看板将任务归为准备中、生产中、待拉回、需处理、已交付五个阶段，卡片保留精确状态。
- 已有远端任务时真实生产状态优先，素材未登记或缺失不再覆盖生成、终态或拉回状态。
- `downloaded` 但本地 MP4 或 MP3 不存在时显示“成品缺失”，不会误判为可拉回或已完成。
- 每条任务新增时长、来源 JSON、最近更新时间、下一步和需处理标记；搜索覆盖状态、下一步和来源。
- 三处看板 EXE 哈希一致；源码、EXE 扫描、Skill 校验和完整离线回归通过，`dashboard_smart_states=OK`。

## v2.1 问题8：新手详细手册

- 详细手册增加第一次使用、日常生产、故障处理三条阅读路径，以及术语、安装检查、六Chat职责、标准话术、状态表、交付清单、故障决策、迁移、安全边界和 FAQ。
- 快速说明保持精简；安装包和文档目录的详细 Markdown 字节一致。
- 生成 v2.1 快速 PDF 3 页、详细 PDF 11 页，使用 A4、中文字体、统一标题层级、表格和页码；逐页渲染检查无裁切、重叠或乱码。
- 参考链接包含 OpenAI Codex 权限、Skills、最佳实践、Automations 和社区 CodexGuide，并注明 2026-08-11 复核及当前节点官方正文 HTTP 403 的限制。
- 文档断言和完整离线回归通过，`documents=OK`、`manuals_identical=true`。
