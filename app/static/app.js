/* TaskBoard — фронтенд, vanilla JS, без сборки */
"use strict";

/* ------------------------------------------------------------------ utils */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v === null || v === undefined) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k === "style") node.style.cssText = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(node.dataset, v);
    else node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

const state = {
  user: null,
  csrf: null,
  boards: [],
  board: null,          // открытая доска с колонками и задачами
  filters: { q: "", priority: ""},
  mode: "login",
  editingTask: null,    // объект задачи или null (создание)
  pendingColumnId: null,
};

let toastTimer = null;
function toast(message, ok = false) {
  const t = $("#toast");
  t.textContent = message;
  t.classList.toggle("ok", ok);
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 3500);
}

async function api(path, { method = "GET", body } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (state.csrf) headers["X-CSRF-Token"] = state.csrf;
  let res;
  try {
    res = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error("Нет связи с сервером");
  }
  let data = null;
  try { data = await res.json(); } catch { /* пустой ответ */ }
  if (res.status === 401 && state.user) {
    showAuth();
    throw new Error("Сессия истекла, войдите снова");
  }
  if (!res.ok) throw new Error((data && data.error) || `Ошибка ${res.status}`);
  if (data && data.csrf_token) state.csrf = data.csrf_token;
  return data;
}

/* ------------------------------------------------------------------ auth */
function showAuth() {
  state.user = null;
  state.csrf = null;
  state.board = null;
  $("#app-view").hidden = true;
  $("#auth-view").hidden = false;
}

function showApp() {
  $("#auth-view").hidden = true;
  $("#app-view").hidden = false;
}

function setupAuth() {
  $$(".tab").forEach((tab) =>
    tab.addEventListener("click", () => {
      state.mode = tab.dataset.tab;
      $$(".tab").forEach((t) => t.classList.toggle("active", t === tab));
      $("#auth-submit").textContent = state.mode === "login" ? "Войти" : "Создать аккаунт";
      $("#auth-error").hidden = true;
    })
  );

  $("#auth-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const payload = {
      username: form.username.value.trim(),
      password: form.password.value,
    };
    const errBox = $("#auth-error");
    errBox.hidden = true;
    try {
      const data = await api(`/api/auth/${state.mode}`, { method: "POST", body: payload });
      state.user = { username: data.username };
      state.csrf = data.csrf_token;
      form.password.value = "";
      $("#whoami").textContent = `👤 ${data.username}`;
      showApp();
      await boot();
    } catch (err) {
      errBox.textContent = err.message;
      errBox.hidden = false;
    }
  });

  $("#logout-btn").addEventListener("click", async () => {
    try { await api("/api/auth/logout", { method: "POST", body: {} }); } catch { /* уже вышли */ }
    showAuth();
  });
}

/* ------------------------------------------------------------------ boards */
async function loadBoards() {
  const data = await api("/api/boards");
  state.boards = data.boards;
  renderBoardList();
}

function renderBoardList() {
  const list = $("#board-list");
  list.textContent = "";
  for (const b of state.boards) {
    const item = el("li", {
      class: state.board && state.board.id === b.id ? "active" : "",
      title: b.name,
      onclick: () => openBoard(b.id),
    }, [
      el("span", { class: "dot", style: `background:${b.color}` }),
      el("span", { class: "name", text: b.name }),
      el("span", { class: "count", text: String(b.task_count ?? 0) }),
      el("button", {
        class: "del", text: "✕", title: "Удалить доску",
        onclick: async (e) => {
          e.stopPropagation();
          if (!confirm(`Удалить доску «${b.name}» со всеми задачами?`)) return;
          try {
            await api(`/api/boards/${b.id}`, { method: "DELETE" });
            if (state.board && state.board.id === b.id) { state.board = null; $("#columns").textContent = ""; }
            await loadBoards();
            toast("Доска удалена", true);
          } catch (err) { toast(err.message); }
        },
      }),
    ]);
    list.append(item);
  }
}

async function openBoard(boardId) {
  try {
    const data = await api(`/api/boards/${boardId}`);
    state.board = data.board;
    $("#empty-state").hidden = true;
    $("#columns").hidden = false;
    renderBoardList();
    renderBoard();
    await refreshStats();
  } catch (err) {
    toast(err.message);
    if (/не найдена/.test(err.message)) {
      state.board = null;
      await loadBoards();
      renderEmpty();
    }
  }
}

function renderEmpty() {
  $("#columns").textContent = "";
  $("#columns").hidden = true;
  $("#empty-state").hidden = false;
  $("#board-title").textContent = "Доска";
  $("#stats-bar").hidden = true;
}

