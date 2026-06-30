let GAME_ID = localStorage.getItem("gameName") || "default";
const gameSelect = document.getElementById("gameSelect");
const newGameBtn = document.getElementById("newGameBtn");

async function setGame(name) {
  GAME_ID = (name || "default").trim() || "default";
  localStorage.setItem("gameName", GAME_ID);
  await fetch("/api/game", { method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ name: GAME_ID }) });
  // 刷新笔记、台词（切换游戏）
  await refreshNotes();
  const linesEl = document.getElementById("lines");
  linesEl.innerHTML = `<div class="empty">${EMPTY.lines}</div>`;
  // 重新加载游戏专属设置到缓存
  try {
    const r = await fetch("/api/settings");
    _settingsCache = await r.json();
  } catch (e) {}
}

async function loadGameList() {
  try {
    const d = await (await fetch("/api/games")).json();
    const games = d.games || [];
    const sel = gameSelect;
    sel.innerHTML = "";
    if (games.length === 0) {
      sel.innerHTML = '<option value="">（尚无游戏）</option>';
    } else {
      games.forEach(g => {
        const opt = document.createElement("option");
        opt.value = g.game_id;
        opt.textContent = `${g.game_id} · ${g.notes_size}字笔记`;
        if (g.is_active) opt.selected = true;
        sel.appendChild(opt);
      });
    }
    if (!games.some(g => g.is_active) && games.length > 0) {
      // 当前活跃游戏不在列表首项？选中第一个
      sel.value = games[0].game_id;
      await setGame(sel.value);
    }
    return games;
  } catch (e) { console.error(e); }
}

gameSelect.addEventListener("change", async () => {
  if (gameSelect.value && gameSelect.value !== GAME_ID) {
    await setGame(gameSelect.value);
  }
});

newGameBtn.addEventListener("click", async () => {
  const name = prompt("输入新游戏名称（支持中文）：");
  if (!name || !name.trim()) return;
  await setGame(name.trim());
  await loadGameList();
});

const socket = io();

const linesEl = document.getElementById("lines");
const notesEl = document.getElementById("notes");
const chatEl = document.getElementById("chat");

const EMPTY = {
  lines: "台词会在这里实时出现。",
  notes: "还没有笔记。回放几句台词，攒够了会自动整理成笔记。",
  chat: "问点什么吧。比如：刚才那个伏笔是什么意思？",
};

linesEl.innerHTML = `<div class="empty">${EMPTY.lines}</div>`;
notesEl.innerHTML = `<div class="empty">${EMPTY.notes}</div>`;
chatEl.innerHTML = `<div class="empty">${EMPTY.chat}</div>`;

function clearEmpty(el) {
  const e = el.querySelector(".empty");
  if (e) e.remove();
}

// 日/夜间主题切换
const themeToggle = document.getElementById("themeToggle");
function applyTheme(t) {
  if (t === "day") document.documentElement.setAttribute("data-theme", "day");
  else document.documentElement.removeAttribute("data-theme");
  if (themeToggle) themeToggle.textContent = t === "day" ? "夜间" : "日间";
}
applyTheme(document.documentElement.getAttribute("data-theme") === "day" ? "day" : "night");
if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") === "day" ? "day" : "night";
    const next = cur === "day" ? "night" : "day";
    applyTheme(next);
    try { localStorage.setItem("theme", next); } catch (e) {}
  });
}

// 智能说话人解析 — 支持多种格式（与后端 parser.py 保持同步）
//   @name@「text」  /  【name】text  /  name「text」 /  name：text
function parseSpeaker(text) {
  if (!text) return { speaker: null, body: text };
  const t = text.trim();
  if (!t) return { speaker: null, body: t };
  const patterns = [
    // 1. @name@「text」
    [/^@([^@]+)@「(.+?)」\s*$/, (m) => [m[1], m[2]]],
    // 2. @name@text（无括号）
    [/^@([^@]+)@(.+?)\s*$/, (m) => [m[1], m[2]]],
    // 3. 【name】text
    [/^【([^】]+)】(.*)$/, (m) => [m[1], m[2]]],
    // 4. 「name」text
    [/^「([^」]+)」\s*(.+)$/, (m) => [m[1], m[2]]],
    // 5. name「text」— 短名字 +「」包裹
    [/^([^\s「」@【】：:，,。\.！!？?、]{1,8})「(.+?)」\s*$/, (m) => [m[1], m[2]]],
    // 6. name：text / name: text
    [/^([^\s：:]{1,8})[：:]\s*(.+)$/, (m) => [m[1], m[2]]],
  ];
  for (const [re, fn] of patterns) {
    const m = t.match(re);
    if (m) {
      const [speaker, body] = fn(m);
      if (speaker && speaker.length <= 16)
        return { speaker: speaker.trim(), body: body.trim() };
      return { speaker: null, body: t };
    }
  }
  return { speaker: null, body: text };
}

