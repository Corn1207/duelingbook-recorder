// app.js — Duelingbook Recorder frontend

let editingId = null;

// ------------------------------------------------------------------
// Init
// ------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  loadReplays();
  loadDeckOptions();
  loadLogs();
  setInterval(loadLogs, 5000);
  setInterval(() => loadReplays(
    document.getElementById("filter-from").value || null,
    document.getElementById("filter-to").value || null
  ), 15000);

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

  // Replay search (desktop + mobile)
  document.getElementById("replay-search").addEventListener("input", () => {
    _replayPage = 1;
    renderTable(_allReplays);
  });
  document.getElementById("replay-search-mobile").addEventListener("input", (e) => {
    document.getElementById("replay-search").value = e.target.value;
    _replayPage = 1;
    renderTable(_allReplays);
  });

  // Decks modal
  document.getElementById("btn-open-decks").addEventListener("click", openDecksModal);
  document.getElementById("btn-close-decks").addEventListener("click", closeDecksModal);
  document.getElementById("btn-add-deck-card").addEventListener("click", addDeckCard);
  document.getElementById("new-card-name").addEventListener("input", onCardInput);
  document.getElementById("new-card-name").addEventListener("blur", () => {
    setTimeout(() => document.getElementById("card-autocomplete").classList.add("hidden"), 200);
  });

  // Deck search
  document.getElementById("deck-search").addEventListener("input", () => {
    _deckPage = 1;
    renderDecksTable(_allDecks);
  });
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
// Load & render replays
// ------------------------------------------------------------------
let _allReplays = [];
let _replayPage = 1;
let _activeTab = "active";
const REPLAY_PAGE_SIZE = 20;

async function loadReplays(from = null, to = null) {
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to)   params.set("to", to);
  const url = "/api/replays" + (params.toString() ? "?" + params : "");
  _allReplays = await fetch(url).then(r => r.json());
  _replayPage = 1;
  renderTable(_allReplays);
  renderStats(_allReplays);
}

function applyFilter() {
  const from = document.getElementById("filter-from").value;
  const to   = document.getElementById("filter-to").value;
  loadReplays(from || null, to || null);
}

function toggleMobileFilters() {
  document.getElementById("mobile-filters").classList.toggle("hidden");
}

function applyMobileFilter() {
  const from = document.getElementById("filter-from-mobile").value;
  const to   = document.getElementById("filter-to-mobile").value;
  loadReplays(from || null, to || null);
  document.getElementById("mobile-filters").classList.add("hidden");
}

function clearMobileFilter() {
  document.getElementById("filter-from-mobile").value = "";
  document.getElementById("filter-to-mobile").value = "";
  loadReplays();
  document.getElementById("mobile-filters").classList.add("hidden");
}

function switchTab(tab) {
  _activeTab = tab;
  _replayPage = 1;
  document.getElementById("tab-active").classList.toggle("active", tab === "active");
  document.getElementById("tab-uploaded").classList.toggle("active", tab === "uploaded");
  document.getElementById("tab-calendar").classList.toggle("active", tab === "calendar");

  const tableWrapper = document.querySelector(".table-wrapper");
  const calView = document.getElementById("calendar-view");
  if (tab === "calendar") {
    tableWrapper.classList.add("hidden");
    calView.classList.remove("hidden");
    renderCalendar();
  } else {
    tableWrapper.classList.remove("hidden");
    calView.classList.add("hidden");
    renderTable(_allReplays);
  }
}