async function createBoard() {
  const name = prompt("Название новой доски:");
  if (!name || !name.trim()) return;
  const color = prompt("Цвет метки (hex, например #6366f1):", "#6366f1") || "#6366f1";
  try {
    const data = await api("/api/boards", { method: "POST", body: { name: name.trim(), color } });
    await loadBoards();
    await openBoard(data.board.id);
    toast("Доска создана", true);
  } catch (err) { toast(err.message); }
}

async function renameBoard() {
  if (!state.board) return;
  const name = prompt("Новое название доски:", state.board.name);
  if (!name || !name.trim() || name.trim() === state.board.name) return;
  try {
    await api(`/api/boards/${state.board.id}`, { method: "PATCH", body: { name: name.trim() } });
    state.board.name = name.trim();
    $("#board-title").textContent = state.board.name;
    await loadBoards();
  } catch (err) { toast(err.message); }
}

/* ------------------------------------------------------------------ columns + tasks */
function filteredTasks(tasks) {
  const q = state.filters.q.toLowerCase();
  return tasks.filter((t) => {
    if (state.filters.priority && t.priority !== state.filters.priority) return false;
    if (!q) return true;
    const hay = [t.title, t.description, ...(t.tags || [])].join(" ").toLowerCase();
    return hay.includes(q);
  });
}

const filtersActive = () => !!(state.filters.q || state.filters.priority);

const PRIO = {
  urgent: ["🔴", "Срочный"],
  high: ["🟠", "Высокий"],
  medium: ["🟡", "Средний"],
  low: ["🟢", "Низкий"],
};

function dueInfo(due) {
  if (!due) return null;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const dueDate = new Date(due + "T00:00:00");
  const days = Math.round((dueDate - today) / 86400000);
  if (days < 0) return { cls: "late", text: `просрочено ${Math.abs(days)} дн.` };
  if (days === 0) return { cls: "soon", text: "сегодня" };
  if (days <= 3) return { cls: "soon", text: `через ${days} дн.` };
  return { cls: "", text: due };
}

function renderBoard() {
  const board = state.board;
  if (!board) return renderEmpty();
  $("#board-title").textContent = board.name;
  const wrap = $("#columns");
  wrap.textContent = "";
  wrap.hidden = false;
  $("#empty-state").hidden = true;

  for (const col of board.columns) {
    const visible = filteredTasks(col.tasks);
    const body = el("div", { class: "col-body", dataset: { columnId: String(col.id) } });

    for (const task of visible) body.append(renderCard(task));

    body.append(el("button", {
      class: "add-task-inline", text: "＋ Добавить задачу",
      onclick: () => openTaskModal(null, col.id),
    }));

    const head = el("div", { class: "col-head" }, [
      el("span", { class: "title", text: col.name, title: "Двойной клик — переименовать",
                   ondblclick: () => renameColumn(col) }),
      el("span", { class: "pill", text: String(visible.length) }),
      el("button", {
        class: "icon-btn", text: "✕", title: "Удалить колонку",
        onclick: async () => {
          if (!confirm(`Удалить колонку «${col.name}» вместе с задачами?`)) return;
          try {
            await api(`/api/columns/${col.id}`, { method: "DELETE" });
            await openBoard(board.id);
            await loadBoards();
            toast("Колонка удалена", true);
          } catch (err) { toast(err.message); }
        },
      }),
    ]);

    const column = el("div", { class: "column", dataset: { columnId: String(col.id) } }, [head, body]);
    setupColumnDrag(head, column, col);
    setupDropZone(body, column);
    wrap.append(column);
  }

  const addCol = el("button", {
    class: "add-task-inline",
    style: "width:220px;flex:none;padding:12px",
    text: "＋ Добавить колонку",
    onclick: addColumn,
  });
  wrap.append(el("div", { class: "column", style: "background:transparent;border:0;width:220px;flex:none" },
    [el("div", { class: "col-body" }, [addCol])]));

}

function renderCard(task) {
  const [icon, label] = PRIO[task.priority] || PRIO.medium;
  const due = dueInfo(task.due_date);
  const overdue = due && due.cls === "late";

  const children = [
    el("div", { class: "t", text: task.title }),
  ];
  if (task.description) children.push(el("div", { class: "d", text: task.description }));

  const meta = el("div", { class: "meta" });
  for (const tag of task.tags || []) meta.append(el("span", { class: "tag", text: tag }));
  if (due) meta.append(el("span", { class: `due ${due.cls}`, text: `📅 ${due.text}` }));
  meta.append(el("span", { class: "prio", title: label, text: icon }));
  children.push(meta);

  const card = el("div", {
    class: `card${overdue ? " overdue" : ""}`,
    draggable: filtersActive() ? null : "true",
    title: filtersActive() ? "Снимите фильтр, чтобы перетаскивать" : "Перетащите в другую колонку",
    onclick: () => openTaskModal(task),
  }, children);

  card.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/plain", String(task.id));
    e.dataTransfer.effectAllowed = "move";
    requestAnimationFrame(() => card.classList.add("dragging"));
  });
  card.addEventListener("dragend", () => {
    card.classList.remove("dragging");
    clearDropHints();
  });
  return card;
}