// 极简 Markdown 渲染（## ### - **粗体**），不依赖 CDN
function renderMd(md) {
  let h = md.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  h = h.replace(/^### (.*)$/gm, "<h3>$1</h3>");
  h = h.replace(/^## (.*)$/gm, "<h2>$1</h2>");
  h = h.replace(/^# (.*)$/gm, "<h1>$1</h1>");
  h = h.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  h = h.replace(/^- (.*)$/gm, "<li>$1</li>");
  h = h.replace(/((?:<li>.*?<\/li>\n?)+)/g, "<ul>$1</ul>");
  h = h.split(/\n{2,}/).map((block) => {
    const t = block.trim();
    if (!t) return "";
    if (/^<(h\d|ul|li|p)/.test(t)) return block;
    return `<p>${block.replace(/\n/g, "<br>")}</p>`;
  }).join("");
  return h;
}

const charsEl = document.getElementById("characters");

function renderNotes(md) {
  if (!md || !md.trim()) {
    notesEl.innerHTML = `<div class="empty">${EMPTY.notes}</div>`;
    return;
  }
  notesEl.innerHTML = renderMd(md);
}

function renderCharacters(md) {
  if (!charsEl) return;
  if (!md || !md.trim()) {
    charsEl.innerHTML = "";
    return;
  }
  charsEl.innerHTML = renderMd(md);
}

// ---- 笔记编辑模式 ----
const editNotesBtn = document.getElementById("editNotes");
const saveNotesBtn = document.getElementById("saveNotes");
const cancelEditBtn = document.getElementById("cancelEdit");
const refreshNotesBtn = document.getElementById("refreshNotes");
let _lastNotesMd = "";  // 保存渲染时的原始 markdown，取消编辑时恢复

function enterEditMode() {
  // 从服务端拉最新原始 markdown，而非 innerHTML 还原
  fetch(`/api/notes?game_id=${GAME_ID}`)
    .then(r => r.json())
    .then(d => {
      _lastNotesMd = d.notes || "";
      const ta = document.createElement("textarea");
      ta.id = "notesEditor";
      ta.className = "notes-editor";
      ta.value = _lastNotesMd;
      ta.spellcheck = false;
      notesEl.innerHTML = "";
      notesEl.appendChild(ta);
      ta.focus();
    });
  editNotesBtn.style.display = "none";
  refreshNotesBtn.style.display = "none";
  saveNotesBtn.style.display = "";
  cancelEditBtn.style.display = "";
}

function exitEditMode(save) {
  if (save) {
    const ta = document.getElementById("notesEditor");
    if (ta) {
      const md = ta.value;
      fetch("/api/notes", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ game_id: GAME_ID, notes: md }),
      }).then(() => renderNotes(md));
    }
  } else {
    renderNotes(_lastNotesMd);
  }
  editNotesBtn.style.display = "";
  refreshNotesBtn.style.display = "";
  saveNotesBtn.style.display = "none";
  cancelEditBtn.style.display = "none";
}

editNotesBtn.onclick = enterEditMode;
saveNotesBtn.onclick = () => exitEditMode(true);
cancelEditBtn.onclick = () => exitEditMode(false);