function renderTable(rows) {
  const tabFiltered = _activeTab === "uploaded"
    ? rows.filter(r => r.status === "uploaded")
    : rows.filter(r => r.status !== "uploaded");

  const q = (document.getElementById("replay-search").value || "").toLowerCase().trim();
  const filtered = q
    ? tabFiltered.filter(r =>
        (r.replay_id || "").toLowerCase().includes(q) ||
        (r.deck1     || "").toLowerCase().includes(q) ||
        (r.deck2     || "").toLowerCase().includes(q) ||
        (r.title     || "").toLowerCase().includes(q)
      )
    : tabFiltered;

  const totalPages = Math.max(1, Math.ceil(filtered.length / REPLAY_PAGE_SIZE));
  if (_replayPage > totalPages) _replayPage = totalPages;
  const start = (_replayPage - 1) * REPLAY_PAGE_SIZE;
  const page  = filtered.slice(start, start + REPLAY_PAGE_SIZE);

  const tbody = document.getElementById("replays-body");
  if (!filtered.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty">No hay replays.</td></tr>';
  } else {
    tbody.innerHTML = page.map(r => `
      <tr>
        <td>${r.publish_at ? r.publish_at.replace("T", " ").slice(0, 16) : "—"}</td>
        <td><code>${r.replay_id}</code> <a href="https://www.duelingbook.com/replay?id=${r.replay_id}" target="_blank" class="btn-view-replay">Ver</a></td>
        <td>${r.deck1 || "—"}</td>
        <td>${r.deck2 || "—"}</td>
        <td>${r.title || "—"}</td>
        <td><span class="badge badge-${r.status}">${statusLabel(r.status)}</span></td>
        <td>${r.youtube_url ? `<a class="yt-link" href="${r.youtube_url}" target="_blank">▶ Ver</a>` : "—"}</td>
        <td class="actions-cell">
          ${r.status === "pending" ? `<button class="btn-record" onclick="startRecording(${r.id})">Grabar</button>` : ""}
          ${!["pending","recording"].includes(r.status) ? `<button class="btn-rerecord" onclick="reRecord(${r.id})">Re-grabar</button>` : ""}
          ${r.status === "recorded" ? `<button class="btn-thumb" onclick="generateThumbnail(${r.id})">Thumbnail</button>` : ""}
          ${["recorded","thumbnail_ready"].includes(r.status) ? `<button class="btn-ai" onclick="generateMetadata(${r.id})">IA</button>` : ""}
          ${r.status === "thumbnail_ready" ? `<button class="btn-thumb" onclick="showThumbnail(${r.id}, '${r.replay_id}')">Ver thumb</button><button class="btn-record" onclick="regenerateThumbnail(${r.id})">Regenerar</button>` : ""}
          ${r.status === "thumbnail_ready" ? `<button class="btn-upload" onclick="uploadToYouTube(${r.id})">YouTube</button>` : ""}
          <button class="btn-edit" onclick="openEditModal(${r.id})">Editar</button>
        </td>
      </tr>
    `).join("");
  }

  renderPagination("replay-pagination", _replayPage, totalPages, (p) => {
    _replayPage = p;
    renderTable(_allReplays);
  });
}

function renderStats(rows) {
  const counts = { pending: 0, recorded: 0, thumbnail_ready: 0, uploaded: 0 };
  rows.forEach(r => { if (counts[r.status] !== undefined) counts[r.status]++; });
  document.getElementById("count-pending").textContent   = counts.pending;
  document.getElementById("count-recorded").textContent  = counts.recorded;
  document.getElementById("count-thumbnail").textContent = counts.thumbnail_ready;
  document.getElementById("count-uploaded").textContent  = counts.uploaded;

  const activeCount = rows.filter(r => r.status !== "uploaded").length;
  document.getElementById("tab-active").textContent   = `⚡ En progreso (${activeCount})`;
  document.getElementById("tab-uploaded").textContent = `✅ Subidos (${counts.uploaded})`;
}

function statusLabel(s) {
  return { pending: "⏳ Pendiente", recording: "🔴 Grabando...", recorded: "🎬 Grabado", thumbnail_ready: "🖼 Thumbnail", uploaded: "✅ Subido" }[s] || s;
}

