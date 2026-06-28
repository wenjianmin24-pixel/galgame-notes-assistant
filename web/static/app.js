const GAME_ID = "default";
const socket = io();

const linesEl = document.getElementById("lines");
const notesEl = document.getElementById("notes");
const chatEl = document.getElementById("chat");

socket.on("line", (data) => {
  const div = document.createElement("div");
  div.className = "line" + (data.marker ? " marker" : "");
  div.textContent = (data.speaker ? `【${data.speaker}】` : "") + data.text;
  linesEl.appendChild(div);
  linesEl.scrollTop = linesEl.scrollHeight;
});

socket.on("notes", (data) => { notesEl.textContent = data.notes || "(暂无笔记)"; });

async function refreshNotes() {
  const r = await fetch(`/api/notes?game_id=${GAME_ID}`);
  const d = await r.json();
  notesEl.textContent = d.notes || "(暂无笔记)";
}

document.getElementById("sendLine").onclick = async () => {
  const t = document.getElementById("lineText").value.trim();
  if (!t) return;
  await fetch("/api/line", { method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ game_id: GAME_ID, text: t }) });
  document.getElementById("lineText").value = "";
};
document.getElementById("lineText").addEventListener("keydown", e => { if (e.key === "Enter") document.getElementById("sendLine").click(); });

document.getElementById("sendMarker").onclick = async () => {
  const t = document.getElementById("markerLabel").value.trim();
  if (!t) return;
  await fetch("/api/marker", { method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ game_id: GAME_ID, label: t }) });
  document.getElementById("markerLabel").value = "";
};

document.getElementById("replay").onclick = async () => {
  await fetch("/api/replay", { method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ game_id: GAME_ID, path: "samples/sample_lines.txt", interval: 0.8 }) });
};

document.getElementById("refreshNotes").onclick = refreshNotes;

document.getElementById("ask").onclick = async () => {
  const q = document.getElementById("question").value.trim();
  if (!q) return;
  const div = document.createElement("div");
  div.textContent = "我: " + q;
  chatEl.appendChild(div);
  document.getElementById("question").value = "";
  const r = await fetch("/api/chat", { method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ game_id: GAME_ID, question: q }) });
  const d = await r.json();
  const a = document.createElement("div");
  a.textContent = "AI: " + d.reply;
  chatEl.appendChild(a);
  chatEl.scrollTop = chatEl.scrollHeight;
  notesEl.textContent = d.notes || "(暂无笔记)";
};
document.getElementById("question").addEventListener("keydown", e => { if (e.key === "Enter") document.getElementById("ask").click(); });

refreshNotes();