socket.on("line", (data) => {
  clearEmpty(linesEl);
  const div = document.createElement("div");
  if (data.marker) {
    div.className = "line marker";
    div.textContent = `— ${data.text} —`;
  } else {
    div.className = "line";
    const { speaker, body } = parseSpeaker(data.text);
    const name = data.speaker || speaker;
    if (name) {
      const s = document.createElement("span");
      s.className = "speaker";
      s.textContent = name;
      div.appendChild(s);
    }
    const b = document.createElement("div");
    b.className = "body";
    b.textContent = body;
    div.appendChild(b);
  }
  linesEl.appendChild(div);
  linesEl.scrollTop = linesEl.scrollHeight;
});

socket.on("notes", (data) => {
  // 如果用户正在编辑中，不覆盖编辑器，只更新内存中的"上次渲染"以备取消时还原
  if (saveNotesBtn.style.display !== "none") {
    _lastNotesMd = data.notes || "";
    return;
  }
  renderNotes(data.notes || "");
});

socket.on("characters", (data) => {
  renderCharacters(data.characters || "");
});

async function refreshNotes() {
  const r = await fetch(`/api/notes?game_id=${GAME_ID}`);
  const d = await r.json();
  renderNotes(d.notes || "");
  renderCharacters(d.characters || "");
}

