/*
 * E2E-тест интерфейса TaskBoard через Playwright (headless Chromium).
 *
 * Подготовка:
 *     npm install && npx playwright install chromium
 *     запущенный сервер:  .venv/bin/python run.py   (http://127.0.0.1:5000)
 *     демо-данные:        .venv/bin/python seed.py
 *
 * Запуск:
 *     node tests/ui/ui_test.mjs   (или make test-ui — со свежей базой)
 *
 * Проверяется: вход, отрисовка доски, счётчик задач, создание и
 * редактирование задачи, drag & drop, поиск, статистика, чистая консоль.
 * Скриншоты сохраняются в docs/.
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const BASE = process.env.TASKBOARD_URL || "http://127.0.0.1:5000";
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const OUT = process.env.TASKBOARD_SHOTS || resolve(ROOT, "docs");

const BOARD_NAME = process.env.TASKBOARD_BOARD || "Разработка TaskBoard";
const LOGIN = process.env.TASKBOARD_USER || "demo";
const PASSWORD = process.env.TASKBOARD_PASS || "demo1234";

mkdirSync(OUT, { recursive: true });

const results = [];
const log = (name, ok, extra = "") =>
  results.push(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? " — " + extra : ""}`);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];

page.on("pageerror", (e) => errors.push("pageerror: " + String(e)));
page.on("console", (m) => {
  if (m.type() !== "error") return;
  if (m.text().includes("401")) return; // штатная проверка сессии на старте
  errors.push("console: " + m.text());
});
page.on("response", (r) => {
  if (r.status() >= 400 && !r.url().includes("/api/auth/me")) {
    errors.push(`http ${r.status()} ${r.url()}`);
  }
});

try {
  // 1. Экран входа
  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForSelector("#auth-view:not([hidden])");
  await page.screenshot({ path: `${OUT}/01-login.png` });
  log("экран входа отображается", true);

  // 2. Вход
  await page.fill('input[name="username"]', LOGIN);
  await page.fill('input[name="password"]', PASSWORD);
  await page.click("#auth-submit");
  await page.waitForSelector("#app-view:not([hidden])", { timeout: 5000 });
  await page.waitForSelector(".column", { timeout: 5000 });
  await page.locator(`.board-list li:has-text("${BOARD_NAME}")`).first().click();
  await page.waitForFunction(
    () => document.querySelectorAll(".card").length >= 7,
    null,
    { timeout: 5000 },
  );
  await page.screenshot({ path: `${OUT}/02-board.png` });
  log("вход и загрузка доски", true);

  // 3. Счётчик задач в сайдбаре не раздут (fan-out JOIN)
  const sideCount = await page
    .locator(`.board-list li:has-text("${BOARD_NAME}")`)
    .first()
    .locator(".count")
    .textContent();
  const totalCards = await page.locator(".card").count();
  log(
    "счётчик задач в сайдбаре совпадает с карточками",
    Number(sideCount) === totalCards,
    `${sideCount} против ${totalCards}`,
  );

  // 4. Создание задачи
  await page.click("#add-task-btn");
  await page.waitForSelector("#task-modal:not([hidden])");
  await page.fill('#task-form input[name="title"]', "Задача из UI-теста");
  await page.fill('#task-form textarea[name="description"]', "создана автоматическим тестом");
  await page.selectOption('#task-form select[name="priority"]', "urgent");
  await page.fill('#task-form input[name="tags"]', "e2e, auto");
  await page.click('#task-form button[type="submit"]');
  await page.waitForSelector("#task-modal", { state: "hidden", timeout: 5000 });
  const created = await page.locator('.card:has-text("Задача из UI-теста")').count();
  log("создание задачи из UI", created === 1, `найдено карточек: ${created}`);

  // 5. Редактирование
  await page.locator('.card:has-text("Задача из UI-теста")').first().click();
  await page.waitForSelector("#task-modal:not([hidden])");
  await page.fill('#task-form input[name="title"]', "Задача переименована");
  await page.click('#task-form button[type="submit"]');
  await page.waitForSelector("#task-modal", { state: "hidden", timeout: 5000 });
  const titles = await page.locator(".card .t").allTextContents();
  const renamed = titles.filter((t) => t.trim() === "Задача переименована").length;
  log("редактирование задачи", renamed === 1);

  // 5b. Подзадачи: добавить, отметить, увидеть прогресс на карточке
  await page.locator('.card:has-text("Задача переименована")').first().click();
  await page.waitForSelector("#task-modal:not([hidden])");
  await page.fill("#subtask-input", "сделать подпункт");
  await page.press("#subtask-input", "Enter");
  const listCount = await page.locator("#subtask-list li").count();
  await page.check("#subtask-list li:first-child input[type='checkbox']");
  const counter = (await page.textContent("#subtask-counter")).trim();
  await page.screenshot({ path: `${OUT}/07-subtasks.png` });
  await page.click('#task-form button[type="submit"]');
  await page.waitForSelector("#task-modal", { state: "hidden", timeout: 5000 });
  const badge = (
    await page.locator('.card:has-text("Задача переименована") .sub-badge').textContent()
  ).trim();
  log(
    "подзадачи: добавление и прогресс",
    listCount === 1 && counter.includes("выполнено 1 из 1") && badge === "☑ 1/1",
    `${counter} · ${badge}`,
  );

  // 6. Drag & drop в соседнюю колонку
  const firstCard = page.locator(".column").nth(0).locator(".card").first();
  const title = (await firstCard.locator(".t").textContent()).trim();
  const targetBody = page.locator(".column").nth(1).locator(".col-body");
  await firstCard.dragTo(targetBody);
  await page.waitForTimeout(700);
  const inSecond = await page
    .locator(".column")
    .nth(1)
    .locator(`.card:has-text("${title}")`)
    .count();
  log("drag & drop между колонками", inSecond === 1, `«${title}» → колонка 2`);
  await page.screenshot({ path: `${OUT}/03-after-dnd.png` });

  // 7. Поиск
  await page.fill("#search", "UI");
  await page.waitForTimeout(400);
  const visibleTitles = await page.locator(".card .t").allTextContents();
  log(
    "поиск фильтрует карточки",
    visibleTitles.length === 1 && visibleTitles[0].includes("drag"),
    `видно ${visibleTitles.length}: ${visibleTitles.join(", ")}`,
  );
  await page.screenshot({ path: `${OUT}/04-search.png` });
  await page.fill("#search", "");
  await page.waitForTimeout(400);

  // 8. Статистика
  await page.click("#stats-btn");
  await page.waitForSelector("#stats-modal:not([hidden])");
  const statCards = await page.locator("#stats-content .stat").count();
  const bars = await page.locator("#stats-content .bar-row").count();
  log("модалка статистики", statCards >= 5 && bars >= 3, `карточек ${statCards}, полос ${bars}`);
  await page.screenshot({ path: `${OUT}/05-stats.png` });
  await page.keyboard.press("Escape");

  // 9. Порядок колонок перетаскиванием заголовка
  const colTitles = () => page.locator(".column .col-head .title").allTextContents();
  const before = (await colTitles())[0];
  // третья колонка «Готово» перетаскивается в самое начало (левая половина цели)
  const thirdHead = page.locator(".column").nth(2).locator(".col-head");
  const firstHead = page.locator(".column").nth(0).locator(".col-head");
  const box = await firstHead.boundingBox();
  await page.dragAndDrop(
    ".columns > .column:nth-child(3) > .col-head",
    ".columns > .column:nth-child(1) > .col-head",
    { targetPosition: { x: 8, y: Math.floor(box.height / 2) } },
  );
  await page.waitForFunction(
    (prev) => {
      const t = document.querySelector(".column .col-head .title");
      return t && t.textContent.trim() !== prev;
    },
    before,
    { timeout: 5000 },
  );
  const afterCol = (await colTitles())[0];
  log("перетаскивание колонки", afterCol === "Готово", `${before} → ${afterCol}`);
  await page.screenshot({ path: `${OUT}/06-column-dnd.png` });

  // 10. Экспорт доски в Markdown
  const md = await page.evaluate(async () => {
    const list = await (await fetch("/api/boards")).json();
    const id = list.boards[0].id;
    const r = await fetch(`/api/boards/${id}/export?format=md`);
    return { ok: r.ok, text: r.ok ? await r.text() : "" };
  });
  log(
    "экспорт в Markdown",
    md.ok && md.text.startsWith("# ") && md.text.includes("## "),
    md.text.split("\n")[0],
  );

  // 11. Горячие клавиши
  await page.keyboard.press("/");
  const searchFocused = await page.evaluate(
    () => document.activeElement && document.activeElement.id === "search",
  );
  log("клавиша / фокусирует поиск", searchFocused === true);
  await page.evaluate(() => document.activeElement.blur());
  await page.keyboard.press("n");
  const modalOpen = await page.isVisible("#task-modal");
  log("клавиша n открывает задачу", modalOpen);
  await page.keyboard.press("Escape");

  // 12. Свои диалоги вместо prompt/confirm: создание и удаление доски
  await page.click("#new-board-btn");
  await page.waitForSelector("#dialog-modal:not([hidden])");
  await page.fill('#dialog-fields input[name="name"]', "Временная доска");
  await page.click("#dialog-ok");
  await page.waitForSelector("#dialog-modal", { state: "hidden", timeout: 5000 });
  await page.waitForFunction(
    () => document.body.textContent.includes("Временная доска"),
    null,
    { timeout: 5000 },
  );
  const createdBoard = await page
    .locator('.board-list li:has-text("Временная доска")')
    .count();
  log("диалог создания доски", createdBoard === 1);

  const tempItem = page.locator('.board-list li:has-text("Временная доска")');
  await tempItem.hover();
  await tempItem.locator(".del").click();
  await page.waitForSelector("#dialog-modal:not([hidden])");
  const dialogMsg = await page.textContent("#dialog-message");
  await page.click("#dialog-ok");
  await page.waitForSelector("#dialog-modal", { state: "hidden", timeout: 5000 });
  await page.waitForFunction(
    () => !document.querySelector(".board-list").textContent.includes("Временная доска"),
    null,
    { timeout: 5000 },
  );
  const titleAfter = await page.textContent("#board-title");
  log(
    "диалог подтверждения удаления + сброс экрана",
    dialogMsg.includes("безвозвратно") && titleAfter.trim() === "Доска",
    `${dialogMsg.slice(0, 30)} · заголовок: «${titleAfter.trim()}»`,
  );

  // 13. Комментарии к задаче
  await page.locator(`.board-list li:has-text("${BOARD_NAME}")`).first().click();
  await page.waitForSelector(".column", { timeout: 5000 });
  await page.locator(".column .card").first().click();
  await page.waitForSelector("#task-modal:not([hidden])");
  await page.waitForSelector("#comment-list li", { timeout: 5000 });
  const hadCount = await page.locator("#comment-list li.comment").count();
  await page.fill("#comment-input", "Комментарий из E2E");
  await page.click("#comment-add");
  await page.waitForFunction(
    () => document.body.textContent.includes("Комментарий из E2E"),
    null,
    { timeout: 5000 },
  );
  const cmtCount = await page.locator("#comment-list li.comment").count();
  log(
    "комментарии: отправка и отображение",
    cmtCount === hadCount + 1,
    `было/стало: ${hadCount} → ${cmtCount}`,
  );
  await page.screenshot({ path: `${OUT}/08-comments.png` });
  await page.keyboard.press("Escape");
  await page.waitForSelector("#task-modal", { state: "hidden", timeout: 5000 });

  // 14. Вкладка «Мои задачи»
  await page.click("#nav-my");
  await page.waitForSelector("#my-view:not([hidden])", { timeout: 5000 });
  await page.waitForSelector("#my-list .my-card", { timeout: 5000 });
  const buckets = await page.locator("#my-list .bucket").count();
  const pills = await page.locator("#my-filters .pill-tab").count();
  const navBadge = await page.textContent("#nav-my-badge");
  log(
    "вкладка «Мои задачи»",
    buckets >= 1 && pills === 6 && Number(navBadge) > 0,
    `групп ${buckets}, фильтров ${pills}, бейдж ${navBadge}`,
  );
  await page.screenshot({ path: `${OUT}/09-my-tasks.png` });

  // 15. Переключение темы
  await page.click("#theme-btn");
  const theme = await page.evaluate(() => document.documentElement.dataset.theme);
  await page.click("#theme-btn");
  const themeBack = await page.evaluate(() => document.documentElement.dataset.theme);
  log("светлая/тёмная тема", theme === "dark" && themeBack === "light", `${theme} → ${themeBack}`);

  // 16. Админ-панель: у демо-юзера её нет, у админа — есть и открывается
  const adminHiddenForUser = await page.evaluate(
    () => document.querySelector("#nav-admin").hidden,
  );
  await page.click("#logout-btn");
  await page.waitForSelector("#auth-view:not([hidden])", { timeout: 5000 });
  await page.fill('input[name="username"]', process.env.TASKBOARD_ADMIN || "admin");
  await page.fill('input[name="password"]', process.env.TASKBOARD_ADMIN_PASS || "admin1234");
  await page.click("#auth-submit");
  await page.waitForSelector("#app-view:not([hidden])", { timeout: 5000 });
  await page.waitForSelector("#nav-admin:not([hidden])", { timeout: 5000 });
  await page.click("#nav-admin");
  await page.waitForSelector("#admin-view:not([hidden])", { timeout: 5000 });
  await page.waitForSelector("#admin-users tbody tr", { timeout: 5000 });
  const aCards = await page.locator("#admin-summary .stat-card").count();
  const aUsers = await page.locator("#admin-users tbody tr").count();
  const aAdmins = await page.locator("#admin-users .role-chip.admin").count();
  log(
    "админ-панель: сводка, пользователи, роли",
    adminHiddenForUser && aCards >= 6 && aUsers >= 2 && aAdmins >= 1,
    `скрыта у юзера: ${adminHiddenForUser}, карточек ${aCards}, юзеров ${aUsers}, админов ${aAdmins}`,
  );
  await page.screenshot({ path: `${OUT}/10-admin.png` });

  // 17. Карточка данных конкретного пользователя
  await page.locator("#admin-users tbody tr").first().click();
  await page.waitForSelector("#admin-detail:not([hidden])", { timeout: 5000 });
  await page.waitForSelector("#admin-detail .admin-board", { timeout: 5000 });
  const aBoards = await page.locator("#admin-detail .admin-board").count();
  const aTasks = await page.locator("#admin-detail .admin-task").count();
  log(
    "админ-панель: данные пользователя",
    aBoards >= 1 && aTasks >= 1,
    `досок ${aBoards}, задач ${aTasks}`,
  );
  await page.screenshot({ path: `${OUT}/11-admin-user.png` });

  // 18. Чистая консоль
  log("консоль без ошибок", errors.length === 0, errors.slice(0, 3).join(" | "));
} catch (e) {
  log("исключение", false, String(e).slice(0, 300));
  await page.screenshot({ path: `${OUT}/99-failure.png` }).catch(() => {});
} finally {
  await browser.close();
}

console.log(results.join("\n"));
const failed = results.some((r) => r.startsWith("FAIL"));
console.log(failed ? "\n=== ЕСТЬ ПРОВАЛЫ ===" : "\n=== ВСЁ ЗАШЛО ===");
process.exit(failed ? 1 : 0);