// ------------------------------------------------------------------
// Replay Modal
// ------------------------------------------------------------------
function openAddModal() {
  editingId = null;
  document.getElementById("modal-title").textContent = "Agregar Replay";
  document.getElementById("replay-form").reset();
  document.getElementById("field-id").value = "";
  document.getElementById("field-label-left").value = "DUELINGBOOK";
  document.getElementById("field-label-right").value = "HIGH RATED";
  document.getElementById("field-publish-at").value = "";
  document.getElementById("field-thumbnail-label1").value = "";
  document.getElementById("field-thumbnail-label2").value = "";
  document.getElementById("btn-delete").style.display = "none";
  document.getElementById("field-replay-id").disabled = false;
  document.getElementById("group-status").style.display = "none";
  document.getElementById("group-youtube-url").style.display = "none";
  document.getElementById("modal-overlay").classList.remove("hidden");
}

async function openEditModal(id) {
  const rows = await fetch(`/api/replays?id=${id}`).then(r => r.json());
  const row = rows.find(r => r.id === id);
  if (!row) return;

  editingId = id;
  document.getElementById("modal-title").textContent = "Editar Replay";
  document.getElementById("field-id").value = id;
  document.getElementById("field-replay-id").value = row.replay_id;
  document.getElementById("field-replay-id").disabled = true;
  document.getElementById("field-deck1").value = row.deck1 || "";
  document.getElementById("field-deck2").value = row.deck2 || "";
  document.getElementById("field-label-left").value = row.label_left || "DUELINGBOOK";
  document.getElementById("field-label-right").value = row.label_right || "HIGH RATED";
  document.getElementById("field-title").value = row.title || "";
  document.getElementById("field-description").value = row.description || "";
  document.getElementById("field-tags").value = row.tags || "";
  document.getElementById("field-notes").value = row.notes || "";
  document.getElementById("field-publish-at").value = row.publish_at || "";
  document.getElementById("field-thumbnail-label1").value = row.thumbnail_label1 || "";
  document.getElementById("field-thumbnail-label2").value = row.thumbnail_label2 || "";
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
    label_left:     document.getElementById("field-label-left").value.trim(),
    label_right:    document.getElementById("field-label-right").value.trim(),
    title:          document.getElementById("field-title").value.trim(),
    description:    document.getElementById("field-description").value.trim(),
    tags:           document.getElementById("field-tags").value.trim(),
    notes:          document.getElementById("field-notes").value.trim(),
    publish_at: document.getElementById("field-publish-at").value || null,
    thumbnail_label1:  document.getElementById("field-thumbnail-label1").value.trim() || null,
    thumbnail_label2:  document.getElementById("field-thumbnail-label2").value.trim() || null,
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

async function deleteReplay() {
  if (!editingId) return;
  if (!confirm("¿Eliminar este replay?")) return;
  await fetch(`/api/replays/${editingId}`, { method: "DELETE" });
  closeModal();
  loadReplays();
}

// ------------------------------------------------------------------
// Recording
// ------------------------------------------------------------------
async function reRecord(id) {
  if (!confirm("¿Re-grabar este replay? El video anterior será reemplazado.")) return;
  await fetch(`/api/replays/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: "pending" }),
  });
  await startRecording(id, false);
}

async function startRecording(id, askConfirm = true) {
  if (askConfirm && !confirm("¿Iniciar grabación? La pantalla será capturada por OBS.")) return;
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

// ------------------------------------------------------------------
// AI Metadata
// ------------------------------------------------------------------
async function generateMetadata(id) {
  if (!confirm("¿Generar título, descripción y tags con IA? Esto sobreescribirá los campos actuales.")) return;

  const btn = event.target;
  btn.textContent = "⏳ Generando...";
  btn.disabled = true;

  const res = await fetch(`/api/replays/${id}/generate-metadata`, { method: "POST" });
  const data = await res.json();

  btn.textContent = "🤖 IA";
  btn.disabled = false;

  if (!res.ok) { alert(data.error || "Error al generar metadata"); return; }

  alert(`✅ Metadata generada:\n\nTÍTULO:\n${data.title}\n\nTAGS:\n${data.tags}`);
  loadReplays();
}

// ------------------------------------------------------------------
// YouTube Upload
// ------------------------------------------------------------------
function uploadToYouTube(id) {
  // Reset radio to default
  document.querySelector('input[name="privacy"][value="private"]').checked = true;

  // Show publish_at info if set
  const row = _allReplays.find(r => r.id === id);
  const infoBox = document.getElementById("publish-at-info");
  const infoDisplay = document.getElementById("publish-at-display");
  if (row && row.publish_at) {
    infoDisplay.textContent = new Date(row.publish_at).toLocaleString();
    infoBox.style.display = "block";
  } else {
    infoBox.style.display = "none";
  }

  const overlay = document.getElementById("privacy-overlay");
  overlay.classList.remove("hidden");

  document.getElementById("btn-confirm-upload").onclick = async () => {
    const privacy = document.querySelector('input[name="privacy"]:checked').value;
    overlay.classList.add("hidden");
    await _doUpload(id, privacy);
  };
}

async function _doUpload(id, privacy) {
  const row = _allReplays.find(r => r.id === id);
  const info = row ? `${row.thumbnail_label1 || row.deck1 || "—"} vs ${row.thumbnail_label2 || row.deck2 || "—"}` : `Replay #${id}`;

  // Show upload modal
  const overlay = document.getElementById("upload-overlay");
  document.getElementById("upload-modal-info").textContent = info;
  document.getElementById("upload-modal-fill").style.width = "0%";
  document.getElementById("upload-modal-pct").textContent = "0%";
  document.getElementById("upload-modal-pct").style.color = "#3b82f6";
  document.getElementById("upload-modal-cancel").textContent = "Cancelar";
  overlay.querySelector("a")?.remove();
  overlay.classList.remove("hidden");

  let evtSource = null;

  document.getElementById("upload-modal-cancel").onclick = () => {
    if (evtSource) evtSource.close();
    overlay.classList.add("hidden");
  };

  // Start upload
  const res = await fetch(`/api/replays/${id}/upload`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ privacy }),
  });
  const data = await res.json();
  if (!res.ok) {
    overlay.classList.add("hidden");
    alert(data.error || "Error al subir");
    return;
  }

  // Listen SSE progress
  evtSource = new EventSource(`/api/replays/${id}/upload/progress`);
  evtSource.onmessage = (e) => {
    const state = JSON.parse(e.data);
    document.getElementById("upload-modal-fill").style.width = state.pct + "%";
    document.getElementById("upload-modal-pct").textContent = state.pct + "%";

    if (state.done) {
      evtSource.close();
      if (state.error) {
        overlay.classList.add("hidden");
        alert("Error al subir: " + state.error);
      } else {
        loadReplays();
        document.getElementById("upload-modal-fill").style.width = "100%";
        document.getElementById("upload-modal-pct").textContent = "✅ ¡Subido!";
        document.getElementById("upload-modal-pct").style.color = "#34d399";
        document.getElementById("upload-modal-cancel").textContent = "Cerrar";
        const link = document.createElement("a");
        link.href = state.url;
        link.target = "_blank";
        link.textContent = state.url;
        link.style.cssText = "display:block;margin-top:12px;color:#3b82f6;font-size:0.82rem;word-break:break-all";
        document.getElementById("upload-modal-cancel").before(link);
      }
    }
  };
  evtSource.onerror = () => {
    evtSource.close();
    overlay.classList.add("hidden");
  };
}

