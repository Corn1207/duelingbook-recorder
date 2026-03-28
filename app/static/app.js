// app.js — Duelingbook Recorder frontend

let editingId = null;

// ------------------------------------------------------------------
// Init
// ------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  loadReplays();

  document.getElementById("btn-add").addEventListener("click", openAddModal);
  document.getElementById("btn-save").addEventListener("click", saveReplay);
  document.getElementById("btn-delete").addEventListener("click", deleteReplay);
  document.getElementById("btn-filter").addEventListener("click", applyFilter);
  document.getElementById("btn-show-all").addEventListener("click", () => {
    document.getElementById("filter-from").value = "";
    document.getElementById("filter-to").value = "";
    loadReplays();
  });
  document.getElementById("btn-close-modal").addEventListener("click", closeModal);
  document.getElementById("field-replay-id").addEventListener("paste", extractIdFromUrl);
});

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------
function extractIdFromUrl(e) {
  const pasted = (e.clipboardData || window.clipboardData).getData("text");
  const match = pasted.match(/[?&]id=([^\s&]+)/);
  if (match) {
    e.preventDefault();
    e.target.value = match[1];
  }
}

// ------------------------------------------------------------------
// Load & render
// ------------------------------------------------------------------
async function loadReplays(from = null, to = null) {
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to)   params.set("to", to);
  const url = "/api/replays" + (params.toString() ? "?" + params : "");
  const rows = await fetch(url).then(r => r.json());
  renderTable(rows);
  renderStats(rows);
}

function applyFilter() {
  const from = document.getElementById("filter-from").value;
  const to   = document.getElementById("filter-to").value;
  loadReplays(from || null, to || null);
}

function renderTable(rows) {
  const tbody = document.getElementById("replays-body");
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty">No hay replays. Agrega uno con el botón +</td></tr>';
    return;
  }

  tbody.innerHTML = rows.map(r => `
    <tr>
      <td>${r.scheduled_date || "—"}</td>
      <td><code>${r.replay_id}</code></td>
      <td>${r.deck1 || "—"}</td>
      <td>${r.deck2 || "—"}</td>
      <td>${r.title || "—"}</td>
      <td><span class="badge badge-${r.status}">${statusLabel(r.status)}</span></td>
      <td>${r.youtube_url ? `<a class="yt-link" href="${r.youtube_url}" target="_blank">▶ Ver</a>` : "—"}</td>
      <td class="actions-cell">
        ${r.status === "pending" ? `<button class="btn-record" onclick="startRecording(${r.id})">⏺ Grabar</button>` : ""}
        <button class="btn-edit" onclick="openEditModal(${r.id})">Editar</button>
      </td>
    </tr>
  `).join("");
}

function renderStats(rows) {
  const counts = { pending: 0, recorded: 0, thumbnail_ready: 0, uploaded: 0 };
  rows.forEach(r => { if (counts[r.status] !== undefined) counts[r.status]++; });
  document.getElementById("count-pending").textContent   = counts.pending;
  document.getElementById("count-recorded").textContent  = counts.recorded;
  document.getElementById("count-thumbnail").textContent = counts.thumbnail_ready;
  document.getElementById("count-uploaded").textContent  = counts.uploaded;
}

function statusLabel(s) {
  return { pending: "⏳ Pendiente", recording: "🔴 Grabando...", recorded: "🎬 Grabado", thumbnail_ready: "🖼 Thumbnail", uploaded: "✅ Subido" }[s] || s;
}

// ------------------------------------------------------------------
// Modal
// ------------------------------------------------------------------
function openAddModal() {
  editingId = null;
  document.getElementById("modal-title").textContent = "Agregar Replay";
  document.getElementById("replay-form").reset();
  document.getElementById("field-id").value = "";
  document.getElementById("btn-delete").style.display = "none";
  document.getElementById("field-replay-id").disabled = false;
  document.getElementById("group-status").style.display = "none";
  document.getElementById("group-youtube-url").style.display = "none";
  document.getElementById("modal-overlay").classList.remove("hidden");
}

async function openEditModal(id) {
  const rows = await fetch("/api/replays").then(r => r.json());
  const row = rows.find(r => r.id === id);
  if (!row) return;

  editingId = id;
  document.getElementById("modal-title").textContent = "Editar Replay";
  document.getElementById("field-id").value = id;
  document.getElementById("field-replay-id").value = row.replay_id;
  document.getElementById("field-replay-id").disabled = true;
  document.getElementById("field-deck1").value = row.deck1 || "";
  document.getElementById("field-deck2").value = row.deck2 || "";
  document.getElementById("field-title").value = row.title || "";
  document.getElementById("field-description").value = row.description || "";
  document.getElementById("field-tags").value = row.tags || "";
  document.getElementById("field-notes").value = row.notes || "";
  document.getElementById("field-date").value = row.scheduled_date || "";
  document.getElementById("field-status").value = row.status || "pending";
  document.getElementById("field-youtube-url").value = row.youtube_url || "";
  document.getElementById("btn-delete").style.display = "inline-block";
  document.getElementById("group-status").style.display = "flex";
  document.getElementById("group-youtube-url").style.display = "flex";
  document.getElementById("modal-overlay").classList.remove("hidden");
}

function closeModal() {
  document.getElementById("modal-overlay").classList.add("hidden");
  editingId = null;
}

async function saveReplay(e) {
  e.preventDefault();
  const payload = {
    replay_id:      document.getElementById("field-replay-id").value.trim(),
    deck1:          document.getElementById("field-deck1").value.trim(),
    deck2:          document.getElementById("field-deck2").value.trim(),
    title:          document.getElementById("field-title").value.trim(),
    description:    document.getElementById("field-description").value.trim(),
    tags:           document.getElementById("field-tags").value.trim(),
    notes:          document.getElementById("field-notes").value.trim(),
    scheduled_date: document.getElementById("field-date").value || null,
    status:         document.getElementById("field-status").value,
    youtube_url:    document.getElementById("field-youtube-url").value.trim(),
  };

  if (!payload.replay_id) { alert("El Replay ID es obligatorio"); return; }

  const isEdit = editingId !== null;
  const url    = isEdit ? `/api/replays/${editingId}` : "/api/replays";
  const method = isEdit ? "PUT" : "POST";

  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data = await res.json();
  if (!res.ok) { alert(data.error || "Error al guardar"); return; }

  closeModal();
  loadReplays();
}

async function startRecording(id) {
  if (!confirm("¿Iniciar grabación? La pantalla será capturada por OBS.")) return;
  const res = await fetch(`/api/replays/${id}/record`, { method: "POST" });
  const data = await res.json();
  if (!res.ok) { alert(data.error || "Error al iniciar grabación"); return; }
  loadReplays();
  pollWhileRecording();
}

let _pollInterval = null;
function pollWhileRecording() {
  if (_pollInterval) return;
  _pollInterval = setInterval(async () => {
    const rows = await fetch("/api/replays").then(r => r.json());
    renderTable(rows);
    renderStats(rows);
    if (!rows.some(r => r.status === "recording")) {
      clearInterval(_pollInterval);
      _pollInterval = null;
    }
  }, 5000);
}

async function deleteReplay() {
  if (!editingId) return;
  if (!confirm("¿Eliminar este replay?")) return;
  await fetch(`/api/replays/${editingId}`, { method: "DELETE" });
  closeModal();
  loadReplays();
}
