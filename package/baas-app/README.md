# BaaS 配音生产协作台原型

这是 v3.0 的协作层原型，也包含一个可直接在浏览器使用的台词生成器：

- `index.html`、`app.js`、`styles.css` 是静态前端。
- 前端通过 Glacier BaaS 管理登录、`tasks` 集合和实时刷新。
- `local-agent/voice_agent.py` 只在本机回环地址提供工作区扫描和安全打开成品目录。
- 安装器会把兼容的看板扫描器复制到本地代理目录，安装后的代理不依赖仓库路径。
- Seedance、ffmpeg、API Key、CC Switch 和真实素材仍由本机原有 Skills 管理。
- 台词生成器使用用户填写的 OpenAI-compatible API，根据剧本和台词要求返回最终台词。

## 运行

先启动本地代理：

```powershell
py -3 .\local-agent\voice_agent.py --workspace-root "D:\配音工作区"
```

再用任意静态服务器打开本目录。直接双击 `index.html` 也能显示本地代理/示例模式；BaaS SSO 是否可用取决于浏览器同域和登录状态。

在页面填写 Glacier BaaS 的公开 `appKey`，点击“连接 BaaS”。不需要 BaaS 也可以直接使用“台词生成器”。

## 生成台词

1. 在“API 地址”填写兼容 OpenAI `chat/completions` 的地址，例如 `https://api.openai.com/v1`。如果填写完整的 `/chat/completions` 地址，页面会直接使用它。
2. 填写模型名称和 API Key。
3. 粘贴剧本或剧情上下文，再填写台词需求。需求可以包含角色、情绪、语速、方言、时长和“只说这句话”等限制。
4. 点击“生成台词”，结果会显示在下方；点击“复制台词”即可交给后续提示词或配音任务。

API Key 只存在当前页面的内存中，刷新页面即清空，不写入 `localStorage`、BaaS、GitHub、日志或本地任务文件。第三方 API 若不允许浏览器跨域，会显示 CORS 错误；此时请使用支持 CORS 的 API，或部署自己的后端代理/本地代理转发，不要把密钥硬编码进网页。

## BaaS 集合约定

前端读写 `tasks` 集合。每条任务至少包含：`external_key`、`project`、`task_id`、`script`、`role`、`line`、`status`、`done`、`total`、`downloaded`、`complete`、`source`、`updated_at`。本地同步由用户显式点击，不会启动时自动写入远端。

## 安全边界

本地代理只绑定 `127.0.0.1`，没有任意命令执行、删除、移动、覆盖或 API 配置接口。`open-output` 只接受扫描结果中的已完成任务，并拒绝打开工作区外路径。
