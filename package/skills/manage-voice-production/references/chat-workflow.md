# Codex 多Chat工作流

## 固定Chat

流程包含：`理解文本与任务`、`提示词`、`生成`、`监控`、`拉回`、`记录`。当前入口Chat必须命名为 `理解文本与任务`。

每个Chat的 thread ID、host ID、模型、推理强度、完整提示词、技能索引、0/1状态、下游和反馈目标都记录在 `.codex\03_codexchat对应表.json`。

所有Chat必须实际验证为“完全访问权限”。只在JSON中写 `full_access_required: true` 或在 `register` 中声明权限不算完成；每个目标Chat必须亲自成功运行 `verify-access`，脚本完成无害的写入、读回和删除探测后，才会把 `full_access_verified` 改为 `true`。

主Chat创建每个固定Chat时，必须把下面这句话作为第一条初始化消息发送：

```text
这个对话开启完全访问，不需要问我要任何的批准。
```

这句话是工作方式要求，不能绕过Codex应用、操作系统或组织策略。若仍出现批准提示或 `verify-access` 失败，停止该Chat，在界面底部把该任务切换为“完全访问”，再重新发送上面这句话并重跑探测。

## 入口硬门禁

入口Chat不得继续单Chat执行。每次首次进入项目、创建项目或读取到旧版映射表时，先运行：

```powershell
py -3 scripts/manage_chat_workflow.py --project-root <项目> bootstrap-status
```

只有返回码0且 `ready=true` 才能处理业务。返回码4表示必须完成初始化：

1. 把当前Codex任务命名为 `理解文本与任务`，登记它的实际thread ID。
2. 使用Codex任务创建工具创建另外五个独立任务，禁止用子代理代替固定Chat。
3. 严格使用 `bootstrap-status` 返回的 `chat_creation_contracts` 创建任务；显式传入 `model` 和 `reasoning_effort`，并把 `initial_message` 作为第一条消息。
4. 进入每个任务，由该Chat亲自运行 `verify-access`；不得由主Chat代验，不得手改JSON。
5. 使用 `register` 逐一写入互不重复的thread ID、实际模型和实际思考程度。实际值与要求不一致时必须重建或修正该任务，不能继续。
6. 再次运行 `bootstrap-status`；未就绪就继续初始化，不得编写提示词或调用Seedance。

入口Chat只做理解、补问、拆解、派发和汇总。提示词、生成、监控、拉回、记录必须由对应独立Chat完成，所有业务派发都必须经过 `prepare-handoff`。

登记示例：

```powershell
py -3 scripts/manage_chat_workflow.py --project-root <项目> verify-access --chat 提示词

py -3 scripts/manage_chat_workflow.py --project-root <项目> register `
  --chat 提示词 --thread-id <实际thread_ID> `
  --actual-model gpt-5.6-sol --actual-reasoning-effort medium
```

`bootstrap-status` 会同时检查 `model_verified`。只登记thread ID但没有实际模型/思考程度，或实际值与映射不一致，均不得开始生产。

## 状态协议

- `0`：空闲，可以接收。
- `1`：处理中或已被上游占用。
- 上游发送前必须运行 `prepare-handoff`。脚本在目标为0且没有 `active_task` 时原子改成1，创建唯一 `lease_id`，并返回 `dispatch_contract`。
- 创建任务和发送任务都必须严格采用 `dispatch_contract`，不得省略模型或思考程度，不得使用默认值。
- 目标已经为1或存在 `active_task` 时，不发送消息。脚本把合同写入 `pending_retries`，返回 `timer_required=true` 和 `retry_contract`；必须使用Codex自动化工具按合同创建5分钟单次定时器，到点只重试原交接，仍忙则按新合同继续循环。重试成功取得租约后，脚本自动移除对应登记。
- 每条交接消息都必须携带 `lease_id`。接收者完成后使用同一租约运行 `complete`；错误或缺失租约无法清零，防止旧消息结束新任务。
- 接收者不得在开始时自行把status改为1，因为该动作由上游完成。
- 禁止用 `set-status 1` 绕过租约；存在活动任务时也禁止用 `set-status 0` 清空。