function clearDropHints() {
  $$(".column.drop-target").forEach((c) => c.classList.remove("drop-target"));
  $$(".col-body.drag-over").forEach((b) => b.classList.remove("drag-over"));
}

function computeDropIndex(body, clientY) {
  const cards = $$(".card:not(.dragging)", body);
  let index = cards.length;
  for (let i = 0; i < cards.length; i++) {
    const r = cards[i].getBoundingClientRect();
    if (clientY < r.top + r.height / 2) { index = i; break; }
  }
  return index;
}

function setupDropZone(body, column) {
  body.addEventListener("dragover", (e) => {
    if (!e.dataTransfer.types.includes("text/plain")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    body.classList.add("drag-over");
    column.classList.add("drop-target");
  });
  body.addEventListener("dragleave", (e) => {
    if (!body.contains(e.relatedTarget)) {
      body.classList.remove("drag-over");
      column.classList.remove("drop-target");
    }
  });
  body.addEventListener("drop", async (e) => {
    e.preventDefault();
    const raw = e.dataTransfer.getData("text/plain");
    clearDropHints();
    if (raw.startsWith("col:")) {
      // колонку бросили на тело другой колонки — ставим перед ней
      const srcId = Number(raw.slice(4));
      const targetId = Number(column.dataset.columnId);
      if (srcId && targetId && srcId !== targetId) await moveColumn(srcId, targetId, false);
      return;
    }
    const id = Number(raw);
    if (!id) return;
    const columnId = Number(body.dataset.columnId);
    const index = computeDropIndex(body, e.clientY);
    await moveTask(id, columnId, index);
  });
}

/* ------------------------------------------------------- перетаскивание колонок */
function setupColumnDrag(head, column, col) {
  head.draggable = "true";
  head.title = "Перетащите, чтобы изменить порядок колонок · двойной клик — переименовать";

  head.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/plain", `col:${col.id}`);
    e.dataTransfer.effectAllowed = "move";
    requestAnimationFrame(() => column.classList.add("dragging-col"));
  });
  head.addEventListener("dragend", () => {
    column.classList.remove("dragging-col");
    clearDropHints();
  });
  head.addEventListener("dragover", (e) => {
    if (!e.dataTransfer.types.includes("text/plain")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    column.classList.add("drop-target");
  });
  head.addEventListener("dragleave", () => column.classList.remove("drop-target"));
  head.addEventListener("drop", async (e) => {
    const raw = e.dataTransfer.getData("text/plain");
    if (!raw.startsWith("col:")) return; // карточки обрабатывает зона ниже
    e.preventDefault();
    e.stopPropagation();
    column.classList.remove("drop-target");
    const srcId = Number(raw.slice(4));
    const targetId = Number(column.dataset.columnId);
    if (!srcId || !targetId || srcId === targetId) return;
    const rect = column.getBoundingClientRect();
    const after = e.clientX > rect.left + rect.width / 2;
    await moveColumn(srcId, targetId, after);
  });
}

async function moveColumn(srcId, targetId, after) {
  if (!state.board) return;
  const cols = state.board.columns;
  const from = cols.findIndex((c) => c.id === srcId);
  if (from < 0) return;
  const [col] = cols.splice(from, 1);
  let to = cols.findIndex((c) => c.id === targetId);
  if (to < 0) { cols.splice(from, 0, col); return; }
  if (after) to += 1;
  cols.splice(to, 0, col);
  renderBoard();

  try {
    await api(`/api/columns/${srcId}`, { method: "PATCH", body: { position: to } });
    await openBoard(state.board.id);  // канонический порядок с сервера
  } catch (err) {
    toast(err.message);
    await openBoard(state.board.id);
  }
}

