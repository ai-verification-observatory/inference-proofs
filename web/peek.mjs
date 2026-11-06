// One-shot screenshot: node peek.mjs <page> <width> <height> <out.png> [full: 1] [js to run first]
// PLAYWRIGHT_MODULE: path to playwright's index.mjs (default: the "playwright" package). BASE: the server.
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const BASE = process.env.BASE || 'http://127.0.0.1:4440/';
const [pg, w, h, out, full, js] = process.argv.slice(2);
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: +w, height: +h } });
const p = await ctx.newPage();
const errs = []; p.on('pageerror', (e) => errs.push(String(e))); p.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()); });
await p.goto(BASE + pg, { waitUntil: 'networkidle' });
await p.waitForTimeout(2500);
if (js) { await p.evaluate(js); await p.waitForTimeout(900); }
if (full === '1') { const H = await p.evaluate(() => document.documentElement.scrollHeight); await p.setViewportSize({ width: +w, height: H }); await p.waitForTimeout(300); }
await p.screenshot({ path: out });
const ov = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth);
console.log('errors', errs, 'overflow', ov);
await b.close();