async function post(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

document.getElementById("sendLine").onclick = async () => {
  const t = document.getElementById("lineText").value.trim();
  if (!t) return;
  await post("/api/line", { game_id: GAME_ID, text: t });
  document.getElementById("lineText").value = "";
};
document.getElementById("lineText").addEventListener("keydown", (e) => {
  if (e.key === "Enter") document.getElementById("sendLine").click();
});

document.getElementById("sendMarker").onclick = async () => {
  const t = document.getElementById("markerLabel").value.trim();
  if (!t) return;
  await post("/api/marker", { game_id: GAME_ID, label: t });
  document.getElementById("markerLabel").value = "";
};

document.getElementById("replay").onclick = async () => {
  await post("/api/replay", { game_id: GAME_ID, path: "samples/sample_lines.txt", interval: 0.8 });
};

document.getElementById("refreshNotes").onclick = refreshNotes;

document.getElementById("ask").onclick = async () => {
  const q = document.getElementById("question").value.trim();
  if (!q) return;
  clearEmpty(chatEl);

  const me = document.createElement("div");
  me.className = "msg me";
  me.innerHTML = '<div class="who">我</div><div class="body"></div>';
  me.querySelector(".body").textContent = q;
  chatEl.appendChild(me);
  document.getElementById("question").value = "";
  chatEl.scrollTop = chatEl.scrollHeight;

  const d = await post("/api/chat", { game_id: GAME_ID, question: q });
  // 过滤掉回填用的 INSIGHT: 行，不在聊天里显示
  const clean = (d.reply || "")
    .split("\n")
    .filter((l) => !/^INSIGHT:/i.test(l.trim()))
    .join("\n")
    .trim();

  const a = document.createElement("div");
  a.className = "msg ai";
  a.innerHTML = '<div class="who">伴读</div><div class="body"></div>';
  a.querySelector(".body").textContent = clean;
  chatEl.appendChild(a);
  chatEl.scrollTop = chatEl.scrollHeight;

  renderNotes(d.notes || "");
  renderCharacters(d.characters || "");
};
document.getElementById("question").addEventListener("keydown", (e) => {
  if (e.key === "Enter") document.getElementById("ask").click();
});

const txStatusEl = document.getElementById("txStatus");
async function pollTxStatus() {
  try {
    const d = await (await fetch("/api/textractor/status")).json();
    txStatusEl.classList.toggle("on", !!d.connected);
    txStatusEl.querySelector(".tx-label").textContent =
      d.connected ? "Textractor 已连" : (d.running ? "Textractor 待连" : "Textractor 未启");
  } catch (e) {}
}
pollTxStatus();
setInterval(pollTxStatus, 3000);
socket.on("textractor_status", () => pollTxStatus());

// 启动：同步游戏 → 加载列表 → 刷新笔记
(async () => {
  await setGame(GAME_ID);
  const games = await loadGameList();
  if (games && games.length === 0) {
    // 新游戏没有 meta，手动刷新一次
    await refreshNotes();
  }
})();

// ---- 设置面板 ----
const settingsOverlay = document.getElementById("settingsOverlay");
const settingsBtn = document.getElementById("settingsBtn");
const closeSettings = document.getElementById("closeSettings");
const saveSettings = document.getElementById("saveSettings");
const setFields = {
  llm_base_url: document.getElementById("set_llm_base_url"),
  llm_api_key: document.getElementById("set_llm_api_key"),
  capture_mode: document.getElementById("set_capture_mode"),
  ocr_mode: document.getElementById("set_ocr_mode"),
  ocr_region: null,  // composite: x,y,w,h
  ocr_interval: document.getElementById("set_ocr_interval"),
  ocr_window: document.getElementById("set_ocr_window"),
};

// 各角色模型块（动态生成）：role → {base_url, api_key, model, datalist, result}
const mb = {};
const MODEL_ROLES = [
  { role: "organize", label: "整理模型" },
  { role: "chat", label: "对话模型" },
  { role: "embed", label: "Embedding 模型" },
];
const VISION_ROLE = { role: "ocr_vision", label: "AI 视觉 OCR 模型" };

function buildModelBlock(cfg, container) {
  const { role, label } = cfg;
  const wrap = document.createElement("div");
  wrap.className = "model-block";
  wrap.innerHTML = `
    <div class="mb-title">${label} <span class="test-result" id="tr_${role}"></span></div>
    <input class="field" id="mb_${role}_base_url" placeholder="端点（留空用全局）">
    <input class="field" id="mb_${role}_api_key" type="password" placeholder="API Key（留空用全局）">
    <div class="model-row">
      <input class="field" id="mb_${role}_model" list="ml_${role}" placeholder="模型名">
      <datalist id="ml_${role}"></datalist>
      <button class="btn btn-ghost btn-sm" data-role="${role}" data-act="load">拉取</button>
      <button class="btn btn-ghost btn-sm" data-role="${role}" data-act="test">测试</button>
    </div>`;
  container.appendChild(wrap);
  mb[role] = {
    base_url: document.getElementById(`mb_${role}_base_url`),
    api_key: document.getElementById(`mb_${role}_api_key`),
    model: document.getElementById(`mb_${role}_model`),
    datalist: document.getElementById(`ml_${role}`),
    result: document.getElementById(`tr_${role}`),
  };
  wrap.querySelectorAll("button").forEach((b) => {
    b.onclick = () => (b.dataset.act === "load" ? loadModels : testModel)(b.dataset.role);
  });
}
MODEL_ROLES.forEach((c) => buildModelBlock(c, document.getElementById("modelBlocks")));
buildModelBlock(VISION_ROLE, document.getElementById("ocrVisionBlock"));

let _settingsCache = {};

async function loadSettings() {
  try {
    const r = await fetch("/api/settings");
    _settingsCache = await r.json();
  } catch (e) { _settingsCache = {}; }
  _populateSettings();
}

function _mbRead(role, field) {
  const s = _settingsCache;
  if (field === "model") {
    const legacy = { organize: "llm_model_organize", chat: "llm_model_chat", embed: "embed_model" }[role];
    return s[`llm_${role}_model`] || (legacy && s[legacy]) || "";
  }
  return s[`llm_${role}_${field}`] || "";
}

function _populateSettings() {
  const s = _settingsCache;
  setFields.llm_base_url.value = s.llm_base_url || "";
  setFields.llm_api_key.value = s.llm_api_key || "";
  setFields.capture_mode.value = s.capture_mode || "textractor";
  setFields.ocr_mode.value = s.ocr_mode || "local";
  document.getElementById("ocrVisionBlock").style.display =
    setFields.ocr_mode.value === "ai_vision" ? "" : "none";
  for (const role of Object.keys(mb)) {
    mb[role].base_url.value = _mbRead(role, "base_url");
    mb[role].api_key.value = _mbRead(role, "api_key");
    mb[role].model.value = _mbRead(role, "model");
    mb[role].result.textContent = "";
  }
  _updateRegionPreview(s.ocr_region);
  setFields.ocr_interval.value = s.ocr_interval ?? 1.0;
  _ensureWindowOption(s.ocr_window);
  setFields.ocr_window.value = s.ocr_window || "";
}

setFields.ocr_mode.onchange = () => {
  document.getElementById("ocrVisionBlock").style.display =
    setFields.ocr_mode.value === "ai_vision" ? "" : "none";
};

async function loadModels(role) {
  const m = mb[role];
  m.result.textContent = "拉取中…"; m.result.className = "test-result";
  const params = new URLSearchParams({ role });
  if (m.base_url.value.trim()) params.set("base_url", m.base_url.value.trim());
  if (m.api_key.value.trim()) params.set("api_key", m.api_key.value.trim());
  try {
    const d = await (await fetch("/api/models?" + params)).json();
    if (d.error) { m.result.textContent = "✗ " + d.error; m.result.className = "test-result err"; return; }
    m.datalist.innerHTML = "";
    (d.models || []).forEach((id) => {
      const o = document.createElement("option"); o.value = id; m.datalist.appendChild(o);
    });
    m.result.textContent = `✓ ${d.models.length} 个模型`; m.result.className = "test-result ok";
  } catch (e) { m.result.textContent = "✗ " + e; m.result.className = "test-result err"; }
}

async function testModel(role) {
  const m = mb[role];
  m.result.textContent = "测试中…"; m.result.className = "test-result";
  try {
    const r = await fetch("/api/models/test", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        role,
        base_url: m.base_url.value.trim() || undefined,
        api_key: m.api_key.value.trim() || undefined,
        model: m.model.value.trim() || undefined,
      }),
    });
    const d = await r.json();
    if (d.ok) { m.result.textContent = "✓ " + (d.reply || "OK"); m.result.className = "test-result ok"; }
    else { m.result.textContent = "✗ " + (d.error || d.reply || "失败"); m.result.className = "test-result err"; }
  } catch (e) { m.result.textContent = "✗ " + e; m.result.className = "test-result err"; }
}