// ------------------------------------------------------------------
// Thumbnail
// ------------------------------------------------------------------
async function generateThumbnail(id) {
  const res = await fetch(`/api/replays/${id}/thumbnail`, { method: "POST" });
  const data = await res.json();
  if (!res.ok) { alert(data.error || "Error al generar thumbnail"); return; }
  const rows = await fetch("/api/replays").then(r => r.json());
  const row = rows.find(r => r.id === id);
  loadReplays();
  if (row) showThumbnail(id, row.replay_id);
}

async function regenerateThumbnail(id) {
  // Revert to recorded so endpoint accepts it
  await fetch(`/api/replays/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: "recorded" }),
  });
  await generateThumbnail(id);
}

function showThumbnail(id, replayId) {
  const overlay = document.getElementById("thumb-overlay");
  const img = document.getElementById("thumb-preview");
  img.src = `/thumbnails/${id}_${replayId}.jpg?t=${Date.now()}`;
  overlay.classList.remove("hidden");
}

// ------------------------------------------------------------------
// Log Panel
// ------------------------------------------------------------------
let _logCollapsed = true;

async function loadLogs() {
  const lines = await fetch("/api/logs?lines=200").then(r => r.json());
  const pre = document.getElementById("log-content");
  const body = document.getElementById("log-body");
  const status = document.getElementById("log-status");

  const html = lines.map(line => {
    if (line.includes("[ERROR]"))   return `<span class="log-error">${escHtml(line)}</span>`;
    if (line.includes("[WARNING]")) return `<span class="log-warning">${escHtml(line)}</span>`;
    return `<span class="log-info">${escHtml(line)}</span>`;
  }).join("\n");

  pre.innerHTML = html || "Sin logs aún.";
  status.textContent = `${lines.length} líneas`;

  // Auto-scroll al fondo solo si ya estaba al fondo
  const atBottom = body.scrollHeight - body.scrollTop <= body.clientHeight + 40;
  if (atBottom) body.scrollTop = body.scrollHeight;
}

function toggleLogs() {
  _logCollapsed = !_logCollapsed;
  document.getElementById("log-body").classList.toggle("collapsed", _logCollapsed);
  document.getElementById("log-chevron").textContent = _logCollapsed ? "▼" : "▲";
}

async function clearLogs() {
  if (!confirm("¿Limpiar el archivo de logs?")) return;
  await fetch("/api/logs", { method: "DELETE" });
  loadLogs();
}

function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

// ------------------------------------------------------------------
// Decks Modal
// ------------------------------------------------------------------
// ------------------------------------------------------------------
// Card autocomplete
// ------------------------------------------------------------------
let _cardSearchTimer = null;

function onCardInput(e) {
  const q = e.target.value.trim();
  const list = document.getElementById("card-autocomplete");
  clearTimeout(_cardSearchTimer);
  if (q.length < 2) { list.classList.add("hidden"); return; }
  _cardSearchTimer = setTimeout(() => fetchCardSuggestions(q), 300);
}

async function fetchCardSuggestions(q) {
  const list = document.getElementById("card-autocomplete");
  const names = await fetch(`/api/cards/search?q=${encodeURIComponent(q)}`).then(r => r.json());
  if (!names.length) { list.classList.add("hidden"); return; }
  list.innerHTML = names.map(n => `<li>${escHtml(n)}</li>`).join("");
  list.querySelectorAll("li").forEach((li, i) => {
    li.addEventListener("mousedown", () => selectCard(names[i]));
  });
  list.classList.remove("hidden");
}

function selectCard(name) {
  document.getElementById("new-card-name").value = name;
  document.getElementById("card-autocomplete").classList.add("hidden");
}

async function loadDeckOptions() {
  const rows = await fetch("/api/decks").then(r => r.json());
  const names = [...new Set(rows.map(r => r.deck_name))];
  const datalist = document.getElementById("deck-options");
  datalist.innerHTML = names.map(n => `<option value="${n}">`).join("");
}

let _allDecks = [];
let _deckPage = 1;
const DECK_PAGE_SIZE = 20;

async function openDecksModal() {
  await loadDecksTable();
  document.getElementById("decks-overlay").classList.remove("hidden");
}

function closeDecksModal() {
  document.getElementById("decks-overlay").classList.add("hidden");
  loadDeckOptions(); // refresh autocomplete
}

async function loadDecksTable() {
  _allDecks = await fetch("/api/decks").then(r => r.json());
  _deckPage = 1;
  renderDecksTable(_allDecks);
}

function renderDecksTable(rows) {
  const q = (document.getElementById("deck-search").value || "").toLowerCase().trim();
  const filtered = q
    ? rows.filter(r =>
        (r.deck_name || "").toLowerCase().includes(q) ||
        (r.card_name || "").toLowerCase().includes(q)
      )
    : rows;

  const totalPages = Math.max(1, Math.ceil(filtered.length / DECK_PAGE_SIZE));
  if (_deckPage > totalPages) _deckPage = totalPages;
  const start = (_deckPage - 1) * DECK_PAGE_SIZE;
  const page  = filtered.slice(start, start + DECK_PAGE_SIZE);

  const tbody = document.getElementById("decks-body");
  if (!filtered.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="empty">No hay decks.</td></tr>';
  } else {
    tbody.innerHTML = page.map(r => `
      <tr id="deck-row-${r.id}">
        <td><span id="deck-name-${r.id}">${r.deck_name}</span></td>
        <td><span id="card-name-${r.id}">${r.card_name}</span></td>
        <td class="actions-cell">
          <button class="btn-edit" data-id="${r.id}" data-deck="${escHtml(r.deck_name)}" data-card="${escHtml(r.card_name)}" onclick="editDeckCard(this.dataset.id, this.dataset.deck, this.dataset.card)">Editar</button>
          <button class="btn-edit" onclick="deleteDeckCard(${r.id})">Eliminar</button>
        </td>
      </tr>
    `).join("");
  }

  renderPagination("deck-pagination", _deckPage, totalPages, (p) => {
    _deckPage = p;
    renderDecksTable(_allDecks);
  });
}

async function addDeckCard() {
  const deck_name = document.getElementById("new-deck-name").value.trim();
  const card_name = document.getElementById("new-card-name").value.trim();
  if (!deck_name || !card_name) { alert("Completa ambos campos"); return; }

  const res = await fetch("/api/decks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ deck_name, card_name }),
  });
  if (!res.ok) { alert("Error al agregar"); return; }
  document.getElementById("new-deck-name").value = "";
  document.getElementById("new-card-name").value = "";
  await loadDecksTable();
}

function editDeckCard(id, deckName, cardName) {
  const row = document.getElementById(`deck-row-${id}`);
  row.innerHTML = `
    <td><input type="text" id="edit-deck-${id}" style="width:100%"></td>
    <td><input type="text" id="edit-card-${id}" style="width:100%"></td>
    <td class="actions-cell">
      <button class="btn-success btn" onclick="saveDeckCard(${id})">Guardar</button>
      <button class="btn-edit" onclick="renderDecksTable(_allDecks)">Cancelar</button>
    </td>
  `;
  document.getElementById(`edit-deck-${id}`).value = deckName;
  document.getElementById(`edit-card-${id}`).value = cardName;
}

async function saveDeckCard(id) {
  const deck_name = document.getElementById(`edit-deck-${id}`).value.trim();
  const card_name = document.getElementById(`edit-card-${id}`).value.trim();
  if (!deck_name || !card_name) { alert("Completa ambos campos"); return; }
  await fetch(`/api/decks/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ deck_name, card_name }),
  });
  await loadDecksTable();
  loadDeckOptions();
}

