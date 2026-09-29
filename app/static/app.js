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
  editingSubtasks: [],  // черновик чеклиста в открытой модалке
  pendingColumnId: null,
  view: "board",        // "board" | "my" — какая вкладка открыта
  my: { period: "", tasks: [], summary: null },
  comments: [],         // комментарии загруженной задачи
  admin: { summary: null, users: [] },
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

/* ------------------------------------------------------------------ theme */
const THEME_KEY = "taskboard-theme";

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const btn = $("#theme-btn");
  if (btn) btn.textContent = theme === "dark" ? "☀️" : "🌙";
  try { localStorage.setItem(THEME_KEY, theme); } catch { /* приватный режим */ }
}

function setupTheme() {
  let saved = null;
  try { saved = localStorage.getItem(THEME_KEY); } catch { /* нет хранилища */ }
  applyTheme(saved || "light");
  $("#theme-btn").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
  });
}

/* ------------------------------------------------------------------ auth */
function setUserName(username) {
  $("#whoami").textContent = username;
  $("#avatar").textContent = (username || "?").slice(0, 1).toUpperCase();
}

function showAuth() {
  state.user = null;
  state.csrf = null;
  state.board = null;
  $("#app-view").hidden = true;
  $("#auth-view").hidden = false;
  $("#nav-admin").hidden = true;
}

function applyRole(user) {
  const admin = user && user.role === "admin";
  $("#nav-admin").hidden = !admin;
  $("#urole").textContent = admin ? "администратор" : "владелец рабочего пространства";
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

  // подсказка для демо-аккаунта
  const hint = $("#demo-hint");
  hint.hidden = false;
  hint.addEventListener("click", () => {
    const form = $("#auth-form");
    form.username.value = "demo";
    form.password.value = "demo1234";
    form.username.focus();
    toast("Данные подставлены — нажмите «Войти»", true);
  });

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
      state.user = { username: data.username, role: data.role || "user" };
      state.csrf = data.csrf_token;
      form.password.value = "";
      setUserName(data.username);
      applyRole(state.user);
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
          const ok = await confirmDialog(
            "Удалить доску",
            `«${b.name}» и все её задачи будут удалены безвозвратно.`,
          );
          if (!ok) return;
          try {
            await api(`/api/boards/${b.id}`, { method: "DELETE" });
            if (state.board && state.board.id === b.id) {
              state.board = null;
              if (state.view === "board") renderEmpty();  // сброс экрана удалённой доски
            }
            await loadBoards();
            if (state.view === "my") await refreshMyTasks();
            toast("Доска удалена", true);
          } catch (err) { toast(err.message); }
        },
      }),
    ]);
    list.append(item);
  }
}

async function openBoard(boardId) {
  if (state.view !== "board") {
    state.view = "board";
    $("#nav-my").classList.remove("active");
    $("#my-view").hidden = true;
    updateToolbar();
  }
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
  $("#admin-view").hidden = true;
  $("#empty-state").hidden = false;
  $("#board-title").textContent = "Доска";
  $("#board-dot").hidden = true;
  $("#stats-bar").hidden = true;
}

async function createBoard() {
  const data = await inputDialog("Новая доска", [
    { name: "name", label: "Название", placeholder: "Мой проект", maxlength: 100 },
    { name: "color", label: "Цвет метки", type: "color", value: "#6366f1" },
  ], "Создать");
  if (!data || !data.name.trim()) return;
  try {
    const res = await api("/api/boards", {
      method: "POST",
      body: { name: data.name.trim(), color: data.color },
    });
    await loadBoards();
    await openBoard(res.board.id);
    toast("Доска создана", true);
  } catch (err) { toast(err.message); }
}

