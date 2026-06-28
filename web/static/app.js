const GAME_ID = "default";
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

// 把 "【主角】你好" 拆成说话人 + 正文
function parseSpeaker(text) {
  const m = /^【([^】]+)】(.*)/.exec(text);
  return m ? { speaker: m[1], body: m[2] } : { speaker: null, body: text };
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

function renderNotes(md) {
  if (!md || !md.trim()) {
    notesEl.innerHTML = `<div class="empty">${EMPTY.notes}</div>`;
    return;
  }
  notesEl.innerHTML = renderMd(md);
}

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

socket.on("notes", (data) => renderNotes(data.notes || ""));

async function refreshNotes() {
  const r = await fetch(`/api/notes?game_id=${GAME_ID}`);
  const d = await r.json();
  renderNotes(d.notes || "");
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
};
document.getElementById("question").addEventListener("keydown", (e) => {
  if (e.key === "Enter") document.getElementById("ask").click();
});

refreshNotes();