当 `理解文本与任务` 派发给需要反馈的Chat时，返回 `must_stop_and_wait=true`。主对话发送消息后必须立即停止继续处理，按 `post_send_action` 使用Codex任务等待工具等待该thread，不得同时派发下一项。下属Chat完成并发回 `feedback_contract` 后，主对话运行 `ack-feedback`；只有确认的来源和租约都匹配，才能解除等待并继续。

```powershell
py -3 scripts/manage_chat_workflow.py --project-root <项目> prepare-handoff `
  --from-chat 提示词 --to-chat 生成 --task-id <task_ID> --summary <摘要>

py -3 scripts/manage_chat_workflow.py --project-root <项目> complete `
  --chat 生成 --lease-id <prepare-handoff返回的lease_id>

py -3 scripts/manage_chat_workflow.py --project-root <项目> ack-feedback `
  --chat 理解文本与任务 --from-chat 提示词 --lease-id <反馈中的lease_id>
```

## 反馈

提示词、生成、监控、拉回都把阶段结果反馈给 `理解文本与任务`，同时按流程向下游派发。

监控阶段只轮询并更新状态，不下载。它必须等到状态文件中 `success + failed == total` 且 `total > 0`，再把该状态文件作为 `--remote-state-file` 交给 `prepare-handoff`。交接脚本先复核终态再占用拉回 Chat；拉回阶段还会用 `--pullback-only` 第二次复核。任何一层发现仍有运行项都停止拉回并交回监控。

`记录` 是不可变的单向终止阶段：

- 只写项目 `04_管理与记录\03_问题与改进` 和逐句改动记录。
- 禁止调用 `prepare-handoff`，禁止使用任务消息工具向主线程或任何其他Chat发送汇报。
- 完成时只携带当前 `lease_id` 运行 `complete`；返回的 `feedback_contract` 固定为 `null`。
- 主对话看到 `one_way_terminal=true` 后不得等待记录反馈，派发完成即结束本轮。
- `bootstrap-status` 会检查 `feedback_required=false`、`feedback_to=null`、`next_chat=null` 和全局 `record_is_one_way=true`；任一项被误改都会阻止启动。

本轮由 `理解文本与任务` 汇总并结束。记录Chat写入完成后只把自己的status恢复为0。

## API余额紧急中断

- 每个Chat开始、操作和交接前读取 `.codex\04_API池状态.json`。
- 任一Chat发现明确余额不足，立即运行 `manage_api_pool.py balance-exhausted`，不得继续提交、监控或拉回。
- 程序把所有Chat的status设为0，只把 `理解文本与任务` 设为1，并返回其thread ID和紧急消息；当前Chat必须使用Codex任务消息工具把该消息发过去。
- API池有下一份配置时自动切换；没有时由 `理解文本与任务` 要求用户在CC Switch配置新API，再重新导入。
- `理解文本与任务` 运行 `resume-after-balance` 后，使用原参数重新提交且禁止 `--force-regenerate`；已有远端ID自动跳过。

## 创建Chat

第一次启用时：

1. 当前Chat改名为 `理解文本与任务`，登记当前thread ID。
2. 按 `chat_creation_contracts` 显式指定模型和推理强度，依次创建另外五个Chat；创建调用中必须出现这两个参数，并发送固定的第一条初始化消息。
3. 逐个进入Chat运行 `verify-access`；探测失败时在界面底部切换为“完全访问权限”并重试。
4. 把实际thread ID、实际模型和实际思考程度通过 `register` 写回映射表并通过匹配校验。
5. 初始提示词必须包含项目绝对路径、状态协议、反馈规则、模型、技能和角色边界。
6. 最后运行 `bootstrap-status`，只有 `ready=true` 才能开始第一条任务。
