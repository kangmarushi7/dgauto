const { chromium } = require("playwright");
const config = require("../config");

function pickUserAgent() {
  const list = config.userAgents;
  return list[Math.floor(Math.random() * list.length)];
}

function randomDelay(min = config.delayMinMs, max = config.delayMaxMs) {
  const lo = Math.min(min, max);
  const hi = Math.max(min, max);
  const ms = Math.floor(lo + Math.random() * (hi - lo + 1));
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function createBrowser() {
  const browser = await chromium.launch({ headless: config.headless });
  const context = await browser.newContext({
    userAgent: pickUserAgent(),
    viewport: { width: 1440, height: 900 },
    locale: "en-US",
    extraHTTPHeaders: {
      "Accept-Language": "en-US,en;q=0.9",
      Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
  });
  return { browser, context };
}

async function withPage(fn) {
  const { browser, context } = await createBrowser();
  const page = await context.newPage();
  try {
    return await fn(page, context);
  } finally {
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
  }
}

async function gotoSafe(page, url, { waitUntil = "domcontentloaded", timeout = 60000 } = {}) {
  await page.goto(url, { waitUntil, timeout });
  await randomDelay(800, 1600);
}

module.exports = {
  pickUserAgent,
  randomDelay,
  createBrowser,
  withPage,
  gotoSafe,
};
