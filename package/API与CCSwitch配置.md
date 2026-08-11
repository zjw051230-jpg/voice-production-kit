# API 与 CC Switch 配置 v2.1

## Seedance API

1. 双击桌面的 `Seedance API配置工具`，也可以打开项目 `04_管理与记录\01_API配置\Seedance API配置工具.exe`。
2. 从下拉框选择项目，再选择 `test版` 或 `正式版`。
3. 在遮罩输入框中填写一份 API Key，点“添加 API”；程序立即写入磁盘。有多份时重复添加，重复密钥自动忽略。
4. 在列表中选择需要优先使用的密钥，点“设为当前”；删除和设为当前也会立即写盘。底部“保存并生成配置”用于手动确认或重试。
5. 程序自动编号并整理到 `apis\api_pool\<线路>`，把当前项生成到 `apis\doubao_api_config.json`；被移除或替换的旧配置归档到 `apis\api_pool\_archive`。
6. `.codex\04_API池状态.json` 保存机器状态，`.codex\04_API池与余额切换.md` 保存不含密钥的人类摘要。

API Key 只写入所选项目的私有配置 JSON，不显示在列表、日志、索引或隐藏说明中。配置过程不调用网络 API。原 `配置Seedance API.ps1` 保留为兼容入口；无参数双击时同样启动桌面程序，显式传入参数时仍可从 CC Switch 导入。

也可以由 Codex 运行：

```powershell
py -3 scripts\manage_api_pool.py --project-root <项目根目录> import
```

自动化程序和索引不得输出 API Key。只有用户明确要求生成时才能调用付费 API。

接口：

- 视频上传：`POST https://chat.q1.com/api/upload/video`
- 音频上传：`POST https://chat.q1.com/api/upload/audio`
- 提交生成：`POST https://chat.q1.com/v1/videos`
- 查询状态：`GET https://chat.q1.com/v1/videos/{id}`
- 下载成品：`GET https://chat.q1.com/v1/videos/{id}/content`

上传地址不带 `/v1`。`401/403` 检查密钥、权限和余额；`404` 检查上传地址；`422` 检查字段、时长、画幅和素材 URL。

### 余额不足自动切换

任一 Chat 发现明确余额不足时，Seedance 流水线退出码为 `42`，停止尚未开始的提交，保存所有已有远端ID，并调用 API池程序：

```powershell
py -3 scripts\manage_api_pool.py --project-root <项目根目录> balance-exhausted --source-chat <当前Chat> --task-id <任务ID> --error "余额不足"
```

程序暂停全部Chat、只唤醒 `理解文本与任务`、切换下一份API并返回必须发送的thread ID和紧急消息。总入口确认新API后运行：

```powershell
py -3 scripts\manage_api_pool.py --project-root <项目根目录> resume-after-balance
```

再使用原任务参数重新提交，不加 `--force-regenerate`。已有远端ID的版本不得重复提交。

## CC Switch：只映射 `5.5 -> dpskv4`

安装包包含 CC Switch 3.18.0，安装后位于 `%LOCALAPPDATA%\Programs\CC Switch\cc-switch.exe`。用户数据库位于 `%USERPROFILE%\.cc-switch\cc-switch.db`，不会被安装包携带或覆盖。

### 用户操作顺序

1. 打开 CC Switch，在 Codex 区域新增或选中要使用的 provider。
2. 在 CC Switch 界面中本地填写该 provider 的 API 地址和密钥，保存并设为当前 provider。不要把密钥发给 Codex。
3. 完全退出 CC Switch，包括系统托盘；此时先不要关闭 Codex。
4. 把下面整段话发给 Codex：

```text
我已经在 CC Switch 中完成 Codex provider 和 API 配置，并已完全退出 CC Switch。请读取当前 v2.1 安装包中的“API与CCSwitch配置.md”，使用 scripts\configure_ccswitch_model.py 处理当前 Codex provider。只允许新增或修改显示名严格等于“5.5”的这一条映射，使它实际请求“dpskv4”；绝对禁止修改、重命名、删除或映射任何其他模型，也不得修改 API Key、base_url、provider ID 或其他数据库表。先执行 dry-run，只有预览明确显示“5.5 -> dpskv4”且显示其他模型未改变时，才自动备份数据库并执行修改；随后运行数据库完整性检查，报告 provider 名称和 ID、备份路径、映射结果与检查结果。完成后停止，不做其他操作。
```

5. Codex 完成并报告后，关闭 Codex。
6. 重新启动 CC Switch，重新选择或应用刚才的 provider。
7. 重新启动 Codex，在模型列表选择显示名 `5.5`，发送一条无敏感信息的测试消息。
8. 在 CC Switch 请求日志中确认实际请求模型为 `dpskv4`。

### Codex 执行规则

脚本已锁死，只能处理：

```json
{"model": "dpskv4", "displayName": "5.5"}
```

先预览：

```powershell
py -3 .\scripts\configure_ccswitch_model.py --dry-run
```

无法唯一识别当前 provider 时，只能读取准确 provider ID 后再次预览：

```powershell
py -3 .\scripts\configure_ccswitch_model.py --provider-id <准确的Provider_ID> --dry-run
```

预览必须同时出现：

```text
preview: 5.5 -> dpskv4
scope: only displayName=5.5; other models unchanged
```

然后去掉 `--dry-run` 执行。脚本先把数据库备份到 `%USERPROFILE%\.cc-switch\backups`，只更新选定 Codex provider 的 `settings_config`，并执行 `PRAGMA integrity_check`。

严禁把 `5.6`、`5.6-sol`、`5.6-terra`、`5.6-luna` 或任何其他模型映射到 `dpskv4`。严禁使用批量替换，严禁修改其他 provider、API Key、base URL 或数据库表。

### 回滚

若模型未出现、请求名不对或 CC Switch 无法启动：

1. 完全退出 Codex 和 CC Switch。
2. 保留当前 `cc-switch.db` 用于排查。
3. 将 `%USERPROFILE%\.cc-switch\backups\cc-switch.before-model-map.<时间>.db` 恢复为 `%USERPROFILE%\.cc-switch\cc-switch.db`。
4. 启动 CC Switch，重新应用 provider，再启动 Codex。
