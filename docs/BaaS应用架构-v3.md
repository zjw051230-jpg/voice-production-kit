# BaaS 配音应用架构 v3

## 目标

在不替换现有 Codex、Seedance、ffmpeg 和 Windows 文件工作流的前提下，增加多人可用的任务协作应用。

```text
浏览器 / 静态托管页面
  ├─ Glacier BaaS：登录、任务、实时状态、反馈、审计
  └─ localhost：本机工作代理
        ├─ 读取项目注册表和 .codex 索引
        ├─ 调用现有看板扫描逻辑
        └─ 只打开已完成成品目录

本机 Codex Skills
  └─ 提示词、Seedance、监控、拉回、MP3 和 API 配置
```

## 在线台词生成

页面内的“台词生成器”支持两条通道。默认的“冰川 AI”通道在完成 Glacier SSO 后调用 `app.ai.chat`，由冰川后端按当前登录用户额度处理；另一条“自有 OpenAI-compatible API”通道才会由浏览器向用户填写的 `{base_url}/chat/completions` 发起请求。两条通道都把模型返回的中文台词显示为可复制文本。

系统提示词固定约束模型：只输出最终台词，不输出分析、标题、旁白或额外人物；保留用户指定的角色、事实、情绪、语气和台词范围。用户可以在台词需求中继续指定角色、语速、时长、方言、情绪和是否只能说某一句。

冰川通道不需要用户填写第三方 API Key，但剧本和台词需求会发送到 Glacier AI，计费和权限跟随当前 SSO 用户；`app.ai` 只在冰川同域页面可用。直接打开 `file://` 页面时，页面不会强制跳转当前窗口，而是让用户在新标签完成冰川登录，回到原页面后再次点击连接；这样避免登录后无法回到本地文件。自有 API 通道的 API Key 只存在当前页面 JavaScript 内存中：不进 `localStorage`，不进 BaaS，不进 GitHub，不进日志，也不由本地代理接收。页面刷新后密钥清空。浏览器直接请求第三方 API 需要对方允许 CORS；不允许时应使用支持 CORS 的服务或自行部署后端代理，不能把密钥硬编码到静态网页。

## 已加入安装包的原型

- `package/baas-app/`：静态 BaaS 前端，默认只读；用户点击“同步本机到 BaaS”后才写入 `tasks` 集合。
- `package/local-agent/voice_agent.py`：仅绑定 `127.0.0.1` 的本地代理，提供 `/api/health`、`/api/scan` 和受保护的 `/api/open-output`。
- 安装后部署到工作区隐藏目录 `.voice-production-collab`。

## BaaS 数据边界

建议使用以下集合：

```text
projects          项目元数据
tasks             台词任务和当前状态
task_variants     每句 4 个或更多生成变体
assets            参考素材索引，不保存本地密钥
task_runs         远端提交和监控摘要
feedback          返工意见和问题
delivery_records  成品交付记录
audit_events      操作审计
```

集合只保存任务摘要、状态、项目 ID、文件 ID 或本地路径索引。API Key、CC Switch 数据库、完整提示词和未交付生产素材仍留在本机项目目录。

## 同步规则

1. 页面启动只读取本地代理和 BaaS，不自动写远端。
2. 本机生成、监控或拉回完成后，由用户或总入口显式触发同步。
3. 同步键使用 `external_key = project + task_ID`，避免重复创建。
4. BaaS 状态只反映本机事实，不允许网页伪造“已完成”。
5. 文件需要多人查看时才上传 BaaS OSS；使用 `file_id` 和鉴权 URL，不保存公网直链。

## 为什么需要本地代理

浏览器不能直接访问 `D:\配音工作区`、运行 ffmpeg、创建 Windows 快捷方式或修改本地 API 配置。代理只做受控的本地桥接，不提供任意命令执行、删除、移动、覆盖或密钥接口。

## 运行

```powershell
py -3 .\local-agent\voice_agent.py --workspace-root "D:\配音工作区"
```

然后打开 `baas-app/index.html` 或将该目录部署到静态托管。仓库提供 `.github/workflows/deploy-dialogue-app.yml`，合并到 `main` 后会把该目录发布到 GitHub Pages；发布地址通常是 `https://<账号>.github.io/<仓库>/`。BaaS SSO 需要按 `baas.md` 的同域规则运行；未配置 appKey 时仍可使用本机扫描和示例模式，台词生成器仍可单独使用。

## 后续扩展

下一阶段可以加入任务创建、反馈写回、DingTalk 通知和 OSS 成品上传；这些功能应继续通过 BaaS API 和本地代理分层实现，不把本地密钥或生产脚本搬进网页。
