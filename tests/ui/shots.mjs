/**
 * Демо-скриншоты интерфейса: node tests/ui/shots.mjs
 * Логинится под demo, снимает ключевые экраны в docs/screens/.
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = path.join(ROOT, "docs", "screens");
const BASE = process.env.BASE_URL || "http://127.0.0.1:5000";

mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const shot = (name) => page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: false });

await page.goto(BASE, { waitUntil: "networkidle" });
await shot("01-login");

await page.fill('input[name="username"]', "demo");
await page.fill('input[name="password"]', "demo1234");
await page.click("#auth-submit");
await page.waitForSelector(".column", { timeout: 8000 });
await page.waitForTimeout(400);
await shot("02-board");

// модалка задачи с чеклистом и комментариями
await page.locator(".card", { hasText: "Реализовать REST API" }).first().click();
await page.waitForSelector("#task-modal:not([hidden])");
await page.waitForTimeout(600);
await shot("03-task-modal");
await page.keyboard.press("Escape");

// статистика
await page.click("#stats-btn");
await page.waitForSelector("#stats-modal:not([hidden])");
await page.waitForTimeout(300);
await shot("04-stats");
await page.keyboard.press("Escape");

// «Мои задачи»
await page.click("#nav-my");
await page.waitForSelector("#my-view:not([hidden])");
await page.waitForTimeout(600);
await shot("05-my-tasks");

// тёмная тема + доска
await page.click("#theme-btn");
await page.locator(".board-list li").first().click();
await page.waitForSelector(".column", { timeout: 8000 });
await page.waitForTimeout(400);
await shot("06-dark-board");

await browser.close();
console.log(`Скриншоты сохранены в ${OUT}`);