async function moveTask(taskId, columnId, index) {
  if (!state.board) return;
  // оптимистичное обновление
  let task = null;
  for (const col of state.board.columns) {
    const i = col.tasks.findIndex((t) => t.id === taskId);
    if (i >= 0) { task = col.tasks.splice(i, 1)[0]; break; }
  }
  if (!task) return;
  const target = state.board.columns.find((c) => c.id === columnId);
  if (!target) return;
  const bounded = Math.max(0, Math.min(index, target.tasks.length));
  target.tasks.splice(bounded, 0, task);
  task.column_id = columnId;
  renderBoard();

  try {
    await api(`/api/tasks/${taskId}/move`, { method: "POST", body: { column_id: columnId, index: bounded } });
    await refreshStats();
    await loadBoards();
  } catch (err) {
    toast(err.message);
    await openBoard(state.board.id);
  }
}

async function addColumn() {
  const name = prompt("Название колонки:");
  if (!name || !name.trim()) return;
  try {
    await api(`/api/boards/${state.board.id}/columns`, { method: "POST", body: { name: name.trim() } });
    await openBoard(state.board.id);
  } catch (err) { toast(err.message); }
}

async function renameColumn(col) {
  const name = prompt("Новое название колонки:", col.name);
  if (!name || !name.trim() || name.trim() === col.name) return;
  try {
    await api(`/api/columns/${col.id}`, { method: "PATCH", body: { name: name.trim() } });
    col.name = name.trim();
    renderBoard();
  } catch (err) { toast(err.message); }
}

/* ------------------------------------------------------------------ task modal */
function openTaskModal(task, columnId = null) {
  state.editingTask = task || null;
  const form = $("#task-form");
  const modal = $("#task-modal");
  $("#task-error").hidden = true;

  $("#task-modal-title").textContent = task ? "Редактирование задачи" : "Новая задача";
  $("#task-delete").hidden = !task;

  const colSelect = form.column_id;
  colSelect.textContent = "";
  for (const col of (state.board ? state.board.columns : [])) {
    colSelect.append(el("option", { value: String(col.id), text: col.name }));
  }

  form.title.value = task ? task.title : "";
  form.description.value = task ? task.description : "";
  form.priority.value = task ? task.priority : "medium";
  form.due_date.value = task && task.due_date ? task.due_date : "";
  form.tags.value = task ? (task.tags || []).join(", ") : "";
  if (task) colSelect.value = String(task.column_id);
  else if (columnId) colSelect.value = String(columnId);

  modal.hidden = false;
  setTimeout(() => form.title.focus(), 30);
}

function closeModals() {
  $("#task-modal").hidden = true;
  $("#stats-modal").hidden = true;
}

function setupTaskModal() {
  $("#task-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const errBox = $("#task-error");
    errBox.hidden = true;
    const tags = form.tags.value.split(",").map((s) => s.trim()).filter(Boolean);
    const payload = {
      title: form.title.value.trim(),
      description: form.description.value,
      priority: form.priority.value,
      due_date: form.due_date.value || null,
      column_id: Number(form.column_id.value),
      tags,
    };
    try {
      if (state.editingTask) {
        await api(`/api/tasks/${state.editingTask.id}`, { method: "PATCH", body: payload });
        toast("Задача обновлена", true);
      } else {
        await api(`/api/boards/${state.board.id}/tasks`, { method: "POST", body: payload });
        toast("Задача создана", true);
      }
      closeModals();
      await openBoard(state.board.id);
      await loadBoards();
    } catch (err) {
      errBox.textContent = err.message;
      errBox.hidden = false;
    }
  });

  $("#task-delete").addEventListener("click", async () => {
    if (!state.editingTask) return;
    if (!confirm("Удалить задачу?")) return;
    try {
      await api(`/api/tasks/${state.editingTask.id}`, { method: "DELETE" });
      closeModals();
      await openBoard(state.board.id);
      await loadBoards();
      toast("Задача удалена", true);
    } catch (err) { toast(err.message); }
  });

  $$("[data-close]").forEach((btn) => btn.addEventListener("click", closeModals));
  $$(".modal").forEach((m) =>
    m.addEventListener("mousedown", (e) => { if (e.target === m) closeModals(); })
  );
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModals(); });
}

/* ------------------------------------------------------------------ stats */
async function refreshStats() {
  if (!state.board) return;
  try {
    const s = await api(`/api/boards/${state.board.id}/stats`);
    const bar = $("#stats-bar");
    bar.textContent = "";
    const chips = [
      ["Всего", s.total],
      ["Готово", `${s.done} (${s.done_percent}%)`],
      ["Просрочено", s.overdue],
      ["Скоро срок", s.due_soon],
      ["Срочные", s.by_priority.urgent],
    ];
    for (const [k, v] of chips) bar.append(el("span", {}, [`${k}: `, el("b", { text: String(v) })]));
    bar.hidden = false;
  } catch { /* статистика необязательна */ }
}