function _ensureWindowOption(title) {
  if (!title) return;
  const sel = setFields.ocr_window;
  for (const opt of sel.options) {
    if (opt.value === title) return;
  }
  const opt = document.createElement("option");
  opt.value = title; opt.textContent = title;
  sel.appendChild(opt);
}

async function refreshWindowList() {
  const btn = document.getElementById("refreshWindowsBtn");
  const cur = setFields.ocr_window.value;
  btn.disabled = true; btn.textContent = "刷新中...";
  try {
    const d = await (await fetch("/api/ocr/windows")).json();
    const sel = setFields.ocr_window;
    // 保留"不绑定"项，清掉其余
    while (sel.options.length > 1) sel.remove(1);
    for (const t of (d.windows || [])) {
      const opt = document.createElement("option");
      opt.value = t; opt.textContent = t;
      sel.appendChild(opt);
    }
    // 试着恢复之前选的
    _ensureWindowOption(cur);
    sel.value = cur || "";
  } catch (e) { console.error(e); }
  btn.disabled = false; btn.textContent = "刷新";
}

function _updateRegionPreview(r) {
  const el = document.getElementById("regionPreview");
  if (r && r.w && r.h) {
    el.textContent = `${r.x}, ${r.y} · ${r.w} × ${r.h}`;
    el.classList.remove("muted");
  } else {
    el.textContent = "未设置";
    el.classList.add("muted");
  }
}

async function saveSettingsNow() {
  const updates = {
    llm_base_url: setFields.llm_base_url.value.trim(),
    llm_api_key: setFields.llm_api_key.value.trim(),
    capture_mode: setFields.capture_mode.value,
    ocr_mode: setFields.ocr_mode.value,
    ocr_interval: parseFloat(setFields.ocr_interval.value) || 1.0,
    ocr_window: setFields.ocr_window.value,
  };
  for (const role of Object.keys(mb)) {
    updates[`llm_${role}_base_url`] = mb[role].base_url.value.trim();
    updates[`llm_${role}_api_key`] = mb[role].api_key.value.trim();
    updates[`llm_${role}_model`] = mb[role].model.value.trim();
  }
  // ocr_region 由"截图上框选"按钮直接写入，这里不覆盖
  await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  _settingsCache = { ..._settingsCache, ...updates };
  settingsOverlay.style.display = "none";
}

