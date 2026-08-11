# Codex 多Chat工作流

## 固定Chat

流程包含：`理解文本与任务`、`提示词`、`生成`、`监控`、`拉回`、`记录`。当前入口Chat必须命名为 `理解文本与任务`。

每个Chat的 thread ID、host ID、模型、推理强度、完整提示词、技能索引、0/1状态、下游和反馈目标都记录在 `.codex\03_codexchat对应表.json`。

所有Chat必须实际验证为“完全访问权限”。只在JSON中写 `full_access_required: true` 不算完成；验证后才把 `full_access_verified` 改为 `true`。

## 入口硬门禁

入口Chat不得继续单Chat执行。每次首次进入项目、创建项目或读取到旧版映射表时，先运行：

```powershell
py -3 scripts/manage_chat_workflow.py --project-root <项目> bootstrap-status
```

只有返回码0且 `ready=true` 才能处理业务。返回码4表示必须完成初始化：

1. 把当前Codex任务命名为 `理解文本与任务`，登记它的实际thread ID。
2. 使用Codex任务创建工具创建另外五个独立任务，禁止用子代理代替固定Chat。
3. 创建每个任务时显式传入映射表中的 `model` 和 `reasoning_effort`，禁止采用界面或工具默认值。
4. 在每个任务中启用并实际验证完全访问权限。
5. 使用 `register` 逐一写入互不重复的thread ID、实际模型、实际思考程度和权限验证结果。实际值与要求不一致时必须重建或修正该任务，不能继续。
6. 再次运行 `bootstrap-status`；未就绪就继续初始化，不得编写提示词或调用Seedance。

入口Chat只做理解、补问、拆解、派发和汇总。提示词、生成、监控、拉回、记录必须由对应独立Chat完成，所有业务派发都必须经过 `prepare-handoff`。

登记示例：

```powershell
py -3 scripts/manage_chat_workflow.py --project-root <项目> register `
  --chat 提示词 --thread-id <实际thread_ID> `
  --actual-model gpt-5.6-sol --actual-reasoning-effort medium `
  --full-access-verified true
```

`bootstrap-status` 会同时检查 `model_verified`。只登记thread ID但没有实际模型/思考程度，或实际值与映射不一致，均不得开始生产。

## 状态协议

- `0`：空闲，可以接收。
- `1`：处理中或已被上游占用。
- 上游发送前必须运行 `prepare-handoff`。脚本在目标为0时原子改成1并返回 `dispatch_contract`，其中包含thread ID、host ID、精确模型、精确思考程度和提示词文件。
- 创建任务和发送任务都必须严格采用 `dispatch_contract`，不得省略模型或思考程度，不得使用默认值。
- 目标已经为1时，不发送消息；创建5分钟心跳，时间到后重新运行 `prepare-handoff`，持续循环。
- 每条交接消息都必须提醒接收者：完成后运行 `complete` 把自己的status改为0。
- 接收者不得在开始时自行把status改为1，因为该动作由上游完成。

```powershell
py -3 scripts/manage_chat_workflow.py --project-root <项目> prepare-handoff `
  --from-chat 提示词 --to-chat 生成 --task-id <task_ID> --summary <摘要>

py -3 scripts/manage_chat_workflow.py --project-root <项目> complete --chat 生成
```

## 反馈

提示词、生成、监控、拉回都把阶段结果反馈给 `理解文本与任务`，同时按流程向下游派发。`记录` 是单向阶段，只写项目 `04_管理与记录\03_问题与改进` 和逐句改动记录，不向其他Chat反馈。

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
2. 按映射表显式指定模型和推理强度，依次创建另外五个Chat；创建调用中必须出现这两个参数。
3. 把实际thread ID、实际模型和实际思考程度通过 `register` 写回映射表并通过匹配校验。
4. 逐个打开Chat，在界面底部把权限切换为“完全访问权限”，验证后登记。
5. 初始提示词必须包含项目绝对路径、状态协议、反馈规则、模型、技能和角色边界。
6. 最后运行 `bootstrap-status`，只有 `ready=true` 才能开始第一条任务。