async function showStats() {
  if (!state.board) return;
  try {
    const s = await api(`/api/boards/${state.board.id}/stats`);
    const box = $("#stats-content");
    box.textContent = "";

    const grid = el("div", { class: "stat-grid" });
    const cells = [
      ["Задач", s.total],
      ["Готово", `${s.done_percent}%`],
      ["Просрочено", s.overdue],
      ["Срок ≤ 3 дн.", s.due_soon],
      ["Без срока", s.without_due],
    ];
    for (const [k, v] of cells) {
      grid.append(el("div", { class: "stat" }, [
        el("div", { class: "v", text: String(v) }),
        el("div", { class: "k", text: k }),
      ]));
    }
    box.append(grid);

    const max = Math.max(1, ...s.by_column.map((c) => c.count), ...Object.values(s.by_priority));
    const section = (title, rows) => {
      const wrap = el("div", { style: "margin-top:16px" }, [el("div", { class: "muted", text: title })]);
      for (const row of rows) {
        wrap.append(el("div", { class: "bar-row" }, [
          el("span", { class: "lbl", text: row.label }),
          el("div", { class: "bar-track" }, [
            el("div", { class: "bar-fill", style: `width:${(row.value / max) * 100}%;${row.color ? `background:${row.color}` : ""}` }),
          ]),
          el("span", { class: "num", text: String(row.value) }),
        ]));
      }
      return wrap;
    };

    box.append(section("По колонкам", s.by_column.map((c) => ({ label: c.name, value: c.count }))));
    const colors = { urgent: "#ef4444", high: "#f97316", medium: "#eab308", low: "#22c55e" };
    box.append(section("По приоритетам", Object.entries(s.by_priority).map(([p, v]) => ({
      label: PRIO[p][1], value: v, color: colors[p],
    }))));

    $("#stats-modal").hidden = false;
  } catch (err) { toast(err.message); }
}

/* ------------------------------------------------------------------ экспорт */
async function exportBoard(e) {
  const fmt = e.target.value;
  e.target.value = "";
  if (!fmt || !state.board) return;
  try {
    const res = await fetch(`/api/boards/${state.board.id}/export?format=${fmt}`);
    if (!res.ok) {
      let msg = `Ошибка ${res.status}`;
      try { msg = (await res.json()).error || msg; } catch { /* не JSON */ }
      throw new Error(msg);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = el("a", { href: url, download: `board-${state.board.id}.${fmt}` });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 3000);
    toast(`Доска выгружена в ${fmt === "md" ? "Markdown" : "JSON"}`, true);
  } catch (err) {
    toast(err.message);
  }
}

/* ------------------------------------------------------------------ горячие клавиши */
function setupShortcuts() {
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeModals(); return; }
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(tag);
    if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
    if ($("#app-view").hidden) return;

    if (e.key === "/") {
      e.preventDefault();
      $("#search").focus();
    } else if (e.key.toLowerCase() === "n") {
      e.preventDefault();
      $("#add-task-btn").click();
    }
  });
}

/* ------------------------------------------------------------------ boot */
async function boot() {
  await loadBoards();
  if (state.boards.length) await openBoard(state.boards[0].id);
  else renderEmpty();
}

async function start() {
  setupAuth();
  setupTaskModal();
  setupShortcuts();

  $("#new-board-btn").addEventListener("click", createBoard);
  $("#add-column-btn").addEventListener("click", () => state.board ? addColumn() : toast("Сначала создайте доску"));
  $("#add-task-btn").addEventListener("click", () => {
    if (!state.board) return toast("Сначала создайте доску");
    const first = state.board.columns[0];
    openTaskModal(null, first ? first.id : null);
  });
  $("#stats-btn").addEventListener("click", showStats);
  $("#export").addEventListener("change", exportBoard);
  $("#board-title").addEventListener("dblclick", renameBoard);
  $("#board-title").title = "Двойной клик — переименовать";

  let searchTimer = null;
  $("#search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.filters.q = e.target.value.trim();
      renderBoard();
    }, 150);
  });
  $("#priority-filter").addEventListener("change", (e) => {
    state.filters.priority = e.target.value;
    renderBoard();
  });

  // попытка восстановить сессию
  try {
    const me = await api("/api/auth/me");
    state.user = { username: me.username };
    state.csrf = me.csrf_token;
    $("#whoami").textContent = `👤 ${me.username}`;
    showApp();
    await boot();
  } catch {
    showAuth();
  }
}

document.addEventListener("DOMContentLoaded", start);
