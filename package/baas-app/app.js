(function () {
  "use strict";

  const state = { app: null, baasRows: [], localRows: [], demo: false, unsubscribe: null };
  const $ = (id) => document.getElementById(id);
  const configKeys = { appKey: "voice_baas_app_key", baseUrl: "voice_baas_base_url", agentUrl: "voice_local_agent_url" };
  const demoRows = [
    { key: "demo::task_demo_01", project: "演示项目", task_id: "task_demo_01", script: "示例剧本", role: "月儿", line: "这是一个协作任务示例。", status: "已完成", stage: "已交付", done: 4, total: 4, downloaded: 4, complete: true, updated_at: "演示数据" },
    { key: "demo::task_demo_02", project: "演示项目", task_id: "task_demo_02", script: "示例剧本", role: "阿瓜", line: "本机代理连接后会显示真实状态。", status: "生成中", stage: "生产中", done: 1, total: 4, downloaded: 0, complete: false, updated_at: "演示数据" }
  ];

  function getConfig() {
    return {
      appKey: $("appKey").value.trim() || localStorage.getItem(configKeys.appKey) || "",
      baseUrl: $("baseUrl").value.trim() || localStorage.getItem(configKeys.baseUrl) || "https://chat-test.q1.com/baas",
      agentUrl: $("agentUrl").value.trim() || localStorage.getItem(configKeys.agentUrl) || "http://127.0.0.1:8765"
    };
  }

  function saveConfig(c) {
    Object.entries(configKeys).forEach(([field, key]) => localStorage.setItem(key, c[field]));
  }

  function say(text, kind) {
    const el = $("notice"); el.textContent = text; el.className = "notice" + (kind ? " " + kind : "");
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>\"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[ch]));
  }

  function normalizeDoc(doc) {
    const data = doc && doc.data && typeof doc.data === "object" ? doc.data : (doc || {});
    return { ...data, id: doc && doc.id || data.id || "", key: data.key || data.external_key || data.task_key || data.task_id || "" };
  }

  function stateClass(row) {
    const s = String(row.status || "");
    if (["已完成", "已交付", "已结束（含失败）"].includes(s)) return "done";
    if (["生成中", "已提交", "生产中"].includes(s)) return "running";
    if (["素材缺失", "拉回失败", "成品缺失", "需处理"].includes(s)) return "attention";
    return "";
  }

  function mergeRows() {
    const byKey = new Map();
    [...state.localRows, ...state.baasRows].forEach((row) => {
      const key = row.key || row.external_key || row.task_id;
      if (!key) return;
      byKey.set(key, { ...byKey.get(key), ...row, key });
    });
    return [...byKey.values()].sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
  }

  function render() {
    const rows = state.demo ? demoRows : mergeRows();
    const running = rows.filter((r) => ["生成中", "已提交", "生产中"].includes(r.status)).length;
    const attention = rows.filter((r) => ["素材缺失", "拉回失败", "成品缺失", "需处理"].includes(r.status)).length;
    const complete = rows.filter((r) => r.complete || ["已完成", "已交付"].includes(r.status)).length;
    $("localCount").textContent = state.demo ? "演示" : state.localRows.length;
    $("runningCount").textContent = running;
    $("attentionCount").textContent = attention;
    $("completeCount").textContent = complete;
    $("taskRows").innerHTML = rows.length ? rows.map((row) => {
      const total = Number(row.total || 0), done = Number(row.done || row.downloaded || 0);
      const percent = total ? Math.min(100, Math.round(done * 100 / total)) : 0;
      const canOpen = Boolean(row.complete || row.output_dir);
      return `<tr><td>${escapeHtml(row.project || "未命名项目")}<br><span class="task-id">${escapeHtml(row.task_id || "")}</span></td>` +
        `<td>${escapeHtml(row.script || "未填写")}</td><td class="line"><strong>${escapeHtml(row.role || "")}</strong><br>${escapeHtml(row.line || "")}</td>` +
        `<td><span class="state ${stateClass(row)}">${escapeHtml(row.status || "未知")}</span></td>` +
        `<td class="progress"><div>${done}/${total || "?"}</div><div class="progress-bar"><i style="width:${percent}%"></i></div></td>` +
        `<td>${escapeHtml(row.updated_at || "")}</td><td>${canOpen ? `<button data-open="${escapeHtml(row.key)}">打开成品</button>` : ""}</td></tr>`;
    }).join("") : `<tr><td colspan="7" class="empty">暂无任务。先启动本地代理，或连接 BaaS。</td></tr>`;
    document.querySelectorAll("[data-open]").forEach((button) => button.addEventListener("click", () => openOutput(button.dataset.open)));
  }

  async function loadLocal() {
    const c = getConfig();
    try {
      const health = await fetch(c.agentUrl.replace(/\/$/, "") + "/api/health");
      if (!health.ok) throw new Error("本地代理返回错误");
      const payload = await (await fetch(c.agentUrl.replace(/\/$/, "") + "/api/scan")).json();
      state.localRows = Array.isArray(payload.tasks) ? payload.tasks : [];
      $("agentState").textContent = "在线"; $("agentState").className = "ok";
      say(`本地代理在线，已读取 ${state.localRows.length} 条任务。`, "ok");
    } catch (error) {
      state.localRows = []; $("agentState").textContent = "离线"; $("agentState").className = "warn";
      say("本地代理未连接：" + (error.message || error), "");
    }
    render();
  }

  async function connectBaas() {
    const c = getConfig(); saveConfig(c); $("appKey").value = c.appKey; $("baseUrl").value = c.baseUrl; $("agentUrl").value = c.agentUrl;
    if (!window.GlacierBaaS) { say("未加载 Glacier BaaS SDK；当前仍可使用本地代理和示例模式。", "error"); return; }
    if (!c.appKey) { say("请填写 appKey。它不是 API Key。", "error"); return; }
    try {
      state.app = window.GlacierBaaS.init({ appKey: c.appKey, baseUrl: c.baseUrl });
      await state.app.auth.sso({ redirectOnGuest: true });
      const me = state.app.auth.currentUser(); $("connectionState").textContent = me && (me.display_name || me.email) || "已登录"; $("connectionState").className = "badge ok";
      await loadBaas();
      if (state.unsubscribe) state.unsubscribe();
      state.unsubscribe = state.app.collection("tasks").subscribe(loadBaas);
      $("sync").disabled = false; say("BaaS 已连接，任务会实时刷新。", "ok");
    } catch (error) { $("connectionState").textContent = "连接失败"; $("connectionState").className = "badge warn"; say("BaaS 连接失败：" + (error.message || error), "error"); }
  }

  async function loadBaas() {
    if (!state.app) return;
    try { const result = await state.app.collection("tasks").list({ limit: 500, orderBy: "updated_at", desc: true }); state.baasRows = (result.docs || []).map(normalizeDoc); render(); }
    catch (error) { say("读取 BaaS 任务失败：" + (error.message || error), "error"); }
  }

  async function syncToBaas() {
    if (!state.app) return;
    const tasks = state.localRows;
    try {
      for (const row of tasks) {
        const found = await state.app.collection("tasks").list({ where: { external_key: row.key }, limit: 1 });
        const data = { ...row, external_key: row.key, synced_from: "local-agent", synced_at: new Date().toISOString() };
        if (found.docs && found.docs[0]) await state.app.collection("tasks").update(found.docs[0].id, data);
        else await state.app.collection("tasks").create(data);
      }
      await loadBaas(); say(`已同步 ${tasks.length} 条本机任务到 BaaS。`, "ok");
    } catch (error) { say("同步失败：" + (error.message || error), "error"); }
  }

  async function openOutput(key) {
    const c = getConfig();
    try { const response = await fetch(c.agentUrl.replace(/\/$/, "") + "/api/open-output", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key }) }); if (!response.ok) throw new Error(await response.text()); say("已请求本机打开成品目录。", "ok"); }
    catch (error) { say("打开成品失败：" + (error.message || error), "error"); }
  }

  $("connectBaas").addEventListener("click", connectBaas);
  $("refresh").addEventListener("click", () => { loadLocal(); loadBaas(); });
  $("sync").addEventListener("click", syncToBaas);
  $("demo").addEventListener("click", () => { state.demo = !state.demo; $("demo").textContent = state.demo ? "隐藏示例" : "显示示例"; render(); });
  ["appKey", "baseUrl", "agentUrl"].forEach((id) => $(id).value = localStorage.getItem(configKeys[id]) || $(id).value);
  loadLocal(); render();
})();