settingsBtn.onclick = () => {
  loadSettings().then(() => {
    settingsOverlay.style.display = "flex";
    refreshWindowList();  // 打开时刷新一次窗口列表
  });
};
closeSettings.onclick = () => settingsOverlay.style.display = "none";
saveSettings.onclick = saveSettingsNow;
document.getElementById("refreshWindowsBtn").addEventListener("click", refreshWindowList);
settingsOverlay.addEventListener("click", (e) => {
  if (e.target === settingsOverlay) settingsOverlay.style.display = "none";
});

// Tab switching
document.querySelectorAll(".stab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".stab").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".stab-panel").forEach(p => p.style.display = "none");
    document.getElementById(btn.dataset.tab).style.display = "";
  });
});

// 区域框选 — 在截图上拖动选取（不依赖游戏窗口前台可见）
const snapshotOverlay = document.getElementById("snapshotOverlay");
const snapshotCanvas = document.getElementById("snapshotCanvas");
const snapshotHint = document.getElementById("snapshotHint");
const snapshotSelInfo = document.getElementById("snapshotSelInfo");
const confirmRegionBtn = document.getElementById("confirmRegionBtn");
const snapCtx = snapshotCanvas.getContext("2d");
let _snapImg = null;          // Image 对象
let _snapScale = 1;           // canvas 像素 / 图像像素
let _snapSel = null;          // {x,y,w,h} 图像坐标

function _canvasToImageCoord(cx, cy) {
  const rect = snapshotCanvas.getBoundingClientRect();
  const px = (cx - rect.left) * (snapshotCanvas.width / rect.width);
  const py = (cy - rect.top) * (snapshotCanvas.height / rect.height);
  return [px / _snapScale, py / _snapScale];
}

function _redrawSnap() {
  if (!_snapImg) return;
  snapCtx.clearRect(0, 0, snapshotCanvas.width, snapshotCanvas.height);
  snapCtx.drawImage(_snapImg, 0, 0, snapshotCanvas.width, snapshotCanvas.height);
  if (_snapSel) {
    const x = _snapSel.x * _snapScale, y = _snapSel.y * _snapScale;
    const w = _snapSel.w * _snapScale, h = _snapSel.h * _snapScale;
    snapCtx.fillStyle = "rgba(200,132,44,0.25)";
    snapCtx.fillRect(x, y, w, h);
    snapCtx.strokeStyle = "#C9842C";
    snapCtx.lineWidth = 2;
    snapCtx.strokeRect(x, y, w, h);
  }
}

async function loadSnapshot() {
  snapshotHint.textContent = "截图中…（PrintWindow 抓窗口内容，游戏被盖住也能抓）";
  snapshotCanvas.style.display = "none";
  confirmRegionBtn.disabled = true;
  _snapSel = null;
  snapshotSelInfo.textContent = "";
  // 先确保选中的窗口已存到服务端
  const win = setFields.ocr_window.value;
  await fetch("/api/settings", {
    method: "PUT", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ ocr_window: win }),
  });
  _settingsCache.ocr_window = win;
  try {
    const blob = await (await fetch("/api/ocr/window-snapshot")).blob();
    if (blob.type && blob.type.includes("json")) {
      const d = await blob.json();
      snapshotHint.textContent = "失败：" + (d.error || "未知错误");
      return;
    }
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      _snapImg = img;
      // 缩放到弹窗可容纳的尺寸
      const maxW = 1000, maxH = 560;
      let scale = Math.min(maxW / img.width, maxH / img.height, 1);
      _snapScale = scale;
      snapshotCanvas.width = Math.round(img.width * scale);
      snapshotCanvas.height = Math.round(img.height * scale);
      snapshotCanvas.style.display = "";
      snapshotHint.textContent = `截图 ${img.width}×${img.height} · 在图上拖动框选台词区域`;
      _redrawSnap();
    };
    img.src = url;
  } catch (e) {
    snapshotHint.textContent = "截图失败：" + e;
  }
}