async function deleteDeckCard(id) {
  if (!confirm("¿Eliminar esta carta?")) return;
  await fetch(`/api/decks/${id}`, { method: "DELETE" });
  await loadDecksTable();
}

// ------------------------------------------------------------------
// Pagination helper
// ------------------------------------------------------------------
function renderPagination(containerId, currentPage, totalPages, onPageClick) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (totalPages <= 1) { container.innerHTML = ""; return; }

  const pages = [];
  for (let i = 1; i <= totalPages; i++) {
    pages.push(
      `<button class="page-btn${i === currentPage ? " page-btn-active" : ""}" onclick="(${onPageClick.toString()})(${i})">${i}</button>`
    );
  }
  container.innerHTML = pages.join("");
}

// ------------------------------------------------------------------
// Calendar
// ------------------------------------------------------------------
let _calYear  = new Date().getFullYear();
let _calMonth = new Date().getMonth(); // 0-indexed

function calPrev() { if (_calMonth === 0) { _calMonth = 11; _calYear--; } else _calMonth--; renderCalendar(); }
function calNext() { if (_calMonth === 11) { _calMonth = 0; _calYear++; } else _calMonth++; renderCalendar(); }

function renderCalendar() {
  const monthNames = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"];
  const dayNames   = ["Dom","Lun","Mar","Mié","Jue","Vie","Sáb"];

  document.getElementById("cal-title").textContent = `${monthNames[_calMonth]} ${_calYear}`;

  // Group replays by publish_at date (or scheduled_date as fallback)
  const byDate = {};
  _allReplays.forEach(r => {
    const date = r.publish_at ? r.publish_at.slice(0, 10) : r.scheduled_date;
    if (!date) return;
    if (!byDate[date]) byDate[date] = [];
    byDate[date].push(r);
  });

  const firstDay = new Date(_calYear, _calMonth, 1).getDay();
  const daysInMonth = new Date(_calYear, _calMonth + 1, 0).getDate();
  const today = new Date().toISOString().slice(0, 10);

  let html = dayNames.map(d => `<div class="cal-day-name">${d}</div>`).join("");

  // Empty cells before first day
  for (let i = 0; i < firstDay; i++) html += `<div class="cal-day empty"></div>`;

  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${_calYear}-${String(_calMonth + 1).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
    const isToday = dateStr === today;
    const replays = byDate[dateStr] || [];
    const dots = replays.map(r => `<span class="cal-dot ${r.status}"></span>`).join("");
    html += `<div class="cal-day${isToday ? " today" : ""}" data-date="${dateStr}"
      onmouseenter="showCalTooltip(event,'${dateStr}')"
      onmouseleave="hideCalTooltip()"
      ontouchstart="showCalTooltip(event,'${dateStr}')"
      ontouchend="hideCalTooltip()">
      <div class="cal-day-num">${d}</div>
      <div>${dots}</div>
    </div>`;
  }

  document.getElementById("cal-grid").innerHTML = html;
}

function showCalTooltip(e, dateStr) {
  const replays = _allReplays.filter(r => (r.publish_at ? r.publish_at.slice(0, 10) : r.scheduled_date) === dateStr);
  if (!replays.length) return;

  const tooltip = document.getElementById("cal-tooltip");
  const items = replays.map(r => `
    <div class="cal-tooltip-item">
      <div class="cal-tooltip-deck">${r.thumbnail_label1 || r.deck1 || "—"} vs ${r.thumbnail_label2 || r.deck2 || "—"}</div>
      <div class="cal-tooltip-status">${statusLabel(r.status)}</div>
    </div>
  `).join("");

  tooltip.innerHTML = `<div style="font-size:0.75rem;color:#888;margin-bottom:8px">${dateStr}</div>${items}`;
  tooltip.classList.remove("hidden");

  // Position near cursor
  const x = e.clientX + 12;
  const y = e.clientY + 12;
  tooltip.style.left = (x + 290 > window.innerWidth ? x - 310 : x) + "px";
  tooltip.style.top  = (y + 200 > window.innerHeight ? y - 220 : y) + "px";
}

function hideCalTooltip() {
  document.getElementById("cal-tooltip").classList.add("hidden");
}
