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
  const sideCount = await page.locator(".board-list li .count").first().textContent();
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
  log("создание задачи из UI", created === 1);

  // 5. Редактирование
  await page.locator('.card:has-text("Задача из UI-теста")').first().click();
  await page.waitForSelector("#task-modal:not([hidden])");
  await page.fill('#task-form input[name="title"]', "Задача переименована");
  await page.click('#task-form button[type="submit"]');
  await page.waitForSelector("#task-modal", { state: "hidden", timeout: 5000 });
  const titles = await page.locator(".card .t").allTextContents();
  const renamed = titles.filter((t) => t.trim() === "Задача переименована").length;
  log("редактирование задачи", renamed === 1);

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

  // 9. Чистая консоль
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