async function renameBoard() {
  if (!state.board) return;
  const data = await inputDialog("Переименовать доску", [
    { name: "name", label: "Название", value: state.board.name, maxlength: 100 },
    { name: "color", label: "Цвет метки", type: "color", value: state.board.color || "#6366f1" },
  ], "Сохранить");
  if (!data || !data.name.trim()) return;
  try {
    await api(`/api/boards/${state.board.id}`, {
      method: "PATCH",
      body: { name: data.name.trim(), color: data.color },
    });
    state.board.name = data.name.trim();
    state.board.color = data.color;
    $("#board-title").textContent = state.board.name;
    await loadBoards();
    toast("Доска обновлена", true);
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
  const dot = $("#board-dot");
  dot.style.background = board.color || "var(--accent)";
  dot.hidden = false;
  const wrap = $("#columns");
  wrap.textContent = "";
  wrap.hidden = false;
  $("#empty-state").hidden = true;

  board.columns.forEach((col, colIndex) => {
    const finishedColumn = colIndex === board.columns.length - 1;
    const visible = filteredTasks(col.tasks);
    const body = el("div", { class: "col-body", dataset: { columnId: String(col.id) } });

    for (const task of visible) body.append(renderCard(task, finishedColumn));

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
          const ok = await confirmDialog(
            "Удалить колонку",
            `«${col.name}» и все задачи в ней будут удалены безвозвратно.`,
          );
          if (!ok) return;
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
  });

  const addCol = el("button", {
    class: "add-task-inline",
    style: "width:220px;flex:none;padding:12px",
    text: "＋ Добавить колонку",
    onclick: addColumn,
  });
  wrap.append(el("div", { class: "column", style: "background:transparent;border:0;width:220px;flex:none" },
    [el("div", { class: "col-body" }, [addCol])]));

}

function renderCard(task, finished = false) {
  const [icon, label] = PRIO[task.priority] || PRIO.medium;
  // у выполненных задач срок не «горит» — показываем просто дату
  const due = finished
    ? (task.due_date ? { cls: "", text: task.due_date } : null)
    : dueInfo(task.due_date);
  const overdue = !finished && due && due.cls === "late";

  const children = [
    el("div", { class: "t", text: task.title }),
  ];
  if (task.description) children.push(el("div", { class: "d", text: task.description }));

  const meta = el("div", { class: "meta" });
  for (const tag of task.tags || []) meta.append(el("span", { class: "tag", text: tag }));
  const subs = task.subtasks || [];
  if (subs.length) {
    const done = subs.filter((s) => s.done).length;
    meta.append(el("span", {
      class: "sub-badge",
      title: "Подзадачи",
      text: `☑ ${done}/${subs.length}`,
    }));
  }
  if (task.comments) meta.append(el("span", {
    class: "cmt-badge", title: "Комментарии", text: `💬 ${task.comments}`,
  }));
  if (due) meta.append(el("span", { class: `due ${due.cls}`, text: `📅 ${due.text}` }));
  meta.append(el("span", {
    class: `prio-dot ${task.priority}`, title: `Приоритет: ${label}`, text: "",
  }));
  children.push(meta);

  const card = el("div", {
    class: `card prio-${task.priority}${overdue ? " overdue" : ""}`,
    draggable: filtersActive() ? null : "true",
    title: filtersActive() ? "Снимите фильтр, чтобы перетаскивать" : "Открыть задачу · перетащите в другую колонку",
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
  const data = await inputDialog("Новая колонка", [
    { name: "name", label: "Название", placeholder: "Например, Ревью", maxlength: 60 },
  ], "Добавить");
  if (!data || !data.name.trim()) return;
  try {
    await api(`/api/boards/${state.board.id}/columns`, {
      method: "POST",
      body: { name: data.name.trim() },
    });
    await openBoard(state.board.id);
    toast("Колонка добавлена", true);
  } catch (err) { toast(err.message); }
}

async function renameColumn(col) {
  const data = await inputDialog("Переименовать колонку", [
    { name: "name", label: "Название", value: col.name, maxlength: 60 },
  ], "Сохранить");
  if (!data || !data.name.trim()) return;
  try {
    await api(`/api/columns/${col.id}`, { method: "PATCH", body: { name: data.name.trim() } });
    col.name = data.name.trim();
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
  state.editingSubtasks = (task ? task.subtasks || [] : []).map((s) => ({ ...s }));
  renderSubtasks();
  $("#subtask-input").value = "";
  if (task) colSelect.value = String(task.column_id);
  else if (columnId) colSelect.value = String(columnId);

  // комментарии есть только у сохранённых задач
  const commentBlock = $("#comments-block");
  state.comments = [];
  if (task) {
    commentBlock.hidden = false;
    $("#comment-list").textContent = "";
    $("#comment-input").value = "";
    $("#comment-counter").textContent = task.comments ? `${task.comments} шт.` : "";
    loadComments(task.id);
  } else {
    commentBlock.hidden = true;
    $("#comment-input").value = "";
  }

  modal.hidden = false;
  setTimeout(() => form.title.focus(), 30);
}

function closeModals() {
  $("#task-modal").hidden = true;
  $("#stats-modal").hidden = true;
  $("#admin-task-modal").hidden = true;
}

/* ------------------------------------------------------------------ подзадачи */
function updateSubCounter() {
  const total = state.editingSubtasks.length;
  const done = state.editingSubtasks.filter((s) => s.done).length;
  $("#subtask-counter").textContent = total ? `выполнено ${done} из ${total}` : "";
}

function renderSubtasks() {
  const list = $("#subtask-list");
  list.textContent = "";
  state.editingSubtasks.forEach((s, i) => {
    const cb = el("input", { type: "checkbox", title: "Отметить выполненной" });
    cb.checked = !!s.done;
    cb.addEventListener("change", () => {
      s.done = cb.checked;
      text.classList.toggle("done", s.done);
      updateSubCounter();
    });
    const text = el("span", { class: `sub-text${s.done ? " done" : ""}`, text: s.text });
    const del = el("button", {
      class: "icon-btn",
      text: "✕",
      title: "Удалить подзадачу",
      onclick: () => {
        state.editingSubtasks.splice(i, 1);
        renderSubtasks();
      },
    });
    list.append(el("li", {}, [cb, text, del]));
  });
  updateSubCounter();
}

function addSubtask() {
  const input = $("#subtask-input");
  const value = input.value.trim();
  if (!value) return;
  if (state.editingSubtasks.length >= 50) {
    toast("Не больше 50 подзадач");
    return;
  }
  state.editingSubtasks.push({ text: value, done: false });
  input.value = "";
  renderSubtasks();
  input.focus();
}

function setupTaskModal() {
  $("#subtask-add").addEventListener("click", addSubtask);
  $("#subtask-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();  // не отправлять форму
      addSubtask();
    }
  });

  $("#comment-add").addEventListener("click", addComment);
  $("#comment-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      addComment();
    }
  });

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
      subtasks: state.editingSubtasks.map((s) => ({
        ...(s.id ? { id: s.id } : {}),
        text: s.text,
        done: !!s.done,
      })),
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
      await loadBoards();
      if (state.view === "board" && state.board) await openBoard(state.board.id);
      else await refreshMyTasks();
    } catch (err) {
      errBox.textContent = err.message;
      errBox.hidden = false;
    }
  });

  $("#task-delete").addEventListener("click", async () => {
    if (!state.editingTask) return;
    const ok = await confirmDialog(
      "Удалить задачу",
      `«${state.editingTask.title}» будет удалена безвозвратно.`,
    );
    if (!ok) return;
    try {
      await api(`/api/tasks/${state.editingTask.id}`, { method: "DELETE" });
      closeModals();
      await loadBoards();
      if (state.view === "board" && state.board) await openBoard(state.board.id);
      else await refreshMyTasks();
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
  if (!state.board || state.view !== "board") return;
  try {
    const s = await api(`/api/boards/${state.board.id}/stats`);
    const bar = $("#stats-bar");
    bar.textContent = "";

    bar.append(el("span", { class: "chip" }, [
      "Готово ", el("b", { text: `${s.done_percent}%` }),
    ]));
    bar.append(el("div", { class: "progress", title: "Доля выполненных задач" }, [
      el("i", { style: `width:${Math.min(100, s.done_percent)}%` }),
    ]));

    const chips = [
      ["Всего", s.total, false],
      ["Просрочено", s.overdue, s.overdue > 0],
      ["Скоро срок", s.due_soon, false],
      ["Срочные", s.by_priority.urgent, false],
      ["Подзадачи", `${s.subtasks_done}/${s.subtasks_total}`, false],
    ];
    for (const [k, v, alert] of chips) {
      bar.append(el("span", { class: `chip${alert ? " alert" : ""}` }, [
        `${k}: `, el("b", { text: String(v) }),
      ]));
    }
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
      ["Подзадачи", `${s.subtasks_done}/${s.subtasks_total}`],
    ];
    for (const [k, v] of cells) {
      const alert = k === "Просрочено" && Number(v) > 0;
      grid.append(el("div", { class: `stat${alert ? " alert" : ""}` }, [
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

/* --------------------------------------------------------------- мои задачи */
const MY_PERIODS = [
  ["", "Активные"],
  ["overdue", "Просрочено"],
  ["today", "Сегодня"],
  ["week", "На неделе"],
  ["later", "Позже"],
  ["none", "Без срока"],
];

const BUCKET_TITLES = {
  overdue: "⏰ Просрочено",
  today: "📍 Сегодня",
  week: "📅 На этой неделе",
  later: "🗓 Позже",
  none: "🔕 Без срока",
  done: "✅ Выполнено",
};

function updateNavBadge(summary) {
  const badge = $("#nav-my-badge");
  if (!summary) return;
  const active = summary.total - summary.done;
  badge.textContent = String(active);
  badge.hidden = false;
  badge.classList.toggle("alert", summary.overdue > 0);
}

async function refreshMyTasks() {
  try {
    const params = new URLSearchParams();
    if (state.my.period) params.set("period", state.my.period);
    if (state.filters.q) params.set("q", state.filters.q);
    if (state.filters.priority) params.set("priority", state.filters.priority);
    const data = await api(`/api/my-tasks?${params}`);
    state.my.tasks = data.results;
    state.my.summary = data.summary;
    updateNavBadge(data.summary);
    if (state.view === "my") renderMyTasks();
  } catch (err) {
    if (state.view === "my") toast(err.message);
  }
}

function updateToolbar() {
  const boardMode = state.view === "board";
  for (const id of ["#stats-btn", "#export", "#add-column-btn", "#add-task-btn"]) {
    $(id).hidden = !boardMode;
  }
  const boardish = state.view !== "admin";
  $(".search-wrap").hidden = !boardish;
  $("#priority-filter").hidden = !boardish;
}

function renderMyTasks() {
  const filters = $("#my-filters");
  filters.textContent = "";
  const summary = state.my.summary || {};

  for (const [key, label] of MY_PERIODS) {
    const n = key === ""
      ? (summary.total ?? 0) - (summary.done ?? 0)
      : (summary[key] ?? 0);
    filters.append(el("button", {
      class: `pill-tab${state.my.period === key ? " active" : ""}`,
      onclick: () => {
        state.my.period = key;
        refreshMyTasks();
      },
    }, [label, el("span", { class: "n", text: String(n) })]));
  }

  const wrap = $("#my-list");
  wrap.textContent = "";

  if (!state.my.tasks.length) {
    wrap.append(el("div", { class: "empty" }, [
      el("div", { class: "empty-icon", text: "🎉" }),
      el("h3", { text: "Задач по фильтру нет" }),
      el("p", { class: "muted", text: "Снимите фильтры или добавьте новую задачу на доске." }),
    ]));
    return;
  }

  const groups = {};
  for (const t of state.my.tasks) {
    const key = t.finished ? "done" : t.bucket;
    (groups[key] = groups[key] || []).push(t);
  }

  const order = ["overdue", "today", "week", "later", "none", "done"];
  for (const key of order) {
    const items = groups[key];
    if (!items || !items.length) continue;
    const list = el("div", { class: "my-list" });
    for (const t of items) list.append(renderMyCard(t));
    wrap.append(el("div", { class: "bucket" }, [
      el("div", { class: `bucket-head ${key}` }, [
        el("span", { text: BUCKET_TITLES[key] }),
        el("span", { class: "cnt", text: `${items.length}` }),
        el("span", { class: "line" }),
      ]),
      list,
    ]));
  }
}

function renderMyCard(task) {
  const due = dueInfo(task.due_date);
  const subs = task.subtasks || [];
  const done = subs.filter((s) => s.done).length;

  return el("div", {
    class: `my-card prio-${task.priority}${task.finished ? " done" : ""}`,
    title: "Открыть задачу",
    onclick: () => jumpToTask(task),
  }, [
    el("div", { class: "body" }, [
      el("div", { class: "t", text: task.title }),
      el("div", { class: "sub" }, [
        el("span", { class: "where" }, [
          el("span", { class: "dot", style: `background:${task.board_color || "var(--accent)"}` }),
          `${task.board_name} → ${task.column_name}`,
        ]),
        ...(task.tags || []).map((tag) => el("span", { class: "tag", text: tag })),
        ...(subs.length ? [el("span", { class: "sub-badge", text: `☑ ${done}/${subs.length}` })] : []),
        ...(task.comments ? [el("span", { class: "cmt-badge", text: `💬 ${task.comments}` })] : []),
        ...(due ? [el("span", { class: `due ${due.cls}`, text: `📅 ${due.text}` })] : []),
      ]),
    ]),
    el("span", {
      class: `prio-dot ${task.priority}`,
      title: `Приоритет: ${PRIO[task.priority][1]}`,
      text: "",
    }),
  ]);
}

async function jumpToTask(task) {
  await showBoardView();
  await openBoard(task.board_id);
  const col = (state.board && state.board.columns || []).find((c) => c.id === task.column_id);
  const fresh = col && col.tasks.find((t) => t.id === task.id);
  if (fresh) openTaskModal(fresh);
  else toast("Задача не найдена — возможно, она удалена");
}

async function showMyView() {
  state.view = "my";
  $("#nav-my").classList.add("active");
  $("#nav-admin").classList.remove("active");
  $("#columns").hidden = true;
  $("#admin-view").hidden = true;
  $("#empty-state").hidden = true;
  $("#stats-bar").hidden = true;
  $("#board-title").textContent = "Мои задачи";
  $("#board-dot").hidden = true;
  $("#my-view").hidden = false;
  updateToolbar();
  await refreshMyTasks();
}

async function showBoardView() {
  state.view = "board";
  $("#nav-my").classList.remove("active");
  $("#nav-admin").classList.remove("active");
  $("#my-view").hidden = true;
  $("#admin-view").hidden = true;
  updateToolbar();
  if (state.board) {
    $("#empty-state").hidden = true;
    renderBoard();
    await refreshStats();
  } else {
    renderEmpty();
  }
}

/* --------------------------------------------------------------- админ-панель */
function hideWorkViews() {
  $("#columns").hidden = true;
  $("#my-view").hidden = true;
  $("#admin-view").hidden = true;
  $("#empty-state").hidden = true;
  $("#stats-bar").hidden = true;
}

async function showAdminView() {
  state.view = "admin";
  $("#nav-my").classList.remove("active");
  $("#nav-admin").classList.add("active");
  hideWorkViews();
  $("#board-title").textContent = "Админ-панель";
  $("#board-dot").hidden = true;
  $("#admin-view").hidden = false;
  updateToolbar();
  await refreshAdmin();
}

async function refreshAdmin() {
  try {
    const [s, u] = await Promise.all([
      api("/api/admin/summary"),
      api("/api/admin/users"),
    ]);
    state.admin.summary = s.summary;
    state.admin.users = u.users;
    renderAdminSummary();
    renderAdminUsers();
  } catch (err) {
    toast(err.message);
  }
}

function renderAdminSummary() {
  const s = state.admin.summary || {};
  const cards = [
    ["users", "Пользователей", "👥", `${s.admins || 0} с ролью администратора`],
    ["active_users", "Активных", "📈", "с досками или комментариями"],
    ["boards", "Досок", "🗂️", `${s.columns || 0} колонок`],
    ["tasks", "Задач", "🧩", `${s.done_tasks || 0} в колонке «Готово»`],
    ["subtasks", "Подзадач", "☑️", `${s.subtasks_done || 0} выполнено`],
    ["comments", "Комментариев", "💬", "обсуждения в задачах"],
  ];
  const wrap = $("#admin-summary");
  wrap.textContent = "";
  for (const [key, label, icon, sub] of cards) {
    wrap.append(el("div", { class: "stat-card" }, [
      el("span", { class: "stat-ico", text: icon }),
      el("div", { class: "stat-body" }, [
        el("div", { class: "stat-n", text: String(s[key] ?? 0) }),
        el("div", { class: "stat-l", text: label }),
        el("div", { class: "stat-sub", text: sub }),
      ]),
    ]));
  }
}

function renderAdminUsers() {
  const tbody = $("#admin-users tbody");
  tbody.textContent = "";
  const users = state.admin.users;
  $("#admin-users-n").textContent = `· ${users.length}`;

  for (const u of users) {
    const isAdmin = u.role === "admin";
    const me = state.user && u.username === state.user.username;
    const actions = [];
    if (!me) {
      actions.push(el("button", {
        class: "btn ghost sm",
        text: isAdmin ? "Убрать админа" : "Сделать админом",
        onclick: async (e) => {
          e.stopPropagation();
          try {
            await api(`/api/admin/users/${u.id}/role`, {
              method: "POST",
              body: { role: isAdmin ? "user" : "admin" },
            });
            toast(`${u.username}: роль обновлена`, true);
            refreshAdmin();
          } catch (err) { toast(err.message); }
        },
      }));
      actions.push(el("button", {
        class: "btn danger ghost sm",
        text: "Удалить",
        onclick: async (e) => {
          e.stopPropagation();
          const ok = await confirmDialog(
            "Удалить аккаунт?",
            `Пользователь ${u.username} и все его доски, задачи и комментарии
             будут удалены безвозвратно.`,
          );
          if (!ok) return;
          try {
            await api(`/api/admin/users/${u.id}`, { method: "DELETE" });
            toast(`${u.username} удалён`, true);
            $("#admin-detail").hidden = true;
            refreshAdmin();
          } catch (err) { toast(err.message); }
        },
      }));
    }

    tbody.append(el("tr", {
      class: "row-clickable",
      title: "Показать данные пользователя",
      onclick: () => openAdminUser(u.id),
    }, [
      el("td", {}, [
        el("span", { class: "avatar sm", text: (u.username || "?").slice(0, 1).toUpperCase() }),
        el("span", { class: "cell-user", text: u.username + (me ? " (вы)" : "") }),
      ]),
      el("td", {}, [
        el("span", { class: `role-chip${isAdmin ? " admin" : ""}`, text: isAdmin ? "админ" : "юзер" }),
      ]),
      el("td", { class: "num", text: String(u.boards) }),
      el("td", { class: "num", text: String(u.tasks) }),
      el("td", { class: "num", text: String(u.comments) }),
      el("td", { class: "muted", text: u.last_activity ? fmtStamp(u.last_activity) : "нет задач" }),
      el("td", { class: "cell-actions", onclick: (e) => e.stopPropagation() }, actions),
    ]));
  }
}

async function openAdminUser(userId) {
  try {
    const data = await api(`/api/admin/users/${userId}`);
    renderAdminUser(data);
  } catch (err) {
    toast(err.message);
  }
}

function renderAdminUser(data) {
  const u = data.user;
  $("#admin-detail-title").textContent = `Данные: ${u.username}`;
  const body = $("#admin-detail-body");
  body.textContent = "";

  const meta = el("div", { class: "meta-chips" }, [
    el("span", { class: "chip", text: `роль: ${u.role === "admin" ? "администратор" : "пользователь"}` }),
    el("span", { class: "chip", text: `регистрация: ${u.created_at ? u.created_at.slice(0, 10) : "—"}` }),
    el("span", { class: "chip", text: `досок: ${u.boards}` }),
    el("span", { class: "chip", text: `задач: ${u.tasks}` }),
    el("span", { class: "chip", text: `комментариев: ${u.comments}` }),
  ]);
  body.append(meta);

  if (!data.boards.length) {
    body.append(el("p", { class: "muted", text: "У пользователя пока нет досок." }));
    $("#admin-detail").hidden = false;
    $("#admin-detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
    return;
  }

  for (const b of data.boards) {
    const boardBox = el("div", { class: "admin-board" });
    boardBox.append(el("div", { class: "admin-board-head" }, [
      el("span", { class: "board-dot", style: `background:${b.color}` }),
      el("b", { text: b.name }),
      el("span", { class: "muted", text: `${b.tasks_count} задач` }),
    ]));
    const cols = el("div", { class: "admin-cols" });
    for (const c of b.columns) {
      const col = el("div", { class: "admin-col" });
      col.append(el("div", { class: "admin-col-title", text: `${c.name} · ${c.tasks.length}` }));
      if (!c.tasks.length) {
        col.append(el("div", { class: "muted empty-col", text: "пусто" }));
      }
      for (const t of c.tasks) {
        col.append(el("div", {
          class: "admin-task",
          title: "Показать параметры задачи",
          onclick: () => openAdminTask(t.id),
        }, [
          el("div", { class: "admin-task-title" }, [
            el("span", { class: `prio-dot ${t.priority}`, title: t.priority }),
            el("span", { text: t.title }),
          ]),
          el("div", { class: "admin-task-meta muted" }, [
            t.due_date ? el("span", { text: `📅 ${t.due_date}` }) : null,
            el("span", { text: `☑ ${t.sub_done}/${t.sub_total}` }),
            el("span", { text: `💬 ${t.comments}` }),
            t.tags.length ? el("span", { text: `#${t.tags.join(" #")}` }) : null,
          ]),
        ]));
      }
      cols.append(col);
    }
    boardBox.append(cols);
    body.append(boardBox);
  }

  $("#admin-detail").hidden = false;
  $("#admin-detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function openAdminTask(taskId) {
  try {
    const data = await api(`/api/admin/tasks/${taskId}`);
    renderAdminTask(data.task);
  } catch (err) {
    toast(err.message);
  }
}

function atChip(label, value) {
  return el("span", { class: "chip" }, [
    el("b", { text: `${label}: ` }),
    el("span", { text: String(value) }),
  ]);
}

function renderAdminTask(t) {
  $("#at-title").textContent = t.title;
  const body = $("#at-body");
  body.textContent = "";

  const prio = PRIO[t.priority] || ["", t.priority];
  const due = dueInfo(t.due_date);
  body.append(el("div", { class: "meta-chips" }, [
    el("span", { class: "chip" }, [
      el("span", { class: `prio-dot ${t.priority}` }),
      el("b", { text: ` ${prio[1]}` }),
    ]),
    atChip("Статус", t.finished ? "Готово" : "В работе"),
    atChip("Владелец", t.owner),
    atChip("Доска", t.board_name),
    atChip("Колонка", t.column_name),
    atChip("Срок", t.due_date
      ? `${t.due_date}${due ? ` · ${due.text}` : ""}`
      : "не задан"),
    atChip("Создано", fmtStamp(t.created_at)),
    atChip("Обновлено", fmtStamp(t.updated_at)),
    atChip("ID", `#${t.id}`),
  ]));

  body.append(el("section", { class: "at-block" }, [
    el("h4", { text: "Описание" }),
    el("p", { class: "at-desc", text: t.description || "Описания нет." }),
  ]));

  body.append(el("section", { class: "at-block" }, [
    el("h4", { text: `Теги · ${t.tags.length}` }),
    t.tags.length
      ? el("div", { class: "meta-chips" },
          t.tags.map((tag) => el("span", { class: "chip", text: `#${tag}` })))
      : el("p", { class: "muted", text: "Тегов нет." }),
  ]));

  const subList = el("ul", { class: "subtask-list readonly" });
  for (const s of t.subtasks) {
    const cb = el("input", { type: "checkbox", title: s.done ? "Выполнено" : "Не выполнено" });
    cb.checked = !!s.done;
    cb.disabled = true;
    subList.append(el("li", {}, [
      cb,
      el("span", { class: `sub-text${s.done ? " done" : ""}`, text: s.text }),
    ]));
  }
  body.append(el("section", { class: "at-block" }, [
    el("h4", { text: `Подзадачи · ${t.subtasks_done} из ${t.subtasks_total}` }),
    t.subtasks.length
      ? subList
      : el("p", { class: "muted", text: "Подзадач нет." }),
  ]));

  const cmtList = el("ul", { class: "comment-list" });
  for (const c of t.comments) {
    cmtList.append(el("li", { class: "comment" }, [
      el("div", { class: "comment-head" }, [
        el("span", { class: "avatar", text: (c.username || "?").slice(0, 1).toUpperCase() }),
        el("span", { class: "who", text: c.username }),
        el("span", { class: "when", text: fmtStamp(c.created_at) }),
      ]),
      el("div", { class: "comment-body", text: c.body }),
    ]));
  }
  body.append(el("section", { class: "at-block" }, [
    el("h4", { text: `Обсуждение · ${t.comments_count}` }),
    t.comments.length
      ? cmtList
      : el("p", { class: "muted", text: "Комментариев нет." }),
  ]));

  $("#admin-task-modal").hidden = false;
}

async function searchAdminTasks() {
  const q = $("#admin-task-search").value.trim();
  const box = $("#admin-search-results");
  if (!q) {
    box.className = "search-results muted";
    box.textContent = "Введите запрос — покажем задачи всех аккаунтов.";
    return;
  }
  try {
    const data = await api(`/api/admin/tasks?q=${encodeURIComponent(q)}`);
    box.className = "search-results";
    box.textContent = "";
    if (!data.count) {
      box.append(el("p", { class: "muted", text: "Ничего не найдено." }));
      return;
    }
    for (const t of data.results) {
      box.append(el("div", {
        class: "search-row",
        title: "Показать параметры задачи",
        onclick: () => openAdminTask(t.id),
      }, [
        el("span", { class: `prio-dot ${t.priority}` }),
        el("b", { text: t.title }),
        el("span", { class: "muted", text: `${t.username} · ${t.board_name} · ${t.column_name}` }),
        el("span", { class: "muted", text: `💬 ${t.comments}` }),
      ]));
    }
  } catch (err) {
    toast(err.message);
  }
}

/* --------------------------------------------------------------- комментарии */
function fmtStamp(stamp) {
  if (!stamp) return "";
  try {
    const d = new Date(stamp.replace(" ", "T") + "Z");
    const today = new Date();
    const sameDay = d.toDateString() === today.toDateString();
    const hm = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    if (sameDay) return `сегодня ${hm}`;
    return `${d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" })} ${hm}`;
  } catch {
    return stamp;
  }
}

function renderComments() {
  const list = $("#comment-list");
  list.textContent = "";
  const count = state.comments.length;
  $("#comment-counter").textContent = count ? `${count} шт.` : "";

  if (!count) {
    list.append(el("li", { class: "comment-empty", text: "Комментариев пока нет" }));
    return;
  }

  for (const c of state.comments) {
    const canDelete = state.user && c.username === state.user.username;
    list.append(el("li", { class: "comment" }, [
      el("div", { class: "comment-head" }, [
        el("span", { class: "avatar", text: (c.username || "?").slice(0, 1).toUpperCase() }),
        el("span", { class: "who", text: c.username }),
        el("span", { class: "when", text: fmtStamp(c.created_at) }),
        canDelete ? el("button", {
          class: "icon-btn del", text: "✕", title: "Удалить комментарий",
          onclick: () => deleteComment(c.id),
        }) : null,
      ]),
      el("div", { class: "comment-body", text: c.body }),
    ]));
  }
}

async function loadComments(taskId) {
  try {
    const data = await api(`/api/tasks/${taskId}/comments`);
    state.comments = data.comments;
    renderComments();
  } catch {
    state.comments = [];
    renderComments();
  }
}

async function addComment() {
  const input = $("#comment-input");
  const body = input.value.trim();
  if (!body || !state.editingTask) return;
  const btn = $("#comment-add");
  btn.disabled = true;
  try {
    const res = await api(`/api/tasks/${state.editingTask.id}/comments`, {
      method: "POST",
      body: { body },
    });
    state.comments.push(res.comment);
    input.value = "";
    if (state.editingTask) state.editingTask.comments = state.comments.length;
    renderComments();
    if (state.view === "board") { renderBoard(); refreshMyTasks(); }
    else renderMyTasks();
  } catch (err) {
    toast(err.message);
  } finally {
    btn.disabled = false;
    input.focus();
  }
}

async function deleteComment(id) {
  try {
    await api(`/api/comments/${id}`, { method: "DELETE" });
    state.comments = state.comments.filter((c) => c.id !== id);
    if (state.editingTask) state.editingTask.comments = state.comments.length;
    renderComments();
    if (state.view === "board") { renderBoard(); refreshMyTasks(); }
    else renderMyTasks();
    toast("Комментарий удалён", true);
  } catch (err) {
    toast(err.message);
  }
}

/* ------------------------------------------------------- универсальный диалог */
let dialogResolve = null;

/**
 * Модальный диалог ввода/подтверждения.
 * @returns {Promise<Object|null>} значения полей, true для подтверждения
 *                                 или null при отмене.
 */
function dialog({ title, message = "", fields = [], okText = "ОК", cancelText = "Отмена", danger = false }) {
  return new Promise((resolve) => {
    const modal = $("#dialog-modal");
    const form = $("#dialog-form");
    const fieldsBox = $("#dialog-fields");
    const errBox = $("#dialog-error");

    const finish = (value) => {
      modal.hidden = true;
      document.removeEventListener("keydown", onKey, true);
      const cb = dialogResolve;
      dialogResolve = null;
      if (cb) cb(value);
    };
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        finish(null);
      }
    };

    dialogResolve = resolve;
    $("#dialog-title").textContent = title;
    const msg = $("#dialog-message");
    msg.textContent = message;
    msg.hidden = !message;
    errBox.hidden = true;
    fieldsBox.textContent = "";

    for (const f of fields) {
      if (f.type === "color") {
        const input = el("input", { type: "color", name: f.name, value: f.value || "#6366f1" });
        fieldsBox.append(el("label", { class: "field color-row" }, [
          input, el("span", { text: f.label }),
        ]));
      } else {
        fieldsBox.append(el("label", { class: "field" }, [
          el("span", { text: f.label }),
          el("input", {
            type: "text",
            name: f.name,
            value: f.value ?? "",
            placeholder: f.placeholder ?? "",
            maxlength: String(f.maxlength ?? 100),
            ...(f.required === false ? {} : { required: "required" }),
            autocomplete: "off",
          }),
        ]));
      }
    }

    const okBtn = $("#dialog-ok");
    okBtn.textContent = okText;
    okBtn.classList.toggle("danger-solid", !!danger);
    $("#dialog-cancel").textContent = cancelText;

    form.onsubmit = (e) => {
      e.preventDefault();
      if (!fields.length) return finish(true);
      const data = Object.fromEntries(new FormData(form).entries());
      for (const f of fields) {
        if (f.required === false) continue;
        if (!String(data[f.name] ?? "").trim()) {
          errBox.textContent = f.error || "Заполните поле";
          errBox.hidden = false;
          return;
        }
      }
      finish(data);
    };
    $("#dialog-cancel").onclick = () => finish(null);
    $("[data-dialog-close]").onclick = () => finish(null);
    modal.onmousedown = (e) => {
      if (e.target === modal) finish(null);
    };

    modal.hidden = false;
    document.addEventListener("keydown", onKey, true);
    setTimeout(() => {
      const first = fieldsBox.querySelector("input");
      if (first) first.focus();
      else okBtn.focus();
    }, 30);
  });
}

const confirmDialog = (title, message, okText = "Удалить") =>
  dialog({ title, message, fields: [], okText, danger: true });

const inputDialog = (title, fields, okText = "ОК") =>
  dialog({ title, fields, okText });

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
  await refreshMyTasks();  // бейдж «Мои задачи»
}

async function start() {
  setupAuth();
  setupTaskModal();
  setupShortcuts();
  setupTheme();

  $("#nav-my").addEventListener("click", showMyView);
  $("#nav-admin").addEventListener("click", showAdminView);
  $("#admin-refresh").addEventListener("click", refreshAdmin);
  $("#admin-detail-close").addEventListener("click", () => {
    $("#admin-detail").hidden = true;
  });
  let adminTimer = null;
  $("#admin-task-search").addEventListener("input", () => {
    clearTimeout(adminTimer);
    adminTimer = setTimeout(searchAdminTasks, 250);
  });
  $("#empty-new-board").addEventListener("click", createBoard);
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
  const applyFilters = () => {
    if (state.view === "board") renderBoard();
    else refreshMyTasks();
  };
  $("#search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.filters.q = e.target.value.trim();
      applyFilters();
    }, 150);
  });
  $("#priority-filter").addEventListener("change", (e) => {
    state.filters.priority = e.target.value;
    applyFilters();
  });

  // попытка восстановить сессию
  try {
    const me = await api("/api/auth/me");
    state.user = { username: me.username, role: me.role || "user" };
    state.csrf = me.csrf_token;
    setUserName(me.username);
    applyRole(state.user);
    showApp();
    await boot();
  } catch {
    showAuth();
  }
}

document.addEventListener("DOMContentLoaded", start);