let _dragStart = null;
snapshotCanvas.addEventListener("mousedown", (e) => {
  if (!_snapImg) return;
  _dragStart = _canvasToImageCoord(e.clientX, e.clientY);
});
snapshotCanvas.addEventListener("mousemove", (e) => {
  if (!_dragStart || !_snapImg) return;
  const [x2, y2] = _canvasToImageCoord(e.clientX, e.clientY);
  const x = Math.min(_dragStart[0], x2), y = Math.min(_dragStart[1], y2);
  const w = Math.abs(x2 - _dragStart[0]), h = Math.abs(y2 - _dragStart[1]);
  _snapSel = { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) };
  snapshotSelInfo.textContent = `${_snapSel.x},${_snapSel.y} · ${_snapSel.w}×${_snapSel.h}`;
  confirmRegionBtn.disabled = !(_snapSel.w > 5 && _snapSel.h > 5);
  _redrawSnap();
});
window.addEventListener("mouseup", () => { _dragStart = null; });

confirmRegionBtn.addEventListener("click", async () => {
  if (!_snapSel) return;
  try {
    const r = await fetch("/api/ocr/region", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ region: _snapSel }),
    });
    const d = await r.json();
    if (d.ok) {
      _settingsCache.ocr_region = _snapSel;
      _updateRegionPreview(_snapSel);
      snapshotOverlay.style.display = "none";
    } else {
      alert(d.error || "保存失败");
    }
  } catch (e) { alert(e); }
});

document.getElementById("pickRegionBtn").addEventListener("click", async () => {
  // 先关掉设置面板，露出截图弹窗
  settingsOverlay.style.display = "none";
  snapshotOverlay.style.display = "flex";
  await loadSnapshot();
});
document.getElementById("closeSnapshot").onclick = () => snapshotOverlay.style.display = "none";
document.getElementById("reSnapBtn").onclick = loadSnapshot;
snapshotOverlay.addEventListener("click", (e) => {
  if (e.target === snapshotOverlay) snapshotOverlay.style.display = "none";
});

// OCR 状态轮询：顶栏指示点 + 面板内最近识别
const ocrStatusEl = document.getElementById("ocrStatus");
const ocrLiveEl = document.getElementById("ocrLiveStatus");
const ocrLastEl = document.getElementById("ocrLastText");
const ocrErrorEl = document.getElementById("ocrLastError");
const restartOcrBtn = document.getElementById("restartOcrBtn");
async function pollOcrStatus() {
  try {
    const d = await (await fetch("/api/ocr/status")).json();
    const isOcr = d.mode === "ocr";
    ocrStatusEl.style.display = isOcr ? "" : "none";
    ocrStatusEl.classList.toggle("on", !!d.running);
    ocrStatusEl.querySelector(".ocr-label").textContent =
      d.running ? `OCR 运行中 (${d.frame_count})` : "OCR 未启";
    if (ocrLiveEl) {
      if (d.running) {
        const reg = d.region ? `${d.region.x},${d.region.y} ${d.region.w}×${d.region.h}` : "无区域";
        const mode = d.ocr_mode === "ai_vision" ? "AI视觉" : "本地";
        const lang = d.lang_tag ? ` · ${d.lang_tag}` : "";
        const win = d.window_bound ? ` · 绑定:${d.window}` : " · 屏幕坐标";
        ocrLiveEl.textContent = `运行中[${mode}] · 已识别 ${d.frame_count} 帧${lang}${win} · 区域 ${reg}`;
        ocrLiveEl.classList.add("on");
      } else {
        ocrLiveEl.textContent = isOcr ? "已启用但未运行" : "未启用（当前为 Textractor 通道）";
        ocrLiveEl.classList.remove("on");
      }
      ocrLastEl.textContent = d.last_text || "";
    }
    if (ocrErrorEl) {
      const err = d.init_error || d.last_error;
      if (err) {
        ocrErrorEl.style.display = "";
        ocrErrorEl.textContent = `⚠ ${err}`;
      } else {
        ocrErrorEl.style.display = "none";
      }
    }
  } catch (e) {}
}
pollOcrStatus();
setInterval(pollOcrStatus, 2000);

if (restartOcrBtn) {
  restartOcrBtn.addEventListener("click", async () => {
    restartOcrBtn.disabled = true;
    restartOcrBtn.textContent = "重启中...";
    try {
      await fetch("/api/ocr/restart", { method: "POST" });
    } catch (e) {}
    setTimeout(() => {
      restartOcrBtn.disabled = false;
      restartOcrBtn.textContent = "重启 OCR";
      pollOcrStatus();
    }, 800);
  });
}
